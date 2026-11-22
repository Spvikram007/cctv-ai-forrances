"""
Multi-Camera Track Manager.
Enforces per-camera tracker isolation so track IDs are never mixed
or shared across independent camera channels.
"""

import threading
from typing import Dict, List, Optional
from engines.tracking_engine.byte_tracker import ByteTracker, TrackedObject
from core.logging.logger import get_logger

logger = get_logger("track_manager")


class MultiCameraTrackManager:
    """
    Manages isolated ByteTracker instances per camera channel.
    Guarantees strict per-channel track isolation.
    """

    def __init__(
        self,
        high_threshold: float = 0.5,
        low_threshold: float = 0.1,
        match_threshold: float = 0.3,
        max_lost_frames: int = 30,
        min_hits: int = 3,
    ) -> None:
        self._high_threshold = high_threshold
        self._low_threshold = low_threshold
        self._match_threshold = match_threshold
        self._max_lost_frames = max_lost_frames
        self._min_hits = min_hits

        self._trackers: Dict[str, ByteTracker] = {}
        self._lock = threading.Lock()

    def get_tracker(self, channel_id: str) -> ByteTracker:
        """Retrieves or creates an isolated tracker for a channel."""
        with self._lock:
            if channel_id not in self._trackers:
                self._trackers[channel_id] = ByteTracker(
                    high_threshold=self._high_threshold,
                    low_threshold=self._low_threshold,
                    match_threshold=self._match_threshold,
                    max_lost_frames=self._max_lost_frames,
                    min_hits=self._min_hits,
                )
                logger.debug("Initialized isolated ByteTracker for channel [%s]", channel_id)
            return self._trackers[channel_id]

    def update_channel(self, channel_id: str, detections: list, timestamp: float = 0.0) -> List[TrackedObject]:
        """Runs tracking update on the channel's isolated tracker."""
        tracker = self.get_tracker(channel_id)
        return tracker.update(detections, timestamp)

    def reset_channel(self, channel_id: str) -> None:
        """Resets tracking state for a specific channel."""
        with self._lock:
            if channel_id in self._trackers:
                self._trackers[channel_id].reset()
                logger.info("Reset tracking state for channel [%s]", channel_id)

    def remove_channel(self, channel_id: str) -> None:
        """Removes a channel tracker on camera disconnect."""
        with self._lock:
            if channel_id in self._trackers:
                del self._trackers[channel_id]

    def get_active_track_count(self, channel_id: str) -> int:
        with self._lock:
            tracker = self._trackers.get(channel_id)
            return tracker.active_track_count if tracker else 0

    def reset_all(self) -> None:
        with self._lock:
            for tracker in self._trackers.values():
                tracker.reset()
            self._trackers.clear()


# Global track manager singleton
track_manager = MultiCameraTrackManager()
