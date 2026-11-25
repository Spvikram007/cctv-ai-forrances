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
from enum import Enum
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import httpx

from core.logging.logger import get_logger

logger = get_logger("onvif_client")


class PTZUnsupportedError(Exception):
    """Raised when an invoked PTZ operation is unsupported by the target camera."""
    pass


class PTZDirection(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    UP_LEFT = "UP_LEFT"
    UP_RIGHT = "UP_RIGHT"
    DOWN_LEFT = "DOWN_LEFT"
    DOWN_RIGHT = "DOWN_RIGHT"
    ZOOM_IN = "ZOOM_IN"
    ZOOM_OUT = "ZOOM_OUT"
    STOP = "STOP"


@dataclass
class PTZPreset:
    token: str
    name: str


@dataclass
class PTZCapabilities:
    has_ptz: bool = False
    ptz_url: str = ""
    supports_continuous: bool = True
    supports_absolute: bool = False
    supports_relative: bool = False
    supports_presets: bool = True
    supports_home: bool = True
    pan_tilt_limits: Tuple[Tuple[float, float], Tuple[float, float]] = ((-1.0, 1.0), (-1.0, 1.0))
    zoom_limits: Tuple[float, float] = (-1.0, 1.0)


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

    def ptz_get_capabilities(self, profile_token: Optional[str] = None) -> PTZCapabilities:
        """Inspects PTZ capabilities, service endpoints, and ranges for the target camera."""
        if not self.capabilities.has_ptz:
            return PTZCapabilities(has_ptz=False)

        if not self.capabilities.ptz_url:
            try:
                self.get_capabilities()
            except Exception as e:
                logger.debug("Failed querying capabilities from [%s]: %s", self.ip_address, e)
                return PTZCapabilities(has_ptz=False)

        if not self.capabilities.has_ptz or not self.capabilities.ptz_url:
            return PTZCapabilities(has_ptz=False)

        caps = PTZCapabilities(has_ptz=True, ptz_url=self.capabilities.ptz_url)

        # Query PTZ Configurations if available
        try:
            body = "<tptz:GetConfigurations />"
            xml_resp = self._send_soap_request(
                service_url=self.capabilities.ptz_url,
                action="http://www.onvif.org/ver20/ptz/wsdl/GetConfigurations",
                body_xml=body,
            )
            root = self._strip_namespaces(xml_resp)
            if root.findall(".//PTZConfiguration"):
                caps.supports_continuous = True
                caps.supports_relative = True
                caps.supports_absolute = True
                caps.supports_presets = True
                caps.supports_home = True
        except Exception as e:
            logger.warning("Could not query full PTZ configurations from [%s]: %s", self.ip_address, e)

        return caps

    def ptz_continuous_move(
        self,
        profile_token: str,
        pan: float = 0.0,
        tilt: float = 0.0,
        zoom: float = 0.0,
        timeout_sec: Optional[float] = None,
    ) -> None:
        """Issues continuous PTZ movement speed vectors (-1.0 to 1.0)."""
        if not self.capabilities.has_ptz or not self.capabilities.ptz_url:
            raise PTZUnsupportedError("Target camera does not support ONVIF PTZ operations.")

        # Clamp speed vectors to valid range [-1.0, 1.0]
        pan = max(-1.0, min(1.0, float(pan)))
        tilt = max(-1.0, min(1.0, float(tilt)))
        zoom = max(-1.0, min(1.0, float(zoom)))

        timeout_xml = f"<tptz:Timeout>PT{int(timeout_sec)}S</tptz:Timeout>" if timeout_sec else ""

        body = f"""<tptz:ContinuousMove>
  <tptz:ProfileToken>{profile_token}</tptz:ProfileToken>
  <tptz:Velocity>
    <tt:PanTilt x="{pan:.2f}" y="{tilt:.2f}" space="http://www.onvif.org/ver10/tptz/PanTiltSpaces/VelocityGenericSpace"/>
    <tt:Zoom x="{zoom:.2f}" space="http://www.onvif.org/ver10/tptz/ZoomSpaces/VelocityGenericSpace"/>
  </tptz:Velocity>
  {timeout_xml}
</tptz:ContinuousMove>"""

        try:
            self._send_soap_request(
                service_url=self.capabilities.ptz_url,
                action="http://www.onvif.org/ver20/ptz/wsdl/ContinuousMove",
                body_xml=body,
            )
        except Exception as e:
            if "ActionNotSupported" in str(e) or "NotImplemented" in str(e):
                raise PTZUnsupportedError(f"ContinuousMove unsupported: {e}") from e
            raise

    def ptz_relative_move(
        self,
        profile_token: str,
        pan: float = 0.0,
        tilt: float = 0.0,
        zoom: float = 0.0,
        speed: float = 1.0,
    ) -> None:
        """Issues relative translation vector movement."""
        if not self.capabilities.has_ptz or not self.capabilities.ptz_url:
            raise PTZUnsupportedError("Target camera does not support ONVIF PTZ operations.")

        pan = max(-1.0, min(1.0, float(pan)))
        tilt = max(-1.0, min(1.0, float(tilt)))
        zoom = max(-1.0, min(1.0, float(zoom)))
        speed = max(0.1, min(1.0, float(speed)))

        body = f"""<tptz:RelativeMove>
  <tptz:ProfileToken>{profile_token}</tptz:ProfileToken>
  <tptz:Translation>
    <tt:PanTilt x="{pan:.2f}" y="{tilt:.2f}" space="http://www.onvif.org/ver10/tptz/PanTiltSpaces/TranslationGenericSpace"/>
    <tt:Zoom x="{zoom:.2f}" space="http://www.onvif.org/ver10/tptz/ZoomSpaces/TranslationGenericSpace"/>
  </tptz:Translation>
  <tptz:Speed>
    <tt:PanTilt x="{speed:.2f}" y="{speed:.2f}"/>
    <tt:Zoom x="{speed:.2f}"/>
  </tptz:Speed>
</tptz:RelativeMove>"""

        try:
            self._send_soap_request(
                service_url=self.capabilities.ptz_url,
                action="http://www.onvif.org/ver20/ptz/wsdl/RelativeMove",
                body_xml=body,
            )
        except Exception as e:
            if "ActionNotSupported" in str(e) or "NotImplemented" in str(e):
                raise PTZUnsupportedError(f"RelativeMove unsupported: {e}") from e
            raise

    def ptz_absolute_move(
        self,
        profile_token: str,
        pan: float = 0.0,
        tilt: float = 0.0,
        zoom: float = 0.0,
        speed: float = 1.0,
    ) -> None:
        """Issues absolute coordinate movement."""
        if not self.capabilities.has_ptz or not self.capabilities.ptz_url:
            raise PTZUnsupportedError("Target camera does not support ONVIF PTZ operations.")

        pan = max(-1.0, min(1.0, float(pan)))
        tilt = max(-1.0, min(1.0, float(tilt)))
        zoom = max(-1.0, min(1.0, float(zoom)))
        speed = max(0.1, min(1.0, float(speed)))

        body = f"""<tptz:AbsoluteMove>
  <tptz:ProfileToken>{profile_token}</tptz:ProfileToken>
  <tptz:Position>
    <tt:PanTilt x="{pan:.2f}" y="{tilt:.2f}" space="http://www.onvif.org/ver10/tptz/PanTiltSpaces/PositionGenericSpace"/>
    <tt:Zoom x="{zoom:.2f}" space="http://www.onvif.org/ver10/tptz/ZoomSpaces/PositionGenericSpace"/>
  </tptz:Position>
  <tptz:Speed>
    <tt:PanTilt x="{speed:.2f}" y="{speed:.2f}"/>
    <tt:Zoom x="{speed:.2f}"/>
  </tptz:Speed>
</tptz:AbsoluteMove>"""

        try:
            self._send_soap_request(
                service_url=self.capabilities.ptz_url,
                action="http://www.onvif.org/ver20/ptz/wsdl/AbsoluteMove",
                body_xml=body,
            )
        except Exception as e:
            if "ActionNotSupported" in str(e) or "NotImplemented" in str(e):
                raise PTZUnsupportedError(f"AbsoluteMove unsupported: {e}") from e
            raise

    def ptz_stop(self, profile_token: str) -> None:
        """Halts all active PTZ movements on the camera."""
        if not self.capabilities.has_ptz or not self.capabilities.ptz_url:
            return

        body = f"""<tptz:Stop>
  <tptz:ProfileToken>{profile_token}</tptz:ProfileToken>
  <tptz:PanTilt>true</tptz:PanTilt>
  <tptz:Zoom>true</tptz:Zoom>
</tptz:Stop>"""

        try:
            self._send_soap_request(
                service_url=self.capabilities.ptz_url,
                action="http://www.onvif.org/ver20/ptz/wsdl/Stop",
                body_xml=body,
            )
        except Exception as e:
            logger.warning("PTZ Stop command encountered error on [%s]: %s", self.ip_address, e)

    def ptz_get_presets(self, profile_token: str) -> List[PTZPreset]:
        """Queries configured camera PTZ presets."""
        if not self.capabilities.has_ptz or not self.capabilities.ptz_url:
            return []

        body = f"""<tptz:GetPresets>
  <tptz:ProfileToken>{profile_token}</tptz:ProfileToken>
</tptz:GetPresets>"""

        try:
            xml_resp = self._send_soap_request(
                service_url=self.capabilities.ptz_url,
                action="http://www.onvif.org/ver20/ptz/wsdl/GetPresets",
                body_xml=body,
            )
            root = self._strip_namespaces(xml_resp)
            presets: List[PTZPreset] = []
            for preset_elem in root.findall(".//Preset"):
                token = preset_elem.attrib.get("token", "")
                name_elem = preset_elem.find("Name")
                name = name_elem.text.strip() if name_elem is not None and name_elem.text else token
                if token:
                    presets.append(PTZPreset(token=token, name=name))
            return presets
        except Exception as e:
            logger.warning("GetPresets failed on [%s]: %s", self.ip_address, e)
            return []

    def ptz_set_preset(self, profile_token: str, preset_name: str, preset_token: Optional[str] = None) -> str:
        """Saves current PTZ position as named preset."""
        if not self.capabilities.has_ptz or not self.capabilities.ptz_url:
            raise PTZUnsupportedError("Target camera does not support ONVIF PTZ operations.")

        token_xml = f"<tptz:PresetToken>{preset_token}</tptz:PresetToken>" if preset_token else ""
        body = f"""<tptz:SetPreset>
  <tptz:ProfileToken>{profile_token}</tptz:ProfileToken>
  <tptz:PresetName>{preset_name}</tptz:PresetName>
  {token_xml}
</tptz:SetPreset>"""

        xml_resp = self._send_soap_request(
            service_url=self.capabilities.ptz_url,
            action="http://www.onvif.org/ver20/ptz/wsdl/SetPreset",
            body_xml=body,
        )
        root = self._strip_namespaces(xml_resp)
        assigned_token_elem = root.find(".//PresetToken")
        if assigned_token_elem is not None and assigned_token_elem.text:
            return assigned_token_elem.text.strip()
        return preset_token or preset_name

    def ptz_goto_preset(self, profile_token: str, preset_token: str, speed: float = 1.0) -> None:
        """Navigates to a configured PTZ preset token."""
        if not self.capabilities.has_ptz or not self.capabilities.ptz_url:
            raise PTZUnsupportedError("Target camera does not support ONVIF PTZ operations.")

        speed = max(0.1, min(1.0, float(speed)))
        body = f"""<tptz:GotoPreset>
  <tptz:ProfileToken>{profile_token}</tptz:ProfileToken>
  <tptz:PresetToken>{preset_token}</tptz:PresetToken>
  <tptz:Speed>
    <tt:PanTilt x="{speed:.2f}" y="{speed:.2f}"/>
    <tt:Zoom x="{speed:.2f}"/>
  </tptz:Speed>
</tptz:GotoPreset>"""

        self._send_soap_request(
            service_url=self.capabilities.ptz_url,
            action="http://www.onvif.org/ver20/ptz/wsdl/GotoPreset",
            body_xml=body,
        )

    def ptz_remove_preset(self, profile_token: str, preset_token: str) -> bool:
        """Deletes a PTZ preset."""
        if not self.capabilities.has_ptz or not self.capabilities.ptz_url:
            return False

        body = f"""<tptz:RemovePreset>
  <tptz:ProfileToken>{profile_token}</tptz:ProfileToken>
  <tptz:PresetToken>{preset_token}</tptz:PresetToken>
</tptz:RemovePreset>"""

        try:
            self._send_soap_request(
                service_url=self.capabilities.ptz_url,
                action="http://www.onvif.org/ver20/ptz/wsdl/RemovePreset",
                body_xml=body,
            )
            return True
        except Exception as e:
            logger.warning("RemovePreset failed on [%s]: %s", self.ip_address, e)
            return False

    def ptz_goto_home_position(self, profile_token: str, speed: float = 1.0) -> None:
        """Navigates PTZ camera to its configured home position."""
        if not self.capabilities.has_ptz or not self.capabilities.ptz_url:
            raise PTZUnsupportedError("Target camera does not support ONVIF PTZ operations.")

        speed = max(0.1, min(1.0, float(speed)))
        body = f"""<tptz:GotoHomePosition>
  <tptz:ProfileToken>{profile_token}</tptz:ProfileToken>
  <tptz:Speed>
    <tt:PanTilt x="{speed:.2f}" y="{speed:.2f}"/>
    <tt:Zoom x="{speed:.2f}"/>
  </tptz:Speed>
</tptz:GotoHomePosition>"""

        try:
            self._send_soap_request(
                service_url=self.capabilities.ptz_url,
                action="http://www.onvif.org/ver20/ptz/wsdl/GotoHomePosition",
                body_xml=body,
            )
        except Exception as e:
            if "ActionNotSupported" in str(e) or "NotImplemented" in str(e):
                raise PTZUnsupportedError(f"GotoHomePosition unsupported: {e}") from e
            raise

    def ptz_set_home_position(self, profile_token: str) -> None:
        """Sets the current PTZ coordinates as the camera's home position."""
        if not self.capabilities.has_ptz or not self.capabilities.ptz_url:
            raise PTZUnsupportedError("Target camera does not support ONVIF PTZ operations.")

        body = f"""<tptz:SetHomePosition>
  <tptz:ProfileToken>{profile_token}</tptz:ProfileToken>
</tptz:SetHomePosition>"""

        try:
            self._send_soap_request(
                service_url=self.capabilities.ptz_url,
                action="http://www.onvif.org/ver20/ptz/wsdl/SetHomePosition",
                body_xml=body,
            )
        except Exception as e:
            if "ActionNotSupported" in str(e) or "NotImplemented" in str(e):
                raise PTZUnsupportedError(f"SetHomePosition unsupported: {e}") from e
            raise

    def get_system_date_and_time(self) -> Dict[str, Any]:
        """Queries camera date, time, and NTP configuration."""
        body = "<tds:GetSystemDateAndTime />"
        xml_resp = self._send_soap_request(
            service_url=self.device_service_url,
            action="http://www.onvif.org/ver10/device/wsdl/GetSystemDateAndTime",
            body_xml=body,
        )
        root = self._strip_namespaces(xml_resp)

        tz_elem = root.find(".//TimeZone/TZ")
        tz_str = tz_elem.text.strip() if tz_elem is not None and tz_elem.text else "UTC"

        year_elem = root.find(".//UTCDateTime/Date/Year")
        month_elem = root.find(".//UTCDateTime/Date/Month")
        day_elem = root.find(".//UTCDateTime/Date/Day")
        hour_elem = root.find(".//UTCDateTime/Time/Hour")
        min_elem = root.find(".//UTCDateTime/Time/Minute")
        sec_elem = root.find(".//UTCDateTime/Time/Second")

        dt_iso = ""
        if year_elem is not None and year_elem.text:
            try:
                y = int(year_elem.text)
                m = int(month_elem.text) if month_elem is not None and month_elem.text else 1
                d = int(day_elem.text) if day_elem is not None and day_elem.text else 1
                hh = int(hour_elem.text) if hour_elem is not None and hour_elem.text else 0
                mm = int(min_elem.text) if min_elem is not None and min_elem.text else 0
                ss = int(sec_elem.text) if sec_elem is not None and sec_elem.text else 0
                dt = datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc)
                dt_iso = dt.isoformat()
            except Exception:
                pass

        return {
            "date_time_utc": dt_iso,
            "time_zone": tz_str,
            "raw_response": xml_resp,
        }

    def set_system_date_and_time(self, dt: datetime, time_zone: str = "UTC") -> bool:
        """Synchronizes camera clock with VMS master clock."""
        dt_utc = dt.astimezone(timezone.utc)
        body = f"""<tds:SetSystemDateAndTime>
  <tds:DateTimeType>Manual</tds:DateTimeType>
  <tds:DaylightSavings>false</tds:DaylightSavings>
  <tds:TimeZone>
    <tt:TZ>{time_zone}</tt:TZ>
  </tds:TimeZone>
  <tds:UTCDateTime>
    <tt:Time>
      <tt:Hour>{dt_utc.hour}</tt:Hour>
      <tt:Minute>{dt_utc.minute}</tt:Minute>
      <tt:Second>{dt_utc.second}</tt:Second>
    </tt:Time>
    <tt:Date>
      <tt:Year>{dt_utc.year}</tt:Year>
      <tt:Month>{dt_utc.month}</tt:Month>
      <tt:Day>{dt_utc.day}</tt:Day>
    </tt:Date>
  </tds:UTCDateTime>
</tds:SetSystemDateAndTime>"""

        try:
            self._send_soap_request(
                service_url=self.device_service_url,
                action="http://www.onvif.org/ver10/device/wsdl/SetSystemDateAndTime",
                body_xml=body,
            )
            return True
        except Exception as e:
            logger.warning("SetSystemDateAndTime failed on [%s]: %s", self.ip_address, e)
            return False

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
