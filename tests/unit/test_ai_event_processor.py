"""
Unit tests for AI Event Processor:
Deduplication, Severity Mapping, Recording Triggers,
Snapshots, and Database Persistence.
"""

import os
import time
import pytest
import numpy as np
from unittest.mock import MagicMock

from engines.event_engine.event_processor import (
    AIEventProcessor,
    EventDeduplicator,
    AIEventRecord,
)
from engines.detection_engine.yolo_detector import DetectionResult
from engines.tracking_engine.byte_tracker import TrackedObject
from engines.ai_engine.inference_worker import InferenceResult


def test_event_deduplication():
    """Verifies duplicate suppression within suppression window."""
    dedup = EventDeduplicator(suppression_window_sec=1.0)

    # First event: allowed
    assert dedup.is_duplicate("CAM_01", "DETECTION_PERSON", "person", track_id=1) is False

    # Second event immediately: suppressed
    assert dedup.is_duplicate("CAM_01", "DETECTION_PERSON", "person", track_id=1) is True

    # Different track ID: allowed
    assert dedup.is_duplicate("CAM_01", "DETECTION_PERSON", "person", track_id=2) is False

    # Different channel: allowed
    assert dedup.is_duplicate("CAM_02", "DETECTION_PERSON", "person", track_id=1) is False


def test_event_severity_mapping():
    """Verifies severity classification based on target class."""
    processor = AIEventProcessor(persist_to_database=False)

    assert processor.SEVERITY_MAP["person"] == "WARNING"
    assert processor.SEVERITY_MAP["car"] == "INFO"
    assert processor.SEVERITY_MAP["truck"] == "INFO"
    assert processor.SEVERITY_MAP["motorcycle"] == "INFO"
    assert processor.SEVERITY_MAP["bicycle"] == "INFO"


def test_event_recording_trigger():
    """Verifies that high-severity events trigger event-based recording."""
    mock_rec_mgr = MagicMock()
    processor = AIEventProcessor(
        recording_manager=mock_rec_mgr,
        persist_to_database=False,
    )

    result = InferenceResult(
        channel_id="CAM_SEC_01",
        timestamp=time.time(),
        detections=[
            DetectionResult(0, "person", 0.85, 0.2, 0.2, 0.1, 0.2, 100, 100, 50, 100)
        ],
        tracked_objects=[
            TrackedObject(1, 0, "person", 0.85, (0.2, 0.2, 0.1, 0.2), (100, 100, 50, 100))
        ],
        inference_latency_ms=12.5,
        device="GPU",
    )

    events = processor.process_inference_result(result)
    assert len(events) == 1
    assert events[0].event_type == "DETECTION_PERSON"
    assert events[0].severity == "WARNING"

    # Verify RecordingManager was called to trigger recording
    mock_rec_mgr.trigger_event_recording.assert_called_once_with(
        channel_id="CAM_SEC_01",
        event_name="DETECTION_PERSON",
        duration_sec=15.0,
    )


def test_detection_snapshot_creation(tmp_path):
    """Verifies snapshot JPEG generation with directory hierarchy."""
    processor = AIEventProcessor(
        persist_to_database=False,
        snapshots_dir=str(tmp_path / "snaps"),
    )

    dummy_frame = np.full((360, 640, 3), 80, dtype=np.uint8)
    snap_path = processor.save_detection_snapshot(
        channel_id="CAM_TEST_01",
        frame=dummy_frame,
        bbox_pixels=(50, 50, 100, 150),
        timestamp=time.time(),
    )

    assert snap_path is not None
    assert os.path.exists(snap_path)
    assert snap_path.endswith(".jpg")
    assert os.path.getsize(snap_path) > 0


def test_detection_and_event_db_persistence(test_db_manager, tmp_path):
    """Verifies that detections and AI events are written to the database."""
    processor = AIEventProcessor(
        persist_to_database=True,
        snapshots_dir=str(tmp_path / "snaps"),
    )

    det = DetectionResult(0, "person", 0.92, 0.3, 0.3, 0.15, 0.25, 120, 120, 60, 100)
    det_id = processor.persist_detection("TEST_CH_01", det, timestamp=time.time(), track_id=42)
    assert det_id is not None

    evt_id = processor.persist_event(
        channel_id="TEST_CH_01",
        event_type="DETECTION_PERSON",
        severity="WARNING",
        timestamp=time.time(),
        details={"test": True},
    )
    assert evt_id is not None

    stats = processor.get_statistics()
    assert stats["recent_event_count"] >= 0
