"""
Multi-Object Tracking Engine Package.
ByteTrack algorithm with Kalman filter and Hungarian association.
"""

from engines.tracking_engine.byte_tracker import (
    ByteTracker,
    TrackedObject,
    KalmanBoxTracker,
    iou_batch,
    linear_assignment,
)
from engines.tracking_engine.track_manager import (
    MultiCameraTrackManager,
    track_manager,
)

__all__ = [
    "ByteTracker",
    "TrackedObject",
    "KalmanBoxTracker",
    "iou_batch",
    "linear_assignment",
    "MultiCameraTrackManager",
    "track_manager",
]
