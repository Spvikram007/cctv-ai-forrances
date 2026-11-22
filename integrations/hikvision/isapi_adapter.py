"""
Hikvision ISAPI Adapter.
Communicates with Hikvision IP Cameras, NVRs, and DVRs via HTTP REST ISAPI.
Supports channel enumeration, device info retrieval, and RTSP stream generation.
"""

import re
import xml.etree.ElementTree as ET
from typing import Dict, Any, List
import httpx

from integrations.generic_devices.base_adapter import BaseDeviceAdapter, RecorderInfo, ChannelInfo
from core.logging.logger import get_logger

logger = get_logger("hikvision_isapi")


class HikvisionISAPIAdapter(BaseDeviceAdapter):
    """Adapter for Hikvision devices using ISAPI XML protocol."""

    def __init__(self, ip_address: str, port: int = 80, username: str = "admin", password: str = "", rtsp_port: int = 554, timeout_sec: float = 5.0):
        super().__init__(ip_address, port, username, password, timeout_sec)
        self.rtsp_port = rtsp_port
        self.base_url = f"http://{self.ip_address}:{self.port}/ISAPI"

    def _get(self, endpoint: str) -> str:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        auth = httpx.DigestAuth(self.username, self.password)
        with httpx.Client(timeout=self.timeout_sec) as client:
            resp = client.get(url, auth=auth)
            resp.raise_for_status()
            return resp.text

    @staticmethod
    def _strip_ns(xml_str: str) -> ET.Element:
        clean = re.sub(r' xmlns="[^"]+"', '', xml_str)
        return ET.fromstring(clean)

    def test_connection(self) -> Dict[str, Any]:
        try:
            xml_resp = self._get("System/deviceInfo")
            root = self._strip_ns(xml_resp)
            model = root.findtext("model", "Hikvision Device")
            serial = root.findtext("serialNumber", "Unknown")
            firmware = root.findtext("firmwareVersion", "Unknown")
            return {
                "success": True,
                "manufacturer": "Hikvision",
                "model": model,
                "serial_number": serial,
                "firmware_version": firmware,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def connect_and_probe(self) -> RecorderInfo:
        device_test = self.test_connection()
        if not device_test.get("success"):
            raise ConnectionError(f"Failed to connect to Hikvision device at {self.ip_address}: {device_test.get('error')}")

        channels: List[ChannelInfo] = []

        # Try to enumerate IP channels on NVR via ContentMgmt
        try:
            chan_xml = self._get("ContentMgmt/InputProxy/channels")
            root = self._strip_ns(chan_xml)
            for proxy in root.findall(".//InputProxyChannel"):
                ch_id_str = proxy.findtext("id", "1")
                ch_num = int(ch_id_str)
                name = proxy.findtext("name", f"Camera {ch_num}")
                online = proxy.findtext(".//online", "true").lower() == "true"

                # Hikvision standard RTSP format: rtsp://user:pass@ip:554/Streaming/Channels/{ch}01 (Main), {ch}02 (Sub)
                main_url = f"rtsp://{self.username}:{self.password}@{self.ip_address}:{self.rtsp_port}/Streaming/Channels/{ch_num}01"
                sub_url = f"rtsp://{self.username}:{self.password}@{self.ip_address}:{self.rtsp_port}/Streaming/Channels/{ch_num}02"

                channels.append(ChannelInfo(
                    channel_number=ch_num,
                    name=name,
                    is_online=online,
                    main_stream_url=main_url,
                    sub_stream_url=sub_url,
                ))
        except Exception:
            # Fallback for single IP camera: channel 1
            main_url = f"rtsp://{self.username}:{self.password}@{self.ip_address}:{self.rtsp_port}/Streaming/Channels/101"
            sub_url = f"rtsp://{self.username}:{self.password}@{self.ip_address}:{self.rtsp_port}/Streaming/Channels/102"
            channels.append(ChannelInfo(
                channel_number=1,
                name=f"{device_test.get('model', 'Camera')} Ch 1",
                is_online=True,
                main_stream_url=main_url,
                sub_stream_url=sub_url,
            ))

        return RecorderInfo(
            manufacturer="Hikvision",
            model=device_test.get("model", "Hikvision Device"),
            serial_number=device_test.get("serial_number", "Unknown"),
            firmware_version=device_test.get("firmware_version", "Unknown"),
            total_channels=len(channels),
            channels=channels,
        )
