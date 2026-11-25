"""
Unit Tests for Low-Light Enhancement (Phase 9 - F-040).
"""

import pytest
import numpy as np
import cv2

from engines.enhancement_engine.low_light import LowLightEnhancer


@pytest.fixture
def enhancer() -> LowLightEnhancer:
    return LowLightEnhancer()


@pytest.fixture
def low_light_frame() -> np.ndarray:
    """Creates a synthetic dark surveillance scene."""
    h, w = 360, 640
    img = np.full((h, w, 3), 20, dtype=np.uint8)
    # Add a dim license plate or object
    cv2.rectangle(img, (200, 150), (440, 210), (45, 45, 50), -1)
    cv2.putText(img, "MH12AB1234", (210, 195), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (80, 80, 80), 2)
    # Add deep black shadow
    cv2.rectangle(img, (0, 0), (100, 100), (5, 5, 5), -1)
    return img


def test_clahe_lab_expands_luminance_without_shifting_chroma(enhancer: LowLightEnhancer, low_light_frame: np.ndarray) -> None:
    """Verifies that CLAHE in Lab space increases L* without altering a* and b*."""
    lab_orig = cv2.cvtColor(low_light_frame, cv2.COLOR_BGR2LAB)
    l_orig, a_orig, b_orig = cv2.split(lab_orig)

    enhanced = enhancer.clahe_lab(low_light_frame, clip_limit=3.0, noise_gate=False)
    lab_enh = cv2.cvtColor(enhanced, cv2.COLOR_BGR2LAB)
    l_enh, a_enh, b_enh = cv2.split(lab_enh)

    # Luminance should increase on average in dark regions
    assert np.mean(l_enh) > np.mean(l_orig)

    # Chromatic channels should be preserved within integer quantization error (<= 1)
    assert np.max(np.abs(a_enh.astype(int) - a_orig.astype(int))) <= 1
    assert np.max(np.abs(b_enh.astype(int) - b_orig.astype(int))) <= 1


def test_noise_floor_gating_protects_near_black(enhancer: LowLightEnhancer, low_light_frame: np.ndarray) -> None:
    """Verifies that near-black pixels below threshold are not over-amplified."""
    # Pixel in deep shadow (val=5)
    shadow_orig = low_light_frame[10, 10, 0]

    # Without gate
    ungated = enhancer.clahe_lab(low_light_frame, clip_limit=4.0, noise_gate=False)
    # With gate
    gated = enhancer.clahe_lab(low_light_frame, clip_limit=4.0, noise_gate=True, noise_gate_threshold=20.0)

    # Gated version should keep near-black region much closer to original shadow than ungated
    assert gated[10, 10, 0] <= ungated[10, 10, 0]


def test_adaptive_gamma_brightens_shadows(enhancer: LowLightEnhancer, low_light_frame: np.ndarray) -> None:
    """Verifies adaptive gamma correction boosts dark values."""
    orig_mean = np.mean(low_light_frame)
    gamma_corrected = enhancer.adaptive_gamma(low_light_frame, gamma=0.5)
    new_mean = np.mean(gamma_corrected)

    assert new_mean > orig_mean


def test_multi_scale_retinex(enhancer: LowLightEnhancer, low_light_frame: np.ndarray) -> None:
    """Verifies Multi-Scale Retinex with Color Restoration outputs valid uint8 BGR."""
    retinex_out = enhancer.enhance_retinex(low_light_frame, scales=[15, 80])

    assert retinex_out.shape == low_light_frame.shape
    assert retinex_out.dtype == np.uint8
    # Dynamic range should be wider than original low-light
    assert np.std(retinex_out) > np.std(low_light_frame)


def test_enhance_combined_mode(enhancer: LowLightEnhancer, low_light_frame: np.ndarray) -> None:
    """Verifies combined mode applies CLAHE and gamma."""
    enhanced = enhancer.enhance(low_light_frame, method="combined", clip_limit=3.0, gamma=0.55)

    assert enhanced.shape == low_light_frame.shape
    assert np.mean(enhanced) > np.mean(low_light_frame)


def test_edge_cases_empty_and_uniform_frames(enhancer: LowLightEnhancer) -> None:
    """Verifies robustness on empty or solid frames."""
    assert enhancer.enhance(None) is None
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    assert enhancer.enhance(empty).size == 0

    all_black = np.zeros((100, 100, 3), dtype=np.uint8)
    out_black = enhancer.enhance(all_black)
    assert out_black.shape == all_black.shape

    all_white = np.full((100, 100, 3), 255, dtype=np.uint8)
    out_white = enhancer.enhance(all_white)
    assert out_white.shape == all_white.shape
