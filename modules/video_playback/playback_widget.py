"""
Playback Workspace Component.
Provides multi-camera synchronized recorded video playback, 1/4/9/16 grid layouts,
master playback clock controls (play/pause/stop/seek/step/speeds),
interactive timeline scrubbing, and forensic video clip export dialog.
"""

import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QComboBox, QDateEdit, QDateTimeEdit, QFileDialog,
    QDialog, QProgressBar, QCheckBox, QTextEdit, QLineEdit, QMessageBox, QFrame
)
from PySide6.QtCore import Qt, QTimer, QDate, QDateTime, Signal, QThread
from PySide6.QtGui import QFont, QIcon

from modules.live_monitoring.video_widget import VideoTileWidget
from modules.video_playback.timeline_widget import TimelineWidget
from engines.video_engine.playback_controller import playback_controller, PlaybackState
from engines.video_engine.video_exporter import video_exporter
from database.database_manager import db_manager
from database.models.devices import DeviceChannel, Device
from core.logging.logger import get_logger

logger = get_logger("playback_widget")


class ExportWorkerThread(QThread):
    """Background worker thread for video clip export."""
    progress = Signal(float)
    finished_job = Signal(object)
    failed = Signal(str)

    def __init__(self, channel_id: str, start_dt: datetime, end_dt: datetime,
                 out_path: str, is_evidence: bool, notes: str):
        super().__init__()
        self.channel_id = channel_id
        self.start_dt = start_dt
        self.end_dt = end_dt
        self.out_path = out_path
        self.is_evidence = is_evidence
        self.notes = notes

    def run(self):
        try:
            job = video_exporter.export_clip(
                channel_id=self.channel_id,
                start_time=self.start_dt,
                end_time=self.end_dt,
                output_path=self.out_path,
                is_evidence=self.is_evidence,
                notes=self.notes,
                progress_callback=lambda pct: self.progress.emit(pct),
            )
            self.finished_job.emit(job)
        except Exception as exc:
            self.failed.emit(str(exc))


class ClipExportDialog(QDialog):
    """Forensic Clip Export Dialog with SHA-256 integrity hashing and evidence locking."""

    def __init__(self, channel_id: str, default_start: datetime, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Export Surveillance Video Clip (MP4 + SHA-256)")
        self.resize(540, 420)
        self.channel_id = channel_id
        self.export_thread: Optional[ExportWorkerThread] = None

        self._init_ui(default_start)

    def _init_ui(self, default_start: datetime) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header Info
        lbl_head = QLabel("VIDEO EXTRACTION & FORENSIC EXPORT")
        lbl_head.setStyleSheet("color: #58a6ff; font-weight: bold; font-size: 14px;")
        layout.addWidget(lbl_head)

        lbl_desc = QLabel("Extracts seamless MP4 footage, generates SHA-256 audit manifest, and preserves evidence.")
        lbl_desc.setStyleSheet("color: #8b949e; font-size: 11px;")
        layout.addWidget(lbl_desc)

        # Channel Selection
        h_ch = QHBoxLayout()
        h_ch.addWidget(QLabel("Camera Channel:"))
        self.txt_ch = QLineEdit(self.channel_id)
        self.txt_ch.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; padding: 4px;")
        h_ch.addWidget(self.txt_ch)
        layout.addLayout(h_ch)

        # Time Bounds
        h_time = QHBoxLayout()
        lbl_from = QLabel("Start UTC:")
        self.edit_start = QDateTimeEdit(QDateTime(default_start.year, default_start.month, default_start.day,
                                                  default_start.hour, default_start.minute, default_start.second))
        self.edit_start.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.edit_start.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; padding: 4px;")

        lbl_to = QLabel("End UTC:")
        end_default = default_start + timedelta(minutes=15)
        self.edit_end = QDateTimeEdit(QDateTime(end_default.year, end_default.month, end_default.day,
                                                end_default.hour, end_default.minute, end_default.second))
        self.edit_end.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.edit_end.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; padding: 4px;")

        h_time.addWidget(lbl_from)
        h_time.addWidget(self.edit_start)
        h_time.addWidget(lbl_to)
        h_time.addWidget(self.edit_end)
        layout.addLayout(h_time)

        # Destination Path
        h_path = QHBoxLayout()
        self.edit_dest = QLineEdit(os.path.abspath(f"storage/exports/export_{self.channel_id}_{int(datetime.now().timestamp())}.mp4"))
        self.edit_dest.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; padding: 4px;")
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_destination)
        h_path.addWidget(self.edit_dest)
        h_path.addWidget(btn_browse)
        layout.addLayout(h_path)

        # Evidence Protection Checkbox
        self.chk_evidence = QCheckBox("Flag as Protected Evidence (Prevents retention pruning / deletion)")
        self.chk_evidence.setStyleSheet("color: #d29922; font-weight: bold;")
        self.chk_evidence.setChecked(True)
        layout.addWidget(self.chk_evidence)

        # Notes / Reason
        layout.addWidget(QLabel("Investigation Notes / Reason:"))
        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText("Enter legal case reference, officer details, or investigation purpose...")
        self.txt_notes.setMaximumHeight(60)
        self.txt_notes.setStyleSheet("background-color: #21262d; border: 1px solid #30363d;")
        layout.addWidget(self.txt_notes)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Action Buttons
        h_btns = QHBoxLayout()
        h_btns.addStretch()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_start = QPushButton("Start Export")
        self.btn_start.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 6px 14px;")
        self.btn_start.clicked.connect(self._start_export)
        h_btns.addWidget(self.btn_cancel)
        h_btns.addWidget(self.btn_start)
        layout.addLayout(h_btns)

    def _browse_destination(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Video Clip", self.edit_dest.text(), "MP4 Video (*.mp4)")
        if path:
            self.edit_dest.setText(path)

    def _start_export(self) -> None:
        start_qdt = self.edit_start.dateTime()
        end_qdt = self.edit_end.dateTime()

        start_dt = datetime(start_qdt.date().year(), start_qdt.date().month(), start_qdt.date().day(),
                            start_qdt.time().hour(), start_qdt.time().minute(), start_qdt.time().second(),
                            tzinfo=timezone.utc)
        end_dt = datetime(end_qdt.date().year(), end_qdt.date().month(), end_qdt.date().day(),
                          end_qdt.time().hour(), end_qdt.time().minute(), end_qdt.time().second(),
                          tzinfo=timezone.utc)

        if end_dt <= start_dt:
            QMessageBox.warning(self, "Validation Error", "End time must be strictly after start time.")
            return

        dest = self.edit_dest.text().strip()
        if not dest:
            QMessageBox.warning(self, "Validation Error", "Please provide a valid destination file path.")
            return

        self.btn_start.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.export_thread = ExportWorkerThread(
            channel_id=self.txt_ch.text().strip(),
            start_dt=start_dt,
            end_dt=end_dt,
            out_path=dest,
            is_evidence=self.chk_evidence.isChecked(),
            notes=self.txt_notes.toPlainText().strip(),
        )
        self.export_thread.progress.connect(self.progress_bar.setValue)
        self.export_thread.finished_job.connect(self._on_export_success)
        self.export_thread.failed.connect(self._on_export_failure)
        self.export_thread.start()

    def _on_export_success(self, job) -> None:
        self.progress_bar.setValue(100)
        msg = f"Export completed successfully!\nFile: {job.destination_path}\nSHA-256: {job.sha256_hash}"
        QMessageBox.information(self, "Export Complete", msg)
        self.accept()

    def _on_export_failure(self, err: str) -> None:
        self.btn_start.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Export Failed", f"Export operation failed:\n{err}")


class PlaybackWidget(QWidget):
    """Integrated Playback Workspace."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.active_channels: List[str] = ["ch_1", "ch_2", "ch_3", "ch_4"]
        self.tiles: List[VideoTileWidget] = []

        self._init_ui()
        self._setup_playback_timer()
        self._load_timeline_data()

    def _init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        # 1. Top Control Bar (Date, Layout, Export)
        top_bar = self._create_top_control_bar()
        root_layout.addWidget(top_bar)

        # 2. Central Video Grid
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(6)
        root_layout.addWidget(self.grid_container, stretch=1)

        # 3. Playback Controls Bar
        controls_bar = self._create_controls_bar()
        root_layout.addWidget(controls_bar)

        # 4. Interactive Timeline Widget
        self.timeline = TimelineWidget(self)
        self.timeline.set_channels(self.active_channels)
        self.timeline.seek_requested.connect(self._on_timeline_seek)
        root_layout.addWidget(self.timeline)

        # Build initial 2x2 grid
        self._rebuild_grid(2, 2)

    def _create_top_control_bar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 4px;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        # Date Selector
        layout.addWidget(QLabel("Date:"))
        self.date_picker = QDateEdit(QDate.currentDate())
        self.date_picker.setCalendarPopup(True)
        self.date_picker.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; padding: 4px;")
        self.date_picker.dateChanged.connect(self._on_date_changed)
        layout.addWidget(self.date_picker)

        # Grid Layout Selector
        layout.addWidget(QLabel("Grid:"))
        self.combo_grid = QComboBox()
        self.combo_grid.addItems(["1x1 (Single)", "2x2 (4 Cameras)", "3x3 (9 Cameras)", "4x4 (16 Cameras)"])
        self.combo_grid.setCurrentIndex(1)  # Default 2x2
        self.combo_grid.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; padding: 4px;")
        self.combo_grid.currentIndexChanged.connect(self._on_grid_layout_changed)
        layout.addWidget(self.combo_grid)

        # Refresh Footage Button
        self.btn_refresh = QPushButton("Refresh Footage")
        self.btn_refresh.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; padding: 4px 8px;")
        self.btn_refresh.clicked.connect(self._load_timeline_data)
        layout.addWidget(self.btn_refresh)

        layout.addStretch()

        # Export Clip Button
        self.btn_export = QPushButton("Export Clip (MP4)")
        self.btn_export.setStyleSheet("background-color: #1f6feb; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px;")
        self.btn_export.clicked.connect(self._open_export_dialog)
        layout.addWidget(self.btn_export)

        return bar

    def _create_controls_bar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 4px;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        # Play / Pause
        self.btn_play_pause = QPushButton("▶ Play")
        self.btn_play_pause.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        self.btn_play_pause.clicked.connect(self._toggle_play_pause)
        layout.addWidget(self.btn_play_pause)

        # Stop
        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; padding: 6px 12px; border-radius: 4px;")
        self.btn_stop.clicked.connect(self._stop_playback)
        layout.addWidget(self.btn_stop)

        # Step Back
        self.btn_step_back = QPushButton("⏮ -1f")
        self.btn_step_back.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; padding: 6px 10px; border-radius: 4px;")
        self.btn_step_back.clicked.connect(lambda: playback_controller.step_backward(1))
        layout.addWidget(self.btn_step_back)

        # Step Forward
        self.btn_step_fwd = QPushButton("⏭ +1f")
        self.btn_step_fwd.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; padding: 6px 10px; border-radius: 4px;")
        self.btn_step_fwd.clicked.connect(lambda: playback_controller.step_forward(1))
        layout.addWidget(self.btn_step_fwd)

        # Speed Selector
        layout.addWidget(QLabel("Speed:"))
        self.combo_speed = QComboBox()
        self.combo_speed.addItems(["0.25x", "0.5x", "1.0x", "2.0x", "4.0x", "8.0x", "16.0x"])
        self.combo_speed.setCurrentText("1.0x")
        self.combo_speed.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; padding: 4px;")
        self.combo_speed.currentIndexChanged.connect(self._on_speed_changed)
        layout.addWidget(self.combo_speed)

        layout.addStretch()

        # Position / Master Clock Indicator
        self.lbl_master_clock = QLabel("Current: 00:00:00 UTC")
        self.lbl_master_clock.setStyleSheet("color: #58a6ff; font-weight: bold; font-size: 13px;")
        layout.addWidget(self.lbl_master_clock)

        # Sync Badge
        lbl_sync = QLabel("● SYNCHRONIZED")
        lbl_sync.setStyleSheet("color: #3fb950; font-size: 11px; font-weight: bold;")
        layout.addWidget(lbl_sync)

        return bar

    def _setup_playback_timer(self) -> None:
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(33)  # ~30 FPS UI tick
        self.play_timer.timeout.connect(self._on_playback_tick)
        self.play_timer.start()

    def _rebuild_grid(self, rows: int, cols: int) -> None:
        # Clear existing layout
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)

        self.tiles.clear()
        total_slots = rows * cols
        channels = [f"ch_{i+1}" for i in range(total_slots)]
        self.active_channels = channels

        idx = 0
        for r in range(rows):
            for c in range(cols):
                ch_id = channels[idx]
                tile = VideoTileWidget(channel_id=ch_id, channel_name=f"Camera {idx+1}")
                self.grid_layout.addWidget(tile, r, c)
                self.tiles.append(tile)
                idx += 1

        # Configure playback controller channels
        playback_controller.set_channels(channels)
        self.timeline.set_channels(channels)
        self._load_timeline_data()

    def _on_grid_layout_changed(self, index: int) -> None:
        layouts = [(1, 1), (2, 2), (3, 3), (4, 4)]
        if 0 <= index < len(layouts):
            r, c = layouts[index]
            self._rebuild_grid(r, c)

    def _toggle_play_pause(self) -> None:
        if playback_controller.state == PlaybackState.PLAYING:
            playback_controller.pause()
            self.btn_play_pause.setText("▶ Play")
            self.btn_play_pause.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        else:
            playback_controller.play()
            self.btn_play_pause.setText("⏸ Pause")
            self.btn_play_pause.setStyleSheet("background-color: #d29922; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")

    def _stop_playback(self) -> None:
        playback_controller.stop()
        self.btn_play_pause.setText("▶ Play")
        self.btn_play_pause.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")

    def _on_speed_changed(self) -> None:
        txt = self.combo_speed.currentText().replace("x", "")
        try:
            speed = float(txt)
            playback_controller.set_speed(speed)
        except ValueError:
            pass

    def _on_timeline_seek(self, target_dt: datetime) -> None:
        playback_controller.seek_to_timestamp(target_dt)
        self._update_display_frames(target_dt)

    def _on_playback_tick(self) -> None:
        clock = playback_controller.master_clock
        if playback_controller.state == PlaybackState.PLAYING:
            clock = playback_controller.update_clock_tick()
            self.timeline.set_current_time(clock)
            self._update_display_frames(clock)

        self.lbl_master_clock.setText(f"Current: {clock.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    def _update_display_frames(self, target_dt: datetime) -> None:
        for tile in self.tiles:
            frame = playback_controller.get_frame(tile.channel_id)
            tile.update_frame(frame, target_dt.timestamp())

    def _on_date_changed(self) -> None:
        qdate = self.date_picker.date()
        dt_start = datetime(qdate.year(), qdate.month(), qdate.day(), 0, 0, 0, tzinfo=timezone.utc)
        dt_end = dt_start + timedelta(hours=24)
        self.timeline.set_view_range(dt_start, dt_end)
        playback_controller.seek_to_timestamp(dt_start)
        self._load_timeline_data()

    def _load_timeline_data(self) -> None:
        """Fetches recording segments for all active channels within current view bounds."""
        for ch in self.active_channels:
            intervals = playback_controller.get_recording_intervals(
                channel_id=ch,
                start_time=self.timeline.view_start,
                end_time=self.timeline.view_end
            )
            self.timeline.set_recording_data(ch, intervals)

    def _open_export_dialog(self) -> None:
        primary_ch = self.active_channels[0] if self.active_channels else "ch_1"
        dialog = ClipExportDialog(channel_id=primary_ch, default_start=playback_controller.master_clock, parent=self)
        dialog.exec()
