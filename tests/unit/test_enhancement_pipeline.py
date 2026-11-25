"""
Unit Tests for Enhancement Pipeline, Worker, and Audit Manifests (Phase 9 - F-045).
"""

import os
import json
import tempfile
import pytest
import numpy as np
import cv2

from engines.enhancement_engine.enhancement_pipeline import (
    EnhancementConfig,
    EnhancementPipeline,
    EnhancementWorker,
    EnhancementManifest,
    PresetProfile,
)


@pytest.fixture
def pipeline() -> EnhancementPipeline:
    return EnhancementPipeline(preferred_device="CPU")


@pytest.fixture
def sample_frame() -> np.ndarray:
    frame = np.full((180, 240, 3), 40, dtype=np.uint8)
    cv2.putText(frame, "TEST 01", (30, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (180, 180, 180), 2)
    return frame


def test_pipeline_process_frame_end_to_end(pipeline: EnhancementPipeline, sample_frame: np.ndarray) -> None:
    """Verifies pipeline chains filters cleanly."""
    cfg = EnhancementConfig(
        low_light_enabled=True,
        low_light_method="clahe_lab",
        denoise_enabled=True,
        denoise_method="fast",
        sharpen_enabled=True,
        sharpen_method="unsharp",
        super_resolution_enabled=True,
        super_resolution_scale=2,
        watermark_enabled=True,
    )

    out = pipeline.process_frame(sample_frame, cfg)

    # Resolution should be doubled due to 2x SR
    assert out.shape == (360, 480, 3)
    assert out.dtype == np.uint8


def test_preset_profiles_produce_valid_configs() -> None:
    """Verifies all predefined preset profiles generate complete configurations."""
    presets = [
        PresetProfile.neutral(),
        PresetProfile.night_vision(),
        PresetProfile.fog_penetration(),
        PresetProfile.license_plate_clarity(),
        PresetProfile.face_detail(),
    ]

    for p in presets:
        assert isinstance(p, EnhancementConfig)
        cfg_dict = p.to_dict()
        assert "low_light_enabled" in cfg_dict
        assert "dehaze_enabled" in cfg_dict
        assert "denoise_enabled" in cfg_dict
        assert "sharpen_enabled" in cfg_dict
        assert "super_resolution_enabled" in cfg_dict


def test_non_destructive_image_export_and_manifest(pipeline: EnhancementPipeline, sample_frame: np.ndarray) -> None:
    """Verifies non-destructive image processing with cryptographic SHA-256 sidecar manifest."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, "source_evidence.png")
        cv2.imwrite(src_path, sample_frame)

        # Store initial source content & hash
        with open(src_path, "rb") as f:
            original_bytes = f.read()

        out_path = os.path.join(tmpdir, "enhanced_evidence.png")
        cfg = PresetProfile.license_plate_clarity()

        saved_path, manifest = pipeline.process_image_file(
            input_path=src_path,
            output_path=out_path,
            config=cfg,
        )

        assert os.path.exists(saved_path)
        manifest_path = f"{saved_path}.manifest.json"
        assert os.path.exists(manifest_path)

        # 1. VERIFY SOURCE RECORDING WAS NOT ALTERED (Immutability guarantee)
        with open(src_path, "rb") as f:
            after_bytes = f.read()
        assert original_bytes == after_bytes, "Source file was modified! Must remain read-only."

        # 2. VERIFY MANIFEST METADATA & DISCLAIMER
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_json = json.load(f)

        assert manifest_json["source_sha256"] == manifest.source_sha256
        assert manifest_json["enhanced_sha256"] == manifest.enhanced_sha256
        assert "AI ENHANCED - NOT ORIGINAL EVIDENCE" in manifest_json["forensic_disclaimer"]
        assert manifest_json["engine_version"] == "0.9.0-alpha"
        assert manifest_json["source_resolution"] == [240, 180]
        assert manifest_json["enhanced_resolution"] == [480, 360]


def test_non_destructive_video_clip_export(pipeline: EnhancementPipeline, sample_frame: np.ndarray) -> None:
    """Verifies video clip enhancement and progress callback."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_video = os.path.join(tmpdir, "source_clip.mp4")
        out_video = os.path.join(tmpdir, "enhanced_clip.mp4")

        # Create short 10-frame synthetic test video
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(src_video, fourcc, 10.0, (240, 180))
        for _ in range(10):
            writer.write(sample_frame)
        writer.release()

        progress_calls = []

        def on_prog(curr, total, pct):
            progress_calls.append((curr, total, pct))

        cfg = EnhancementConfig(
            denoise_enabled=True,
            denoise_method="fast",
            sharpen_enabled=True,
            sharpen_alpha=1.0,
            watermark_enabled=True,
        )

        saved_clip, manifest = pipeline.process_video_clip(
            input_path=src_video,
            output_path=out_video,
            config=cfg,
            progress_cb=on_prog,
        )

        assert os.path.exists(saved_clip)
        assert len(progress_calls) > 0
        assert os.path.exists(f"{saved_clip}.manifest.json")


def test_enhancement_worker_thread(pipeline: EnhancementPipeline, sample_frame: np.ndarray) -> None:
    """Verifies asynchronous background worker execution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_video = os.path.join(tmpdir, "worker_src.mp4")
        out_video = os.path.join(tmpdir, "worker_out.mp4")

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(src_video, fourcc, 10.0, (240, 180))
        for _ in range(5):
            writer.write(sample_frame)
        writer.release()

        completed = []

        def on_done(path, mf):
            completed.append(path)

        worker = EnhancementWorker(
            pipeline=pipeline,
            input_path=src_video,
            output_path=out_video,
            config=PresetProfile.neutral(),
            on_complete=on_done,
        )

        worker.start()
        worker.join(timeout=10.0)

        assert not worker.is_alive()
        assert len(completed) == 1
        assert os.path.exists(out_video)
