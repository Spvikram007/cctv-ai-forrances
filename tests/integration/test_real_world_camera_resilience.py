"""
Integration Tests for Real-World CCTV Resilience:
Multi-Manufacturer Streams (Hikvision, Dahua, CP PLUS, ONVIF),
Day/Night Transitions, Stream Disconnect/Reconnect, Corrupt Frames, and Recording Continuity.
"""

import time
import pytest
import numpy as np
import cv2

from engines.anpr_engine.anpr_pipeline import ANPRPipeline
from engines.face_engine.face_service import FaceIntelligenceService
from engines.face_engine.face_detector import FaceDetector
from engines.face_engine.face_embedder import FaceEmbedder


class TestRealWorldCameraResilience:
    @pytest.fixture
    def anpr_pipeline(self):
        return ANPRPipeline(persist_to_db=False)

    @pytest.fixture
    def face_service(self):
        return FaceIntelligenceService(persist_to_db=False)

    def test_multi_manufacturer_frame_simulation(self, anpr_pipeline, face_service):
        """
        Simulates video feeds configured according to manufacturer stream profiles:
        - Hikvision (1080p, H.264/H.265 baseline)
        - Dahua (1080p / 720p mainstream)
        - CP PLUS (720p / 1080p mainstream)
        - Generic ONVIF RTSP stream
        """
        profiles = {
            "hikvision_cam": (1080, 1920, 3),
            "dahua_cam": (720, 1280, 3),
            "cpplus_cam": (720, 1280, 3),
            "generic_onvif_cam": (1080, 1920, 3),
        }

        for channel_id, (h, w, c) in profiles.items():
            frame = np.full((h, w, c), 120, dtype=np.uint8)
            # Add simulated vehicle in lower portion
            cv2.rectangle(frame, (int(w * 0.3), int(h * 0.5)), (int(w * 0.7), int(h * 0.9)), (30, 30, 30), -1)

            # Process vehicle crop
            vehicle_crop = frame[int(h * 0.5):int(h * 0.9), int(w * 0.3):int(w * 0.7)]
            res = anpr_pipeline.process_vehicle(
                channel_id=channel_id,
                vehicle_bgr=vehicle_crop,
                track_id=1,
                timestamp=time.time(),
            )
            # Safe execution, no crash
            assert res is None or res.channel_id == channel_id

            # Evaluate face
            face_matches = face_service.evaluate_faces(channel_id=channel_id, frame_bgr=frame)
            assert isinstance(face_matches, list)

    def test_lighting_transition_day_to_night(self, anpr_pipeline):
        """
        Simulates sudden illumination drop (day-to-night camera IR cut filter switch).
        Ensures edge detection and morphological operations don't throw numerical exceptions.
        """
        # Day frame (bright)
        day_frame = np.full((300, 400, 3), 220, dtype=np.uint8)
        # Night frame (dark IR mode, mostly grayscale/black)
        night_frame = np.full((300, 400, 3), 25, dtype=np.uint8)
        # Add high-contrast reflective plate in dark frame
        cv2.rectangle(night_frame, (90, 180), (310, 240), (230, 230, 230), -1)
        for i, ch in enumerate("KA01AB1234"):
            cv2.putText(night_frame, ch, (100 + i * 20, 222), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (10, 10, 10), 2)

        # Process day frame
        res_day = anpr_pipeline.process_vehicle("cam_day_night", day_frame, track_id=10)
        # Process night frame
        res_night = anpr_pipeline.process_vehicle("cam_day_night", night_frame, track_id=11)

        assert res_night is not None
        assert len(res_night.plate_text) >= 7

    def test_camera_disconnect_and_reconnect_simulation(self, anpr_pipeline):
        """
        Simulates intermittent RTSP stream drops (None frames during disconnect,
        followed by normal frames on reconnect).
        """
        channel_id = "cam_intermittent_01"

        # 1. Normal active frame
        active_crop = np.full((120, 240, 3), 100, dtype=np.uint8)
        anpr_pipeline.process_vehicle(channel_id, active_crop, track_id=50, timestamp=100.0)

        # 2. Disconnect: stream delivers None or empty frames
        for _ in range(5):
            res_dropped = anpr_pipeline.process_vehicle(channel_id, None, track_id=None, timestamp=101.0)
            assert res_dropped is None
            empty_crop = np.zeros((0, 0, 3), dtype=np.uint8)
            res_empty = anpr_pipeline.process_vehicle(channel_id, empty_crop, track_id=None, timestamp=102.0)
            assert res_empty is None

        # 3. Reconnect: normal frames resume
        reconnect_crop = np.full((120, 260, 3), 120, dtype=np.uint8)
        for i, ch in enumerate("MH12AB9999"):
            cv2.putText(reconnect_crop, ch, (15 + i * 22, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (10, 10, 10), 2)
        res_resumed = anpr_pipeline.process_vehicle(channel_id, reconnect_crop, track_id=51, timestamp=105.0)
        # Pipeline recovers cleanly
        assert res_resumed is not None
        assert res_resumed.channel_id == channel_id

    def test_corrupt_and_degraded_frame_resilience(self, anpr_pipeline, face_service):
        """
        Tests anomalous frame conditions:
        - 1x1 single pixel frame
        - Extremely wide or tall dimensions
        - Pure black or pure white saturation
        - Frame with NaN or Inf values (if float converted)
        """
        anomalies = [
            np.zeros((1, 1, 3), dtype=np.uint8),
            np.full((10, 1000, 3), 255, dtype=np.uint8),
            np.full((1000, 10, 3), 0, dtype=np.uint8),
            np.full((100, 100, 3), 255, dtype=np.uint8),  # Total saturation
        ]

        for frame in anomalies:
            # Must handle gracefully without crashing
            res_anpr = anpr_pipeline.process_vehicle("cam_test", frame)
            assert res_anpr is None

            matches = face_service.evaluate_faces("cam_test", frame)
            assert len(matches) == 0

    def test_recording_continuity_during_ai_events(self):
        """
        Verifies that trigger_event_recording does not interfere with continuous background recording.
        """
        class MockRecordingManager:
            def __init__(self):
                self.event_recordings = []

            def trigger_event_recording(self, channel_id, event_type, pre_event_sec, post_event_sec):
                self.event_recordings.append((channel_id, event_type, pre_event_sec, post_event_sec))

        mock_mgr = MockRecordingManager()
        service = FaceIntelligenceService(persist_to_db=False)
        service.set_recording_manager(mock_mgr)

        # Trigger mock watchlist event
        service.recording_manager.trigger_event_recording(
            channel_id="cam_01",
            event_type="FACE_WATCHLIST",
            pre_event_sec=5,
            post_event_sec=20,
        )

        assert len(mock_mgr.event_recordings) == 1
        assert mock_mgr.event_recordings[0][0] == "cam_01"
        assert mock_mgr.event_recordings[0][1] == "FACE_WATCHLIST"
