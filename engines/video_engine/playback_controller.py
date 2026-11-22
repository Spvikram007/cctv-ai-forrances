"""
Synchronized Multi-Camera Playback Engine.
Coordinates master playback clock, variable speeds (0.25x to 16x), frame stepping,
recording gap detection, and accurate UTC timestamp seeking across multiple cameras.
"""

import os
import time
import threading
from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
import cv2
import numpy as np

from database.database_manager import db_manager
from database.models.recordings import Recording, RecordingSegment
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("playback_controller")


def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensures datetime object is UTC timezone-aware."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class PlaybackState(str, Enum):
    STOPPED = "STOPPED"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"


class SingleCameraPlayer:
    """Manages video decoding, segment switching, and seeking for a single playback channel."""

    def __init__(self, channel_id: str) -> None:
        self.channel_id = channel_id
        self._current_segment_id: Optional[str] = None
        self._current_file_path: Optional[str] = None
        self._capture: Optional[cv2.VideoCapture] = None
        self._segment_start_time: Optional[datetime] = None
        self._segment_end_time: Optional[datetime] = None
        self._fps: float = 25.0
        self._current_frame: Optional[np.ndarray] = None
        self._is_in_gap: bool = True

    def close(self) -> None:
        """Releases video file capture."""
        if self._capture:
            self._capture.release()
            self._capture = None
        self._current_segment_id = None
        self._current_file_path = None
        self._current_frame = None
        self._is_in_gap = True

    def seek_to_timestamp(self, target_time: datetime) -> Optional[np.ndarray]:
        """
        Seeks to the frame corresponding to target_time UTC.
        If target_time falls into a recording gap, returns None.
        """
        target_time = to_utc(target_time)

        # 1. Check if target_time is within currently loaded segment
        if (
            self._capture is not None
            and self._segment_start_time is not None
            and self._segment_end_time is not None
            and self._segment_start_time <= target_time <= self._segment_end_time
        ):
            # Calculate millisecond offset
            offset_sec = (target_time - self._segment_start_time).total_seconds()
            offset_ms = max(offset_sec * 1000.0, 0.0)
            self._capture.set(cv2.CAP_PROP_POS_MSEC, offset_ms)
            ret, frame = self._capture.read()
            if ret and frame is not None:
                self._current_frame = frame
                self._is_in_gap = False
                return frame

        # 2. Query database for segment covering target_time
        with db_manager.get_session() as session:
            # Query all segments for this channel and match with normalized timestamps
            candidate_segments = (
                session.query(RecordingSegment)
                .join(Recording)
                .filter(Recording.channel_id == self.channel_id)
                .order_by(RecordingSegment.start_time.asc())
                .all()
            )

            seg = None
            for s in candidate_segments:
                s_start = to_utc(s.start_time)
                s_end = to_utc(s.end_time)
                if s_start and s_end and s_start <= target_time <= s_end:
                    seg = s
                    break

            if not seg or not os.path.exists(seg.file_path):
                # No footage found: Camera is in a recording gap at this timestamp
                self.close()
                self._is_in_gap = True
                return None

            # Open matching segment
            self.close()
            self._capture = cv2.VideoCapture(seg.file_path)
            if not self._capture.isOpened():
                self._is_in_gap = True
                return None

            self._current_segment_id = seg.id
            self._current_file_path = seg.file_path
            self._segment_start_time = to_utc(seg.start_time)
            self._segment_end_time = to_utc(seg.end_time)
            self._fps = self._capture.get(cv2.CAP_PROP_FPS) or 25.0

            offset_sec = (target_time - self._segment_start_time).total_seconds()
            offset_ms = max(offset_sec * 1000.0, 0.0)
            self._capture.set(cv2.CAP_PROP_POS_MSEC, offset_ms)
            ret, frame = self._capture.read()
            if ret and frame is not None:
                self._current_frame = frame
                self._is_in_gap = False
                return frame

        self._is_in_gap = True
        return None

    def read_next_frame(self) -> Optional[np.ndarray]:
        """Reads subsequent frame during continuous playback."""
        if self._capture and self._capture.isOpened():
            ret, frame = self._capture.read()
            if ret and frame is not None:
                self._current_frame = frame
                self._is_in_gap = False
                return frame
        self._is_in_gap = True
        return None

    def get_display_frame(self, target_time: datetime) -> np.ndarray:
        """Returns decoded frame or realistic simulated gap overlay if no footage exists."""
        if not self._is_in_gap and self._current_frame is not None:
            return self._current_frame

        # Render Standby Gap Frame
        w, h = 640, 360
        gap_frame = np.zeros((h, w, 3), dtype=np.uint8)
        gap_frame[:] = (18, 22, 28)
        time_str = target_time.strftime("%Y-%m-%d %H:%M:%S UTC")
        cv2.putText(gap_frame, f"{self.channel_id.upper()} - NO RECORDING AVAILABLE", (w // 2 - 180, h // 2 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 116, 139), 1)
        cv2.putText(gap_frame, f"Timestamp: {time_str}", (w // 2 - 120, h // 2 + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (71, 85, 105), 1)
        return gap_frame


class SynchronizedPlaybackController:
    """Master controller managing multi-camera synchronized playback."""

    def __init__(self) -> None:
        self.state: PlaybackState = PlaybackState.STOPPED
        self.playback_speed: float = 1.0  # 0.25x, 0.5x, 1x, 2x, 4x, 8x, 16x
        self.master_clock: datetime = datetime.now(timezone.utc)
        self.channel_players: Dict[str, SingleCameraPlayer] = {}
        self._lock = threading.RLock()
        self._last_tick_perf: float = 0.0

    def set_channels(self, channel_ids: List[str]) -> None:
        """Configures the set of active playback channels (1, 4, 9, 16)."""
        with self._lock:
            # Close removed players
            for ch in list(self.channel_players.keys()):
                if ch not in channel_ids:
                    self.channel_players[ch].close()
                    del self.channel_players[ch]

            # Initialize new players
            for ch in channel_ids:
                if ch not in self.channel_players:
                    self.channel_players[ch] = SingleCameraPlayer(channel_id=ch)

    def play(self) -> None:
        with self._lock:
            self.state = PlaybackState.PLAYING
            self._last_tick_perf = time.perf_counter()
            bus.publish("playback.state_changed", {"state": "PLAYING", "speed": self.playback_speed})

    def pause(self) -> None:
        with self._lock:
            self.state = PlaybackState.PAUSED
            bus.publish("playback.state_changed", {"state": "PAUSED"})

    def stop(self) -> None:
        with self._lock:
            self.state = PlaybackState.STOPPED
            for player in self.channel_players.values():
                player.close()
            bus.publish("playback.state_changed", {"state": "STOPPED"})

    def set_speed(self, speed: float) -> None:
        with self._lock:
            if speed in [0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0]:
                self.playback_speed = speed
                logger.info("Playback speed set to %.2fx", speed)

    def seek_to_timestamp(self, target_utc: datetime) -> None:
        """Synchronously seeks all active players to a common UTC timestamp."""
        with self._lock:
            self.master_clock = target_utc
            for player in self.channel_players.values():
                player.seek_to_timestamp(target_utc)
            bus.publish("playback.seek", {"timestamp": target_utc.isoformat()})

    def step_forward(self, frame_step: int = 1) -> None:
        """Advances playback by exactly frame_step frames (1 / 25th of a second per frame)."""
        with self._lock:
            delta_sec = frame_step / 25.0
            self.seek_to_timestamp(self.master_clock + timedelta(seconds=delta_sec))

    def step_backward(self, frame_step: int = 1) -> None:
        """Steps playback backward by frame_step frames."""
        with self._lock:
            delta_sec = frame_step / 25.0
            self.seek_to_timestamp(self.master_clock - timedelta(seconds=delta_sec))

    def update_clock_tick(self) -> datetime:
        """Called periodically by UI timer to advance master clock during playback."""
        with self._lock:
            if self.state == PlaybackState.PLAYING:
                now_perf = time.perf_counter()
                elapsed_real = now_perf - self._last_tick_perf
                self._last_tick_perf = now_perf

                # Advance master clock scaled by playback speed
                advanced_sec = elapsed_real * self.playback_speed
                self.master_clock += timedelta(seconds=advanced_sec)

                # Sync all channel players
                for player in self.channel_players.values():
                    player.seek_to_timestamp(self.master_clock)

            return self.master_clock

    def get_frame(self, channel_id: str) -> np.ndarray:
        """Returns frame for designated channel matching master clock timestamp."""
        with self._lock:
            player = self.channel_players.get(channel_id)
            if player:
                return player.get_display_frame(self.master_clock)
            # Default empty frame
            dummy = np.zeros((360, 640, 3), dtype=np.uint8)
            dummy[:] = (18, 22, 28)
            return dummy

    @staticmethod
    def get_recording_intervals(channel_id: str, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        """Queries database for all recording segments for timeline visualization."""
        start_time = to_utc(start_time)
        end_time = to_utc(end_time)

        with db_manager.get_session() as session:
            segments = (
                session.query(RecordingSegment)
                .join(Recording)
                .filter(Recording.channel_id == channel_id)
                .all()
            )

            intervals = []
            for seg in segments:
                s_start = to_utc(seg.start_time)
                s_end = to_utc(seg.end_time)
                if s_start and s_end and s_end >= start_time and s_start <= end_time:
                    intervals.append({
                        "start_time": s_start,
                        "end_time": s_end,
                        "recording_type": seg.recording.recording_type if seg.recording else "CONTINUOUS",
                        "file_path": seg.file_path,
                        "duration_sec": seg.duration_sec,
                    })
            return intervals


# Global playback controller singleton
playback_controller = SynchronizedPlaybackController()
