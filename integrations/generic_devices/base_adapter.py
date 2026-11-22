"""
Base Recorder / Camera Adapter Interface.
Defines common contracts for IP Cameras, NVRs, and DVRs.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class ChannelInfo:
    channel_number: int
    name: str
    is_online: bool = True
    main_stream_url: str = ""
    sub_stream_url: str = ""
    ptz_supported: bool = False
    audio_supported: bool = False


@dataclass
class RecorderInfo:
    manufacturer: str
    model: str
    serial_number: str = "Unknown"
    firmware_version: str = "Unknown"
    total_channels: int = 1
    channels: List[ChannelInfo] = field(default_factory=list)


class BaseDeviceAdapter(ABC):
    """Abstract base class for manufacturer device adapters."""

    def __init__(self, ip_address: str, port: int, username: str = "", password: str = "", timeout_sec: float = 5.0):
        self.ip_address = ip_address
        self.port = port
        self.username = username
        self.password = password
        self.timeout_sec = timeout_sec

    @abstractmethod
    def connect_and_probe(self) -> RecorderInfo:
        """Connects to device, queries system info and enumerates all channels."""
        pass

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """Tests device reachability and credentials."""
        pass
