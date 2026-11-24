"""
Integration Tests for Biometric RBAC Access Control, Key Rotation Workflows,
Retention Policy Enforcement, and Audit Log Completeness.
"""

import os
import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
import numpy as np
import cv2

from database.database_manager import db_manager
from database.models.biometrics import (
    FaceIdentity,
    FaceTemplate,
    FaceEnrollment,
    FaceMatchEvent,
    BiometricAuditLog,
)
from engines.face_engine.face_service import FaceIntelligenceService
from engines.face_engine.face_vault import FaceBiometricVault


class TestBiometricRetentionAndRBAC:
    @pytest.fixture(autouse=True)
    def setup_biometric_env(self, tmp_path, monkeypatch):
        vault_dir = tmp_path / "rbac_vault"
        monkeypatch.setattr(FaceBiometricVault, "VAULT_DIR", vault_dir)
        monkeypatch.setattr(FaceBiometricVault, "KEY_FILE", vault_dir / "master.key")
        monkeypatch.setattr(FaceBiometricVault, "KEYSTORE_FILE", vault_dir / "keystore.dat")
        FaceBiometricVault._initialized = False
        FaceBiometricVault._key_cache.clear()
        FaceBiometricVault.initialize_vault()

    @pytest.fixture
    def face_service(self, tmp_path):
        service = FaceIntelligenceService(
            snapshots_dir=str(tmp_path / "snaps"),
            persist_to_db=True,
        )
        return service

    @pytest.fixture
    def sample_face_image(self):
        """Generates acceptable synthetic face image."""
        img = np.full((112, 112, 3), 160, dtype=np.uint8)
        cv2.circle(img, (56, 56), 44, (210, 210, 210), -1)
        cv2.rectangle(img, (28, 40), (84, 52), (60, 60, 60), -1)
        cv2.circle(img, (40, 46), 5, (20, 20, 20), -1)
        cv2.circle(img, (72, 46), 5, (20, 20, 20), -1)
        cv2.rectangle(img, (42, 78), (70, 84), (50, 50, 50), -1)
        return img

    def test_rbac_access_control_denials_and_grants(self, face_service, sample_face_image):
        """Verifies RBAC enforcement across VIEWER, AUDITOR, SECURITY_OPERATOR, and ADMIN."""
        # 1. VIEWER cannot enroll
        ok, msg = face_service.enroll_identity(
            name="Denied Person",
            identity_code="ID_DENIED_01",
            category="STAFF",
            face_image_bgr=sample_face_image,
            user_role="VIEWER",
        )
        assert ok is False
        assert "RBAC access denied" in msg

        # 2. VIEWER cannot rotate keys
        ok_rot, msg_rot = face_service.rotate_biometric_keys(user_role="VIEWER")
        assert ok_rot is False
        assert "RBAC access denied" in msg_rot

        # 3. VIEWER cannot purge retention
        res = face_service.enforce_retention_policy(user_role="VIEWER")
        assert res.get("error") == -1

        # 4. SECURITY_OPERATOR can enroll
        code_oper = f"ID_STAFF_{uuid.uuid4().hex[:8]}"
        ok_oper, ident_id = face_service.enroll_identity(
            name="Authorized Staff",
            identity_code=code_oper,
            category="STAFF",
            face_image_bgr=sample_face_image,
            user_role="SECURITY_OPERATOR",
            enrolled_by_user_id="operator_01",
        )
        assert ok_oper is True
        assert ident_id is not None

        # 5. SECURITY_OPERATOR cannot rotate keys (ADMIN only)
        ok_rot2, _ = face_service.rotate_biometric_keys(user_role="SECURITY_OPERATOR")
        assert ok_rot2 is False

    def test_key_rotation_service_workflow(self, face_service, sample_face_image):
        """Tests end-to-end master key rotation across stored templates in the database."""
        # Enroll an identity under current key v1
        code_rot = f"ID_KEYROT_{uuid.uuid4().hex[:8]}"
        ok, ident_id = face_service.enroll_identity(
            name="Key Rotation Test",
            identity_code=code_rot,
            category="STAFF",
            face_image_bgr=sample_face_image,
            user_role="ADMIN",
        )
        assert ok is True

        # Check template starts with v1
        with db_manager.get_session() as session:
            tmpl = session.query(FaceTemplate).filter_by(identity_id=ident_id).first()
            assert tmpl.encrypted_template.startswith("v1:")

        # Rotate key as ADMIN
        success, msg = face_service.rotate_biometric_keys(user_role="ADMIN", user_id="admin_01")
        assert success is True
        assert "Successfully rotated key" in msg

        # Verify template in DB was re-encrypted with v2
        with db_manager.get_session() as session:
            tmpl_updated = session.query(FaceTemplate).filter_by(identity_id=ident_id).first()
            assert tmpl_updated.encrypted_template.startswith("v2:")

            # Audit log was created
            audit = session.query(BiometricAuditLog).filter_by(action="ROTATE_MASTER_KEY").first()
            assert audit is not None
            details = json.loads(audit.details_json)
            assert details["key_version"] == 2

    def test_retention_policy_enforcement(self, face_service, sample_face_image, tmp_path):
        """Verifies expiration deactivation, old match event deletion, and snapshot removal."""
        now_dt = datetime.now(timezone.utc)

        # 1. Enroll identity with valid_until in the past (expired)
        past_dt = now_dt - timedelta(days=5)
        code_exp = f"ID_EXP_{uuid.uuid4().hex[:8]}"
        ok, ident_id = face_service.enroll_identity(
            name="Expired Identity",
            identity_code=code_exp,
            category="VISITOR",
            face_image_bgr=sample_face_image,
            valid_until=past_dt,
            user_role="ADMIN",
        )
        assert ok is True

        # 2. Create a dummy old snapshot and match event older than 30 days
        snap_file = tmp_path / "old_face_snap.jpg"
        cv2.imwrite(str(snap_file), sample_face_image)
        old_time = now_dt - timedelta(days=45)

        with db_manager.get_session() as session:
            old_ev = FaceMatchEvent(
                channel_id="cam_01",
                identity_id=ident_id,
                candidate_name="Expired Identity",
                category="VISITOR",
                similarity_score=0.88,
                threshold_applied=0.65,
                snapshot_path=str(snap_file),
                face_bbox_json="[10, 10, 50, 50]",
                timestamp=old_time,
            )
            session.add(old_ev)
            session.commit()

        assert snap_file.exists()

        # 3. Enforce retention policy (30 days)
        counts = face_service.enforce_retention_policy(
            retention_days=30,
            purge_expired_enrollments=True,
            user_role="ADMIN",
        )

        assert counts["expired_enrollments_deactivated"] >= 1
        assert counts["match_events_purged"] >= 1
        assert counts["snapshots_deleted"] >= 1
        # Snapshot was deleted from disk
        assert not snap_file.exists()

        # Identity status in DB is inactive
        with db_manager.get_session() as session:
            ident = session.query(FaceIdentity).filter_by(id=ident_id).first()
            assert ident.is_active is False
            tmpl = session.query(FaceTemplate).filter_by(identity_id=ident_id).first()
            assert tmpl.is_revoked is True
            assert tmpl.revocation_reason == "RETENTION_POLICY_EXPIRED"
