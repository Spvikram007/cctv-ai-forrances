"""
Stream Metrics and Telemetry Models for Video Engine.
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from collections import deque


class StreamState(str, Enum):
    OFFLINE = "OFFLINE"
    CONNECTING = "CONNECTING"
    ONLINE = "ONLINE"
    RECONNECTING = "RECONNECTING"
    FROZEN = "FROZEN"
    ERROR = "ERROR"
    STOPPED = "STOPPED"


@dataclass
class StreamHealthEvent:
    timestamp: datetime
    state: StreamState
    fps: float = 0.0
    message: str = ""


class StreamHealthHistory:
    """Maintains a rolling window of health and state transition events per channel."""

    def __init__(self, maxlen: int = 100) -> None:
        self.maxlen = maxlen
        self.events: deque = deque(maxlen=maxlen)

    def record_event(self, state: StreamState, fps: float = 0.0, message: str = "") -> None:
        self.events.append(StreamHealthEvent(
            timestamp=datetime.now(timezone.utc),
            state=state,
            fps=round(fps, 1),
            message=message,
        ))

    def get_events(self, limit: int = 50) -> list:
        items = list(self.events)
        return items[-limit:]

    def to_dict_list(self, limit: int = 50) -> list:
        return [
            {
                "timestamp": e.timestamp.isoformat(),
                "state": e.state.value,
                "fps": e.fps,
                "message": e.message,
            }
            for e in self.get_events(limit)
        ]


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
    # Phase 3 stream reliability and failover metrics
    is_frozen: bool = False
    frozen_frames_count: int = 0
    decoder_errors_count: int = 0
    packet_loss_pct: float = 0.0
    current_profile: str = "MAIN"
    consecutive_empty_frames: int = 0
    start_time: Optional[datetime] = None
    uptime_seconds: float = 0.0

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
            "is_frozen": self.is_frozen,
            "frozen_frames_count": self.frozen_frames_count,
            "decoder_errors": self.decoder_errors_count,
            "packet_loss_pct": round(self.packet_loss_pct, 1),
            "current_profile": self.current_profile,
            "uptime_seconds": round(self.uptime_seconds, 1),
        }
