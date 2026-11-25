"""
Unit Tests for Dehazing & Visibility Enhancement (Phase 9 - F-041).
"""

import pytest
import numpy as np
import cv2

from engines.enhancement_engine.dehazing import DehazeEnhancer


@pytest.fixture
def dehazer() -> DehazeEnhancer:
    return DehazeEnhancer()


@pytest.fixture
def hazy_frame() -> np.ndarray:
    """Creates a synthetic foggy surveillance scene."""
    h, w = 360, 640
    # Clear background scene
    scene = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.rectangle(scene, (100, 100), (540, 300), (60, 120, 180), -1)
    cv2.putText(scene, "GATE ENTRANCE", (150, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (20, 20, 20), 3)

    # Overlay uniform dense fog / haze: I = J*t + A*(1-t)
    # Transmission t = 0.4, Atmospheric light A = 220
    t = 0.40
    a = 220
    hazy = (scene.astype(np.float32) * t + a * (1.0 - t)).clip(0, 255).astype(np.uint8)
    return hazy


def test_dehazing_recovers_contrast_and_edges(dehazer: DehazeEnhancer, hazy_frame: np.ndarray) -> None:
    """Verifies that dehazing increases image dynamic contrast and visibility."""
    dehazed = dehazer.enhance(hazy_frame, omega=0.95, t0=0.10)

    assert dehazed.shape == hazy_frame.shape
    assert dehazed.dtype == np.uint8

    # Standard deviation (contrast) should increase significantly after fog removal
    assert np.std(dehazed) > np.std(hazy_frame)


def test_dark_channel_computation(dehazer: DehazeEnhancer, hazy_frame: np.ndarray) -> None:
    """Verifies dark channel calculation gives low values for non-sky patches."""
    img_norm = hazy_frame.astype(np.float32) / 255.0
    dark = dehazer._compute_dark_channel(img_norm, patch_size=15)

    assert dark.shape == hazy_frame.shape[:2]
    assert np.min(dark) >= 0.0
    assert np.max(dark) <= 1.0


def test_atmospheric_light_estimation(dehazer: DehazeEnhancer, hazy_frame: np.ndarray) -> None:
    """Verifies atmospheric light vector is within valid range."""
    img_norm = hazy_frame.astype(np.float32) / 255.0
    dark = dehazer._compute_dark_channel(img_norm, patch_size=15)
    atm_light = dehazer._estimate_atmospheric_light(img_norm, dark)

    assert atm_light.shape == (3,)
    assert np.all(atm_light >= 0.1)
    assert np.all(atm_light <= 0.98)


def test_guided_filter_preserves_edges(dehazer: DehazeEnhancer) -> None:
    """Verifies guided filter smooths flat regions while preserving boundary transitions."""
    guide = np.zeros((100, 100), dtype=np.float32)
    guide[:, 50:] = 1.0  # Sharp step edge

    noisy_src = guide + np.random.normal(0, 0.1, (100, 100)).astype(np.float32)
    noisy_src = np.clip(noisy_src, 0.0, 1.0)

    filtered = dehazer._guided_filter(guide, noisy_src, radius=5, eps=1e-3)

    assert filtered.shape == (100, 100)
    # Variance in flat regions should be reduced
    assert np.var(filtered[:, :40]) < np.var(noisy_src[:, :40])
    # Step edge transition should be maintained
    assert filtered[50, 60] > filtered[50, 40]


def test_dehazer_empty_and_solid_frames(dehazer: DehazeEnhancer) -> None:
    """Verifies graceful handling of empty or solid frames."""
    assert dehazer.enhance(None) is None
    solid = np.full((100, 100, 3), 128, dtype=np.uint8)
    out = dehazer.enhance(solid)
    assert out.shape == solid.shape
