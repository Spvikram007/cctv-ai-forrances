"""
Unit Tests for AI Super-Resolution & Forensic Watermarking (Phase 9 - F-044).
"""

import pytest
import numpy as np
import cv2

from engines.enhancement_engine.super_resolution import SuperResolutionEnhancer


@pytest.fixture
def sr_enhancer() -> SuperResolutionEnhancer:
    return SuperResolutionEnhancer(preferred_device="CPU")


@pytest.fixture
def low_res_frame() -> np.ndarray:
    """Creates a 160x120 test frame."""
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    cv2.rectangle(frame, (30, 20), (130, 100), (0, 180, 255), -1)
    cv2.putText(frame, "CCTV", (45, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    return frame


def test_2x_super_resolution_scaling(sr_enhancer: SuperResolutionEnhancer, low_res_frame: np.ndarray) -> None:
    """Verifies 2x scale exactly doubles width and height."""
    h, w = low_res_frame.shape[:2]
    upscaled = sr_enhancer.enhance(low_res_frame, scale=2, add_watermark=False)

    assert upscaled.shape == (h * 2, w * 2, 3)
    assert upscaled.dtype == np.uint8


def test_4x_super_resolution_scaling(sr_enhancer: SuperResolutionEnhancer, low_res_frame: np.ndarray) -> None:
    """Verifies 4x scale exactly quadruples width and height."""
    h, w = low_res_frame.shape[:2]
    upscaled = sr_enhancer.enhance(low_res_frame, scale=4, add_watermark=False)

    assert upscaled.shape == (h * 4, w * 4, 3)
    assert upscaled.dtype == np.uint8


def test_forensic_watermark_stamping(sr_enhancer: SuperResolutionEnhancer, low_res_frame: np.ndarray) -> None:
    """Verifies forensic disclaimer watermark is applied onto enhanced media."""
    # Scale 2x with watermark
    upscaled_wm = sr_enhancer.enhance(low_res_frame, scale=2, add_watermark=True)
    upscaled_clean = sr_enhancer.enhance(low_res_frame, scale=2, add_watermark=False)

    assert upscaled_wm.shape == upscaled_clean.shape

    # Watermarked bottom-right region should differ from clean upscaled region
    h, w = upscaled_wm.shape[:2]
    wm_region = upscaled_wm[h - 40:, w - 200:]
    clean_region = upscaled_clean[h - 40:, w - 200:]

    assert not np.array_equal(wm_region, clean_region)


def test_watermark_positions(sr_enhancer: SuperResolutionEnhancer, low_res_frame: np.ndarray) -> None:
    """Verifies watermark positioning logic."""
    wm_br = sr_enhancer.apply_watermark(low_res_frame, text="TEST EVIDENCE", position="bottom_right")
    wm_tl = sr_enhancer.apply_watermark(low_res_frame, text="TEST EVIDENCE", position="top_left")

    assert wm_br.shape == low_res_frame.shape
    assert wm_tl.shape == low_res_frame.shape


def test_lanczos4_interpolation_quality(sr_enhancer: SuperResolutionEnhancer, low_res_frame: np.ndarray) -> None:
    """Verifies Lanczos-4 produces sharper edges than standard bilinear."""
    h, w = low_res_frame.shape[:2]
    lanczos_out = sr_enhancer._upscale_deterministic(low_res_frame, scale=2, method="lanczos4")
    bilinear_out = cv2.resize(low_res_frame, (w * 2, h * 2), interpolation=cv2.INTER_LINEAR)

    # Edge sharpness should be higher in Lanczos-4 with acutance filter
    lap_lanczos = cv2.Laplacian(lanczos_out, cv2.CV_32F)
    lap_bilinear = cv2.Laplacian(bilinear_out, cv2.CV_32F)

    assert np.var(lap_lanczos) > np.var(lap_bilinear)


def test_active_device_property(sr_enhancer: SuperResolutionEnhancer) -> None:
    """Verifies active device returns descriptive hardware string."""
    assert isinstance(sr_enhancer.active_device, str)
    assert len(sr_enhancer.active_device) > 0
