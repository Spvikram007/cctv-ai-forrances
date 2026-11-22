"""
Dahua CGI Protocol Adapter.
Interacts with Dahua IP Cameras, NVRs, and DVRs via Dahua HTTP RPC/CGI.
"""

import re
from typing import Dict, Any, List
import httpx

from integrations.generic_devices.base_adapter import BaseDeviceAdapter, RecorderInfo, ChannelInfo
from core.logging.logger import get_logger

logger = get_logger("dahua_cgi")


class DahuaCGIAdapter(BaseDeviceAdapter):
    """Adapter for Dahua devices using HTTP CGI commands."""

    def __init__(self, ip_address: str, port: int = 80, username: str = "admin", password: str = "", rtsp_port: int = 554, timeout_sec: float = 5.0):
        super().__init__(ip_address, port, username, password, timeout_sec)
        self.rtsp_port = rtsp_port
        self.base_url = f"http://{self.ip_address}:{self.port}/cgi-bin"

    def _get(self, endpoint: str) -> str:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        auth = httpx.DigestAuth(self.username, self.password)
        with httpx.Client(timeout=self.timeout_sec) as client:
            resp = client.get(url, auth=auth)
            resp.raise_for_status()
            return resp.text

    def test_connection(self) -> Dict[str, Any]:
        try:
            resp_text = self._get("magicBox.cgi?action=getSystemInfo")
            # Sample response:
            # deviceType=DH-XVR5108HS-I3
            # serialNumber=7G02B89PAZ12345
            info = {}
            for line in resp_text.splitlines():
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    info[k] = v
            return {
                "success": True,
                "manufacturer": "Dahua",
                "model": info.get("deviceType", "Dahua Device"),
                "serial_number": info.get("serialNumber", "Unknown"),
                "firmware_version": info.get("appVersion", "Unknown"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def connect_and_probe(self) -> RecorderInfo:
        device_test = self.test_connection()
        if not device_test.get("success"):
            raise ConnectionError(f"Failed to connect to Dahua device: {device_test.get('error')}")

        channels: List[ChannelInfo] = []

        # Check total channels from encode config
        total_channels = 1
        try:
            cfg_text = self._get("configManager.cgi?action=getConfig&name=Encode")
            matches = re.findall(r"table\.Encode\[(\d+)\]", cfg_text)
            if matches:
                max_ch_idx = max(int(m) for m in matches)
                total_channels = max_ch_idx + 1
        except Exception:
            total_channels = 1

        for ch in range(1, total_channels + 1):
            # Dahua standard RTSP: rtsp://user:pass@ip:554/cam/realmonitor?channel={ch}&subtype=0 (Main), 1 (Sub)
            main_url = f"rtsp://{self.username}:{self.password}@{self.ip_address}:{self.rtsp_port}/cam/realmonitor?channel={ch}&subtype=0"
            sub_url = f"rtsp://{self.username}:{self.password}@{self.ip_address}:{self.rtsp_port}/cam/realmonitor?channel={ch}&subtype=1"
            channels.append(ChannelInfo(
                channel_number=ch,
                name=f"Camera {ch}",
                is_online=True,
                main_stream_url=main_url,
                sub_stream_url=sub_url,
            ))

        return RecorderInfo(
            manufacturer="Dahua",
            model=device_test.get("model", "Dahua Device"),
            serial_number=device_test.get("serial_number", "Unknown"),
            firmware_version=device_test.get("firmware_version", "Unknown"),
            total_channels=len(channels),
            channels=channels,
        )
