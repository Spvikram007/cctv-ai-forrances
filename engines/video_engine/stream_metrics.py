"""
Stream Metrics and Telemetry Models for Video Engine.
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any


class StreamState(str, Enum):
    OFFLINE = "OFFLINE"
    CONNECTING = "CONNECTING"
    ONLINE = "ONLINE"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"
    STOPPED = "STOPPED"


@dataclass
class StreamTelemetry:
    """Real-time performance and health metrics for an active stream."""
    channel_id: str
    state: StreamState = StreamState.OFFLINE
    current_fps: float = 0.0
    detected_width: int = 0
    detected_height: int = 0
    bitrate_kbps: int = 0
    total_frames_received: int = 0
    total_frames_dropped: int = 0
    reconnect_count: int = 0
    latency_ms: float = 0.0
    queue_occupancy: int = 0
    queue_capacity: int = 30
    last_frame_timestamp: Optional[datetime] = None
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "state": self.state.value,
            "fps": round(self.current_fps, 1),
            "resolution": f"{self.detected_width}x{self.detected_height}",
            "bitrate_kbps": self.bitrate_kbps,
            "frames_received": self.total_frames_received,
            "frames_dropped": self.total_frames_dropped,
            "reconnect_count": self.reconnect_count,
            "queue_utilization": f"{self.queue_occupancy}/{self.queue_capacity}",
            "last_error": self.last_error,
        }
