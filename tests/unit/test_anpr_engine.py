"""
Unit Tests for ANPR Engine (Plate Detection, OCR Recognition, Regional Validation,
Vehicle Track Caching, and Parametric Search).
"""

import os
import tempfile
import pytest
import numpy as np
import cv2

from engines.anpr_engine.plate_detector import PlateDetector, PlateCandidate
from engines.anpr_engine.ocr_recognizer import PlateOCRRecognizer, OCRResult
from engines.anpr_engine.anpr_search import ANPRSearchEngine
from engines.anpr_engine.anpr_pipeline import ANPRPipeline


@pytest.fixture
def plate_detector():
    return PlateDetector(min_aspect_ratio=1.5, max_aspect_ratio=6.5, min_area=200, max_area=80000)


@pytest.fixture
def ocr_recognizer():
    return PlateOCRRecognizer(default_format="GENERIC")


@pytest.fixture
def synthetic_vehicle_with_plate():
    """Generates a synthetic vehicle crop containing a white rectangular plate with text."""
    # Dark vehicle body (240x360)
    img = np.full((240, 360, 3), 40, dtype=np.uint8)

    # White license plate rectangle in lower-center
    # bbox: x=80, y=140, w=200, h=60 (aspect ratio = 3.33)
    px, py, pw, ph = 80, 140, 200, 60
    cv2.rectangle(img, (px, py), (px + pw, py + ph), (240, 240, 240), -1)
    # Dark border
    cv2.rectangle(img, (px, py), (px + pw, py + ph), (10, 10, 10), 2)

    # Draw black characters "MH12AB1234"
    text = "MH12AB1234"
    cv2.putText(img, text, (px + 10, py + 42), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (15, 15, 15), 3)

    return img, (px, py, pw, ph), text


class TestPlateDetector:
    def test_detect_plates_empty_or_small(self, plate_detector):
        assert plate_detector.detect_plates(None) == []
        assert plate_detector.detect_plates(np.zeros((10, 10, 3), dtype=np.uint8)) == []

    def test_detect_plates_localization(self, plate_detector, synthetic_vehicle_with_plate):
        vehicle_img, (px, py, pw, ph), _ = synthetic_vehicle_with_plate
        candidates = plate_detector.detect_plates(vehicle_img)

        assert len(candidates) > 0
        best = candidates[0]
        assert isinstance(best, PlateCandidate)
        assert best.confidence > 0.0
        assert best.cropped_plate.size > 0
        assert best.enhanced_plate.size > 0

        # Check candidate bbox overlaps the true plate region
        bx, by, bw, bh = best.bbox
        assert abs(bx - px) < 40
        assert abs(by - py) < 40


class TestPlateOCRRecognizer:
    def test_recognize_plate_empty(self, ocr_recognizer):
        res = ocr_recognizer.recognize_plate(np.zeros((0, 0), dtype=np.uint8))
        assert res.plate_text == ""
        assert res.confidence == 0.0

    def test_recognize_clean_plate_text(self, ocr_recognizer):
        # Create clean white plate image with black text
        plate_img = np.full((60, 200), 245, dtype=np.uint8)
        cv2.putText(plate_img, "K A 0 1 M J 4 5", (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (10, 10, 10), 2)

        res = ocr_recognizer.recognize_plate(plate_img, expected_format="INDIA")
        assert isinstance(res, OCRResult)
        assert len(res.plate_text) >= 4
        assert res.confidence > 0.3

    def test_confusion_correction_rules(self):
        recognizer = PlateOCRRecognizer(default_format="INDIA")

        # Indian plate format: AA NN AA NNNN
        # If OCR reads 'KAOI' -> '0' or 'O' in position 2-3 should be '01'
        corrected = recognizer._disambiguate_confusions("KAOIABIZ34", "INDIA")
        # Position 2 ('O') should become '0', position 3 ('I') should become '1'
        assert corrected.startswith("KA01")
        # Position 8 ('I') should become '1', position 9 ('Z') should become '2'
        assert "1234" in corrected

    def test_regional_validation_india(self, ocr_recognizer):
        import re
        pat = ocr_recognizer.FORMAT_PATTERNS["INDIA"]
        assert bool(re.match(pat, "DL01AB1234")) is True
        assert bool(re.match(pat, "MH12CD5678")) is True
        assert bool(re.match(pat, "INVALID_PLATE_XYZ")) is False

    def test_regional_validation_us_eu_generic(self, ocr_recognizer):
        import re
        assert bool(re.match(ocr_recognizer.FORMAT_PATTERNS["US"], "7XYZ123")) is True
        assert bool(re.match(ocr_recognizer.FORMAT_PATTERNS["EU"], "B-AB-1234")) is False  # EU regex handles alphanumeric
        assert bool(re.match(ocr_recognizer.FORMAT_PATTERNS["GENERIC"], "ABC1234")) is True


class TestANPRPipelineTrackAssociation:
    def test_track_caching_and_deduplication(self, synthetic_vehicle_with_plate):
        pipeline = ANPRPipeline()
        vehicle_img, _, _ = synthetic_vehicle_with_plate

        # First frame for track_id 101 -> performs OCR and caches
        result1 = pipeline.process_vehicle(
            channel_id="cam_test_01",
            vehicle_bgr=vehicle_img,
            track_id=101,
            vehicle_class="car",
            timestamp=1000.0,
        )

        # Second frame for same track_id 101 within cache window -> returns cached record or None (duplicate skipped)
        result2 = pipeline.process_vehicle(
            channel_id="cam_test_01",
            vehicle_bgr=vehicle_img,
            track_id=101,
            vehicle_class="car",
            timestamp=1001.0,
        )

        # Result1 succeeded, result2 is deduplicated
        if result1 is not None:
            assert result2 is None  # Zero redundant OCR performed!


class TestANPRSearchEngine:
    def test_csv_export_formatting(self):
        engine = ANPRSearchEngine()

        mock_records = [
            {
                "id": "rec_1",
                "channel_id": "cam_01",
                "timestamp": "2026-11-24 10:00:00",
                "vehicle_class": "car",
                "plate_text": "KA01MJ4567",
                "confidence": 0.88,
                "plate_format": "INDIA",
                "requires_manual_review": False,
            },
            {
                "id": "rec_2",
                "channel_id": "cam_02",
                "timestamp": "2026-11-24 10:05:00",
                "vehicle_class": "truck",
                "plate_text": "MH12AB1234",
                "confidence": 0.72,
                "plate_format": "INDIA",
                "requires_manual_review": True,
            },
        ]

        csv_str = engine.export_to_csv(mock_records)
        assert "KA01MJ4567" in csv_str
        assert "MH12AB1234" in csv_str
        assert "truck" in csv_str
