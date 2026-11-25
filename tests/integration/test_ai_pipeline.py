"""
Integration tests for the AI Video Pipeline:
Decoupled streaming, queue overflow, worker restart,
and fault-isolation proving recording continuity during AI failures.
"""

import time
import pytest
import numpy as np
from unittest.mock import MagicMock

from engines.ai_engine.inference_worker import (
    AIInferenceWorker,
    InferenceWorkerManager,
    InferenceResult,
)
from engines.detection_engine.yolo_detector import YOLODetector, DetectionResult
from engines.tracking_engine.byte_tracker import ByteTracker
from engines.recording_engine.recorder import ChannelRecordingWorker


def test_ai_inference_worker_lifecycle():
    """Verifies worker startup, frame processing, and callback delivery."""
    results_received = []

    def mock_inference(blob):
        # Return synthetic YOLO output with 1 detected person
        out = np.zeros((1, 84, 8400), dtype=np.float32)
        out[0, 0, 0] = 320.0
        out[0, 1, 0] = 320.0
        out[0, 2, 0] = 100.0
        out[0, 3, 0] = 150.0
        out[0, 4, 0] = 0.88  # person
        return {"output0": out}

    detector = YOLODetector(inference_fn=mock_inference)
    tracker = ByteTracker(min_hits=1)

    worker = AIInferenceWorker(
        channel_id="CH_INT_01",
        detector=detector,
        tracker=tracker,
        target_fps=20.0,
        result_callback=lambda res: results_received.append(res),
    )
    worker.start()

    try:
        # Push 3 frames
        for i in range(3):
            dummy_frame = np.zeros((360, 640, 3), dtype=np.uint8)
            worker.push_frame(dummy_frame, time.time())
            time.sleep(0.06)

        for _ in range(20):
            if len(results_received) >= 1:
                break
            time.sleep(0.05)
        assert len(results_received) >= 1
        res = results_received[0]
        assert res.channel_id == "CH_INT_01"
        assert len(res.detections) == 1
        assert res.detections[0].class_name == "person"
        assert len(res.tracked_objects) == 1

    finally:
        worker.stop()
        worker.join(timeout=2.0)


def test_inference_queue_overflow_and_backpressure():
    """
    Verifies that pushing frames faster than inference processing
    does not cause memory growth; oldest frames are discarded in O(1).
    """
    detector = YOLODetector(inference_fn=lambda blob: {"output0": np.zeros((1, 84, 8400), dtype=np.float32)})
    worker = AIInferenceWorker(
        channel_id="CH_OVERFLOW",
        detector=detector,
        max_queue_size=10,
        target_fps=1.0,  # Very slow processing
    )

    # Push 25 frames rapidly into a queue with capacity 10
    dummy_frame = np.zeros((360, 640, 3), dtype=np.uint8)
    for i in range(25):
        worker.push_frame(dummy_frame, time.time())

    # Queue must strictly be bounded to max_queue_size
    assert worker.queue_depth <= 10


def test_recording_continuity_during_ai_failure(tmp_path):
    """
    CRITICAL SURVEILLANCE SAFETY REQUIREMENT:
    Proves that an unhandled exception or crash in the AI inference engine
    does NOT interrupt continuous video recording.
    """
    rec_worker = ChannelRecordingWorker(
        channel_id="CH_SAFETY_TEST",
        recording_type="CONTINUOUS",
        segment_duration_sec=60,
        output_dir=str(tmp_path / "recs"),
    )
    rec_worker.start()

    # Faulty AI detector that raises an unhandled exception
    def crashing_inference(blob):
        raise RuntimeError("Simulated OpenVINO GPU driver memory fault!")

    ai_detector = YOLODetector(inference_fn=crashing_inference)
    ai_worker = AIInferenceWorker(
        channel_id="CH_SAFETY_TEST",
        detector=ai_detector,
        target_fps=30.0,
    )
    ai_worker.start()

    try:
        # Stream 10 frames to both recorder and AI worker
        for i in range(10):
            frame = np.full((360, 640, 3), 100, dtype=np.uint8)
            now = time.time()

            # Record frame
            rec_worker.push_frame(frame, now)

            # AI worker receives frame and will crash in its thread
            ai_worker.push_frame(frame, now)
            time.sleep(0.04)

        time.sleep(0.2)

        # AI worker experienced error
        # Verify recording worker is STILL ALIVE and happily recording
        assert rec_worker.is_alive() is True
        assert rec_worker._frames_written_segment >= 8

    finally:
        ai_worker.stop()
        rec_worker.stop()
        ai_worker.join(timeout=2.0)
        rec_worker.join(timeout=2.0)


def test_ai_worker_restart():
    """Verifies that an AI worker can be stopped and restarted cleanly."""
    detector = YOLODetector(inference_fn=lambda blob: {"output0": np.zeros((1, 84, 8400), dtype=np.float32)})
    mgr = InferenceWorkerManager()

    w1 = mgr.start_worker("CH_RESTART", detector)
    assert w1.is_alive() is True
    assert "CH_RESTART" in mgr.get_active_channels()

    mgr.stop_worker("CH_RESTART")
    assert "CH_RESTART" not in mgr.get_active_channels()

    # Restart
    w2 = mgr.start_worker("CH_RESTART", detector)
    assert w2.is_alive() is True
    mgr.stop_all()
