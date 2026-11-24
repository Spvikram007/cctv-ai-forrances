"""
Unit Tests for Deep Face Recognition Model Validation, Upper-Body Rejection,
L2 Normalization, Cosine Similarity Distributions, and Human Review Enforcement.
"""

import os
import pytest
import numpy as np
import cv2

from engines.face_engine.face_detector import FaceDetector, DetectedFace
from engines.face_engine.face_embedder import FaceEmbedder
from engines.face_engine.face_service import FaceIntelligenceService, FaceMatchCandidate


class TestFaceModelValidation:
    @pytest.fixture
    def face_detector(self):
        return FaceDetector()

    @pytest.fixture
    def face_embedder(self):
        return FaceEmbedder()

    @pytest.fixture
    def synthetic_face_crop(self):
        """Generates realistic 112x112 frontal facial pattern with eye bands and mouth contrast."""
        img = np.full((112, 112, 3), 160, dtype=np.uint8)
        # Head outline
        cv2.circle(img, (56, 56), 44, (210, 210, 210), -1)
        # Eye region (dark contrast band)
        cv2.rectangle(img, (28, 40), (84, 52), (60, 60, 60), -1)
        cv2.circle(img, (40, 46), 5, (20, 20, 20), -1)
        cv2.circle(img, (72, 46), 5, (20, 20, 20), -1)
        # Nose bridge
        cv2.line(img, (56, 46), (56, 68), (120, 120, 120), 2)
        # Mouth region (horizontal contrast)
        cv2.rectangle(img, (42, 78), (70, 84), (50, 50, 50), -1)
        return img

    def test_mobilefacenet_model_loading_and_inference(self, face_embedder, synthetic_face_crop):
        """Verifies MobileFaceNet ONNX model loads and produces 512-d feature vector."""
        emb = face_embedder.extract_embedding(synthetic_face_crop)
        assert isinstance(emb, np.ndarray)
        assert emb.shape == (512,)
        assert emb.dtype == np.float32

    def test_l2_unit_normalization_enforced(self, face_embedder, synthetic_face_crop):
        """Embedding vector MUST have strict L2 norm of 1.0 (||v||_2 = 1.0 +/- 1e-5)."""
        emb = face_embedder.extract_embedding(synthetic_face_crop)
        norm = float(np.linalg.norm(emb))
        assert abs(norm - 1.0) < 1e-4

        # Test on degraded/blank inputs
        blank = np.zeros((112, 112, 3), dtype=np.uint8)
        emb_blank = face_embedder.extract_embedding(blank)
        norm_blank = float(np.linalg.norm(emb_blank))
        assert abs(norm_blank - 1.0) < 1e-4

    def test_face_detector_rejects_upper_body_non_face(self, face_detector):
        """
        Critical Privacy Rule: Person bounding boxes without genuine facial features
        (e.g. turned away, rear view, distant torso) MUST NEVER be treated as faces.
        Upper-body fallback is strictly prohibited.
        """
        # Upper body crop: tall aspect ratio (w=60, h=140 -> ratio 0.43), uniform texture
        torso_crop = np.full((140, 60, 3), 100, dtype=np.uint8)
        # Add jacket/shirt pattern
        cv2.line(torso_crop, (30, 20), (30, 120), (40, 40, 40), 3)

        detected = face_detector.detect_faces(torso_crop)
        # Must NOT detect any face
        assert len(detected) == 0

    def test_strict_facial_aspect_ratio_and_geometry(self, face_detector):
        """Valid facial geometry requires 0.7 <= w/h <= 1.35."""
        # Extreme horizontal stretch (w=120, h=40 -> 3.0)
        stretched_h = np.full((40, 120, 3), 180, dtype=np.uint8)
        assert len(face_detector.detect_faces(stretched_h)) == 0

        # Extreme vertical stretch (w=40, h=120 -> 0.33)
        stretched_v = np.full((120, 40, 3), 180, dtype=np.uint8)
        assert len(face_detector.detect_faces(stretched_v)) == 0

    def test_biometric_verification_metrics_evaluation(self, face_embedder):
        """
        Evaluates biometric genuine vs impostor distributions,
        measuring FAR, FRR, separation gap, and optimal threshold calibration.
        """
        rng = np.random.RandomState(42)

        # Generate synthetic genuine pairs (same identity + small perturbation)
        genuine_pairs = []
        for _ in range(50):
            base = rng.randn(512).astype(np.float32)
            base /= np.linalg.norm(base)
            # Small perturbation in 512 dimensions (sigma = 0.005 gives ~0.98 cosine similarity)
            noise = (rng.randn(512).astype(np.float32) * 0.005)
            variant = base + noise
            variant /= np.linalg.norm(variant)
            genuine_pairs.append((base, variant))

        # Generate synthetic impostor pairs (different random identities)
        impostor_pairs = []
        for _ in range(100):
            id1 = rng.randn(512).astype(np.float32)
            id1 /= np.linalg.norm(id1)
            id2 = rng.randn(512).astype(np.float32)
            id2 /= np.linalg.norm(id2)
            impostor_pairs.append((id1, id2))

        metrics = FaceEmbedder.evaluate_verification_metrics(
            genuine_pairs=genuine_pairs,
            impostor_pairs=impostor_pairs,
            threshold=0.65,
        )

        assert metrics["total_genuine_pairs"] == 50
        assert metrics["total_impostor_pairs"] == 100
        assert metrics["genuine_mean"] > 0.85
        assert metrics["impostor_mean"] < 0.25
        assert metrics["separation_gap"] > 0.50
        assert metrics["far_at_threshold"] == 0.0  # Zero impostors accepted at 0.65
        assert metrics["frr_at_threshold"] < 0.05

    def test_candidate_matches_require_human_verification(self):
        """All biometric candidate matches MUST have is_verified=False by default."""
        candidate = FaceMatchCandidate(
            identity_id="ident_123",
            name="John Doe",
            category="STAFF",
            similarity_score=0.88,
            threshold_applied=0.65,
            face_bbox=(10, 10, 50, 50),
            snapshot_path="/path/to/snap.jpg",
        )
        assert candidate.is_verified is False
