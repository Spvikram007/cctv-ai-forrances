"""
Unit Tests for Motion Blur Reduction & Sharpening (Phase 9 - F-043).
"""

import pytest
import numpy as np
import cv2

from engines.enhancement_engine.sharpening import SharpeningEnhancer


@pytest.fixture
def sharpener() -> SharpeningEnhancer:
    return SharpeningEnhancer()


@pytest.fixture
def soft_frame() -> np.ndarray:
    """Creates a frame with soft optical edges."""
    h, w = 240, 320
    sharp = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.putText(sharp, "SECURITY 4K", (40, 130), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (240, 240, 240), 3)

    # Blur to simulate lens softness / motion
    soft = cv2.GaussianBlur(sharp, (7, 7), 2.0)
    return sharp, soft


def test_unsharp_mask_enhances_acutance(sharpener: SharpeningEnhancer, soft_frame) -> None:
    """Verifies unsharp masking increases edge gradient sharpness."""
    _, soft = soft_frame
    sharpened = sharpener.unsharp_mask(soft, alpha=1.5, sigma=1.5, threshold=5.0)

    assert sharpened.shape == soft.shape

    # Compute Sobel edge magnitude
    gray_soft = cv2.cvtColor(soft, cv2.COLOR_BGR2GRAY)
    gray_sharp = cv2.cvtColor(sharpened, cv2.COLOR_BGR2GRAY)

    grad_soft = cv2.Sobel(gray_soft, cv2.CV_32F, 1, 1)
    grad_sharp = cv2.Sobel(gray_sharp, cv2.CV_32F, 1, 1)

    assert np.max(np.abs(grad_sharp)) > np.max(np.abs(grad_soft))


def test_gradient_threshold_gating_suppresses_noise_sharpening(sharpener: SharpeningEnhancer) -> None:
    """Verifies that flat noisy background below threshold is not amplified."""
    flat_noise = np.full((100, 100, 3), 100, dtype=np.uint8)
    # Add tiny noise (amplitude 3)
    flat_noise[::2, ::2] = 103

    # With high threshold, flat noise should not be sharpened
    gated = sharpener.unsharp_mask(flat_noise, alpha=2.0, sigma=1.0, threshold=15.0)

    # Max difference should be tiny
    assert np.max(np.abs(gated.astype(int) - flat_noise.astype(int))) <= 2


def test_laplacian_sharpen(sharpener: SharpeningEnhancer, soft_frame) -> None:
    """Verifies Laplacian high-pass sharpening."""
    _, soft = soft_frame
    lap_out = sharpener.laplacian_sharpen(soft, alpha=1.2)
    assert lap_out.shape == soft.shape
    assert np.std(lap_out) >= np.std(soft)


def test_directional_deblur(sharpener: SharpeningEnhancer, soft_frame) -> None:
    """Verifies directional deblurring with oriented PSF."""
    _, soft = soft_frame
    deblurred = sharpener.directional_deblur(soft, angle_deg=45.0, length=7, alpha=1.2)
    assert deblurred.shape == soft.shape


def test_non_hallucination_guarantee(sharpener: SharpeningEnhancer) -> None:
    """Verifies no synthetic or generative hallucinations occur on empty or black regions."""
    pure_black = np.zeros((100, 100, 3), dtype=np.uint8)
    out = sharpener.enhance(pure_black, method="unsharp", alpha=2.0)
    # Pure black should stay pure black; absolutely zero hallucinated pixels
    np.testing.assert_array_equal(out, pure_black)
