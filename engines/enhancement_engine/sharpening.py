"""
Motion Blur Reduction & Sharpening (Phase 9 - F-043).
Implements unsharp masking with edge-gradient gating, Laplacian sharpening,
and directional deblurring. Strictly contrast and edge-acutance restoration;
guarantees NO generative evidence hallucination.
"""

from typing import Optional, Tuple
import cv2
import numpy as np


class SharpeningEnhancer:
    """
    Clarifies soft optical edges, motion blur, and out-of-focus surveillance footage
    using edge-gated unsharp masking and directional deconvolution.
    Strictly contrast-enhancement: never introduces or hallucinates non-existent features.
    """

    def __init__(self) -> None:
        pass

    def enhance(
        self,
        frame: np.ndarray,
        method: str = "unsharp",
        alpha: float = 1.2,
        radius: float = 1.5,
        threshold: float = 8.0,
        direction_angle_deg: Optional[float] = None,
        motion_length: int = 5,
    ) -> np.ndarray:
        """
        Sharpen and deblur a frame.

        Args:
            frame: Input BGR uint8 image.
            method: 'unsharp', 'laplacian', or 'directional'.
            alpha: Sharpening intensity multiplier (0.2 to 3.0).
            radius: Gaussian blur radius/sigma for unsharp mask (0.5 to 4.0).
            threshold: Edge magnitude threshold to avoid amplifying background noise grain.
            direction_angle_deg: Motion blur direction in degrees (for directional deblur).
            motion_length: Estimated motion blur kernel length in pixels.

        Returns:
            Sharpened BGR uint8 image.
        """
        if frame is None or frame.size == 0:
            return frame

        alpha = float(np.clip(alpha, 0.1, 4.0))

        if method == "laplacian":
            return self.laplacian_sharpen(frame, alpha=alpha)
        elif method == "directional" and direction_angle_deg is not None:
            return self.directional_deblur(
                frame,
                angle_deg=direction_angle_deg,
                length=motion_length,
                alpha=alpha,
            )
        else:
            return self.unsharp_mask(frame, alpha=alpha, sigma=radius, threshold=threshold)

    def unsharp_mask(
        self,
        frame: np.ndarray,
        alpha: float = 1.2,
        sigma: float = 1.5,
        threshold: float = 8.0,
    ) -> np.ndarray:
        """
        Unsharp masking with edge-gradient noise gating.
        Only boosts high-frequency signals exceeding `threshold`, preserving smooth regions.
        """
        ksize = int(2 * np.ceil(2 * sigma) + 1)
        blurred = cv2.GaussianBlur(frame, (ksize, ksize), sigma)

        frame_f = frame.astype(np.float32)
        blurred_f = blurred.astype(np.float32)
        diff = frame_f - blurred_f

        # Gradient gating: compute gradient magnitude to suppress flat noise amplification
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        grad_mag = np.sqrt(grad_x * grad_x + grad_y * grad_y)

        # Smooth gate transition
        gate = (grad_mag / max(1.0, threshold)).clip(0.0, 1.0)[:, :, np.newaxis]

        # Apply gated sharpening
        sharpened = frame_f + (alpha * diff * gate)
        return sharpened.clip(0, 255).astype(np.uint8)

    def laplacian_sharpen(self, frame: np.ndarray, alpha: float = 1.0) -> np.ndarray:
        """
        Laplacian second-derivative high-pass sharpening.
        """
        kernel = np.array([
            [0, -1, 0],
            [-1, 5, -1],
            [0, -1, 0]
        ], dtype=np.float32)

        filtered = cv2.filter2D(frame, -1, kernel)
        if alpha == 1.0:
            return filtered
        return cv2.addWeighted(frame, float(1.0 - alpha), filtered, float(alpha), 0)

    def directional_deblur(
        self,
        frame: np.ndarray,
        angle_deg: float = 0.0,
        length: int = 5,
        alpha: float = 1.0,
    ) -> np.ndarray:
        """
        Directional motion deblurring using oriented Point Spread Function (PSF) approximation.
        """
        if length <= 1:
            return frame

        # Generate directional line kernel (PSF)
        psf = np.zeros((length, length), dtype=np.float32)
        center = (length - 1) / 2.0
        rad = np.deg2rad(angle_deg)
        cos_val = np.cos(rad)
        sin_val = np.sin(rad)

        for i in range(length):
            offset = i - center
            x = int(round(center + offset * cos_val))
            y = int(round(center + offset * sin_val))
            if 0 <= x < length and 0 <= y < length:
                psf[y, x] = 1.0

        psf_sum = np.sum(psf)
        if psf_sum > 0:
            psf /= psf_sum
        else:
            return frame

        # Approximate deblurring: unsharp mask along motion vector
        motion_blurred = cv2.filter2D(frame, -1, psf)
        diff = frame.astype(np.float32) - motion_blurred.astype(np.float32)
        deblurred = frame.astype(np.float32) + alpha * diff
        return deblurred.clip(0, 255).astype(np.uint8)
