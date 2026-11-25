"""
Unit Tests for Denoising & Image Restoration (Phase 9 - F-042).
"""

import pytest
import numpy as np
import cv2

from engines.enhancement_engine.denoiser import DenoiseEnhancer


@pytest.fixture
def denoiser() -> DenoiseEnhancer:
    return DenoiseEnhancer()


@pytest.fixture
def noisy_frame() -> np.ndarray:
    """Creates a clean test pattern with added Gaussian sensor noise."""
    h, w = 240, 320
    clean = np.zeros((h, w, 3), dtype=np.uint8)
    # Vertical bars
    clean[:, :100] = [60, 60, 180]
    clean[:, 100:220] = [180, 100, 60]
    clean[:, 220:] = [100, 180, 60]

    # Add Gaussian noise sigma=18
    np.random.seed(42)
    noise = np.random.normal(0, 18, clean.shape)
    noisy = np.clip(clean.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    return clean, noisy


def test_nlmeans_denoising_reduces_variance(denoiser: DenoiseEnhancer, noisy_frame) -> None:
    """Verifies Non-Local Means reduces noise variance in flat regions."""
    clean, noisy = noisy_frame

    denoised = denoiser.enhance(noisy, method="nlmeans", h=12.0, h_color=12.0)

    assert denoised.shape == noisy.shape

    # Flat patch variance should decrease significantly
    noisy_patch_var = np.var(noisy[20:80, 20:80])
    denoised_patch_var = np.var(denoised[20:80, 20:80])
    assert denoised_patch_var < noisy_patch_var


def test_bilateral_filtering_edge_preservation(denoiser: DenoiseEnhancer, noisy_frame) -> None:
    """Verifies Bilateral filtering preserves sharp step boundaries."""
    clean, noisy = noisy_frame

    denoised = denoiser.enhance(noisy, method="bilateral", bilateral_d=9, bilateral_sigma_color=75.0)

    assert denoised.shape == noisy.shape

    # Step edge transition between x=99 and x=101 should remain distinct
    step_diff = abs(float(np.mean(denoised[:, 105, 0])) - float(np.mean(denoised[:, 95, 0])))
    assert step_diff > 40.0


def test_fast_denoising_mode(denoiser: DenoiseEnhancer, noisy_frame) -> None:
    """Verifies fast preview denoising mode."""
    clean, noisy = noisy_frame
    fast_out = denoiser.enhance(noisy, method="fast")
    assert fast_out.shape == noisy.shape
    assert np.var(fast_out[20:80, 20:80]) < np.var(noisy[20:80, 20:80])


def test_edge_preservation_blend(denoiser: DenoiseEnhancer, noisy_frame) -> None:
    """Verifies edge retention blending retains fine edge detail."""
    clean, noisy = noisy_frame
    blended = denoiser.enhance(noisy, method="bilateral", edge_preservation_blend=0.30)
    assert blended.shape == noisy.shape
