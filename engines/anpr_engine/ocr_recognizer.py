"""
License Plate Character Segmentation, OCR Recognition, and Format Validation.
Operates fully local/offline with character-level confidence scoring, learned CNN classification,
multi-line plate support, and positional confusion resolution.
"""

import os
from pathlib import Path
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
    Performs character blob segmentation, multi-line row clustering,
    learned CNN character classification via ONNX / OpenVINO,
    positional confusion correction, and regional format validation.
    """

    CHAR_SET: str = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    DEFAULT_MODEL_PATH: str = "models/anpr/plate_character_recognizer.onnx"

    FORMAT_PATTERNS = {
        "INDIA": r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$",
        "US": r"^[A-Z0-9]{6,8}$",
        "EU": r"^[A-Z]{1,3}[A-Z0-9]{4,7}$",
        "GENERIC": r"^[A-Z0-9]{4,10}$",
    }

    # Positional character confusion disambiguation tables
    DIGIT_TO_ALPHA = {
        "0": "O",
        "1": "I",
        "2": "Z",
        "4": "A",
        "5": "S",
        "8": "B",
    }
    ALPHA_TO_DIGIT = {
        "O": "0",
        "D": "0",
        "Q": "0",
        "I": "1",
        "L": "1",
        "Z": "2",
        "A": "4",
        "S": "5",
        "B": "8",
    }

    def __init__(
        self,
        default_format: str = "GENERIC",
        model_path: Optional[str] = None,
    ) -> None:
        self.default_format = default_format
        self.model_path = model_path or self.DEFAULT_MODEL_PATH
        self._onnx_session = None
        self._ov_compiled_model = None
        self._init_character_templates()
        self._init_neural_model()

    def _init_neural_model(self) -> None:
        """Initializes OpenVINO or ONNX Runtime session for the learned character CNN."""
        if not self.model_path or not os.path.exists(self.model_path):
            proj_root = Path(__file__).resolve().parent.parent.parent
            candidate = proj_root / self.model_path
            if candidate.exists():
                self.model_path = str(candidate)

        if self.model_path and os.path.exists(self.model_path):
            # 1. Try OpenVINO first
            try:
                import openvino as ov
                core = ov.Core()
                ov_model = core.read_model(self.model_path)
                try:
                    self._ov_compiled_model = core.compile_model(ov_model, "CPU")
                    logger.info("PlateOCRRecognizer: Compiled OpenVINO model from %s", self.model_path)
                except Exception as compile_err:
                    logger.debug("OpenVINO compile failed (%s); trying ONNX Runtime.", compile_err)
            except Exception as ov_err:
                logger.debug("OpenVINO unavailable for OCR model (%s); trying ONNX Runtime.", ov_err)

            # 2. Try ONNX Runtime
            if self._ov_compiled_model is None:
                try:
                    import onnxruntime as ort
                    self._onnx_session = ort.InferenceSession(
                        self.model_path,
                        providers=["CPUExecutionProvider"]
                    )
                    logger.info("PlateOCRRecognizer: Loaded ONNX Runtime session from %s", self.model_path)
                except Exception as ort_err:
                    logger.warning("Could not initialize OCR ONNX model (%s); falling back to template matching.", ort_err)

    def _init_character_templates(self) -> None:
        """
        Generates standard synthetic 28x28 binary character reference templates (0-9, A-Z)
        using clean sans-serif geometric rendering and aspect-ratio preserving normalization.
        """
        self._templates: Dict[str, np.ndarray] = {}
        for ch in self.CHAR_SET:
            t = np.zeros((40, 40), dtype=np.uint8)
            cv2.putText(t, ch, (5, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 255, 2)
            x, y, w, h = cv2.boundingRect(t)
            self._templates[ch] = self._normalize_character_crop(t[y:y + h, x:x + w])

    def recognize(
        self,
        enhanced_plate: np.ndarray,
        expected_format: Optional[str] = None,
    ) -> OCRResult:
        """Alias for recognize_plate."""
        return self.recognize_plate(enhanced_plate, expected_format)

    @staticmethod
    def _normalize_character_crop(char_crop: np.ndarray) -> np.ndarray:
        """
        Normalizes a cropped character bounding box into a standard 28x28 canvas:
        Preserves aspect ratio, resizes max dimension to 20 pixels,
        and centers within 28x28 with 4px margin.
        """
        h, w = char_crop.shape[:2]
        if h <= 0 or w <= 0:
            return np.zeros((28, 28), dtype=np.uint8)
        scale = 20.0 / max(h, w)
        nh = max(1, min(28, int(h * scale)))
        nw = max(1, min(28, int(w * scale)))
        res = cv2.resize(char_crop, (nw, nh), interpolation=cv2.INTER_AREA)
        canvas = np.zeros((28, 28), dtype=np.uint8)
        y_off = (28 - nh) // 2
        x_off = (28 - nw) // 2
        canvas[y_off:y_off + nh, x_off:x_off + nw] = res
        return canvas

    def recognize_plate(
        self,
        enhanced_plate: np.ndarray,
        expected_format: Optional[str] = None,
    ) -> OCRResult:
        """
        Segments and classifies characters on an enhanced plate image.
        Supports single-line and multi-line / two-tier plates.
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

        min_char_h = max(5, int(h * 0.10))
        max_char_h = int(h * 0.95)
        min_char_w = 3
        max_char_w = int(w * 0.35)

        for cnt in contours:
            cx, cy, cw, ch_h = cv2.boundingRect(cnt)
            if min_char_h <= ch_h <= max_char_h and min_char_w <= cw <= max_char_w:
                aspect = float(cw) / float(ch_h)
                if 0.10 <= aspect <= 1.5:
                    char_boxes.append((cx, cy, cw, ch_h))

        if not char_boxes:
            fmt_to_use = expected_format or self.default_format
            return OCRResult(
                plate_text="UNREADABLE",
                confidence=0.10,
                character_confidences=[0.10],
                format_valid=False,
                plate_format=fmt_to_use,
                requires_manual_review=True,
            )

        # 3. Multi-line vs Single-line Ordering
        # Cluster boxes into lines based on vertical overlap and y-centers
        ordered_boxes = self._order_character_boxes(char_boxes, plate_height=h)

        # Filter overlapping / duplicate boxes within each line
        filtered_boxes: List[Tuple[int, int, int, int]] = []
        for box in ordered_boxes:
            if not filtered_boxes:
                filtered_boxes.append(box)
                continue
            prev = filtered_boxes[-1]
            # If same line and horizontally heavily overlapping, skip duplicate
            if abs(box[1] - prev[1]) < (h * 0.20) and (box[0] - prev[0]) < (prev[2] * 0.35):
                continue
            filtered_boxes.append(box)

        # 4. Classify Each Character
        recognized_chars: List[str] = []
        confidences: List[float] = []
        char_prob_dists: List[Dict[str, float]] = []

        for cx, cy, cw, ch_h in filtered_boxes:
            char_crop = thresh[cy:cy + ch_h, cx:cx + cw]
            char_crop_res = self._normalize_character_crop(char_crop)

            best_char, best_score, prob_dist = self._classify_char(char_crop_res)
            recognized_chars.append(best_char)
            confidences.append(best_score)
            char_prob_dists.append(prob_dist)

        raw_text = "".join(recognized_chars)
        fmt_to_use = expected_format or self.default_format

        # 5. Positional Confusion Disambiguation
        refined_text, refined_confs = self._disambiguate_confusions(
            raw_text, confidences, char_prob_dists, fmt_to_use
        )

        # 6. Format Validation
        pattern = self.FORMAT_PATTERNS.get(fmt_to_use, self.FORMAT_PATTERNS["GENERIC"])
        is_valid = bool(re.match(pattern, refined_text))
        avg_conf = round(sum(refined_confs) / len(refined_confs), 3) if refined_confs else 0.0

        # Mark for manual review if low confidence (< 0.70) or invalid format
        needs_review = (avg_conf < 0.70) or (not is_valid)

        return OCRResult(
            plate_text=refined_text,
            confidence=avg_conf,
            character_confidences=refined_confs,
            format_valid=is_valid,
            plate_format=fmt_to_use,
            requires_manual_review=needs_review,
        )

    def _order_character_boxes(
        self,
        char_boxes: List[Tuple[int, int, int, int]],
        plate_height: int,
    ) -> List[Tuple[int, int, int, int]]:
        """
        Orders character boxes. Supports multi-line plates (e.g. two-tier):
        Clusters boxes into lines by y-center, sorts lines from top to bottom,
        and sorts characters within each line from left to right.
        """
        if len(char_boxes) <= 1:
            return char_boxes

        # Check if characters are distributed across distinct vertical tiers
        y_centers = [cy + (ch / 2.0) for (_, cy, _, ch) in char_boxes]
        min_yc, max_yc = min(y_centers), max(y_centers)

        # If vertical spread is significant (> 25% plate height), cluster into lines
        if (max_yc - min_yc) > (plate_height * 0.25):
            mid_y = (min_yc + max_yc) / 2.0
            top_line = [b for b in char_boxes if (b[1] + b[3] / 2.0) <= mid_y]
            bottom_line = [b for b in char_boxes if (b[1] + b[3] / 2.0) > mid_y]

            top_line.sort(key=lambda b: b[0])
            bottom_line.sort(key=lambda b: b[0])
            return top_line + bottom_line

        # Single line: standard left-to-right sort
        return sorted(char_boxes, key=lambda b: b[0])

    def _classify_char(self, char_28x28: np.ndarray) -> Tuple[str, float, Dict[str, float]]:
        """
        Classifies character crop.
        Uses learned CNN model via OpenVINO or ONNX Runtime when available,
        outputting 36-class softmax probabilities.
        Falls back to normalized template matching if confidence is low.
        """
        prob_dist: Dict[str, float] = {}

        # 1. Neural CNN Inference
        if self._ov_compiled_model is not None or self._onnx_session is not None:
            try:
                # Preprocess: float32, normalized [0.0, 1.0], shape (1, 1, 28, 28)
                norm_img = char_28x28.astype(np.float32) / 255.0
                vec = norm_img.flatten()
                norm = np.linalg.norm(vec)
                if norm > 1e-6:
                    vec = vec / norm
                input_tensor = np.expand_dims(np.expand_dims(vec.reshape(28, 28), axis=0), axis=0)

                if self._ov_compiled_model is not None:
                    infer_req = self._ov_compiled_model.create_infer_request()
                    infer_req.infer({0: input_tensor})
                    logits = infer_req.get_output_tensor(0).data.flatten()
                else:
                    input_name = self._onnx_session.get_inputs()[0].name
                    outputs = self._onnx_session.run(None, {input_name: input_tensor})
                    logits = outputs[0].flatten()

                # Softmax calculation
                exp_logits = np.exp(logits - np.max(logits))
                probs = exp_logits / np.sum(exp_logits)

                for idx, ch in enumerate(self.CHAR_SET):
                    prob_dist[ch] = float(probs[idx]) if idx < len(probs) else 0.0

                best_idx = int(np.argmax(probs))
                best_char = self.CHAR_SET[best_idx]
                best_score = float(probs[best_idx])

                if best_score >= 0.20:
                    return best_char, round(best_score, 3), prob_dist
            except Exception as e:
                logger.debug("Neural OCR character inference failed (%s); falling back to template matching.", e)

        # 2. Template Matching Fallback
        best_char = "0"
        best_score = -1.0

        for ch, tmpl in self._templates.items():
            res = cv2.matchTemplate(char_28x28, tmpl, cv2.TM_CCOEFF_NORMED)
            score = float(res[0][0])
            norm_score = max(0.01, min(0.99, (score + 1.0) / 2.0))
            prob_dist[ch] = norm_score
            if score > best_score:
                best_score = score
                best_char = ch

        norm_score = max(0.10, min(0.99, (best_score + 1.0) / 2.0))
        return best_char, round(norm_score, 3), prob_dist

    def _disambiguate_confusions(
        self,
        text: str,
        confidences_or_format: Any = "GENERIC",
        prob_dists: Optional[List[Dict[str, float]]] = None,
        format_name: Optional[str] = None,
    ) -> Any:
        """
        Applies positional syntax rules to resolve letter/digit confusions
        (e.g., in Indian plates: 0-1 alpha, 2-3 digits, next 1-3 alpha, last 4 digits).
        Supports both direct signature (text, format_name) and full signature (text, confs, prob_dists, format_name).
        """
        if isinstance(confidences_or_format, str):
            fmt_to_use = confidences_or_format
            confs = [0.85] * len(text)
            probs: List[Dict[str, float]] = [{}] * len(text)
            return_tuple = False
        else:
            fmt_to_use = format_name or self.default_format
            confs = list(confidences_or_format) if confidences_or_format else [0.85] * len(text)
            probs = prob_dists or [{}] * len(text)
            return_tuple = True

        chars = list(text)

        if fmt_to_use == "INDIA" and len(chars) >= 8:
            def force_alpha(idx: int):
                if idx >= len(chars):
                    return
                ch = chars[idx]
                if ch.isdigit():
                    if ch in self.DIGIT_TO_ALPHA:
                        chars[idx] = self.DIGIT_TO_ALPHA[ch]
                    elif idx < len(probs) and probs[idx]:
                        alpha_probs = {c: p for c, p in probs[idx].items() if c.isalpha()}
                        if alpha_probs:
                            best_alpha = max(alpha_probs, key=alpha_probs.get)
                            chars[idx] = best_alpha
                            confs[idx] = round(alpha_probs[best_alpha], 3)

            def force_digit(idx: int):
                if idx >= len(chars):
                    return
                ch = chars[idx]
                if ch.isalpha():
                    if ch in self.ALPHA_TO_DIGIT:
                        chars[idx] = self.ALPHA_TO_DIGIT[ch]
                    elif idx < len(probs) and probs[idx]:
                        digit_probs = {c: p for c, p in probs[idx].items() if c.isdigit()}
                        if digit_probs:
                            best_digit = max(digit_probs, key=digit_probs.get)
                            chars[idx] = best_digit
                            confs[idx] = round(digit_probs[best_digit], 3)

            # Positions 0, 1: must be alpha (State code, e.g. MH, DL, KA)
            force_alpha(0)
            force_alpha(1)

            # Position 2: must be digit (District code)
            force_digit(2)

            if len(chars) == 10:
                # Format: AA NN AA NNNN (e.g. KA 01 AB 1234)
                force_digit(3)
                force_alpha(4)
                force_alpha(5)
                for idx in [6, 7, 8, 9]:
                    force_digit(idx)
            elif len(chars) == 9:
                # Format: AA N AA NNNN or AA NN A NNNN
                if chars[3].isdigit():
                    force_digit(3)
                    force_alpha(4)
                else:
                    force_alpha(3)
                for idx in range(5, 9):
                    force_digit(idx)
            else:
                # General fallback: last 4 must be digits
                for idx in range(max(4, len(chars) - 4), len(chars)):
                    force_digit(idx)

            refined_str = "".join(chars)
            return (refined_str, confs) if return_tuple else refined_str

        return ("".join(chars), confs) if return_tuple else "".join(chars)
