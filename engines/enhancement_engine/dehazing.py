"""
Dehazing & Atmospheric Visibility Enhancement (Phase 9 - F-041).
Implements Dark Channel Prior (DCP), atmospheric light estimation,
Guided Filter transmission map refinement, and radiance recovery.
"""

from typing import Tuple
import cv2
import numpy as np


class DehazeEnhancer:
    """
    Restores visibility in foggy, hazy, smoky, or dusty surveillance footage
    using Dark Channel Prior (DCP) and Guided Filter transmission refinement.
    """

    def __init__(self) -> None:
        pass

    def enhance(
        self,
        frame: np.ndarray,
        patch_size: int = 15,
        omega: float = 0.95,
        t0: float = 0.10,
        guided_filter_radius: int = 40,
        guided_filter_eps: float = 1e-3,
    ) -> np.ndarray:
        """
        Dehaze a frame using Dark Channel Prior.

        Args:
            frame: Input BGR uint8 image.
            patch_size: Local neighborhood window size for dark channel calculation.
            omega: Haze retention factor (0.95 preserves subtle aerial perspective).
            t0: Lower bound transmission threshold to prevent division by near-zero.
            guided_filter_radius: Radius for guided filtering transmission map.
            guided_filter_eps: Regularization parameter for guided filter.

        Returns:
            Dehazed BGR uint8 image.
        """
        if frame is None or frame.size == 0:
            return frame

        # Downscale for fast transmission map calculation on high-res inputs (e.g. 1080p, 4K)
        h, w = frame.shape[:2]
        max_dim = 640
        scale = 1.0
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            proc_w = int(w * scale)
            proc_h = int(h * scale)
            small_frame = cv2.resize(frame, (proc_w, proc_h), interpolation=cv2.INTER_AREA)
        else:
            small_frame = frame

        img_norm = small_frame.astype(np.float32) / 255.0

        # 1. Dark Channel calculation
        dark_channel = self._compute_dark_channel(img_norm, patch_size=patch_size)

        # 2. Atmospheric light estimation
        atm_light = self._estimate_atmospheric_light(img_norm, dark_channel)

        # 3. Transmission map estimation
        raw_transmission = self._estimate_transmission(img_norm, atm_light, omega=omega, patch_size=patch_size)

        # 4. Guided filter refinement using grayscale guidance
        gray_guidance = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        refined_transmission = self._guided_filter(
            gray_guidance,
            raw_transmission,
            radius=guided_filter_radius,
            eps=guided_filter_eps,
        )

        # Upscale refined transmission map back to full resolution if downscaled
        if scale != 1.0:
            full_transmission = cv2.resize(refined_transmission, (w, h), interpolation=cv2.INTER_LINEAR)
        else:
            full_transmission = refined_transmission

        # 5. Recover scene radiance at full resolution
        full_img_norm = frame.astype(np.float32) / 255.0
        recovered = self._recover_radiance(full_img_norm, atm_light, full_transmission, t0=t0)

        # Return uint8 BGR
        return (recovered * 255.0).clip(0, 255).astype(np.uint8)

    def _compute_dark_channel(self, img_norm: np.ndarray, patch_size: int = 15) -> np.ndarray:
        """Computes min channel followed by min filter over local neighborhood."""
        min_channel = np.min(img_norm, axis=2)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (patch_size, patch_size))
        dark_channel = cv2.erode(min_channel, kernel)
        return dark_channel

    def _estimate_atmospheric_light(self, img_norm: np.ndarray, dark_channel: np.ndarray) -> np.ndarray:
        """
        Picks the top 0.1% brightest pixels in the dark channel and
        selects the highest intensity pixel in the original image.
        """
        h, w = dark_channel.shape
        num_pixels = h * w
        top_k = max(1, int(num_pixels * 0.001))

        flat_dark = dark_channel.reshape(-1)
        flat_img = img_norm.reshape(-1, 3)

        # Find indices of top_k in dark channel
        top_indices = np.argpartition(flat_dark, -top_k)[-top_k:]

        # Select pixel with maximum intensity magnitude among top indices
        top_candidates = flat_img[top_indices]
        candidate_intensities = np.sum(top_candidates, axis=1)
        best_idx = np.argmax(candidate_intensities)

        atm_light = top_candidates[best_idx]
        # Safeguard atmospheric light to avoid zeros or extreme values
        return np.clip(atm_light, 0.1, 0.98)

    def _estimate_transmission(
        self,
        img_norm: np.ndarray,
        atm_light: np.ndarray,
        omega: float = 0.95,
        patch_size: int = 15,
    ) -> np.ndarray:
        """Computes raw transmission map."""
        normalized = img_norm / atm_light
        dark_norm = self._compute_dark_channel(normalized, patch_size=patch_size)
        transmission = 1.0 - omega * dark_norm
        return np.clip(transmission, 0.0, 1.0)

    def _guided_filter(
        self,
        guide: np.ndarray,
        src: np.ndarray,
        radius: int = 40,
        eps: float = 1e-3,
    ) -> np.ndarray:
        """
        Fast Box-Filter implementation of Guided Filter for edge-preserving smoothing.
        Prevents halo artifacts along depth boundaries.
        """
        ksize = (2 * radius + 1, 2 * radius + 1)
        mean_i = cv2.blur(guide, ksize)
        mean_p = cv2.blur(src, ksize)
        corr_i = cv2.blur(guide * guide, ksize)
        corr_ip = cv2.blur(guide * src, ksize)

        var_i = corr_i - mean_i * mean_i
        cov_ip = corr_ip - mean_i * mean_p

        a = cov_ip / (var_i + eps)
        b = mean_p - a * mean_i

        mean_a = cv2.blur(a, ksize)
        mean_b = cv2.blur(b, ksize)

        q = mean_a * guide + mean_b
        return np.clip(q, 0.0, 1.0)

    def _recover_radiance(
        self,
        img_norm: np.ndarray,
        atm_light: np.ndarray,
        transmission: np.ndarray,
        t0: float = 0.10,
    ) -> np.ndarray:
        """J(x) = (I(x) - A) / max(t(x), t0) + A."""
        t_bounded = np.maximum(transmission, t0)[:, :, np.newaxis]
        recovered = (img_norm - atm_light) / t_bounded + atm_light
        return np.clip(recovered, 0.0, 1.0)
