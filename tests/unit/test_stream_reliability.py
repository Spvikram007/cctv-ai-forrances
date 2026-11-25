"""
Unit tests for Stream Reliability, Failover, Exponential Backoff,
Frozen Frame Detection, Profile Switching, and Diagnostics.
"""

import os
import json
import time
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import numpy as np

from engines.video_engine.rtsp_streamer import (
    RTSPStreamWorker, validate_rtsp_url, mask_rtsp_url
)
from engines.video_engine.stream_metrics import StreamState, StreamTelemetry
from engines.video_engine.stream_manager import (
    StreamManager, CameraConnectionTester, ConnectionTestReport
)
from core.events.event_bus import bus


class TestStreamReliabilityAndFailover(unittest.TestCase):
    """Test suite for stream reliability, frozen frame detection, profile switching, and diagnostics."""

    def setUp(self):
        self.stream_manager = StreamManager(max_channels=16)

    def tearDown(self):
        self.stream_manager.stop_all()

    def test_rtsp_url_validation(self):
        """Verifies RTSP URL syntax validation and reachability checks."""
        # Valid URLs
        valid, msg = validate_rtsp_url("rtsp://admin:pass@192.168.1.100:554/Streaming/Channels/101")
        self.assertTrue(valid)

        valid, msg = validate_rtsp_url("rtsp://10.0.0.50/live")
        self.assertTrue(valid)

        valid, msg = validate_rtsp_url("test://camera_1")
        self.assertTrue(valid)

        # Invalid URLs
        invalid, msg = validate_rtsp_url("")
        self.assertFalse(invalid)

        invalid, msg = validate_rtsp_url("http://192.168.1.100/video.mjpg")
        self.assertFalse(invalid)

        invalid, msg = validate_rtsp_url("rtsp:///invalid/no/host")
        self.assertFalse(invalid)

    def test_credential_masking(self):
        """Verifies sensitive passwords in RTSP URLs are strictly scrubbed."""
        masked = mask_rtsp_url("rtsp://admin:SuperSecretPassword123@192.168.1.100:554/live")
        self.assertNotIn("SuperSecretPassword123", masked)
        self.assertIn("******", masked)

    def test_exponential_backoff_calculation(self):
        """Verifies exponential backoff delay progression and cap."""
        worker = RTSPStreamWorker(
            channel_id="ch_test_backoff",
            rtsp_url="test://dummy",
            reconnect_interval_sec=2.0,
        )
        self.assertEqual(worker.initial_backoff_sec, 1.0)
        self.assertEqual(worker.current_backoff, 1.0)

        # Simulate consecutive reconnect failures
        delays = []
        for _ in range(5):
            worker.current_backoff = min(worker.max_backoff_sec, worker.current_backoff * worker.backoff_multiplier)
            delays.append(worker.current_backoff)

        self.assertEqual(delays, [2.0, 4.0, 8.0, 16.0, 30.0])
        # Verify capped at max_backoff_sec
        worker.current_backoff = min(worker.max_backoff_sec, worker.current_backoff * worker.backoff_multiplier)
        self.assertEqual(worker.current_backoff, 30.0)

    def test_frozen_frame_detection_and_recovery(self):
        """Verifies that stationary/frozen frames trigger FROZEN state and recover when content changes."""
        worker = RTSPStreamWorker(
            channel_id="ch_test_frozen",
            rtsp_url="test://frozen",
        )
        worker.telemetry.state = StreamState.ONLINE
        worker.frozen_threshold_sec = 0.5  # 500ms threshold for test

        frozen_frame = np.full((120, 160, 3), 100, dtype=np.uint8)
        now = time.time()

        # 1. Initial frame sets timestamp
        is_frozen = worker._check_frozen_frame(frozen_frame, now)
        self.assertFalse(is_frozen)
        self.assertFalse(worker.telemetry.is_frozen)

        # 2. Frame within threshold -> not frozen yet
        is_frozen = worker._check_frozen_frame(frozen_frame, now + 0.2)
        self.assertFalse(is_frozen)

        # 3. Identical frame past threshold -> frozen!
        is_frozen = worker._check_frozen_frame(frozen_frame, now + 0.6)
        self.assertTrue(is_frozen)
        self.assertTrue(worker.telemetry.is_frozen)
        self.assertEqual(worker.telemetry.state, StreamState.FROZEN)
        self.assertEqual(worker.telemetry.frozen_frames_count, 1)

        # 4. Fresh changed frame arrives -> recovered!
        changed_frame = np.full((120, 160, 3), 200, dtype=np.uint8)
        is_frozen = worker._check_frozen_frame(changed_frame, now + 0.8)
        self.assertFalse(is_frozen)
        self.assertFalse(worker.telemetry.is_frozen)
        self.assertEqual(worker.telemetry.state, StreamState.ONLINE)

    def test_dynamic_stream_profile_switching(self):
        """Verifies switching from MAIN to SUB stream profile seamlessly."""
        worker = RTSPStreamWorker(
            channel_id="ch_switch_test",
            rtsp_url="test://main_stream",
        )
        self.assertEqual(worker.telemetry.current_profile, "MAIN")

        events_captured = []
        bus.subscribe("stream.switched", lambda ev: events_captured.append(ev.data if hasattr(ev, "data") else ev))

        # Switch to SUB stream
        success = worker.switch_stream_profile("SUB", "test://sub_stream")
        self.assertTrue(success)
        self.assertEqual(worker.telemetry.current_profile, "SUB")
        self.assertTrue(worker._switch_profile_event.is_set())
        self.assertEqual(worker._pending_switch_url, "test://sub_stream")

        self.assertEqual(len(events_captured), 1)
        self.assertEqual(events_captured[0]["from_profile"], "MAIN")
        self.assertEqual(events_captured[0]["to_profile"], "SUB")

    def test_camera_connection_tester(self):
        """Verifies camera connection diagnostic tester."""
        # Simulated test
        with patch("socket.create_connection") as mock_conn:
            mock_conn.return_value.__enter__.return_value = MagicMock()
            report = CameraConnectionTester.test_camera("192.168.1.50", rtsp_port=554, onvif_port=0)
            self.assertTrue(report.success)
            self.assertTrue(report.rtsp_reachable)
            self.assertGreaterEqual(report.latency_ms, 0.0)

    def test_stream_diagnostics_report_and_export(self):
        """Verifies comprehensive diagnostics generation and export with credential scrubbing."""
        worker = self.stream_manager.start_stream(
            channel_id="ch_diag_1",
            rtsp_url="test://camera_diag",
            channel_name="Gate Cam",
            is_test_stream=True,
        )
        time.sleep(0.1)

        # Generate diagnostics
        report = self.stream_manager.get_diagnostics_report("ch_diag_1")
        self.assertIn("channels", report)
        self.assertIn("ch_diag_1", report["channels"])
        ch_info = report["channels"]["ch_diag_1"]
        self.assertEqual(ch_info["channel_name"], "Gate Cam")
        self.assertIn("fps_measured", ch_info)
        self.assertIn("queue_occupancy", ch_info)
        self.assertIn("frame_drop_rate_pct", ch_info)

        # Export diagnostics log
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            exported_file = self.stream_manager.export_diagnostics_log(tmp_path)
            self.assertTrue(os.path.exists(exported_file))
            with open(exported_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("total_channels_registered", data)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
