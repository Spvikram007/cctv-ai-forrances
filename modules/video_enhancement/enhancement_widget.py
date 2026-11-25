"""
Video Enhancement Command Workspace (Phase 9 - F-045).
Comprehensive PySide6 GUI featuring interactive split-screen comparative canvas,
real-time filter sliders, preset profiles, and asynchronous export to storage/enhanced/
with cryptographic SHA-256 audit manifests.
"""

import os
import time
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QLabel,
    QPushButton,
    QComboBox,
    QSlider,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QGroupBox,
    QFormLayout,
    QFileDialog,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QFrame,
    QRadioButton,
    QButtonGroup,
)

import cv2
import numpy as np

from core.logging.logger import get_logger
from core.config.settings import settings
from engines.enhancement_engine.enhancement_pipeline import (
    EnhancementConfig,
    EnhancementPipeline,
    EnhancementWorker,
    EnhancementManifest,
    PresetProfile,
)
from modules.video_enhancement.comparison_view import ComparisonSplitView

logger = get_logger("enhancement_widget")


class VideoEnhancementWidget(QWidget):
    """
    Primary workspace widget for non-destructive video enhancement.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.pipeline = EnhancementPipeline(preferred_device=settings.ai.preferred_device)
        self._current_orig_frame: Optional[np.ndarray] = None
        self._current_enh_frame: Optional[np.ndarray] = None
        self._current_source_path: Optional[str] = None
        self._active_worker: Optional[EnhancementWorker] = None

        self._init_ui()
        self._load_sample_frame()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(10)

        # 1. Header Toolbar
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        lbl_title = QLabel("VIDEO ENHANCEMENT & AI SUPER-RESOLUTION")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #58a6ff;")
        lbl_sub = QLabel("Non-Destructive Forensic Video & Image Restoration | Phase 9")
        lbl_sub.setStyleSheet("font-size: 11px; color: #8b949e;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        # Preset Dropdown
        lbl_preset = QLabel("Preset:")
        lbl_preset.setStyleSheet("color: #c9d1d9; font-weight: 600;")
        header_layout.addWidget(lbl_preset)

        self.cmb_preset = QComboBox()
        self.cmb_preset.addItems([
            "Neutral (Reset)",
            "Night Vision (Low-Light + Denoise)",
            "Fog & Smoke Penetration (Dehaze)",
            "License Plate Clarity (Sharpen + 2x SR)",
            "Face Detail (Lab CLAHE + Denoise + 2x SR)",
        ])
        self.cmb_preset.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 4px 8px; border-radius: 4px;")
        self.cmb_preset.currentIndexChanged.connect(self._on_preset_changed)
        header_layout.addWidget(self.cmb_preset)

        # Media Load Buttons
        btn_load_img = QPushButton("Load Snapshot")
        btn_load_img.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 5px 12px; border-radius: 4px;")
        btn_load_img.clicked.connect(self._load_image_dialog)
        header_layout.addWidget(btn_load_img)

        btn_load_vid = QPushButton("Load Clip")
        btn_load_vid.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 5px 12px; border-radius: 4px;")
        btn_load_vid.clicked.connect(self._load_video_dialog)
        header_layout.addWidget(btn_load_vid)

        btn_demo = QPushButton("Generate Test Frame")
        btn_demo.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; color: #58a6ff; padding: 5px 12px; border-radius: 4px;")
        btn_demo.clicked.connect(self._load_sample_frame)
        header_layout.addWidget(btn_demo)

        main_layout.addLayout(header_layout)

        # 2. Main Workspace Splitter (Viewer on left, Controls on right)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(4)

        # Left: Comparative Canvas & Controls
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.view_canvas = ComparisonSplitView()
        left_layout.addWidget(self.view_canvas, stretch=1)

        # Canvas bottom bar (View mode toggle & Split slider)
        canvas_bar = QHBoxLayout()
        lbl_mode = QLabel("View Mode:")
        lbl_mode.setStyleSheet("color: #8b949e; font-size: 11px;")
        canvas_bar.addWidget(lbl_mode)

        self.btn_mode_split = QPushButton("Split Slider")
        self.btn_mode_split.setCheckable(True)
        self.btn_mode_split.setChecked(True)
        self.btn_mode_split.setStyleSheet("background-color: #1f6feb; color: white; border-radius: 4px; padding: 3px 8px; font-size: 11px;")
        self.btn_mode_split.clicked.connect(lambda: self._set_mode("split"))
        canvas_bar.addWidget(self.btn_mode_split)

        self.btn_mode_sbs = QPushButton("Side-by-Side")
        self.btn_mode_sbs.setCheckable(True)
        self.btn_mode_sbs.setStyleSheet("background-color: #21262d; color: #c9d1d9; border-radius: 4px; padding: 3px 8px; font-size: 11px;")
        self.btn_mode_sbs.clicked.connect(lambda: self._set_mode("side_by_side"))
        canvas_bar.addWidget(self.btn_mode_sbs)

        canvas_bar.addSpacing(16)
        lbl_slider = QLabel("Split Position:")
        lbl_slider.setStyleSheet("color: #8b949e; font-size: 11px;")
        canvas_bar.addWidget(lbl_slider)

        self.slider_split = QSlider(Qt.Horizontal)
        self.slider_split.setRange(2, 98)
        self.slider_split.setValue(50)
        self.slider_split.valueChanged.connect(lambda v: self.view_canvas.set_split_ratio(v / 100.0))
        self.view_canvas.split_position_changed.connect(lambda r: self.slider_split.setValue(int(r * 100)))
        canvas_bar.addWidget(self.slider_split)

        canvas_bar.addStretch()
        self.lbl_canvas_info = QLabel("Frame: 1280x720 | 0 ms")
        self.lbl_canvas_info.setStyleSheet("color: #8b949e; font-size: 11px;")
        canvas_bar.addWidget(self.lbl_canvas_info)

        left_layout.addLayout(canvas_bar)
        splitter.addWidget(left_widget)

        # Right: Parameter Control Sidebar (Scrollable)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumWidth(360)
        scroll_area.setMaximumWidth(440)
        scroll_area.setStyleSheet("QScrollArea { border: 1px solid #30363d; background-color: #161b22; }")

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(12)

        # Panel 1: Low-Light Enhancement (F-040)
        box_low_light = QGroupBox("Low-Light Enhancement (F-040)")
        box_low_light.setStyleSheet("QGroupBox { color: #58a6ff; font-weight: 600; border: 1px solid #30363d; border-radius: 6px; margin-top: 6px; padding: 10px; }")
        fl_low = QFormLayout(box_low_light)

        self.chk_low_light = QCheckBox("Enable Low-Light Enhancement")
        self.chk_low_light.setStyleSheet("color: #c9d1d9; font-weight: 500;")
        self.chk_low_light.toggled.connect(self._on_param_changed)
        fl_low.addRow(self.chk_low_light)

        self.cmb_low_light_method = QComboBox()
        self.cmb_low_light_method.addItems(["clahe_lab", "retinex", "gamma", "combined"])
        self.cmb_low_light_method.setStyleSheet("background-color: #21262d; color: #c9d1d9;")
        self.cmb_low_light_method.currentIndexChanged.connect(self._on_param_changed)
        fl_low.addRow("Algorithm:", self.cmb_low_light_method)

        self.spn_clip_limit = QDoubleSpinBox()
        self.spn_clip_limit.setRange(1.0, 10.0)
        self.spn_clip_limit.setSingleStep(0.5)
        self.spn_clip_limit.setValue(2.5)
        self.spn_clip_limit.setStyleSheet("background-color: #21262d; color: #c9d1d9;")
        self.spn_clip_limit.valueChanged.connect(self._on_param_changed)
        fl_low.addRow("CLAHE Clip:", self.spn_clip_limit)

        self.spn_gamma = QDoubleSpinBox()
        self.spn_gamma.setRange(0.2, 1.5)
        self.spn_gamma.setSingleStep(0.05)
        self.spn_gamma.setValue(0.60)
        self.spn_gamma.setStyleSheet("background-color: #21262d; color: #c9d1d9;")
        self.spn_gamma.valueChanged.connect(self._on_param_changed)
        fl_low.addRow("Target Gamma:", self.spn_gamma)

        self.chk_noise_gate = QCheckBox("Noise-Floor Gating (Near-Black Protection)")
        self.chk_noise_gate.setChecked(True)
        self.chk_noise_gate.setStyleSheet("color: #8b949e;")
        self.chk_noise_gate.toggled.connect(self._on_param_changed)
        fl_low.addRow(self.chk_noise_gate)
        right_layout.addWidget(box_low_light)

        # Panel 2: Dehazing & Visibility (F-041)
        box_dehaze = QGroupBox("Dehazing & Atmospheric Clarity (F-041)")
        box_dehaze.setStyleSheet("QGroupBox { color: #58a6ff; font-weight: 600; border: 1px solid #30363d; border-radius: 6px; margin-top: 6px; padding: 10px; }")
        fl_dehaze = QFormLayout(box_dehaze)

        self.chk_dehaze = QCheckBox("Enable Haze / Smoke Penetration")
        self.chk_dehaze.setStyleSheet("color: #c9d1d9; font-weight: 500;")
        self.chk_dehaze.toggled.connect(self._on_param_changed)
        fl_dehaze.addRow(self.chk_dehaze)

        self.spn_omega = QDoubleSpinBox()
        self.spn_omega.setRange(0.5, 1.0)
        self.spn_omega.setSingleStep(0.05)
        self.spn_omega.setValue(0.95)
        self.spn_omega.setStyleSheet("background-color: #21262d; color: #c9d1d9;")
        self.spn_omega.valueChanged.connect(self._on_param_changed)
        fl_dehaze.addRow("Removal (Omega):", self.spn_omega)

        self.spn_t0 = QDoubleSpinBox()
        self.spn_t0.setRange(0.05, 0.40)
        self.spn_t0.setSingleStep(0.05)
        self.spn_t0.setValue(0.10)
        self.spn_t0.setStyleSheet("background-color: #21262d; color: #c9d1d9;")
        self.spn_t0.valueChanged.connect(self._on_param_changed)
        fl_dehaze.addRow("Floor (t0):", self.spn_t0)
        right_layout.addWidget(box_dehaze)

        # Panel 3: Denoising & Smoothing (F-042)
        box_denoise = QGroupBox("Denoising & Image Restoration (F-042)")
        box_denoise.setStyleSheet("QGroupBox { color: #58a6ff; font-weight: 600; border: 1px solid #30363d; border-radius: 6px; margin-top: 6px; padding: 10px; }")
        fl_denoise = QFormLayout(box_denoise)

        self.chk_denoise = QCheckBox("Enable Sensor Noise Reduction")
        self.chk_denoise.setStyleSheet("color: #c9d1d9; font-weight: 500;")
        self.chk_denoise.toggled.connect(self._on_param_changed)
        fl_denoise.addRow(self.chk_denoise)

        self.cmb_denoise_method = QComboBox()
        self.cmb_denoise_method.addItems(["nlmeans", "bilateral", "fast"])
        self.cmb_denoise_method.setStyleSheet("background-color: #21262d; color: #c9d1d9;")
        self.cmb_denoise_method.currentIndexChanged.connect(self._on_param_changed)
        fl_denoise.addRow("Filter Method:", self.cmb_denoise_method)

        self.spn_denoise_h = QDoubleSpinBox()
        self.spn_denoise_h.setRange(2.0, 25.0)
        self.spn_denoise_h.setSingleStep(1.0)
        self.spn_denoise_h.setValue(8.0)
        self.spn_denoise_h.setStyleSheet("background-color: #21262d; color: #c9d1d9;")
        self.spn_denoise_h.valueChanged.connect(self._on_param_changed)
        fl_denoise.addRow("Strength (h):", self.spn_denoise_h)
        right_layout.addWidget(box_denoise)

        # Panel 4: Sharpening & Deblur (F-043)
        box_sharpen = QGroupBox("Motion Deblur & Sharpening (F-043)")
        box_sharpen.setStyleSheet("QGroupBox { color: #58a6ff; font-weight: 600; border: 1px solid #30363d; border-radius: 6px; margin-top: 6px; padding: 10px; }")
        fl_sharpen = QFormLayout(box_sharpen)

        self.chk_sharpen = QCheckBox("Enable Edge Sharpening")
        self.chk_sharpen.setStyleSheet("color: #c9d1d9; font-weight: 500;")
        self.chk_sharpen.toggled.connect(self._on_param_changed)
        fl_sharpen.addRow(self.chk_sharpen)

        self.cmb_sharpen_method = QComboBox()
        self.cmb_sharpen_method.addItems(["unsharp", "laplacian", "directional"])
        self.cmb_sharpen_method.setStyleSheet("background-color: #21262d; color: #c9d1d9;")
        self.cmb_sharpen_method.currentIndexChanged.connect(self._on_param_changed)
        fl_sharpen.addRow("Method:", self.cmb_sharpen_method)

        self.spn_sharpen_alpha = QDoubleSpinBox()
        self.spn_sharpen_alpha.setRange(0.2, 3.5)
        self.spn_sharpen_alpha.setSingleStep(0.2)
        self.spn_sharpen_alpha.setValue(1.2)
        self.spn_sharpen_alpha.setStyleSheet("background-color: #21262d; color: #c9d1d9;")
        self.spn_sharpen_alpha.valueChanged.connect(self._on_param_changed)
        fl_sharpen.addRow("Sharpness (Alpha):", self.spn_sharpen_alpha)
        right_layout.addWidget(box_sharpen)

        # Panel 5: AI Super-Resolution (F-044)
        box_sr = QGroupBox("AI Super-Resolution (F-044)")
        box_sr.setStyleSheet("QGroupBox { color: #58a6ff; font-weight: 600; border: 1px solid #30363d; border-radius: 6px; margin-top: 6px; padding: 10px; }")
        fl_sr = QFormLayout(box_sr)

        self.chk_sr = QCheckBox("Enable Super-Resolution")
        self.chk_sr.setStyleSheet("color: #c9d1d9; font-weight: 500;")
        self.chk_sr.toggled.connect(self._on_param_changed)
        fl_sr.addRow(self.chk_sr)

        scale_box = QHBoxLayout()
        self.rb_sr_2x = QRadioButton("2x Scale")
        self.rb_sr_2x.setChecked(True)
        self.rb_sr_2x.setStyleSheet("color: #c9d1d9;")
        self.rb_sr_2x.toggled.connect(self._on_param_changed)
        self.rb_sr_4x = QRadioButton("4x Scale")
        self.rb_sr_4x.setStyleSheet("color: #c9d1d9;")
        self.rb_sr_4x.toggled.connect(self._on_param_changed)
        scale_box.addWidget(self.rb_sr_2x)
        scale_box.addWidget(self.rb_sr_4x)
        scale_box.addStretch()
        fl_sr.addRow("Target Scale:", scale_box)

        lbl_device = QLabel(f"Device: {self.pipeline.super_resolution_enhancer.active_device}")
        lbl_device.setStyleSheet("color: #3fb950; font-size: 11px; font-weight: 600;")
        fl_sr.addRow(lbl_device)

        self.chk_watermark = QCheckBox("Forensic Watermark (Enforced)")
        self.chk_watermark.setChecked(True)
        self.chk_watermark.setEnabled(False)  # Strictly non-negotiable for forensic truthfulness
        self.chk_watermark.setStyleSheet("color: #8b949e; font-size: 10px;")
        fl_sr.addRow(self.chk_watermark)
        right_layout.addWidget(box_sr)

        # Panel 6: Non-Destructive Actions & Manifest Info (F-045)
        box_export = QGroupBox("Non-Destructive Export & Audit (F-045)")
        box_export.setStyleSheet("QGroupBox { color: #3fb950; font-weight: 600; border: 1px solid #238636; border-radius: 6px; margin-top: 6px; padding: 10px; }")
        export_layout = QVBoxLayout(box_export)

        btn_apply = QPushButton("Apply Parameters & Preview")
        btn_apply.setStyleSheet("background-color: #1f6feb; color: white; font-weight: 600; padding: 8px; border-radius: 4px;")
        btn_apply.clicked.connect(self._apply_pipeline)
        export_layout.addWidget(btn_apply)

        btn_export = QPushButton("Export Enhanced Media...")
        btn_export.setStyleSheet("background-color: #238636; color: white; font-weight: 600; padding: 8px; border-radius: 4px;")
        btn_export.clicked.connect(self._export_media_dialog)
        export_layout.addWidget(btn_export)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { border: 1px solid #30363d; border-radius: 4px; text-align: center; } QProgressBar::chunk { background-color: #238636; }")
        export_layout.addWidget(self.progress_bar)

        self.lbl_export_info = QLabel("Isolation: storage/enhanced/ | Source untouched")
        self.lbl_export_info.setStyleSheet("color: #8b949e; font-size: 10px;")
        self.lbl_export_info.setWordWrap(True)
        export_layout.addWidget(self.lbl_export_info)

        right_layout.addWidget(box_export)
        right_layout.addStretch()

        scroll_area.setWidget(right_widget)
        splitter.addWidget(scroll_area)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

    def _set_mode(self, mode: str) -> None:
        """Switch canvas view mode."""
        self.btn_mode_split.setChecked(mode == "split")
        self.btn_mode_sbs.setChecked(mode == "side_by_side")

        if mode == "split":
            self.btn_mode_split.setStyleSheet("background-color: #1f6feb; color: white; border-radius: 4px; padding: 3px 8px; font-size: 11px;")
            self.btn_mode_sbs.setStyleSheet("background-color: #21262d; color: #c9d1d9; border-radius: 4px; padding: 3px 8px; font-size: 11px;")
        else:
            self.btn_mode_sbs.setStyleSheet("background-color: #1f6feb; color: white; border-radius: 4px; padding: 3px 8px; font-size: 11px;")
            self.btn_mode_split.setStyleSheet("background-color: #21262d; color: #c9d1d9; border-radius: 4px; padding: 3px 8px; font-size: 11px;")

        self.view_canvas.set_view_mode(mode)

    def _get_current_config(self) -> EnhancementConfig:
        """Constructs an EnhancementConfig from UI widgets."""
        scale = 1
        if self.chk_sr.isChecked():
            scale = 4 if self.rb_sr_4x.isChecked() else 2

        return EnhancementConfig(
            low_light_enabled=self.chk_low_light.isChecked(),
            low_light_method=self.cmb_low_light_method.currentText(),
            low_light_clip_limit=self.spn_clip_limit.value(),
            low_light_gamma=self.spn_gamma.value(),
            low_light_noise_gate=self.chk_noise_gate.isChecked(),
            dehaze_enabled=self.chk_dehaze.isChecked(),
            dehaze_omega=self.spn_omega.value(),
            dehaze_t0=self.spn_t0.value(),
            denoise_enabled=self.chk_denoise.isChecked(),
            denoise_method=self.cmb_denoise_method.currentText(),
            denoise_h=self.spn_denoise_h.value(),
            sharpen_enabled=self.chk_sharpen.isChecked(),
            sharpen_method=self.cmb_sharpen_method.currentText(),
            sharpen_alpha=self.spn_sharpen_alpha.value(),
            super_resolution_enabled=self.chk_sr.isChecked(),
            super_resolution_scale=scale,
            watermark_enabled=True,
        )

    def _on_param_changed(self) -> None:
        """Auto-preview on small images or user triggers."""
        # Optional: trigger preview
        pass

    def _on_preset_changed(self, index: int) -> None:
        """Applies a preset configuration."""
        if index == 0:
            cfg = PresetProfile.neutral()
        elif index == 1:
            cfg = PresetProfile.night_vision()
        elif index == 2:
            cfg = PresetProfile.fog_penetration()
        elif index == 3:
            cfg = PresetProfile.license_plate_clarity()
        elif index == 4:
            cfg = PresetProfile.face_detail()
        else:
            return

        # Block signals temporarily to prevent redundant updates
        self.chk_low_light.setChecked(cfg.low_light_enabled)
        idx_ll = self.cmb_low_light_method.findText(cfg.low_light_method)
        if idx_ll >= 0:
            self.cmb_low_light_method.setCurrentIndex(idx_ll)
        self.spn_clip_limit.setValue(cfg.low_light_clip_limit)
        self.spn_gamma.setValue(cfg.low_light_gamma)
        self.chk_noise_gate.setChecked(cfg.low_light_noise_gate)

        self.chk_dehaze.setChecked(cfg.dehaze_enabled)
        self.spn_omega.setValue(cfg.dehaze_omega)
        self.spn_t0.setValue(cfg.dehaze_t0)

        self.chk_denoise.setChecked(cfg.denoise_enabled)
        idx_dn = self.cmb_denoise_method.findText(cfg.denoise_method)
        if idx_dn >= 0:
            self.cmb_denoise_method.setCurrentIndex(idx_dn)
        self.spn_denoise_h.setValue(cfg.denoise_h)

        self.chk_sharpen.setChecked(cfg.sharpen_enabled)
        idx_sh = self.cmb_sharpen_method.findText(cfg.sharpen_method)
        if idx_sh >= 0:
            self.cmb_sharpen_method.setCurrentIndex(idx_sh)
        self.spn_sharpen_alpha.setValue(cfg.sharpen_alpha)

        self.chk_sr.setChecked(cfg.super_resolution_enabled)
        if cfg.super_resolution_scale == 4:
            self.rb_sr_4x.setChecked(True)
        else:
            self.rb_sr_2x.setChecked(True)

        self._apply_pipeline()

    def _apply_pipeline(self) -> None:
        """Processes the loaded frame through the pipeline and updates the canvas."""
        if self._current_orig_frame is None:
            return

        cfg = self._get_current_config()
        t0 = time.perf_counter()
        self._current_enh_frame = self.pipeline.process_frame(self._current_orig_frame, cfg)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.view_canvas.set_images(self._current_orig_frame, self._current_enh_frame)

        src_h, src_w = self._current_orig_frame.shape[:2]
        enh_h, enh_w = self._current_enh_frame.shape[:2]
        self.lbl_canvas_info.setText(
            f"Source: {src_w}x{src_h} | Output: {enh_w}x{enh_h} | Latency: {elapsed_ms:.1f} ms"
        )

    def _load_sample_frame(self) -> None:
        """Generates a synthetic surveillance test frame for validation."""
        h, w = 720, 1280
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        # Low-light gradient background
        for y in range(h):
            val = int(15 + 30 * (y / float(h)))
            frame[y, :] = [val, val, val]

        # Street lamp glow (low-light test target)
        cv2.circle(frame, (900, 200), 120, (180, 210, 255), -1)
        cv2.circle(frame, (900, 200), 60, (230, 245, 255), -1)

        # Vehicle & license plate mockup
        cv2.rectangle(frame, (250, 360), (750, 580), (45, 45, 60), -1)
        cv2.rectangle(frame, (400, 500), (600, 550), (200, 200, 200), -1)
        cv2.putText(frame, "KA-01-MJ-5020", (415, 538), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)

        # Person silhouette mockup
        cv2.ellipse(frame, (180, 420), (35, 75), 0, 0, 360, (30, 30, 30), -1)
        cv2.circle(frame, (180, 320), 25, (40, 40, 40), -1)

        # Add simulated sensor noise and haze
        noise = np.random.normal(0, 8, frame.shape).astype(np.int16)
        noisy = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        # Subtle haze overlay
        haze = np.full_like(frame, 40)
        simulated = cv2.addWeighted(noisy, 0.75, haze, 0.25, 0)

        self._current_orig_frame = simulated
        self._current_source_path = "sample_surveillance_frame.png"
        self._apply_pipeline()

    def _load_image_dialog(self) -> None:
        """Loads an image snapshot from disk."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Surveillance Snapshot",
            settings.storage.snapshots_dir,
            "Images (*.png *.jpg *.jpeg *.bmp)",
        )
        if path:
            frame = cv2.imread(path)
            if frame is not None:
                self._current_orig_frame = frame
                self._current_source_path = path
                self._apply_pipeline()
            else:
                QMessageBox.warning(self, "Read Error", f"Could not load image from {path}")

    def _load_video_dialog(self) -> None:
        """Loads a video recording clip from disk."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Surveillance Recording Clip",
            settings.storage.recordings_dir,
            "Video Files (*.mp4 *.avi *.mkv *.ts)",
        )
        if path:
            cap = cv2.VideoCapture(path)
            ret, frame = cap.read()
            cap.release()
            if ret and frame is not None:
                self._current_orig_frame = frame
                self._current_source_path = path
                self._apply_pipeline()
            else:
                QMessageBox.warning(self, "Read Error", f"Could not extract frame from {path}")

    def _export_media_dialog(self) -> None:
        """Exports enhanced media non-destructively to storage/enhanced/."""
        if self._current_orig_frame is None:
            QMessageBox.information(self, "No Media", "Please load an image or clip first.")
            return

        cfg = self._get_current_config()

        # Ask whether to export current snapshot or full video if source is video
        is_video = bool(self._current_source_path and Path(self._current_source_path).suffix.lower() in (".mp4", ".avi", ".mkv"))

        if is_video:
            reply = QMessageBox.question(
                self,
                "Export Choice",
                "Source is a video clip. Export full enhanced video clip?\n(Select 'No' to export single frame snapshot only)",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Cancel:
                return
            if reply == QMessageBox.Yes:
                self._start_video_export(self._current_source_path, cfg)
                return

        # Snapshot export
        default_dir = Path(settings.storage.enhanced_dir) / "snapshots"
        default_dir.mkdir(parents=True, exist_ok=True)
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Enhanced Snapshot (Non-Destructive)",
            str(default_dir / "enhanced_snapshot.png"),
            "PNG Image (*.png);;JPEG Image (*.jpg)",
        )
        if out_path:
            try:
                # Save temp source if it was synthetic
                src_path = self._current_source_path
                if src_path == "sample_surveillance_frame.png" or not os.path.exists(str(src_path)):
                    src_temp = str(default_dir / "temp_source.png")
                    cv2.imwrite(src_temp, self._current_orig_frame)
                    src_path = src_temp

                saved_path, manifest = self.pipeline.process_image_file(
                    input_path=src_path,
                    output_path=out_path,
                    config=cfg,
                )
                self.lbl_export_info.setText(
                    f"Exported: {Path(saved_path).name}\nSHA-256: {manifest.enhanced_sha256[:16]}...\nManifest: {Path(saved_path).name}.manifest.json"
                )
                QMessageBox.information(
                    self,
                    "Export Complete",
                    f"Enhanced output saved to:\n{saved_path}\n\nSidecar audit manifest created.\nSource recording was unaltered.",
                )
            except Exception as e:
                logger.error("Export failed: %s", e, exc_info=True)
                QMessageBox.critical(self, "Export Failed", str(e))

    def _start_video_export(self, video_path: str, cfg: EnhancementConfig) -> None:
        """Starts asynchronous background worker for video clip enhancement."""
        default_dir = Path(settings.storage.enhanced_dir) / "recordings"
        default_dir.mkdir(parents=True, exist_ok=True)
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Enhanced Video Clip",
            str(default_dir / f"enhanced_{Path(video_path).stem}.mp4"),
            "MP4 Video (*.mp4)",
        )
        if not out_path:
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        def on_prog(curr: int, total: int, pct: float) -> None:
            QTimer.singleShot(0, lambda: self.progress_bar.setValue(int(pct)))

        def on_done(saved_path: str, manifest: EnhancementManifest) -> None:
            def _update() -> None:
                self.progress_bar.setVisible(False)
                self.lbl_export_info.setText(
                    f"Saved: {Path(saved_path).name}\nSHA-256: {manifest.enhanced_sha256[:16]}..."
                )
                QMessageBox.information(
                    self,
                    "Clip Export Complete",
                    f"Enhanced clip successfully written to:\n{saved_path}\n\nAudit manifest saved.",
                )
            QTimer.singleShot(0, _update)

        def on_err(err: Exception) -> None:
            def _err() -> None:
                self.progress_bar.setVisible(False)
                QMessageBox.critical(self, "Export Error", f"Clip processing failed:\n{err}")
            QTimer.singleShot(0, _err)

        self._active_worker = EnhancementWorker(
            pipeline=self.pipeline,
            input_path=video_path,
            output_path=out_path,
            config=cfg,
            on_progress=on_prog,
            on_complete=on_done,
            on_error=on_err,
        )
        self._active_worker.start()
