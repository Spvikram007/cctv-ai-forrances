"""
License Plate Detection, Localization, Perspective Correction, and Image Enhancement.
Operates strictly offline using OpenCV computer vision algorithms and local models.
"""

from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
import cv2
import numpy as np

from core.logging.logger import get_logger

logger = get_logger("plate_detector")


@dataclass
class PlateCandidate:
    bbox: Tuple[int, int, int, int]  # (x, y, w, h) within the vehicle crop
    confidence: float
    cropped_plate: np.ndarray
    enhanced_plate: np.ndarray


class PlateDetector:
    """
    Localizes license plate candidate regions on vehicles,
    performs deskewing / perspective correction, and contrast enhancement.
    Supports single-line (aspect ratio 2.5 - 5.5) and multi-line/square (aspect ratio 1.1 - 2.5) plates.
    """

    def __init__(
        self,
        min_aspect_ratio: float = 1.1,
        max_aspect_ratio: float = 6.0,
        min_area: int = 400,
        max_area: int = 80000,
    ) -> None:
        self.min_aspect_ratio = min_aspect_ratio
        self.max_aspect_ratio = max_aspect_ratio
        self.min_area = min_area
        self.max_area = max_area
        self.clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))

    def detect_plates(self, vehicle_bgr: np.ndarray) -> List[PlateCandidate]:
        """
        Detects candidate license plate regions in a cropped vehicle image.
        Returns a list of PlateCandidate objects ordered by detection confidence.
        Supports single-line and two-tier / square plates.
        """
        if vehicle_bgr is None or vehicle_bgr.size == 0:
            return []

        h, w = vehicle_bgr.shape[:2]
        if h < 30 or w < 40:
            return []

        # 1. Grayscale & Noise Reduction
        gray = cv2.cvtColor(vehicle_bgr, cv2.COLOR_BGR2GRAY)
        blurred = cv2.bilateralFilter(gray, 9, 75, 75)

        # 2. Vertical Edge Detection (Sobel) to capture vertical plate characters
        sobelx = cv2.Sobel(blurred, cv2.CV_8U, 1, 0, ksize=3)

        # 3. Morphological Closing: combine both horizontal and square structuring elements
        # Kernel 1: Horizontal fusion for standard single-line rectangular plates (17x3)
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3))
        closed_h = cv2.morphologyEx(sobelx, cv2.MORPH_CLOSE, kernel_h)

        # Kernel 2: Square fusion for two-tier / multi-line plates (9x9)
        kernel_sq = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        closed_sq = cv2.morphologyEx(sobelx, cv2.MORPH_CLOSE, kernel_sq)

        # Fuse edge maps
        closed = cv2.bitwise_or(closed_h, closed_sq)

        # 4. Otsu Binarization
        _, thresh = cv2.threshold(closed, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # 5. Contour Extraction
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates: List[PlateCandidate] = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if not (self.min_area <= area <= self.max_area):
                continue

            x, y, cw, ch = cv2.boundingRect(cnt)
            aspect_ratio = float(cw) / float(ch)

            if self.min_aspect_ratio <= aspect_ratio <= self.max_aspect_ratio:
                # Add padding around detected plate
                pad_x = int(cw * 0.08)
                pad_y = int(ch * 0.18)
                x1 = max(0, x - pad_x)
                y1 = max(0, y - pad_y)
                x2 = min(w, x + cw + pad_x)
                y2 = min(h, y + ch + pad_y)

                plate_crop = vehicle_bgr[y1:y2, x1:x2]
                if plate_crop.size == 0:
                    continue

                # Perspective deskewing
                deskewed = self.correct_perspective(plate_crop, cnt - np.array([x1, y1]))
                enhanced = self.enhance_plate(deskewed)

                # Confidence heuristic: single-line ideal ~3.5, two-tier ideal ~1.4
                if aspect_ratio < 2.2:
                    ratio_diff = abs(aspect_ratio - 1.4) / 1.4
                else:
                    ratio_diff = abs(aspect_ratio - 3.5) / 3.5
                conf = max(0.40, min(0.98, 1.0 - (ratio_diff * 0.45)))

                candidates.append(
                    PlateCandidate(
                        bbox=(x1, y1, x2 - x1, y2 - y1),
                        confidence=round(conf, 3),
                        cropped_plate=deskewed,
                        enhanced_plate=enhanced,
                    )
                )

        # If no morphological contour found, use bottom-center heuristic crop (typical plate location)
        if not candidates:
            # Lower 40% center of vehicle
            ph = int(h * 0.25)
            pw = int(w * 0.55)
            px = int((w - pw) / 2)
            py = int(h * 0.65)
            fallback_crop = vehicle_bgr[py:py + ph, px:px + pw]
            if fallback_crop.size > 0:
                enhanced = self.enhance_plate(fallback_crop)
                candidates.append(
                    PlateCandidate(
                        bbox=(px, py, pw, ph),
                        confidence=0.50,
                        cropped_plate=fallback_crop,
                        enhanced_plate=enhanced,
                    )
                )

        # Sort descending by confidence
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates

    def correct_perspective(self, plate_crop: np.ndarray, contour: np.ndarray) -> np.ndarray:
        """
        Deskews a tilted license plate using minimum bounding rotated rectangle.
        """
        try:
            rect = cv2.minAreaRect(contour)
            box = cv2.boxPoints(rect)
            box = np.int0(box)

            # Order points: top-left, top-right, bottom-right, bottom-left
            pts = np.float32(box)
            rect_w = int(rect[1][0])
            rect_h = int(rect[1][1])
            if rect_w < rect_h:
                rect_w, rect_h = rect_h, rect_w

            if rect_w < 20 or rect_h < 10:
                return plate_crop

            dst_pts = np.float32([
                [0, 0],
                [rect_w - 1, 0],
                [rect_w - 1, rect_h - 1],
                [0, rect_h - 1],
            ])

            # Sort corners
            s = pts.sum(axis=1)
            diff = np.diff(pts, axis=1)
            ordered_pts = np.zeros((4, 2), dtype="float32")
            ordered_pts[0] = pts[np.argmin(s)]
            ordered_pts[2] = pts[np.argmax(s)]
            ordered_pts[1] = pts[np.argmin(diff)]
            ordered_pts[3] = pts[np.argmax(diff)]

            M = cv2.getPerspectiveTransform(ordered_pts, dst_pts)
            warped = cv2.warpPerspective(plate_crop, M, (rect_w, rect_h))
            return warped if warped.size > 0 else plate_crop
        except Exception:
            return plate_crop

    def enhance_plate(self, plate_bgr: np.ndarray) -> np.ndarray:
        """
        Enhances plate contrast and clarity for OCR using CLAHE and bilateral filtering.
        Standardizes output size to 200x50.
        """
        if plate_bgr is None or plate_bgr.size == 0:
            return np.zeros((50, 200), dtype=np.uint8)

        # Resize to standard OCR dimensions
        resized = cv2.resize(plate_bgr, (200, 50), interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        # Adaptive histogram equalization
        clahe_enhanced = self.clahe.apply(gray)

        # Edge-preserving filter
        denoised = cv2.bilateralFilter(clahe_enhanced, 7, 50, 50)
        return denoised
