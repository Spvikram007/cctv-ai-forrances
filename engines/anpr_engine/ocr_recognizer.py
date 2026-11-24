"""
License Plate Character Segmentation, OCR Recognition, and Format Validation.
Operates fully local/offline with character-level confidence scoring and confusion resolution.
"""

import re
from typing import List, Tuple, Dict, Optional, Any
from dataclasses import dataclass
import cv2
import numpy as np

from core.logging.logger import get_logger

logger = get_logger("ocr_recognizer")


@dataclass
class OCRResult:
    plate_text: str
    confidence: float
    character_confidences: List[float]
    format_valid: bool
    plate_format: str
    requires_manual_review: bool


class PlateOCRRecognizer:
    """
    Offline OCR engine for vehicle license plates.
    Performs character blob segmentation, template/neural feature classification,
    positional confusion correction, and regional format validation.
    """

    FORMAT_PATTERNS = {
        "INDIA": r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$",
        "US": r"^[A-Z0-9]{6,8}$",
        "EU": r"^[A-Z]{1,3}[A-Z0-9]{4,7}$",
        "GENERIC": r"^[A-Z0-9]{5,10}$",
    }

    # Positional character confusion disambiguation tables
    DIGIT_TO_ALPHA = {
        "0": "O",
        "1": "I",
        "2": "Z",
        "5": "S",
        "8": "B",
    }
    ALPHA_TO_DIGIT = {
        "O": "0",
        "D": "0",
        "Q": "0",
        "I": "1",
        "Z": "2",
        "S": "5",
        "B": "8",
    }

    def __init__(self, default_format: str = "GENERIC") -> None:
        self.default_format = default_format
        self._init_character_templates()

    def _init_character_templates(self) -> None:
        """
        Generates standard synthetic 28x28 binary character reference templates (0-9, A-Z)
        using clean sans-serif geometric rendering.
        """
        chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        self._templates: Dict[str, np.ndarray] = {}

        for ch in chars:
            img = np.zeros((28, 28), dtype=np.uint8)
            font = cv2.FONT_HERSHEY_SIMPLEX
            # Get text size
            (tw, th), _ = cv2.getTextSize(ch, font, 0.7, 2)
            tx = (28 - tw) // 2
            ty = (28 + th) // 2
            cv2.putText(img, ch, (tx, ty), font, 0.7, 255, 2, cv2.LINE_AA)
            self._templates[ch] = img

    def recognize(
        self,
        enhanced_plate: np.ndarray,
        expected_format: Optional[str] = None,
    ) -> OCRResult:
        """Alias for recognize_plate."""
        return self.recognize_plate(enhanced_plate, expected_format)

    def recognize_plate(
        self,
        enhanced_plate: np.ndarray,
        expected_format: Optional[str] = None,
    ) -> OCRResult:
        """
        Segments and classifies characters on an enhanced plate image.
        Returns complete OCRResult with character and overall confidences.
        """
        if enhanced_plate is None or enhanced_plate.size == 0:
            return OCRResult(
                plate_text="",
                confidence=0.0,
                character_confidences=[],
                format_valid=False,
                plate_format=expected_format or self.default_format,
                requires_manual_review=True,
            )

        # 1. Binarize (Otsu inverse for white plate / dark text or dark plate / white text)
        if len(enhanced_plate.shape) == 3:
            gray = cv2.cvtColor(enhanced_plate, cv2.COLOR_BGR2GRAY)
        else:
            gray = enhanced_plate

        h, w = gray.shape[:2]
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Invert if text is dark on light background (majority pixels light)
        if cv2.countNonZero(thresh) > (h * w * 0.55):
            thresh = cv2.bitwise_not(thresh)

        # 2. Extract Character Contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        char_boxes: List[Tuple[int, int, int, int]] = []

        min_char_h = max(10, int(h * 0.20))
        max_char_h = int(h * 0.95)
        min_char_w = 4
        max_char_w = int(w * 0.30)

        for cnt in contours:
            cx, cy, cw, ch_h = cv2.boundingRect(cnt)
            if min_char_h <= ch_h <= max_char_h and min_char_w <= cw <= max_char_w:
                aspect = float(cw) / float(ch_h)
                if 0.10 <= aspect <= 1.5:
                    char_boxes.append((cx, cy, cw, ch_h))

        # Sort characters horizontally left to right
        char_boxes.sort(key=lambda b: b[0])

        # Filter overlapping boxes
        filtered_boxes: List[Tuple[int, int, int, int]] = []
        for box in char_boxes:
            if not filtered_boxes:
                filtered_boxes.append(box)
                continue
            prev = filtered_boxes[-1]
            if (box[0] - prev[0]) > (prev[2] * 0.4):
                filtered_boxes.append(box)

        # 3. Classify Each Character
        recognized_chars: List[str] = []
        confidences: List[float] = []

        for cx, cy, cw, ch_h in filtered_boxes:
            char_crop = thresh[cy:cy + ch_h, cx:cx + cw]
            char_crop_res = cv2.resize(char_crop, (28, 28), interpolation=cv2.INTER_AREA)

            best_char, best_score = self._classify_char(char_crop_res)
            recognized_chars.append(best_char)
            confidences.append(best_score)

        raw_text = "".join(recognized_chars)
        fmt_to_use = expected_format or self.default_format

        # 4. Positional Confusion Disambiguation
        refined_text = self._disambiguate_confusions(raw_text, fmt_to_use)

        # Fallback if segmentation extracted nothing (e.g. extremely degraded frame)
        if not refined_text:
            return OCRResult(
                plate_text="UNREADABLE",
                confidence=0.10,
                character_confidences=[0.10],
                format_valid=False,
                plate_format=fmt_to_use,
                requires_manual_review=True,
            )

        # 5. Format Validation
        pattern = self.FORMAT_PATTERNS.get(fmt_to_use, self.FORMAT_PATTERNS["GENERIC"])
        is_valid = bool(re.match(pattern, refined_text))
        avg_conf = round(sum(confidences) / len(confidences), 3) if confidences else 0.0

        # Mark for manual review if low confidence (< 0.70) or invalid format
        needs_review = (avg_conf < 0.70) or (not is_valid)

        return OCRResult(
            plate_text=refined_text,
            confidence=avg_conf,
            character_confidences=confidences,
            format_valid=is_valid,
            plate_format=fmt_to_use,
            requires_manual_review=needs_review,
        )

    def _classify_char(self, char_28x28: np.ndarray) -> Tuple[str, float]:
        """Matches character crop against normalized template library."""
        best_char = "0"
        best_score = -1.0

        for ch, tmpl in self._templates.items():
            # Normalized correlation coefficient
            res = cv2.matchTemplate(char_28x28, tmpl, cv2.TM_CCOEFF_NORMED)
            score = float(res[0][0])
            if score > best_score:
                best_score = score
                best_char = ch

        norm_score = max(0.10, min(0.99, (best_score + 1.0) / 2.0))
        return best_char, round(norm_score, 3)

    def _disambiguate_confusions(self, text: str, format_name: str) -> str:
        """
        Applies positional syntax rules to resolve letter/digit confusions
        (e.g., in Indian plates, characters 0-1 are alpha, 2-3 are digits, last 4 are digits).
        """
        if format_name == "INDIA" and len(text) >= 8:
            chars = list(text)
            # Position 0, 1: must be alpha
            for idx in [0, 1]:
                if idx < len(chars) and chars[idx] in self.DIGIT_TO_ALPHA:
                    chars[idx] = self.DIGIT_TO_ALPHA[chars[idx]]
            # Position 2, 3: must be digits
            for idx in [2, 3]:
                if idx < len(chars) and chars[idx] in self.ALPHA_TO_DIGIT:
                    chars[idx] = self.ALPHA_TO_DIGIT[chars[idx]]
            # Last 4 characters: must be digits
            for idx in range(max(4, len(chars) - 4), len(chars)):
                if chars[idx] in self.ALPHA_TO_DIGIT:
                    chars[idx] = self.ALPHA_TO_DIGIT[chars[idx]]
            return "".join(chars)

        return text
