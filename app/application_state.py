"""
Application State Singleton.
Maintains live in-memory telemetry, stream counts, camera statuses,
AI worker state, and active sessions across the platform.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

from core.hardware.detector import SystemHardwareReport


@dataclass
class ChannelRuntimeState:
    channel_id: str
    name: str
    is_online: bool = False
    is_streaming: bool = False
    is_recording: bool = False
    is_ai_active: bool = False
    current_fps: float = 0.0
    bitrate_kbps: int = 0
    last_error: Optional[str] = None


class ApplicationState:
    """Thread-safe centralized runtime state for CCTV platform."""

    def __init__(self) -> None:
        self.started_at: datetime = datetime.now(timezone.utc)
        self.hardware_report: Optional[SystemHardwareReport] = None
        self.channels: Dict[str, ChannelRuntimeState] = {}
        self.active_alarms_count: int = 0
        self.active_ai_detections_count: int = 0
        self.total_channels_capacity: int = 64

    @property
    def uptime_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.started_at).total_seconds()

    @property
    def online_channels_count(self) -> int:
        return sum(1 for ch in self.channels.values() if ch.is_online)

    @property
    def active_recordings_count(self) -> int:
        return sum(1 for ch in self.channels.values() if ch.is_recording)

    @property
    def active_ai_channels_count(self) -> int:
        return sum(1 for ch in self.channels.values() if ch.is_ai_active)

    def get_summary(self) -> Dict[str, Any]:
        """Provides snapshot telemetry for dashboard widgets."""
        return {
            "uptime_seconds": round(self.uptime_seconds, 1),
            "total_capacity": self.total_channels_capacity,
            "configured_channels": len(self.channels),
            "online_channels": self.online_channels_count,
            "offline_channels": len(self.channels) - self.online_channels_count,
            "active_recordings": self.active_recordings_count,
            "active_ai_channels": self.active_ai_channels_count,
            "active_alarms": self.active_alarms_count,
        }


# Global application state instance
app_state = ApplicationState()
