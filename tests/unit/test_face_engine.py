"""
Unit Tests for Face Intelligence Engine (Face Detection, Alignment, Quality Assessment,
512-D L2-Normalized Feature Extraction, AES-256-GCM Vault, Enrollment, and Revocation).
"""

import os
import time
import pytest
import numpy as np
import cv2

from engines.face_engine.face_detector import FaceDetector, FaceQuality, DetectedFace
from engines.face_engine.face_embedder import FaceEmbedder
from engines.face_engine.face_vault import FaceBiometricVault
from engines.face_engine.face_service import FaceIntelligenceService


@pytest.fixture
def face_detector():
    return FaceDetector(min_face_size=30, min_sharpness=20.0, min_illumination=30.0, max_illumination=240.0)


@pytest.fixture
def face_embedder():
    return FaceEmbedder()


@pytest.fixture
def biometric_vault():
    return FaceBiometricVault()


@pytest.fixture
def sample_sharp_face():
    """Generates a synthetic high-contrast sharp facial portrait image."""
    img = np.full((120, 120, 3), 160, dtype=np.uint8)
    # Head contour
    cv2.circle(img, (60, 60), 50, (200, 200, 200), -1)
    # Eyes
    cv2.circle(img, (45, 45), 8, (20, 20, 20), -1)
    cv2.circle(img, (75, 45), 8, (20, 20, 20), -1)
    # Eyebrows
    cv2.line(img, (35, 35), (55, 35), (30, 30, 30), 2)
    cv2.line(img, (65, 35), (85, 35), (30, 30, 30), 2)
    # Nose
    cv2.line(img, (60, 48), (60, 68), (40, 40, 40), 2)
    # Mouth
    cv2.ellipse(img, (60, 85), (20, 10), 0, 0, 180, (20, 20, 20), 3)
    return img


@pytest.fixture
def sample_blurry_face(sample_sharp_face):
    """Generates an excessively blurred version of the face."""
    return cv2.GaussianBlur(sample_sharp_face, (25, 25), 10.0)


class TestFaceDetectorAndQuality:
    def test_detect_faces_empty(self, face_detector):
        assert face_detector.detect_faces(None) == []
        assert face_detector.detect_faces(np.zeros((0, 0, 3), dtype=np.uint8)) == []

    def test_detect_faces_portrait(self, face_detector, sample_sharp_face):
        faces = face_detector.detect_faces(sample_sharp_face)
        assert len(faces) > 0
        best = faces[0]
        assert isinstance(best, DetectedFace)
        assert best.aligned_face.shape == (112, 112, 3)
        assert best.quality.is_acceptable is True
        assert best.quality.overall_quality > 0.2

    def test_quality_sharpness_rejection(self, face_detector, sample_blurry_face):
        quality = face_detector.assess_quality(sample_blurry_face)
        assert quality.is_acceptable is False or quality.sharpness_score < 30.0

    def test_quality_illumination_under_and_over_exposure(self, face_detector):
        # Under-exposed (pitch black)
        dark_img = np.zeros((112, 112, 3), dtype=np.uint8)
        dark_q = face_detector.assess_quality(dark_img)
        assert dark_q.is_acceptable is False
        assert "low light" in (dark_q.rejection_reason or "").lower()

        # Over-exposed (pure white)
        bright_img = np.full((112, 112, 3), 255, dtype=np.uint8)
        bright_q = face_detector.assess_quality(bright_img)
        assert bright_q.is_acceptable is False
        assert "glare" in (bright_q.rejection_reason or "").lower() or "over-exposed" in (bright_q.rejection_reason or "").lower()


class TestFaceEmbedder:
    def test_extract_embedding_dimension_and_l2_norm(self, face_embedder, sample_sharp_face):
        aligned = cv2.resize(sample_sharp_face, (112, 112))
        emb = face_embedder.extract_embedding(aligned)

        assert isinstance(emb, np.ndarray)
        assert emb.shape == (FaceEmbedder.VECTOR_DIM,)
        assert emb.dtype == np.float32

        # L2-norm must strictly equal 1.0 (unit vector)
        norm = np.linalg.norm(emb)
        assert abs(norm - 1.0) < 1e-4

    def test_cosine_similarity(self, face_embedder, sample_sharp_face):
        aligned = cv2.resize(sample_sharp_face, (112, 112))
        emb1 = face_embedder.extract_embedding(aligned)
        emb2 = face_embedder.extract_embedding(aligned)

        # Same face -> similarity should be ~1.0
        sim_same = face_embedder.compute_similarity(emb1, emb2)
        assert abs(sim_same - 1.0) < 1e-4

        # Inverted image face -> substantially lower similarity
        inverted = cv2.bitwise_not(aligned)
        emb_diff = face_embedder.extract_embedding(inverted)
        sim_diff = face_embedder.compute_similarity(emb1, emb_diff)
        assert sim_diff < 0.85


class TestFaceBiometricVault:
    def test_vault_aes_gcm_round_trip(self, biometric_vault):
        # Generate random 512-dim unit vector
        raw_vec = np.random.randn(512).astype(np.float32)
        raw_vec /= np.linalg.norm(raw_vec)

        # Encrypt
        encrypted_hex = biometric_vault.encrypt_template(raw_vec)
        assert isinstance(encrypted_hex, str)
        assert len(encrypted_hex) > 64

        # Decrypt
        decrypted_vec = biometric_vault.decrypt_template(encrypted_hex)
        assert decrypted_vec.shape == (512,)
        np.testing.assert_allclose(raw_vec, decrypted_vec, atol=1e-5)

    def test_vault_tamper_detection(self, biometric_vault):
        raw_vec = np.ones(512, dtype=np.float32) / np.sqrt(512)
        encrypted_hex = biometric_vault.encrypt_template(raw_vec)

        # Tamper with the ciphertext (flip a char)
        tampered_hex = ("0" if encrypted_hex[0] != "0" else "1") + encrypted_hex[1:]
        with pytest.raises(Exception):
            biometric_vault.decrypt_template(tampered_hex)


class TestFaceIntelligenceService:
    def test_authorized_enrollment_and_candidate_matching(self, sample_sharp_face):
        service = FaceIntelligenceService()
        unique_suffix = int(time.time() * 1000) % 100000

        # 1. Enroll authorized identity
        person_name = f"Authorized Specialist Alice {unique_suffix}"
        person_code = f"SPEC-{unique_suffix}"
        success, identity_id = service.enroll_identity(
            name=person_name,
            identity_code=person_code,
            category="AUTHORIZED_STAFF",
            department="Operations",
            face_image_bgr=sample_sharp_face,
            enrolled_by_user_id="admin_01",
            authorization_ref="CONSENT-FORM-001",
        )
        assert success is True
        assert identity_id is not None

        # 2. Match against identical image -> candidate match above threshold
        matches = service.evaluate_faces(
            channel_id="cam_01",
            frame_bgr=sample_sharp_face,
            threshold=0.65,
        )

        assert len(matches) > 0
        best_match = matches[0]
        assert any(m.identity_id == identity_id or "Authorized Specialist Alice" in m.name for m in matches)
        assert best_match.similarity_score >= 0.65
        # Crucial privacy rule: similarity is NEVER proof of identity, requires human verification
        assert best_match.is_verified is False

        # 3. Identity revocation
        revoke_ok = service.revoke_identity(
            identity_id=identity_id,
            reason="Access decommissioned",
            revoked_by_user_id="admin_01",
        )
        assert revoke_ok is True

        # After revocation, evaluate_faces should no longer match this identity
        matches_after = service.evaluate_faces(
            channel_id="cam_01",
            frame_bgr=sample_sharp_face,
            threshold=0.65,
        )
        assert not any(m.identity_id == identity_id for m in matches_after)

    def test_reject_low_quality_enrollment(self, face_detector):
        service = FaceIntelligenceService()
        # Pure black image
        black_img = np.zeros((120, 120, 3), dtype=np.uint8)

        success, err_msg = service.enroll_identity(
            name="Low Quality Bob",
            identity_code="BAD-001",
            category="AUTHORIZED_STAFF",
            department="IT",
            face_image_bgr=black_img,
            enrolled_by_user_id="admin_01",
        )
        assert success is False
        assert "quality" in err_msg.lower() or "acceptable" in err_msg.lower()
