"""
Enhancement Pipeline, Asynchronous Worker & Audit Manifest (Phase 9 - F-045).
Coordinates low-light, dehazing, denoising, sharpening, super-resolution,
and watermark stamping in optimal sequence. Ensures strict source recording
immutability and generates cryptographic SHA-256 audit manifests in storage/enhanced/.
"""

import os
import json
import time
import hashlib
from typing import Dict, Any, Optional, Tuple, Callable
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import threading

import cv2
import numpy as np

from core.logging.logger import get_logger
from core.config.settings import settings
from engines.enhancement_engine.low_light import LowLightEnhancer
from engines.enhancement_engine.dehazing import DehazeEnhancer
from engines.enhancement_engine.denoiser import DenoiseEnhancer
from engines.enhancement_engine.sharpening import SharpeningEnhancer
from engines.enhancement_engine.super_resolution import SuperResolutionEnhancer

logger = get_logger("enhancement_pipeline")


@dataclass
class EnhancementConfig:
    """Master configuration for the video enhancement pipeline."""
    # Low-light enhancement (F-040)
    low_light_enabled: bool = False
    low_light_method: str = "clahe_lab"  # 'clahe_lab', 'retinex', 'gamma', 'combined'
    low_light_clip_limit: float = 2.5
    low_light_gamma: float = 0.6
    low_light_noise_gate: bool = True
    low_light_threshold: float = 18.0

    # Dehazing (F-041)
    dehaze_enabled: bool = False
    dehaze_omega: float = 0.95
    dehaze_t0: float = 0.10
    dehaze_patch_size: int = 15

    # Denoising (F-042)
    denoise_enabled: bool = False
    denoise_method: str = "nlmeans"  # 'nlmeans', 'bilateral', 'fast'
    denoise_h: float = 8.0
    denoise_h_color: float = 8.0
    bilateral_d: int = 9
    bilateral_sigma_color: float = 75.0
    bilateral_sigma_space: float = 75.0
    denoise_edge_blend: float = 0.15

    # Sharpening (F-043)
    sharpen_enabled: bool = False
    sharpen_method: str = "unsharp"  # 'unsharp', 'laplacian', 'directional'
    sharpen_alpha: float = 1.2
    sharpen_radius: float = 1.5
    sharpen_threshold: float = 8.0
    motion_angle_deg: Optional[float] = None
    motion_length: int = 5

    # Super-resolution (F-044)
    super_resolution_enabled: bool = False
    super_resolution_scale: int = 1  # 1 (none), 2 (2x), 4 (4x)
    super_resolution_interp: str = "lanczos4"

    # Forensic Watermark (F-044, F-045)
    watermark_enabled: bool = True
    watermark_text: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PresetProfile:
    """Pre-calibrated enhancement profiles for common surveillance challenges."""

    @staticmethod
    def neutral() -> EnhancementConfig:
        """All filters disabled (neutral baseline)."""
        return EnhancementConfig()

    @staticmethod
    def night_vision() -> EnhancementConfig:
        """Optimized for dark, underexposed night footage."""
        return EnhancementConfig(
            low_light_enabled=True,
            low_light_method="combined",
            low_light_clip_limit=3.5,
            low_light_gamma=0.55,
            low_light_noise_gate=True,
            denoise_enabled=True,
            denoise_method="bilateral",
            denoise_h=10.0,
            sharpen_enabled=True,
            sharpen_alpha=1.0,
            watermark_enabled=True,
        )

    @staticmethod
    def fog_penetration() -> EnhancementConfig:
        """Optimized for dense fog, smoke, haze, and low-contrast weather."""
        return EnhancementConfig(
            dehaze_enabled=True,
            dehaze_omega=0.95,
            dehaze_t0=0.10,
            denoise_enabled=True,
            denoise_method="bilateral",
            denoise_h=6.0,
            sharpen_enabled=True,
            sharpen_alpha=1.2,
            watermark_enabled=True,
        )

    @staticmethod
    def license_plate_clarity() -> EnhancementConfig:
        """Optimized for reading license plates under motion or low resolution."""
        return EnhancementConfig(
            denoise_enabled=True,
            denoise_method="bilateral",
            bilateral_d=7,
            bilateral_sigma_color=50.0,
            bilateral_sigma_space=50.0,
            sharpen_enabled=True,
            sharpen_method="unsharp",
            sharpen_alpha=1.8,
            sharpen_threshold=6.0,
            super_resolution_enabled=True,
            super_resolution_scale=2,
            watermark_enabled=True,
        )

    @staticmethod
    def face_detail() -> EnhancementConfig:
        """Optimized for clarifying facial features and suspect recognition."""
        return EnhancementConfig(
            low_light_enabled=True,
            low_light_method="clahe_lab",
            low_light_clip_limit=2.0,
            low_light_noise_gate=True,
            denoise_enabled=True,
            denoise_method="nlmeans",
            denoise_h=7.0,
            sharpen_enabled=True,
            sharpen_alpha=1.2,
            super_resolution_enabled=True,
            super_resolution_scale=2,
            watermark_enabled=True,
        )


@dataclass
class EnhancementManifest:
    """
    Cryptographic audit manifest generated alongside every enhanced output.
    Proves provenance, parameters applied, and forensic non-destructive isolation.
    """
    source_path: str
    source_sha256: str
    source_resolution: Tuple[int, int]
    enhanced_path: str
    enhanced_sha256: str
    enhanced_resolution: Tuple[int, int]
    config_applied: Dict[str, Any]
    operator: str = "SYSTEM_ADMIN"
    engine_version: str = "0.9.0-alpha"
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    processing_time_ms: float = 0.0
    forensic_disclaimer: str = (
        "AI ENHANCED - NOT ORIGINAL EVIDENCE. "
        "Original source recordings in storage/recordings/ remain unaltered and immutable. "
        "Enhanced outputs reflect algorithmically reconstructed acutance and dynamic range."
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save_json(self, json_path: str) -> None:
        p = Path(json_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


class EnhancementPipeline:
    """
    Orchestrates the enhancement sequence:
    1. Denoise (clean sensor noise before dynamic expansion)
    2. Low-Light / Dehaze (restore luminance & visibility)
    3. Sharpen (clarify optical edges with noise gating)
    4. Super-Resolution (upscale 2x/4x with OpenVINO or Lanczos-4)
    5. Forensic Watermarking (burn legal evidence notice)
    """

    def __init__(self, preferred_device: str = "AUTO") -> None:
        self.low_light_enhancer = LowLightEnhancer()
        self.dehaze_enhancer = DehazeEnhancer()
        self.denoise_enhancer = DenoiseEnhancer()
        self.sharpening_enhancer = SharpeningEnhancer()
        self.super_resolution_enhancer = SuperResolutionEnhancer(preferred_device=preferred_device)

    def process_frame(self, frame: np.ndarray, config: EnhancementConfig) -> np.ndarray:
        """
        Process a single video frame synchronously through the pipeline.
        """
        if frame is None or frame.size == 0:
            return frame

        out = frame.copy()

        # Step 1: Denoise first to avoid amplifying noise floor
        if config.denoise_enabled:
            out = self.denoise_enhancer.enhance(
                out,
                method=config.denoise_method,
                h=config.denoise_h,
                h_color=config.denoise_h_color,
                bilateral_d=config.bilateral_d,
                bilateral_sigma_color=config.bilateral_sigma_color,
                bilateral_sigma_space=config.bilateral_sigma_space,
                edge_preservation_blend=config.denoise_edge_blend,
            )

        # Step 2: Low-light enhancement
        if config.low_light_enabled:
            out = self.low_light_enhancer.enhance(
                out,
                method=config.low_light_method,
                clip_limit=config.low_light_clip_limit,
                gamma=config.low_light_gamma,
                noise_gate=config.low_light_noise_gate,
                noise_gate_threshold=config.low_light_threshold,
            )

        # Step 3: Dehazing
        if config.dehaze_enabled:
            out = self.dehaze_enhancer.enhance(
                out,
                patch_size=config.dehaze_patch_size,
                omega=config.dehaze_omega,
                t0=config.dehaze_t0,
            )

        # Step 4: Sharpening
        if config.sharpen_enabled:
            out = self.sharpening_enhancer.enhance(
                out,
                method=config.sharpen_method,
                alpha=config.sharpen_alpha,
                radius=config.sharpen_radius,
                threshold=config.sharpen_threshold,
                direction_angle_deg=config.motion_angle_deg,
                motion_length=config.motion_length,
            )

        # Step 5: Super-Resolution & Watermarking
        if config.super_resolution_enabled and config.super_resolution_scale > 1:
            out = self.super_resolution_enhancer.enhance(
                out,
                scale=config.super_resolution_scale,
                add_watermark=config.watermark_enabled,
                watermark_text=config.watermark_text,
                interpolation=config.super_resolution_interp,
            )
        elif config.watermark_enabled:
            label = config.watermark_text or SuperResolutionEnhancer.WATERMARK_LABEL_GENERIC
            out = SuperResolutionEnhancer.apply_watermark(out, text=label)

        return out

    def process_image_file(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        config: Optional[EnhancementConfig] = None,
        operator: str = "SYSTEM_ADMIN",
    ) -> Tuple[str, EnhancementManifest]:
        """
        Enhance a still image snapshot file non-destructively, saving output into storage/enhanced/.
        """
        if config is None:
            config = EnhancementConfig()

        in_p = Path(input_path)
        if not in_p.exists():
            raise FileNotFoundError(f"Source file not found: {input_path}")

        # Compute source SHA-256
        source_sha256 = self._compute_sha256(str(in_p))

        frame = cv2.imread(str(in_p))
        if frame is None:
            raise ValueError(f"Failed to read image: {input_path}")

        src_h, src_w = frame.shape[:2]

        t0 = time.perf_counter()
        enhanced_frame = self.process_frame(frame, config)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        enh_h, enh_w = enhanced_frame.shape[:2]

        if output_path is None:
            now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            target_dir = Path(settings.storage.enhanced_dir) / "snapshots"
            target_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(target_dir / f"enhanced_{in_p.stem}_{now_str}{in_p.suffix}")
        else:
            out_p = Path(output_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)

        cv2.imwrite(output_path, enhanced_frame)
        enhanced_sha256 = self._compute_sha256(output_path)

        manifest = EnhancementManifest(
            source_path=str(in_p.resolve()),
            source_sha256=source_sha256,
            source_resolution=(src_w, src_h),
            enhanced_path=str(Path(output_path).resolve()),
            enhanced_sha256=enhanced_sha256,
            enhanced_resolution=(enh_w, enh_h),
            config_applied=config.to_dict(),
            operator=operator,
            processing_time_ms=round(elapsed_ms, 2),
        )

        manifest_path = f"{output_path}.manifest.json"
        manifest.save_json(manifest_path)

        return output_path, manifest

    def process_video_clip(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        config: Optional[EnhancementConfig] = None,
        start_time_sec: float = 0.0,
        duration_sec: Optional[float] = None,
        progress_cb: Optional[Callable[[int, int, float], None]] = None,
        operator: str = "SYSTEM_ADMIN",
        cancel_event: Optional[threading.Event] = None,
    ) -> Tuple[str, EnhancementManifest]:
        """
        Process a video clip file non-destructively, saving output into storage/enhanced/.
        """
        if config is None:
            config = EnhancementConfig()

        in_p = Path(input_path)
        if not in_p.exists():
            raise FileNotFoundError(f"Source video not found: {input_path}")

        source_sha256 = self._compute_sha256(str(in_p))

        cap = cv2.VideoCapture(str(in_p))
        if not cap.isOpened():
            raise ValueError(f"Failed to open video file: {input_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        start_frame = int(start_time_sec * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        if duration_sec is not None:
            frames_to_process = min(int(duration_sec * fps), total_frames - start_frame)
        else:
            frames_to_process = total_frames - start_frame

        frames_to_process = max(1, frames_to_process)

        scale = config.super_resolution_scale if (config.super_resolution_enabled and config.super_resolution_scale > 1) else 1
        out_w = src_w * scale
        out_h = src_h * scale

        if output_path is None:
            now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            target_dir = Path(settings.storage.enhanced_dir) / "recordings"
            target_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(target_dir / f"enhanced_{in_p.stem}_{now_str}.mp4")
        else:
            out_p = Path(output_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(output_path, fourcc, fps, (out_w, out_h))

        processed_count = 0
        t0 = time.perf_counter()

        try:
            while processed_count < frames_to_process:
                if cancel_event is not None and cancel_event.is_set():
                    logger.info("Enhancement clip processing cancelled by operator.")
                    break

                ret, frame = cap.read()
                if not ret:
                    break

                enhanced_frame = self.process_frame(frame, config)
                writer.write(enhanced_frame)
                processed_count += 1

                if progress_cb is not None and processed_count % 5 == 0:
                    pct = (processed_count / float(frames_to_process)) * 100.0
                    progress_cb(processed_count, frames_to_process, pct)
        finally:
            cap.release()
            writer.release()

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        enhanced_sha256 = self._compute_sha256(output_path)

        manifest = EnhancementManifest(
            source_path=str(in_p.resolve()),
            source_sha256=source_sha256,
            source_resolution=(src_w, src_h),
            enhanced_path=str(Path(output_path).resolve()),
            enhanced_sha256=enhanced_sha256,
            enhanced_resolution=(out_w, out_h),
            config_applied=config.to_dict(),
            operator=operator,
            processing_time_ms=round(elapsed_ms, 2),
        )

        manifest_path = f"{output_path}.manifest.json"
        manifest.save_json(manifest_path)

        return output_path, manifest

    @staticmethod
    def _compute_sha256(filepath: str) -> str:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()


class EnhancementWorker(threading.Thread):
    """
    Background worker thread for asynchronous video enhancement.
    Decoupled from PySide6 UI and live streaming threads to guarantee 0 FPS drop.
    """

    def __init__(
        self,
        pipeline: EnhancementPipeline,
        input_path: str,
        output_path: Optional[str] = None,
        config: Optional[EnhancementConfig] = None,
        start_time_sec: float = 0.0,
        duration_sec: Optional[float] = None,
        on_progress: Optional[Callable[[int, int, float], None]] = None,
        on_complete: Optional[Callable[[str, EnhancementManifest], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        super().__init__(daemon=True)
        self.pipeline = pipeline
        self.input_path = input_path
        self.output_path = output_path
        self.config = config or EnhancementConfig()
        self.start_time_sec = start_time_sec
        self.duration_sec = duration_sec
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.on_error = on_error
        self.cancel_event = threading.Event()
        self.result_path: Optional[str] = None
        self.manifest: Optional[EnhancementManifest] = None

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            out_path, manifest = self.pipeline.process_video_clip(
                input_path=self.input_path,
                output_path=self.output_path,
                config=self.config,
                start_time_sec=self.start_time_sec,
                duration_sec=self.duration_sec,
                progress_cb=self.on_progress,
                cancel_event=self.cancel_event,
            )
            self.result_path = out_path
            self.manifest = manifest
            if self.on_complete is not None:
                self.on_complete(out_path, manifest)
        except Exception as e:
            logger.error("Enhancement worker encountered error: %s", e, exc_info=True)
            if self.on_error is not None:
                self.on_error(e)
