"""
Unit tests for YOLO Object Detection (Preprocessing, Decoding, NMS)
and ByteTrack Multi-Object Tracking (State Lifecycle, Per-Camera Isolation).
"""

import pytest
import numpy as np
import cv2

from engines.detection_engine.yolo_detector import YOLODetector, DetectionResult
from engines.tracking_engine.byte_tracker import (
    ByteTracker,
    TrackedObject,
    KalmanBoxTracker,
    iou_batch,
    linear_assignment,
)
from engines.tracking_engine.track_manager import MultiCameraTrackManager


def test_yolo_preprocessing_letterbox():
    """Verifies letterbox resize, aspect ratio preservation, and normalization."""
    detector = YOLODetector(input_width=640, input_height=640)

    # 1920x1080 surveillance image
    dummy_frame = np.full((1080, 1920, 3), 120, dtype=np.uint8)
    blob = detector.preprocess(dummy_frame)

    assert blob.shape == (1, 3, 640, 640)
    assert blob.dtype == np.float32
    assert blob.min() >= 0.0
    assert blob.max() <= 1.0


def test_yolo_postprocessing_synthetic_detection():
    """Verifies YOLO output decoding, NMS suppression, and class filtering."""
    detector = YOLODetector(
        input_width=640,
        input_height=640,
        confidence_threshold=0.50,
        iou_threshold=0.45,
    )
    # Set scale factors as if 1920x1080 was processed
    detector._orig_h, detector._orig_w = 1080, 1920
    detector._scale_x = detector._scale_y = 640 / 1920
    detector._pad_x = 0
    detector._pad_y = int((640 - 1080 * (640 / 1920)) / 2)

    # Synthetic output tensor [1, 84, 8400]
    raw_output = np.zeros((1, 84, 8400), dtype=np.float32)

    # Prediction 0: Person (class 0) at center with 0.85 confidence
    raw_output[0, 0, 0] = 320.0  # cx
    raw_output[0, 1, 0] = 320.0  # cy
    raw_output[0, 2, 0] = 100.0  # w
    raw_output[0, 3, 0] = 200.0  # h
    raw_output[0, 4, 0] = 0.85   # class 0 = person

    # Prediction 1: Duplicate overlapping person (should be suppressed by NMS)
    raw_output[0, 0, 1] = 322.0
    raw_output[0, 1, 1] = 321.0
    raw_output[0, 2, 1] = 98.0
    raw_output[0, 3, 1] = 198.0
    raw_output[0, 4, 1] = 0.75

    # Prediction 2: Car (class 2) at top right with 0.90 confidence
    raw_output[0, 0, 2] = 500.0
    raw_output[0, 1, 2] = 200.0
    raw_output[0, 2, 2] = 120.0
    raw_output[0, 3, 2] = 80.0
    raw_output[0, 6, 2] = 0.90   # class 2 = car

    # Prediction 3: Low confidence below threshold (should be filtered out)
    raw_output[0, 0, 3] = 100.0
    raw_output[0, 1, 3] = 100.0
    raw_output[0, 2, 3] = 50.0
    raw_output[0, 3, 3] = 50.0
    raw_output[0, 4, 3] = 0.30   # low conf person

    detections = detector.postprocess({"output0": raw_output}, (1080, 1920))

    assert len(detections) == 2  # 1 person (NMS suppressed duplicate), 1 car
    classes = [d.class_name for d in detections]
    assert "person" in classes
    assert "car" in classes

    person_det = next(d for d in detections if d.class_name == "person")
    assert person_det.confidence == pytest.approx(0.85)
    assert 0.0 <= person_det.bbox_x <= 1.0
    assert 0.0 <= person_det.bbox_y <= 1.0
    assert person_det.pixel_w > 0
    assert person_det.pixel_h > 0


def test_iou_computation():
    """Verifies vectorized IoU matrix computation."""
    boxes_a = np.array([
        [0.1, 0.1, 0.2, 0.2],  # x1=0.1, y1=0.1, x2=0.3, y2=0.3
    ])
    boxes_b = np.array([
        [0.1, 0.1, 0.2, 0.2],  # Identical box -> IoU = 1.0
        [0.5, 0.5, 0.2, 0.2],  # Disjoint box -> IoU = 0.0
    ])
    iou = iou_batch(boxes_a, boxes_b)
    assert iou[0, 0] == pytest.approx(1.0)
    assert iou[0, 1] == pytest.approx(0.0)


def test_linear_assignment():
    """Verifies Hungarian / greedy linear assignment for tracking association."""
    cost = np.array([
        [0.9, 0.1],
        [0.2, 0.8],
    ])
    matches, unmatched_a, unmatched_b = linear_assignment(cost, threshold=0.5)
    assert (0, 0) in matches
    assert (1, 1) in matches
    assert len(unmatched_a) == 0
    assert len(unmatched_b) == 0


def test_bytetrack_lifecycle():
    """Verifies track creation, state prediction, update, and confirmation."""
    tracker = ByteTracker(high_threshold=0.5, min_hits=2)
    tracker.reset()

    det_frame1 = [
        DetectionResult(
            class_id=0, class_name="person", confidence=0.85,
            bbox_x=0.2, bbox_y=0.2, bbox_w=0.1, bbox_h=0.2,
        )
    ]

    # Frame 1: Track created but not yet confirmed (min_hits=2)
    tracked_1 = tracker.update(det_frame1, timestamp=1.0)
    assert tracker.active_track_count == 1
    # On first frame, time_since_update == 0, so it appears in output
    assert len(tracked_1) == 1
    track_id_1 = tracked_1[0].track_id

    # Frame 2: Object slightly moved
    det_frame2 = [
        DetectionResult(
            class_id=0, class_name="person", confidence=0.88,
            bbox_x=0.21, bbox_y=0.20, bbox_w=0.1, bbox_h=0.2,
        )
    ]
    tracked_2 = tracker.update(det_frame2, timestamp=1.04)
    assert len(tracked_2) == 1
    # Track ID must be preserved across frames
    assert tracked_2[0].track_id == track_id_1
    assert tracked_2[0].frames_tracked == 2


def test_bytetrack_lost_and_recovery():
    """Verifies that an occluded track is marked lost and recovered when seen again."""
    tracker = ByteTracker(max_lost_frames=5, min_hits=1)
    tracker.reset()

    # Initial detection
    det = [DetectionResult(0, "person", 0.9, 0.3, 0.3, 0.1, 0.2)]
    tracker.update(det, 1.0)

    # Frame 2-4: Object temporarily occluded / missed
    for i in range(3):
        tracker.update([], 1.0 + (i + 1) * 0.1)

    assert tracker.lost_track_count >= 1

    # Frame 5: Object reappears at same location
    det_reappear = [DetectionResult(0, "person", 0.85, 0.31, 0.30, 0.1, 0.2)]
    recovered = tracker.update(det_reappear, 1.5)
    assert len(recovered) == 1
    assert recovered[0].track_id == 1  # Recovered original ID


def test_multicamera_track_isolation():
    """
    CRITICAL REQUIREMENT: Verifies that Camera 1 and Camera 2 maintain
    strictly isolated tracking spaces and never share or collide track state.
    """
    mgr = MultiCameraTrackManager()
    mgr.reset_all()

    # Camera 1 detection
    cam1_dets = [DetectionResult(0, "person", 0.9, 0.2, 0.2, 0.1, 0.2)]
    cam1_tracks = mgr.update_channel("CAM_01", cam1_dets, 1.0)
    assert len(cam1_tracks) == 1

    # Camera 2 detection at different location
    cam2_dets = [DetectionResult(2, "car", 0.85, 0.6, 0.6, 0.2, 0.15)]
    cam2_tracks = mgr.update_channel("CAM_02", cam2_dets, 1.0)
    assert len(cam2_tracks) == 1

    # Trackers must be distinct objects
    t1 = mgr.get_tracker("CAM_01")
    t2 = mgr.get_tracker("CAM_02")
    assert t1 is not t2
    assert t1.active_track_count == 1
    assert t2.active_track_count == 1

    # Camera 1 receives empty frame -> its track loses update, Camera 2 unaffected
    mgr.update_channel("CAM_01", [], 1.1)
    assert mgr.get_active_track_count("CAM_02") == 1
