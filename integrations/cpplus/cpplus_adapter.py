"""
CP PLUS Camera & DVR/NVR Adapter.
Supports CP PLUS Orange and Indigo series recorders and IP cameras.
"""

from typing import Dict, Any, List
from integrations.dahua.cgi_adapter import DahuaCGIAdapter
from integrations.generic_devices.base_adapter import BaseDeviceAdapter, RecorderInfo, ChannelInfo
from core.logging.logger import get_logger

logger = get_logger("cpplus_adapter")


class CPPlusAdapter(BaseDeviceAdapter):
    """Adapter for CP PLUS surveillance hardware."""

    def __init__(self, ip_address: str, port: int = 80, username: str = "admin", password: str = "", rtsp_port: int = 554, timeout_sec: float = 5.0):
        super().__init__(ip_address, port, username, password, timeout_sec)
        self.rtsp_port = rtsp_port
        # CP PLUS Orange series largely implements Dahua RPC/CGI standard
        self._underlying_cgi = DahuaCGIAdapter(ip_address, port, username, password, rtsp_port, timeout_sec)

    def test_connection(self) -> Dict[str, Any]:
        res = self._underlying_cgi.test_connection()
        if res.get("success"):
            res["manufacturer"] = "CP PLUS"
        return res

    def connect_and_probe(self) -> RecorderInfo:
        info = self._underlying_cgi.connect_and_probe()
        info.manufacturer = "CP PLUS"
        return info
