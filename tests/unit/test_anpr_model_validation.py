"""
Unit Tests for ANPR Model Validation Across Multi-Condition Synthetic Datasets:
Day, Night, Motion Blur, Low Resolution, Perspective Distortion, and Multi-line Plates.
"""

import pytest
import numpy as np
import cv2

from engines.anpr_engine.plate_detector import PlateDetector, PlateCandidate
from engines.anpr_engine.ocr_recognizer import PlateOCRRecognizer, OCRResult


class TestANPRModelValidation:
    @pytest.fixture
    def plate_detector(self):
        return PlateDetector()

    @pytest.fixture
    def ocr_recognizer(self):
        return PlateOCRRecognizer(default_format="INDIA")

    def _generate_synthetic_plate(
        self,
        plate_text: str = "KA01AB1234",
        width: int = 240,
        height: int = 50,
        bg_val: int = 240,
        text_val: int = 15,
    ) -> np.ndarray:
        """Generates a high-contrast rectangular plate image with clean spaced text."""
        plate_w = max(width, len(plate_text) * 23 + 24)
        plate = np.full((height, plate_w), bg_val, dtype=np.uint8)
        x_start = 12
        for i, ch in enumerate(plate_text):
            cv2.putText(
                plate,
                ch,
                (x_start + i * 22, int(height * 0.72)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                text_val,
                2,
                cv2.LINE_AA,
            )
        return plate

    def test_plate_ocr_cnn_inference(self, ocr_recognizer):
        """Verifies learned CNN character recognition generates 36-class probability distribution."""
        char_canvas = np.zeros((40, 40), dtype=np.uint8)
        cv2.putText(char_canvas, "A", (5, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 255, 2)
        x, y, w, h = cv2.boundingRect(char_canvas)
        norm_img = ocr_recognizer._normalize_character_crop(char_canvas[y : y + h, x : x + w])

        best_char, conf, prob_dist = ocr_recognizer._classify_char(norm_img)
        assert best_char == "A"
        assert conf > 0.50
        assert len(prob_dist) == 36
        assert sum(prob_dist.values()) > 0.80

    def test_normal_day_condition_recognition(self, ocr_recognizer):
        """Tests standard well-illuminated daylight license plate recognition."""
        plate = self._generate_synthetic_plate("DL1CAB1234", width=220, height=50)
        res = ocr_recognizer.recognize_plate(plate, expected_format="INDIA")

        assert res.format_valid is True
        assert res.confidence > 0.65
        assert not res.requires_manual_review

    def test_night_low_illumination_condition(self, ocr_recognizer):
        """Tests low-light nighttime plate condition with adaptive thresholding."""
        clean_plate = self._generate_synthetic_plate("MH12CD5678", width=220, height=50, bg_val=90, text_val=10)
        # Night condition: low contrast, dark overall illumination
        noisy_night = cv2.GaussianBlur(clean_plate, (3, 3), 0)

        res = ocr_recognizer.recognize_plate(noisy_night, expected_format="INDIA")
        assert len(res.plate_text) >= 8

    def test_motion_blur_condition(self, ocr_recognizer):
        """Tests horizontal motion blur characteristic of fast-moving vehicles."""
        clean_plate = self._generate_synthetic_plate("HR26DK9012", width=220, height=50)

        # Apply 5x1 horizontal motion blur kernel
        kernel_motion_blur = np.zeros((5, 5))
        kernel_motion_blur[2, :] = np.ones(5) / 5.0
        blurred = cv2.filter2D(clean_plate, -1, kernel_motion_blur)

        res = ocr_recognizer.recognize_plate(blurred, expected_format="INDIA")
        assert len(res.plate_text) >= 7

    def test_low_resolution_condition(self, ocr_recognizer):
        """Tests plate degradation under distant camera surveillance (downsampled then upsampled)."""
        clean_plate = self._generate_synthetic_plate("KA04MF3456", width=220, height=50)

        # Downsample to 50% resolution, then upscale back
        downsampled = cv2.resize(clean_plate, (110, 25), interpolation=cv2.INTER_AREA)
        upscaled = cv2.resize(downsampled, (220, 50), interpolation=cv2.INTER_CUBIC)

        res = ocr_recognizer.recognize_plate(upscaled, expected_format="INDIA")
        assert len(res.plate_text) >= 7

    def test_perspective_distortion_and_deskewing(self, plate_detector):
        """Tests rotated/tilted plate perspective deskewing."""
        # Create a synthetic vehicle canvas with a tilted plate
        vehicle = np.full((200, 300, 3), 50, dtype=np.uint8)
        # Draw tilted white rectangle (plate)
        pts = np.array([[80, 100], [200, 115], [195, 155], [75, 140]], np.int32)
        cv2.fillPoly(vehicle, [pts], (230, 230, 230))
        cv2.putText(vehicle, "KA05", (90, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (20, 20, 20), 2)

        candidates = plate_detector.detect_plates(vehicle)
        assert len(candidates) >= 1
        best = candidates[0]
        # Aspect ratio of deskewed crop should be rectangular
        h, w = best.cropped_plate.shape[:2]
        assert w > h

    def test_multi_line_square_plate_ordering(self, ocr_recognizer):
        """
        Validates two-tier / multi-line plate support:
        Top tier: DL1C (State code)
        Bottom tier: AB1234 (Registration number)
        OCR should order top-tier first, then bottom-tier.
        """
        # Height 90, Width 160 (aspect ratio ~1.77)
        square_plate = np.full((90, 160), 245, dtype=np.uint8)
        # Line 1 (top): DL01
        for i, ch in enumerate("DL01"):
            cv2.putText(square_plate, ch, (20 + i * 24, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 10, 2)
        # Line 2 (bottom): AB1234
        for i, ch in enumerate("AB1234"):
            cv2.putText(square_plate, ch, (10 + i * 23, 74), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 10, 2)

        res = ocr_recognizer.recognize_plate(square_plate, expected_format="INDIA")
        assert res.format_valid is True
        assert res.plate_text == "DL01AB1234"

    def test_positional_confusion_disambiguation(self, ocr_recognizer):
        """Verifies positional letter/digit confusion resolution in Indian plate syntax."""
        # Input has 'O' and 'I' in digit positions, and '8', '2' in alpha positions:
        # DL (alpha) + OI (should be 01) + BZ (alpha) + I234 (should be 1234)
        raw_confused = "DLOIBZI234"
        corrected = ocr_recognizer._disambiguate_confusions(raw_confused, "INDIA")
        assert corrected == "DL01BZ1234"

    def test_multi_format_validation(self, ocr_recognizer):
        """Validates format compliance for India, US, EU, and Generic patterns."""
        # India
        res_ind = ocr_recognizer.recognize_plate(self._generate_synthetic_plate("MH02EE9999"), "INDIA")
        assert res_ind.format_valid is True

        # US
        res_us = ocr_recognizer.recognize_plate(self._generate_synthetic_plate("7XYZ890"), "US")
        assert res_us.format_valid is True

        # EU
        res_eu = ocr_recognizer.recognize_plate(self._generate_synthetic_plate("B1234CD"), "EU")
        assert res_eu.format_valid is True

        # Generic
        res_gen = ocr_recognizer.recognize_plate(self._generate_synthetic_plate("SURV2026"), "GENERIC")
        assert res_gen.format_valid is True
