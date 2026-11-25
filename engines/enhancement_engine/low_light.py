"""
Low-Light Video Enhancement (Phase 9 - F-040).
Provides Multi-Scale Retinex with Color Restoration (MSRCR),
adaptive CLAHE in CIE L*a*b* space, intensity-dependent gamma correction,
and near-black noise-floor gating.
"""

from typing import List, Optional, Tuple
import cv2
import numpy as np


class LowLightEnhancer:
    """
    Improves visibility in dark, underexposed, or high-contrast night footage
    while preserving chromatic balance and suppressing sensor noise in dark regions.
    """

    def __init__(self) -> None:
        pass

    def enhance(
        self,
        frame: np.ndarray,
        method: str = "clahe_lab",
        clip_limit: float = 2.5,
        gamma: float = 0.6,
        noise_gate: bool = True,
        noise_gate_threshold: float = 18.0,
        retinex_scales: Optional[List[int]] = None,
    ) -> np.ndarray:
        """
        Enhance a low-light frame.

        Args:
            frame: Input BGR uint8 image.
            method: 'clahe_lab', 'retinex', 'gamma', or 'combined'.
            clip_limit: CLAHE clip limit (1.0 to 8.0).
            gamma: Target gamma (0.3 to 1.2, < 1.0 brightens shadows).
            noise_gate: Attenuate amplification in near-black sensor noise floor.
            noise_gate_threshold: Luminance threshold below which noise gating applies.
            retinex_scales: Scales for Multi-Scale Retinex (default: [15, 80, 250]).

        Returns:
            Enhanced BGR uint8 image.
        """
        if frame is None or frame.size == 0:
            return frame

        if method == "retinex":
            return self.enhance_retinex(frame, scales=retinex_scales)
        elif method == "gamma":
            return self.adaptive_gamma(frame, gamma=gamma)
        elif method == "combined":
            # CLAHE in Lab + adaptive gamma + noise gate
            res = self.clahe_lab(
                frame,
                clip_limit=clip_limit,
                noise_gate=noise_gate,
                noise_gate_threshold=noise_gate_threshold,
            )
            return self.adaptive_gamma(res, gamma=gamma)
        else:
            # Default: clahe_lab
            return self.clahe_lab(
                frame,
                clip_limit=clip_limit,
                noise_gate=noise_gate,
                noise_gate_threshold=noise_gate_threshold,
            )

    def clahe_lab(
        self,
        frame: np.ndarray,
        clip_limit: float = 2.5,
        tile_grid_size: Tuple[int, int] = (8, 8),
        noise_gate: bool = True,
        noise_gate_threshold: float = 18.0,
    ) -> np.ndarray:
        """
        Adaptive Contrast Limited Histogram Equalization on L* channel in CIE L*a*b* space.
        Preserves color fidelity (a*, b* untouched) and applies noise-floor gating.
        """
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)

        clahe = cv2.createCLAHE(clipLimit=max(1.0, float(clip_limit)), tileGridSize=tile_grid_size)
        l_enhanced = clahe.apply(l_channel)

        if noise_gate:
            # Sigmoid soft transition around noise_gate_threshold to suppress deep sensor noise amplification
            l_orig_f = l_channel.astype(np.float32)
            l_enh_f = l_enhanced.astype(np.float32)

            # Gate weight: 0.0 near black, 1.0 at normal illumination
            delta = 6.0
            gate_weight = 1.0 / (1.0 + np.exp(-((l_orig_f - noise_gate_threshold) / delta)))
            l_out = (l_enh_f * gate_weight + l_orig_f * (1.0 - gate_weight)).clip(0, 255).astype(np.uint8)
        else:
            l_out = l_enhanced

        lab_out = cv2.merge([l_out, a_channel, b_channel])
        return cv2.cvtColor(lab_out, cv2.COLOR_LAB2BGR)

    def adaptive_gamma(self, frame: np.ndarray, gamma: float = 0.6) -> np.ndarray:
        """
        Intensity-dependent adaptive gamma correction using LUT.
        Lower gamma (< 1.0) stretches dark tones without blowing out bright highlights.
        """
        # Calculate mean luminance
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_lum = float(np.mean(gray)) / 255.0

        # Adjust gamma dynamically based on overall scene brightness
        eff_gamma = float(np.clip(gamma * (0.6 + 0.8 * mean_lum), 0.25, 1.3))

        table = np.array([((i / 255.0) ** eff_gamma) * 255.0 for i in range(256)]).clip(0, 255).astype(np.uint8)
        return cv2.LUT(frame, table)

    def enhance_retinex(
        self,
        frame: np.ndarray,
        scales: Optional[List[int]] = None,
        alpha: float = 125.0,
        beta: float = 46.0,
    ) -> np.ndarray:
        """
        Multi-Scale Retinex with Color Restoration (MSRCR).
        Computes weighted sum of log-ratios across Gaussian blur scales.
        """
        if scales is None:
            scales = [15, 80, 250]

        img_f = frame.astype(np.float32) + 1.0
        weights = [1.0 / len(scales)] * len(scales)

        # 1. Multi-scale retinex
        retinex = np.zeros_like(img_f)
        for s, w in zip(scales, weights):
            # Kernel size roughly 6 * sigma
            ksize = int(6 * s) | 1
            blurred = cv2.GaussianBlur(img_f, (ksize, ksize), s) + 1.0
            retinex += w * (np.log(img_f) - np.log(blurred))

        # 2. Color restoration factor
        sum_channels = np.sum(img_f, axis=2, keepdims=True)
        color_restoration = beta * (np.log(alpha * img_f) - np.log(sum_channels + 1.0))
        msrcr = retinex * color_restoration

        # 3. Dynamic range compression and percentile normalization
        enhanced_channels = []
        for c in range(3):
            ch = msrcr[:, :, c]
            mean = np.mean(ch)
            std = np.std(ch)
            # Clip between mean - 2*std and mean + 2*std
            min_val = mean - 2.0 * std
            max_val = mean + 2.0 * std
            if max_val > min_val:
                norm_ch = ((ch - min_val) / (max_val - min_val) * 255.0).clip(0, 255)
            else:
                norm_ch = np.zeros_like(ch)
            enhanced_channels.append(norm_ch.astype(np.uint8))

        return cv2.merge(enhanced_channels)
