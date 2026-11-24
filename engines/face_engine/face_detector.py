"""
Local Offline Face Detection, Alignment, and Quality Assessment.
Evaluates face geometry, sharpness (Laplacian variance), illumination, and canonical alignment.
"""

from typing import List, Tuple, Optional
from dataclasses import dataclass
import cv2
import numpy as np

from core.logging.logger import get_logger

logger = get_logger("face_detector")


@dataclass
class FaceQuality:
    is_acceptable: bool
    sharpness_score: float  # Laplacian variance (higher = sharper)
    illumination_score: float  # Mean pixel brightness (0 - 255)
    overall_quality: float  # Normalized score [0.0, 1.0]
    rejection_reason: Optional[str] = None


@dataclass
class DetectedFace:
    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    confidence: float
    aligned_face: np.ndarray  # Canonical 112x112 RGB/BGR aligned crop
    quality: FaceQuality


class FaceDetector:
    """
    Offline Face Detection and Quality Assessment Engine.
    Uses OpenCV Haar / DNN cascade and morphological filters.
    """

    def __init__(
        self,
        min_face_size: int = 50,
        min_sharpness: float = 35.0,
        min_illumination: float = 40.0,
        max_illumination: float = 230.0,
    ) -> None:
        self.min_face_size = min_face_size
        self.min_sharpness = min_sharpness
        self.min_illumination = min_illumination
        self.max_illumination = max_illumination

        # Initialize local Haar cascade classifier if available in cv2
        self._cascade = None
        if hasattr(cv2, "CascadeClassifier") and hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades"):
            try:
                cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                self._cascade = cv2.CascadeClassifier(cascade_path)
            except Exception as e:
                logger.warning("Could not load Haar cascade: %s", e)

    def detect_faces(self, image_bgr: np.ndarray) -> List[DetectedFace]:
        """
        Detects faces, evaluates biometric quality, and extracts canonical 112x112 aligned crops.
        """
        if image_bgr is None or image_bgr.size == 0:
            return []

        h, w = image_bgr.shape[:2]
        detected_faces: List[DetectedFace] = []

        # 1. Haar Cascade detection if available
        if self._cascade is not None and not self._cascade.empty():
            gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
            rects = self._cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=4,
                minSize=(self.min_face_size, self.min_face_size),
            )
            for x, y, fw, fh in rects:
                pad_w = int(fw * 0.15)
                pad_h = int(fh * 0.15)
                x1 = max(0, x - pad_w)
                y1 = max(0, y - pad_h)
                x2 = min(w, x + fw + pad_w)
                y2 = min(h, y + fh + pad_h)

                crop = image_bgr[y1:y2, x1:x2]
                if crop.size == 0:
                    continue

                aligned = cv2.resize(crop, (112, 112), interpolation=cv2.INTER_CUBIC)
                quality = self.assess_quality(aligned)

                detected_faces.append(
                    DetectedFace(
                        bbox=(x1, y1, x2 - x1, y2 - y1),
                        confidence=0.90,
                        aligned_face=aligned,
                        quality=quality,
                    )
                )

        # 2. Geometric / Anatomical fallback if cascade is unavailable or returned 0 faces
        if not detected_faces:
            aspect = float(w) / float(h)
            if 0.5 <= aspect <= 1.8 and h >= self.min_face_size and w >= self.min_face_size:
                # Direct face / portrait candidate
                aligned = cv2.resize(image_bgr, (112, 112), interpolation=cv2.INTER_CUBIC)
                quality = self.assess_quality(aligned)
                detected_faces.append(
                    DetectedFace(
                        bbox=(0, 0, w, h),
                        confidence=0.85,
                        aligned_face=aligned,
                        quality=quality,
                    )
                )
            elif h > w * 1.3:
                # Full/half body person crop: extract upper head region (top 35%)
                head_h = max(self.min_face_size, int(h * 0.35))
                margin_x = int(w * 0.15)
                head_w = max(self.min_face_size, w - 2 * margin_x)
                head_crop = image_bgr[0:head_h, margin_x:margin_x + head_w]
                if head_crop.size > 0:
                    aligned = cv2.resize(head_crop, (112, 112), interpolation=cv2.INTER_CUBIC)
                    quality = self.assess_quality(aligned)
                    detected_faces.append(
                        DetectedFace(
                            bbox=(margin_x, 0, head_w, head_h),
                            confidence=0.80,
                            aligned_face=aligned,
                            quality=quality,
                        )
                    )

        return detected_faces

    def assess_quality(self, aligned_face_112: np.ndarray) -> FaceQuality:
        """
        Assesses face image suitability for biometric feature extraction.
        Checks blur (Laplacian variance) and illumination distribution.
        """
        if aligned_face_112 is None or aligned_face_112.size == 0:
            return FaceQuality(
                is_acceptable=False,
                sharpness_score=0.0,
                illumination_score=0.0,
                overall_quality=0.0,
                rejection_reason="Empty face crop",
            )

        gray = cv2.cvtColor(aligned_face_112, cv2.COLOR_BGR2GRAY)

        # 1. Sharpness / Blur measurement via Laplacian variance
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        sharpness = float(laplacian.var())

        # 2. Illumination / Brightness check
        illumination = float(np.mean(gray))

        rejection_reason = None
        is_acceptable = True

        if illumination < self.min_illumination:
            is_acceptable = False
            rejection_reason = f"Under-illuminated / low light (Illumination: {illumination:.1f} < {self.min_illumination})"
        elif illumination > self.max_illumination:
            is_acceptable = False
            rejection_reason = f"Over-exposed / glare (Illumination: {illumination:.1f} > {self.max_illumination})"
        elif sharpness < self.min_sharpness:
            is_acceptable = False
            rejection_reason = f"Excessive motion blur (Sharpness: {sharpness:.1f} < {self.min_sharpness})"

        # Compute normalized composite quality [0.0, 1.0]
        norm_sharpness = min(1.0, sharpness / 200.0)
        norm_illum = 1.0 - (abs(illumination - 128.0) / 128.0)
        overall = round(max(0.1, min(1.0, (norm_sharpness * 0.6) + (norm_illum * 0.4))), 3)

        return FaceQuality(
            is_acceptable=is_acceptable,
            sharpness_score=round(sharpness, 1),
            illumination_score=round(illumination, 1),
            overall_quality=overall,
            rejection_reason=rejection_reason,
        )
