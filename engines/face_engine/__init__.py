"""
Authorized Face Intelligence Engine Package.
"""

from engines.face_engine.face_detector import FaceDetector, DetectedFace, FaceQuality
from engines.face_engine.face_embedder import FaceEmbedder
from engines.face_engine.face_vault import FaceBiometricVault
from engines.face_engine.face_service import (
    FaceIntelligenceService,
    FaceMatchCandidate,
    face_intelligence_service,
)

__all__ = [
    "FaceDetector",
    "DetectedFace",
    "FaceQuality",
    "FaceEmbedder",
    "FaceBiometricVault",
    "FaceIntelligenceService",
    "FaceMatchCandidate",
    "face_intelligence_service",
]
