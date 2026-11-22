"""
Robust Pure-Python ONVIF Client.
Implements WS-Security UsernameToken authentication, Device Information retrieval,
Media Profiles, Stream URI resolution, Capability inspection, and Profile S/T PTZ commands.
"""

import os
import re
import base64
import hashlib
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import httpx

from core.logging.logger import get_logger

logger = get_logger("onvif_client")


@dataclass
class ONVIFDeviceInformation:
    manufacturer: str = "Unknown"
    model: str = "Unknown"
    firmware_version: str = "Unknown"
    serial_number: str = "Unknown"
    hardware_id: str = "Unknown"


@dataclass
class ONVIFProfile:
    token: str
    name: str
    video_encoder_token: Optional[str] = None
    codec: str = "H264"
    width: int = 1920
    height: int = 1080
    fps: int = 25
    bitrate_kbps: int = 4096


@dataclass
class ONVIFCapabilities:
    has_ptz: bool = False
    has_imaging: bool = False
    has_events: bool = False
    media_url: str = ""
    ptz_url: str = ""
    events_url: str = ""
    imaging_url: str = ""


class ONVIFClient:
    """Client for communicating with ONVIF Profile S/G/T compliant cameras."""

    def __init__(
        self,
        ip_address: str,
        port: int = 80,
        username: str = "",
        password: str = "",
        timeout_sec: float = 5.0,
    ) -> None:
        self.ip_address = ip_address
        self.port = port
        self.username = username
        self.password = password
        self.timeout_sec = timeout_sec

        self.device_service_url = f"http://{self.ip_address}:{self.port}/onvif/device_service"
        self.capabilities = ONVIFCapabilities()
        self.device_info = ONVIFDeviceInformation()
        self.profiles: List[ONVIFProfile] = []

    def _build_ws_security_header(self) -> str:
        """Generates WS-Security UsernameToken XML header with PasswordDigest, Nonce, and Created timestamp."""
        if not self.username:
            return ""

        created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        raw_nonce = os.urandom(16)
        nonce_base64 = base64.b64encode(raw_nonce).decode("ascii")

        # WS-Security Password Digest calculation: SHA1(raw_nonce + created_utf8 + password_utf8)
        sha1 = hashlib.sha1()
        sha1.update(raw_nonce)
        sha1.update(created.encode("utf-8"))
        sha1.update(self.password.encode("utf-8"))
        password_digest = base64.b64encode(sha1.digest()).decode("ascii")

        return f"""
  <s:Header>
    <wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
                   xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
      <wsse:UsernameToken>
        <wsse:Username>{self.username}</wsse:Username>
        <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{password_digest}</wsse:Password>
        <wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_base64}</wsse:Nonce>
        <wsu:Created>{created}</wsu:Created>
      </wsse:UsernameToken>
    </wsse:Security>
  </s:Header>"""

    def _send_soap_request(self, service_url: str, action: str, body_xml: str) -> str:
        """Sends an HTTP POST SOAP 1.2 request to the target ONVIF endpoint."""
        header_xml = self._build_ws_security_header()
        envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
            xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
            xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl"
            xmlns:tt="http://www.onvif.org/ver10/schema">
  {header_xml}
  <s:Body>
    {body_xml}
  </s:Body>
</s:Envelope>"""

        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8",
            "Action": action,
        }

        with httpx.Client(timeout=self.timeout_sec) as client:
            resp = client.post(service_url, content=envelope, headers=headers)
            resp.raise_for_status()
            return resp.text

    @staticmethod
    def _strip_namespaces(xml_text: str) -> ET.Element:
        clean = re.sub(r'<\/?([a-zA-Z0-9_-]+:)', lambda m: '<' if not m.group(0).startswith('</') else '</', xml_text)
        clean = re.sub(r'\s+xmlns(?::[a-zA-Z0-9_-]+)?="[^"]*"', '', clean)
        return ET.fromstring(clean)

    def get_capabilities(self) -> ONVIFCapabilities:
        """Queries device capabilities and resolves service URLs (Media, PTZ, Events)."""
        body = "<tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities>"
        xml_resp = self._send_soap_request(
            service_url=self.device_service_url,
            action="http://www.onvif.org/ver10/device/wsdl/GetCapabilities",
            body_xml=body,
        )

        root = self._strip_namespaces(xml_resp)

        media_elem = root.find(".//Media/XAddr")
        ptz_elem = root.find(".//PTZ/XAddr")
        events_elem = root.find(".//Events/XAddr")
        imaging_elem = root.find(".//Imaging/XAddr")

        self.capabilities.media_url = media_elem.text.strip() if media_elem is not None and media_elem.text else f"http://{self.ip_address}:{self.port}/onvif/media_service"
        if ptz_elem is not None and ptz_elem.text:
            self.capabilities.ptz_url = ptz_elem.text.strip()
            self.capabilities.has_ptz = True
        if events_elem is not None and events_elem.text:
            self.capabilities.events_url = events_elem.text.strip()
            self.capabilities.has_events = True
        if imaging_elem is not None and imaging_elem.text:
            self.capabilities.imaging_url = imaging_elem.text.strip()
            self.capabilities.has_imaging = True

        return self.capabilities

    def get_device_information(self) -> ONVIFDeviceInformation:
        """Retrieves manufacturer, model, firmware version, and serial number."""
        body = "<tds:GetDeviceInformation />"
        xml_resp = self._send_soap_request(
            service_url=self.device_service_url,
            action="http://www.onvif.org/ver10/device/wsdl/GetDeviceInformation",
            body_xml=body,
        )

        root = self._strip_namespaces(xml_resp)

        mf = root.find(".//Manufacturer")
        md = root.find(".//Model")
        fw = root.find(".//FirmwareVersion")
        sn = root.find(".//SerialNumber")
        hw = root.find(".//HardwareId")

        self.device_info.manufacturer = mf.text.strip() if mf is not None and mf.text else "Generic ONVIF"
        self.device_info.model = md.text.strip() if md is not None and md.text else "IP Camera"
        self.device_info.firmware_version = fw.text.strip() if fw is not None and fw.text else "Unknown"
        self.device_info.serial_number = sn.text.strip() if sn is not None and sn.text else "Unknown"
        self.device_info.hardware_id = hw.text.strip() if hw is not None and hw.text else "Unknown"

        return self.device_info

    def get_profiles(self) -> List[ONVIFProfile]:
        """Retrieves available media profiles (Main Stream / Substream tokens)."""
        if not self.capabilities.media_url:
            self.get_capabilities()

        body = "<trt:GetProfiles />"
        xml_resp = self._send_soap_request(
            service_url=self.capabilities.media_url,
            action="http://www.onvif.org/ver10/media/wsdl/GetProfiles",
            body_xml=body,
        )

        root = self._strip_namespaces(xml_resp)
        self.profiles.clear()

        for prof in root.findall(".//Profiles"):
            token = prof.attrib.get("token", "")
            name_elem = prof.find("Name")
            name = name_elem.text.strip() if name_elem is not None and name_elem.text else token

            width = 1920
            height = 1080
            fps = 25
            bitrate = 4096
            codec = "H264"

            res_w = prof.find(".//Resolution/Width")
            res_h = prof.find(".//Resolution/Height")
            if res_w is not None and res_w.text:
                width = int(res_w.text)
            if res_h is not None and res_h.text:
                height = int(res_h.text)

            enc = prof.find(".//Encoding")
            if enc is not None and enc.text:
                codec = enc.text.strip()

            profile = ONVIFProfile(
                token=token,
                name=name,
                codec=codec,
                width=width,
                height=height,
                fps=fps,
                bitrate_kbps=bitrate,
            )
            self.profiles.append(profile)

        return self.profiles

    def get_stream_uri(self, profile_token: str, protocol: str = "RTSP") -> str:
        """Retrieves RTSP live stream URI for the designated profile token."""
        if not self.capabilities.media_url:
            self.get_capabilities()

        body = f"""<trt:GetStreamUri>
  <trt:StreamSetup>
    <tt:Stream>RTP-Unicast</tt:Stream>
    <tt:Transport>
      <tt:Protocol>{protocol}</tt:Protocol>
    </tt:Transport>
  </trt:StreamSetup>
  <trt:ProfileToken>{profile_token}</trt:ProfileToken>
</trt:GetStreamUri>"""

        xml_resp = self._send_soap_request(
            service_url=self.capabilities.media_url,
            action="http://www.onvif.org/ver10/media/wsdl/GetStreamUri",
            body_xml=body,
        )

        root = self._strip_namespaces(xml_resp)
        uri_elem = root.find(".//Uri")
        if uri_elem is not None and uri_elem.text:
            raw_uri = uri_elem.text.strip()
            # If URI lacks credentials, inject configured username/password
            if self.username and self.password and "@" not in raw_uri:
                raw_uri = raw_uri.replace("rtsp://", f"rtsp://{self.username}:{self.password}@")
            return raw_uri

        raise ValueError(f"Failed to extract stream URI for profile [{profile_token}].")

    def ptz_continuous_move(self, profile_token: str, pan: float = 0.0, tilt: float = 0.0, zoom: float = 0.0) -> None:
        """Issues continuous PTZ movement speed vectors (-1.0 to 1.0)."""
        if not self.capabilities.has_ptz or not self.capabilities.ptz_url:
            raise RuntimeError("Target camera does not support ONVIF PTZ operations.")

        body = f"""<tptz:ContinuousMove>
  <tptz:ProfileToken>{profile_token}</tptz:ProfileToken>
  <tptz:Velocity>
    <tt:PanTilt x="{pan:.2f}" y="{tilt:.2f}" space="http://www.onvif.org/ver10/tptz/PanTiltSpaces/VelocityGenericSpace"/>
    <tt:Zoom x="{zoom:.2f}" space="http://www.onvif.org/ver10/tptz/ZoomSpaces/VelocityGenericSpace"/>
  </tptz:Velocity>
</tptz:ContinuousMove>"""

        self._send_soap_request(
            service_url=self.capabilities.ptz_url,
            action="http://www.onvif.org/ver20/ptz/wsdl/ContinuousMove",
            body_xml=body,
        )

    def ptz_stop(self, profile_token: str) -> None:
        """Halts all active PTZ movements on the camera."""
        if not self.capabilities.has_ptz or not self.capabilities.ptz_url:
            return

        body = f"""<tptz:Stop>
  <tptz:ProfileToken>{profile_token}</tptz:ProfileToken>
  <tptz:PanTilt>true</tptz:PanTilt>
  <tptz:Zoom>true</tptz:Zoom>
</tptz:Stop>"""

        self._send_soap_request(
            service_url=self.capabilities.ptz_url,
            action="http://www.onvif.org/ver20/ptz/wsdl/Stop",
            body_xml=body,
        )

    def test_connection(self) -> Dict[str, Any]:
        """Tests device reachability and credentials."""
        start = datetime.now()
        try:
            self.get_capabilities()
            self.get_device_information()
            latency = (datetime.now() - start).total_seconds() * 1000
            return {
                "success": True,
                "latency_ms": round(latency, 1),
                "manufacturer": self.device_info.manufacturer,
                "model": self.device_info.model,
                "firmware": self.device_info.firmware_version,
                "has_ptz": self.capabilities.has_ptz,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "latency_ms": -1,
            }
