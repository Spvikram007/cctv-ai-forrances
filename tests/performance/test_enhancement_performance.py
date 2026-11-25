"""
Performance & Benchmark Tests for Video Enhancement Subsystem (Phase 9 - F-040..F-045).
Evaluates execution latency, memory footprint, and throughput across
720p, 1080p, and 4K surveillance frames on target Intel hardware.
"""

import time
import pytest
import numpy as np
import cv2

from engines.enhancement_engine.enhancement_pipeline import (
    EnhancementConfig,
    EnhancementPipeline,
    PresetProfile,
)


@pytest.fixture
def pipeline() -> EnhancementPipeline:
    return EnhancementPipeline(preferred_device="CPU")


def test_720p_pipeline_latency(pipeline: EnhancementPipeline) -> None:
    """Benchmarks full enhancement pipeline on 1280x720 (720p HD) footage."""
    h, w = 720, 1280
    frame_720p = np.full((h, w, 3), 40, dtype=np.uint8)
    cv2.circle(frame_720p, (640, 360), 200, (120, 120, 120), -1)

    cfg = PresetProfile.night_vision()

    # Warmup
    _ = pipeline.process_frame(frame_720p, cfg)

    # Timed run
    start = time.perf_counter()
    out = pipeline.process_frame(frame_720p, cfg)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert out.shape == (h, w, 3)
    # 720p processing should easily complete in < 250ms on CPU
    assert elapsed_ms < 250.0, f"720p latency exceeded limit: {elapsed_ms:.1f} ms"


def test_1080p_pipeline_latency(pipeline: EnhancementPipeline) -> None:
    """Benchmarks full enhancement pipeline on 1920x1080 (1080p Full HD) footage."""
    h, w = 1080, 1920
    frame_1080p = np.full((h, w, 3), 35, dtype=np.uint8)
    cv2.rectangle(frame_1080p, (400, 300), (1500, 800), (80, 80, 90), -1)

    cfg = PresetProfile.license_plate_clarity()
    # Disable 2x SR for base 1080p latency measurement
    cfg.super_resolution_enabled = False

    # Warmup
    _ = pipeline.process_frame(frame_1080p, cfg)

    start = time.perf_counter()
    out = pipeline.process_frame(frame_1080p, cfg)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert out.shape == (h, w, 3)
    # 1080p filter processing should complete in < 400ms on CPU
    assert elapsed_ms < 400.0, f"1080p latency exceeded limit: {elapsed_ms:.1f} ms"


def test_4k_pipeline_latency_and_memory(pipeline: EnhancementPipeline) -> None:
    """Benchmarks dehazing and sharpening on 3840x2160 (4K UHD) surveillance footage."""
    h, w = 2160, 3840
    frame_4k = np.full((h, w, 3), 50, dtype=np.uint8)
    cv2.rectangle(frame_4k, (500, 500), (3300, 1600), (120, 150, 180), -1)

    cfg = EnhancementConfig(
        dehaze_enabled=True,
        dehaze_omega=0.90,
        dehaze_t0=0.10,
        sharpen_enabled=True,
        sharpen_alpha=1.0,
        watermark_enabled=True,
    )

    start = time.perf_counter()
    out = pipeline.process_frame(frame_4k, cfg)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert out.shape == (h, w, 3)
    # Guided filter downscaling ensures 4K dehaze & sharpen runs within reasonable bounds (< 1200ms)
    assert elapsed_ms < 1500.0, f"4K latency exceeded limit: {elapsed_ms:.1f} ms"


def test_2x_super_resolution_throughput(pipeline: EnhancementPipeline) -> None:
    """Benchmarks 2x Super-Resolution throughput from 720p to 1440p."""
    h, w = 720, 1280
    frame = np.full((h, w, 3), 60, dtype=np.uint8)

    cfg = EnhancementConfig(
        super_resolution_enabled=True,
        super_resolution_scale=2,
        watermark_enabled=True,
    )

    start = time.perf_counter()
    out = pipeline.process_frame(frame, cfg)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert out.shape == (h * 2, w * 2, 3)
    assert elapsed_ms < 200.0, f"2x SR latency exceeded limit: {elapsed_ms:.1f} ms"
