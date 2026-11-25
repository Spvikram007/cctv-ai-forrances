"""
Denoising & Image Restoration (Phase 9 - F-042).
Implements Fast Non-Local Means (NL-Means) filtering and
Bilateral edge-preserving filtering to suppress sensor noise
and compression artifacts without destroying critical forensic edges.
"""

from typing import Optional
import cv2
import numpy as np


class DenoiseEnhancer:
    """
    Reduces Gaussian sensor noise, ISO grain, and compression artifacts
    while preserving edge sharpness and fine structural detail.
    """

    def __init__(self) -> None:
        pass

    def enhance(
        self,
        frame: np.ndarray,
        method: str = "nlmeans",
        h: float = 10.0,
        h_color: float = 10.0,
        bilateral_d: int = 9,
        bilateral_sigma_color: float = 75.0,
        bilateral_sigma_space: float = 75.0,
        edge_preservation_blend: float = 0.15,
    ) -> np.ndarray:
        """
        Denoise a frame using Non-Local Means or Bilateral filtering.

        Args:
            frame: Input BGR uint8 image.
            method: 'nlmeans', 'bilateral', or 'fast'.
            h: Filter strength for NL-Means luminance (3.0 to 25.0).
            h_color: Filter strength for NL-Means color components.
            bilateral_d: Diameter of each pixel neighborhood for bilateral filtering.
            bilateral_sigma_color: Filter sigma in the color space.
            bilateral_sigma_space: Filter sigma in the coordinate space.
            edge_preservation_blend: Edge retention weight to blend back sharp edges.

        Returns:
            Denoised BGR uint8 image.
        """
        if frame is None or frame.size == 0:
            return frame

        h_val = float(np.clip(h, 1.0, 30.0))
        h_color_val = float(np.clip(h_color, 1.0, 30.0))

        if method == "nlmeans":
            denoised = cv2.fastNlMeansDenoisingColored(
                frame,
                None,
                h=h_val,
                hColor=h_color_val,
                templateWindowSize=7,
                searchWindowSize=21,
            )
        elif method == "bilateral":
            denoised = cv2.bilateralFilter(
                frame,
                d=int(bilateral_d),
                sigmaColor=float(bilateral_sigma_color),
                sigmaSpace=float(bilateral_sigma_space),
            )
        elif method == "fast":
            # Fast Gaussian + median hybrid for real-time live preview
            median = cv2.medianBlur(frame, 3)
            denoised = cv2.addWeighted(frame, 0.3, median, 0.7, 0)
        else:
            denoised = cv2.fastNlMeansDenoisingColored(
                frame,
                None,
                h=h_val,
                hColor=h_color_val,
                templateWindowSize=7,
                searchWindowSize=21,
            )

        # Blend original edge details in strong gradient regions if requested
        if edge_preservation_blend > 0.0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
            grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
            grad_mag = cv2.magnitude(grad_x, grad_y)
            # Normalize gradient mask to 0.0 - 1.0
            norm_grad = (grad_mag / (np.max(grad_mag) + 1e-5)).clip(0.0, 1.0)
            edge_mask = (norm_grad * edge_preservation_blend)[:, :, np.newaxis]

            orig_f = frame.astype(np.float32)
            denoised_f = denoised.astype(np.float32)
            out_f = orig_f * edge_mask + denoised_f * (1.0 - edge_mask)
            return out_f.clip(0, 255).astype(np.uint8)

        return denoised
