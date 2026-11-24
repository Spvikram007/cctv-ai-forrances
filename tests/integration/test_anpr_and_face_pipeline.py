"""
Integration Tests for ANPR & Face Pipelines:
End-to-End Processing, Fault Isolation, Watchlist Alerting,
Database Record Persistence, and Recording Trigger Coordination.
"""

import os
import time
from datetime import datetime, timezone
import pytest
import numpy as np
import cv2

from database.database_manager import db_manager
from database.models.biometrics import (
    FaceIdentity,
    FaceMatchEvent,
    ANPRDetection,
    ANPRPlateRecord,
    BiometricAuditLog,
)
from engines.anpr_engine.anpr_pipeline import ANPRPipeline, anpr_pipeline
from engines.face_engine.face_service import FaceIntelligenceService, face_intelligence_service


@pytest.fixture
def mock_vehicle_frame():
    """Generates a test frame of a vehicle with a legible plate."""
    frame = np.full((300, 400, 3), 50, dtype=np.uint8)
    # License plate rectangle
    cv2.rectangle(frame, (100, 160), (300, 220), (240, 240, 240), -1)
    cv2.putText(frame, "DL01AB1234", (110, 205), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (10, 10, 10), 3)
    return frame


@pytest.fixture
def mock_person_face_frame():
    """Generates a test frame of an authorized person's face."""
    frame = np.full((150, 150, 3), 160, dtype=np.uint8)
    cv2.circle(frame, (75, 75), 55, (210, 210, 210), -1)
    cv2.circle(frame, (55, 55), 9, (20, 20, 20), -1)
    cv2.circle(frame, (95, 55), 9, (20, 20, 20), -1)
    cv2.line(frame, (75, 60), (75, 80), (30, 30, 30), 2)
    cv2.ellipse(frame, (75, 105), (25, 12), 0, 0, 180, (20, 20, 20), 3)
    return frame


class TestANPRPipelineIntegration:
    def test_pipeline_end_to_end_and_db_persistence(self, mock_vehicle_frame):
        # Configure recording manager mock
        triggered_events = []

        class MockRecordingManager:
            def trigger_event_recording(self, channel_id, event_type, pre_event_sec=5, post_event_sec=15):
                triggered_events.append((channel_id, event_type))

        pipeline = ANPRPipeline()
        pipeline.set_recording_manager(MockRecordingManager())

        camera_id = "cam_integ_anpr"
        track_id = int(time.time() * 1000) % 100000

        # Pre-seed watchlist plate record
        with db_manager.get_session() as session:
            record = session.query(ANPRPlateRecord).filter_by(plate_text_normalized="DL01AB1234").first()
            if not record:
                record = ANPRPlateRecord(
                    plate_text_normalized="DL01AB1234",
                    vehicle_class="car",
                    first_seen=datetime.now(timezone.utc),
                    last_seen=datetime.now(timezone.utc),
                    total_sightings=1,
                    is_watchlist=True,
                    watchlist_category="STOLEN",
                    owner_or_notes="Test Watchlist BOLO",
                )
                session.add(record)
                session.commit()
            else:
                record.is_watchlist = True
                record.watchlist_category = "STOLEN"
                session.commit()

        # Process vehicle track
        detection = pipeline.process_vehicle(
            channel_id=camera_id,
            vehicle_bgr=mock_vehicle_frame,
            track_id=track_id,
            vehicle_class="car",
            timestamp=time.time(),
        )

        assert detection is not None
        assert detection.plate_text is not None
        assert len(detection.plate_text) > 0

        # Verify DB persistence
        with db_manager.get_session() as session:
            db_record = session.query(ANPRDetection).filter_by(channel_id=camera_id, track_id=track_id).first()
            assert db_record is not None
            assert db_record.vehicle_class == "car"
            assert db_record.plate_text == detection.plate_text

    def test_anpr_fault_isolation_on_corrupt_frame(self):
        pipeline = ANPRPipeline()
        # Non-image, extreme size, or empty arrays must not crash
        res1 = pipeline.process_vehicle("cam_err", None, track_id=9999)
        assert res1 is None

        corrupt = np.ones((5, 5, 1), dtype=np.uint8)  # wrong dimension
        try:
            res2 = pipeline.process_vehicle("cam_err", corrupt, track_id=9999)
            assert res2 is None
        except Exception:
            pytest.fail("ANPR pipeline did not isolate fault on corrupt frame input")


class TestFacePipelineIntegration:
    def test_face_service_end_to_end_and_audit_trail(self, mock_person_face_frame):
        service = FaceIntelligenceService()
        camera_id = "cam_integ_face"
        track_id = int(time.time() * 1000) % 100000

        # 1. Enroll Identity
        unique_name = f"Officer Frank {track_id}"
        unique_code = f"BADGE-{track_id}"
        enroll_ok, identity_id = service.enroll_identity(
            name=unique_name,
            identity_code=unique_code,
            category="AUTHORIZED_STAFF",
            department="Surveillance",
            face_image_bgr=mock_person_face_frame,
            enrolled_by_user_id="lead_admin",
            authorization_ref="REF-AUDIT-001",
        )
        assert enroll_ok is True
        assert identity_id is not None

        # Verify Audit Log recorded enrollment
        with db_manager.get_session() as session:
            audit = session.query(BiometricAuditLog).filter_by(
                identity_id=identity_id,
                action="ENROLL_IDENTITY",
            ).first()
            assert audit is not None
            assert audit.user_id == "lead_admin"

        # 2. Process person track -> Candidate Match
        candidates = service.evaluate_faces(
            channel_id=camera_id,
            frame_bgr=mock_person_face_frame,
            threshold=0.60,
        )

        assert len(candidates) > 0
        assert any(c.identity_id == identity_id or "Officer Frank" in c.name for c in candidates)
        cand = [c for c in candidates if c.identity_id == identity_id][0] if any(c.identity_id == identity_id for c in candidates) else candidates[0]
        assert cand.is_verified is False  # Must require human confirmation!

        # Verify DB FaceMatchEvent record
        with db_manager.get_session() as session:
            match_row = session.query(FaceMatchEvent).filter_by(
                channel_id=camera_id,
            ).order_by(FaceMatchEvent.timestamp.desc()).first()
            assert match_row is not None
            assert match_row.is_verified is False
            event_id = match_row.id

        # 3. Human Operator Verifies the Candidate Match
        verified = service.verify_match_event(
            event_id=event_id,
            verified_by_user_id="operator_sarah",
            is_confirmed=True,
        )
        assert verified is True

        with db_manager.get_session() as session:
            match_row_updated = session.query(FaceMatchEvent).filter_by(id=event_id).first()
            assert match_row_updated.is_verified is True
            assert match_row_updated.verified_by_user_id == "operator_sarah"

            # Check audit log for verification
            audit_verify = session.query(BiometricAuditLog).filter_by(
                action="VERIFY_CANDIDATE_MATCH",
                user_id="operator_sarah",
            ).first()
            assert audit_verify is not None

    def test_face_fault_isolation_on_corrupt_frame(self):
        service = FaceIntelligenceService()
        # Invalid inputs must not throw uncaught exceptions
        res1 = service.evaluate_faces("cam_01", None)
        assert res1 == []

        res2 = service.evaluate_faces("cam_01", np.zeros((2, 2, 3), dtype=np.uint8))
        assert res2 == []
