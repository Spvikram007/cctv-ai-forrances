"""
Unit tests for RTSP Stream Engine, Worker Lifecycle, and Bounded Queues.
"""

import time
import numpy as np
from engines.video_engine.rtsp_streamer import RTSPStreamWorker, mask_rtsp_url
from engines.video_engine.stream_manager import StreamManager
from engines.video_engine.stream_metrics import StreamState


def test_mask_rtsp_url():
    raw_url = "rtsp://admin:superSecret123@192.168.1.50:554/Streaming/Channels/101"
    masked = mask_rtsp_url(raw_url)
    assert "superSecret123" not in masked
    assert "rtsp://admin:******@192.168.1.50:554/Streaming/Channels/101" == masked

    # URL without credentials remains unchanged
    public_url = "rtsp://192.168.1.50:554/live"
    assert mask_rtsp_url(public_url) == public_url


def test_stream_worker_synthetic_generation():
    worker = RTSPStreamWorker(
        channel_id="test_cam_1",
        rtsp_url="test://simulated_cam",
        max_buffer_size=10,
        is_test_stream=True,
    )
    worker.start()

    # Wait for a few frames to be decoded and buffered
    time.sleep(0.2)

    assert worker.is_alive()
    assert worker.telemetry.state == StreamState.ONLINE

    latest = worker.get_latest_frame()
    assert latest is not None
    frame, ts = latest
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (360, 640, 3)
    assert ts > 0

    worker.stop()
    worker.join(timeout=2.0)
    assert not worker.is_alive()
    assert worker.telemetry.state == StreamState.STOPPED


def test_bounded_queue_overflow_and_frame_drop():
    buffer_cap = 5
    worker = RTSPStreamWorker(
        channel_id="overflow_test",
        rtsp_url="test://simulated_cam",
        max_buffer_size=buffer_cap,
        is_test_stream=True,
    )
    worker.start()

    # Allow buffer to saturate (over 5 frames)
    time.sleep(0.35)

    with worker._buffer_lock:
        current_len = len(worker._frame_buffer)
        assert current_len <= buffer_cap  # Queue never exceeds bounded limit!

    assert worker.telemetry.total_frames_dropped > 0  # Dropped frames recorded
    worker.stop()
    worker.join(timeout=2.0)


def test_stream_manager_multi_channel():
    manager = StreamManager(max_channels=16)

    # Start 4 concurrent streams
    for i in range(1, 5):
        manager.start_stream(
            channel_id=f"ch_{i}",
            rtsp_url=f"test://sim_{i}",
            channel_name=f"Camera {i}",
            is_test_stream=True,
        )

    time.sleep(0.2)
    assert manager.active_stream_count() == 4

    telemetry = manager.get_all_telemetry()
    assert len(telemetry) == 4
    for i in range(1, 5):
        assert f"ch_{i}" in telemetry
        assert telemetry[f"ch_{i}"]["state"] == "ONLINE"

    manager.stop_all()
    assert manager.active_stream_count() == 0
