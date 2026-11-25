"""
Live Surveillance Monitoring Workspace.
Supports 1, 4, 9, 16, 25, 36, and 64 multi-camera dynamic grid layouts,
double-click tile maximization, drag-and-drop camera assignment,
embedded universal PTZ control panel, multi-monitor window detaching,
keyboard navigation shortcuts, and unblocked frame updates.
"""

from typing import List, Dict, Optional
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QFrame, QComboBox, QSizePolicy,
    QSlider, QDialog, QMessageBox, QSplitter
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QScreen, QGuiApplication

from modules.live_monitoring.video_widget import VideoTileWidget
from engines.video_engine.stream_manager import stream_manager
from engines.video_engine.stream_metrics import StreamTelemetry, StreamState
from engines.video_engine.ptz_controller import ptz_controller
from integrations.onvif.client import PTZDirection
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("live_monitoring")


class PTZControlWidget(QFrame):
    """Universal Pan-Tilt-Zoom control panel widget."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.active_channel_id: str = "ch_1"
        self.setStyleSheet("""
            QFrame { background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 8px; }
            QPushButton { background-color: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 4px; font-weight: bold; min-width: 32px; min-height: 32px; }
            QPushButton:hover { background-color: #30363d; color: #58a6ff; }
            QPushButton:pressed { background-color: #1f6feb; color: #ffffff; }
            QLabel { color: #8b949e; font-size: 11px; }
            QComboBox { background-color: #0d1117; color: #e6edf3; border: 1px solid #30363d; border-radius: 4px; padding: 4px; }
            QSlider::groove:horizontal { height: 4px; background: #30363d; border-radius: 2px; }
            QSlider::handle:horizontal { background: #58a6ff; width: 14px; margin: -5px 0; border-radius: 7px; }
        """)
        self.setFixedWidth(240)
        self._init_ui()

    def set_target_channel(self, channel_id: str, channel_name: str = "") -> None:
        self.active_channel_id = channel_id
        display = f"PTZ: {channel_name or channel_id}"
        self.lbl_target.setText(display)
        self._refresh_presets()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Target label
        self.lbl_target = QLabel(f"PTZ: {self.active_channel_id}")
        self.lbl_target.setStyleSheet("color: #58a6ff; font-weight: bold; font-size: 12px;")
        layout.addWidget(self.lbl_target)

        # 1. 8-Directional Keypad + Center Stop
        pad_grid = QGridLayout()
        pad_grid.setSpacing(4)

        self.btn_ul = QPushButton("↖")
        self.btn_u = QPushButton("↑")
        self.btn_ur = QPushButton("↗")
        self.btn_l = QPushButton("←")
        self.btn_stop = QPushButton("■")
        self.btn_stop.setStyleSheet("background-color: #da3633; color: white;")
        self.btn_r = QPushButton("→")
        self.btn_dl = QPushButton("↙")
        self.btn_d = QPushButton("↓")
        self.btn_dr = QPushButton("↘")

        pad_grid.addWidget(self.btn_ul, 0, 0)
        pad_grid.addWidget(self.btn_u, 0, 1)
        pad_grid.addWidget(self.btn_ur, 0, 2)
        pad_grid.addWidget(self.btn_l, 1, 0)
        pad_grid.addWidget(self.btn_stop, 1, 1)
        pad_grid.addWidget(self.btn_r, 1, 2)
        pad_grid.addWidget(self.btn_dl, 2, 0)
        pad_grid.addWidget(self.btn_d, 2, 1)
        pad_grid.addWidget(self.btn_dr, 2, 2)

        self.btn_ul.clicked.connect(lambda: self._move(PTZDirection.UP_LEFT))
        self.btn_u.clicked.connect(lambda: self._move(PTZDirection.UP))
        self.btn_ur.clicked.connect(lambda: self._move(PTZDirection.UP_RIGHT))
        self.btn_l.clicked.connect(lambda: self._move(PTZDirection.LEFT))
        self.btn_stop.clicked.connect(lambda: self._move(PTZDirection.STOP))
        self.btn_r.clicked.connect(lambda: self._move(PTZDirection.RIGHT))
        self.btn_dl.clicked.connect(lambda: self._move(PTZDirection.DOWN_LEFT))
        self.btn_d.clicked.connect(lambda: self._move(PTZDirection.DOWN))
        self.btn_dr.clicked.connect(lambda: self._move(PTZDirection.DOWN_RIGHT))

        layout.addLayout(pad_grid)

        # 2. Zoom Controls
        zoom_row = QHBoxLayout()
        self.btn_zoom_in = QPushButton("Zoom In (+)")
        self.btn_zoom_out = QPushButton("Zoom Out (-)")
        self.btn_zoom_in.clicked.connect(lambda: self._move(PTZDirection.ZOOM_IN))
        self.btn_zoom_out.clicked.connect(lambda: self._move(PTZDirection.ZOOM_OUT))
        zoom_row.addWidget(self.btn_zoom_in)
        zoom_row.addWidget(self.btn_zoom_out)
        layout.addLayout(zoom_row)

        # 3. Speed Slider
        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Speed:"))
        self.slider_speed = QSlider(Qt.Horizontal)
        self.slider_speed.setRange(10, 100)
        self.slider_speed.setValue(50)
        speed_row.addWidget(self.slider_speed)
        layout.addLayout(speed_row)

        # 4. Preset Management
        layout.addWidget(QLabel("Preset Navigation:"))
        preset_row = QHBoxLayout()
        self.combo_presets = QComboBox()
        preset_row.addWidget(self.combo_presets, stretch=1)

        self.btn_goto_preset = QPushButton("Go")
        self.btn_goto_preset.clicked.connect(self._goto_selected_preset)
        preset_row.addWidget(self.btn_goto_preset)
        layout.addLayout(preset_row)

        preset_action_row = QHBoxLayout()
        self.btn_save_preset = QPushButton("+ Save Preset")
        self.btn_save_preset.clicked.connect(self._save_preset)
        self.btn_home = QPushButton("⌂ Home")
        self.btn_home.clicked.connect(self._goto_home)
        preset_action_row.addWidget(self.btn_save_preset)
        preset_action_row.addWidget(self.btn_home)
        layout.addLayout(preset_action_row)

        layout.addStretch()

    def _get_speed(self) -> float:
        return self.slider_speed.value() / 100.0

    def _move(self, direction: PTZDirection) -> None:
        speed = self._get_speed()
        ptz_controller.dispatch_async(ptz_controller.move_direction, self.active_channel_id, direction, speed)

    def _refresh_presets(self) -> None:
        self.combo_presets.clear()
        presets = ptz_controller.get_presets(self.active_channel_id)
        for p in presets:
            self.combo_presets.addItem(p.name, p.token)

    def _goto_selected_preset(self) -> None:
        idx = self.combo_presets.currentIndex()
        if idx >= 0:
            token = self.combo_presets.currentData()
            ptz_controller.dispatch_async(ptz_controller.goto_preset, self.active_channel_id, token, self._get_speed())

    def _save_preset(self) -> None:
        count = self.combo_presets.count() + 1
        name = f"Preset {count}"
        ptz_controller.set_preset(self.active_channel_id, name)
        self._refresh_presets()

    def _goto_home(self) -> None:
        ptz_controller.dispatch_async(ptz_controller.goto_home_position, self.active_channel_id, self._get_speed())


class DetachedGridWindow(QDialog):
    """Independent multi-monitor detached video monitoring window."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("CCTV AI Platform — Detached Video Wall")
        self.resize(1024, 768)
        self.setStyleSheet("background-color: #0d1117;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header bar
        header = QHBoxLayout()
        header.addWidget(QLabel("Multi-Monitor Detached Surveillance Grid"))
        header.addStretch()

        btn_close = QPushButton("Re-attach / Close")
        btn_close.setStyleSheet("background-color: #da3633; color: white; padding: 4px 12px; border-radius: 4px;")
        btn_close.clicked.connect(self.close)
        header.addWidget(btn_close)
        layout.addLayout(header)

        # 4-up subgrid inside detached window
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(4)

        self.detached_tiles: List[VideoTileWidget] = []
        for i in range(1, 5):
            tile = VideoTileWidget(channel_id=f"detached_ch_{i}", channel_name=f"Wall Cam {i}")
            self.detached_tiles.append(tile)
            row = (i - 1) // 2
            col = (i - 1) % 2
            self.grid_layout.addWidget(tile, row, col)

        layout.addWidget(self.grid_widget, stretch=1)

    def update_tile_frame(self, index: int, frame_bgr: np.ndarray, ts: float) -> None:
        if 0 <= index < len(self.detached_tiles):
            self.detached_tiles[index].update_frame(frame_bgr, ts)


class LiveViewWidget(QWidget):
    """Dynamic multi-channel live surveillance grid supporting 1 to 64 camera layouts."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.current_layout_size = 4  # Default: 4-camera grid (2x2)
        self.max_capacity = 64
        self.tiles: List[VideoTileWidget] = []
        self._previous_layout = 4
        self._maximized_tile_id: Optional[str] = None
        self._is_paused: bool = False
        self._detached_window: Optional[DetachedGridWindow] = None

        self._init_ui()
        self._init_shortcuts()
        self._init_frame_timer()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 1. Top Control Toolbar
        toolbar = QFrame()
        toolbar.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 4px;")
        tool_layout = QHBoxLayout(toolbar)
        tool_layout.setContentsMargins(8, 4, 8, 4)
        tool_layout.setSpacing(8)

        lbl_grid = QLabel("Layout:")
        lbl_grid.setStyleSheet("color: #8b949e; font-weight: 600;")
        tool_layout.addWidget(lbl_grid)

        self.combo_layout = QComboBox()
        self.combo_layout.addItems([
            "1x1 (1 Cam) [Key 1]",
            "2x2 (4 Cam) [Key 2]",
            "3x3 (9 Cam) [Key 3]",
            "4x4 (16 Cam) [Key 4]",
            "5x5 (25 Cam) [Key 5]",
            "6x6 (36 Cam) [Key 6]",
            "8x8 (64 Cam) [Key 7]",
        ])
        self.combo_layout.setCurrentIndex(1)  # 2x2
        self.combo_layout.currentIndexChanged.connect(self._on_combo_layout_changed)
        tool_layout.addWidget(self.combo_layout)

        # Quick Grid Buttons for common layouts
        self.btn_1x1 = QPushButton("1x1")
        self.btn_2x2 = QPushButton("2x2")
        self.btn_3x3 = QPushButton("3x3")
        self.btn_4x4 = QPushButton("4x4")
        self.btn_8x8 = QPushButton("8x8 (64)")

        for btn, count in [(self.btn_1x1, 1), (self.btn_2x2, 4), (self.btn_3x3, 9), (self.btn_4x4, 16), (self.btn_8x8, 64)]:
            btn.setStyleSheet("""
                QPushButton { background-color: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 4px; padding: 4px 8px; font-weight: 600; }
                QPushButton:hover { background-color: #30363d; color: #58a6ff; }
            """)
            btn.clicked.connect(lambda _, c=count: self.set_grid_layout(c))
            tool_layout.addWidget(btn)

        tool_layout.addSpacing(12)

        # PTZ Panel Toggle
        self.btn_toggle_ptz = QPushButton("PTZ Panel")
        self.btn_toggle_ptz.setCheckable(True)
        self.btn_toggle_ptz.setChecked(True)
        self.btn_toggle_ptz.setStyleSheet("""
            QPushButton { background-color: #21262d; color: #8957e5; border: 1px solid #8957e5; border-radius: 4px; padding: 4px 10px; font-weight: 600; }
            QPushButton:checked { background-color: #8957e5; color: #ffffff; }
        """)
        self.btn_toggle_ptz.toggled.connect(self._toggle_ptz_panel)
        tool_layout.addWidget(self.btn_toggle_ptz)

        # Multi-Monitor Detach Button
        self.btn_detach = QPushButton("Detach to Monitor")
        self.btn_detach.setStyleSheet("background-color: #21262d; color: #58a6ff; border: 1px solid #30363d; border-radius: 4px; padding: 4px 10px; font-weight: 600;")
        self.btn_detach.clicked.connect(self._detach_grid_window)
        tool_layout.addWidget(self.btn_detach)

        tool_layout.addStretch()

        # Simulated Test Streams Button
        self.btn_test_streams = QPushButton("Start Test Streams (1-4)")
        self.btn_test_streams.setStyleSheet("background-color: #238636; color: #ffffff; font-weight: 600; padding: 4px 12px; border-radius: 4px;")
        self.btn_test_streams.clicked.connect(self._toggle_test_streams)
        tool_layout.addWidget(self.btn_test_streams)

        main_layout.addWidget(toolbar)

        # 2. Main Content Splitter (Grid on Left, PTZ Panel on Right)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setStyleSheet("QSplitter::handle { background-color: #30363d; }")

        # Video Grid Container
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(4)

        # Pre-instantiate initial 16 video tiles (expandable up to 64 on demand)
        self._ensure_tiles(16)

        self.splitter.addWidget(self.grid_container)

        # Universal PTZ Panel
        self.ptz_panel = PTZControlWidget()
        self.splitter.addWidget(self.ptz_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)

        main_layout.addWidget(self.splitter, stretch=1)
        self._arrange_grid(self.current_layout_size)

    def _init_shortcuts(self) -> None:
        """Configures keyboard shortcuts for fast grid navigation and operational controls."""
        QShortcut(QKeySequence("1"), self, lambda: self.set_grid_layout(1))
        QShortcut(QKeySequence("2"), self, lambda: self.set_grid_layout(4))
        QShortcut(QKeySequence("3"), self, lambda: self.set_grid_layout(9))
        QShortcut(QKeySequence("4"), self, lambda: self.set_grid_layout(16))
        QShortcut(QKeySequence("5"), self, lambda: self.set_grid_layout(25))
        QShortcut(QKeySequence("6"), self, lambda: self.set_grid_layout(36))
        QShortcut(QKeySequence("7"), self, lambda: self.set_grid_layout(64))
        QShortcut(QKeySequence(Qt.Key_Space), self, self._toggle_pause)
        QShortcut(QKeySequence(Qt.Key_Escape), self, self._on_escape_pressed)

    def _on_escape_pressed(self) -> None:
        if self._maximized_tile_id:
            self.set_grid_layout(self._previous_layout)

    def _toggle_pause(self) -> None:
        self._is_paused = not self._is_paused
        logger.info("Live view frame updates %s", "PAUSED" if self._is_paused else "RESUMED")

    def _toggle_ptz_panel(self, checked: bool) -> None:
        self.ptz_panel.setVisible(checked)

    def _detach_grid_window(self) -> None:
        """Opens multi-monitor detached video wall window."""
        if not self._detached_window:
            self._detached_window = DetachedGridWindow(self)
        self._detached_window.show()
        self._detached_window.raise_()
        self._detached_window.activateWindow()

    def _on_tile_selected(self, channel_id: str) -> None:
        for t in self.tiles:
            t.set_selected(t.channel_id == channel_id)
        target = next((t for t in self.tiles if t.channel_id == channel_id), None)
        name = target.channel_name if target else channel_id
        self.ptz_panel.set_target_channel(channel_id, name)

    def _on_camera_dropped(self, tile_channel_id: str, dropped_channel_id: str) -> None:
        """Handles drag-and-drop camera re-assignment."""
        tile = next((t for t in self.tiles if t.channel_id == tile_channel_id), None)
        if tile:
            tile.channel_name = f"Camera {dropped_channel_id}"
            logger.info("Assigned camera [%s] to tile [%s]", dropped_channel_id, tile_channel_id)

    def _on_profile_switched(self, channel_id: str, profile_type: str) -> None:
        stream_manager.switch_channel_profile(channel_id, profile_type)

    def _on_ptz_requested(self, channel_id: str) -> None:
        self.btn_toggle_ptz.setChecked(True)
        self.ptz_panel.show()
        self._on_tile_selected(channel_id)

    def _on_combo_layout_changed(self, index: int) -> None:
        counts = [1, 4, 9, 16, 25, 36, 64]
        if 0 <= index < len(counts):
            self.set_grid_layout(counts[index])

    def _ensure_tiles(self, count: int) -> None:
        """Dynamically instantiates tiles up to requested count (max 64)."""
        current_count = len(self.tiles)
        target_count = min(self.max_capacity, max(current_count, count))
        for i in range(current_count, target_count):
            ch_num = i + 1
            ch_id = f"ch_{ch_num}"
            tile = VideoTileWidget(channel_id=ch_id, channel_name=f"Camera {ch_num}")
            tile.double_clicked.connect(self._on_tile_double_clicked)
            tile.tile_selected.connect(self._on_tile_selected)
            tile.camera_dropped.connect(self._on_camera_dropped)
            tile.profile_switched.connect(self._on_profile_switched)
            tile.ptz_requested.connect(self._on_ptz_requested)
            self.tiles.append(tile)

    def _arrange_grid(self, count: int) -> None:
        """Positions tiles according to grid count (1, 4, 9, 16, 25, 36, 64)."""
        self._ensure_tiles(count)

        for i in reversed(range(self.grid_layout.count())):
            item = self.grid_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)

        cols_map = {1: 1, 4: 2, 9: 3, 16: 4, 25: 5, 36: 6, 64: 8}
        cols = cols_map.get(count, int(np.ceil(np.sqrt(count))))

        for idx in range(len(self.tiles)):
            tile = self.tiles[idx]
            if idx < count:
                row = idx // cols
                col = idx % cols
                self.grid_layout.addWidget(tile, row, col)
                tile.show()
            else:
                tile.hide()

    def set_grid_layout(self, count: int) -> None:
        """Sets active multi-camera grid layout."""
        self.current_layout_size = count
        self._maximized_tile_id = None
        self._arrange_grid(count)

        counts = [1, 4, 9, 16, 25, 36, 64]
        if count in counts:
            self.combo_layout.blockSignals(True)
            self.combo_layout.setCurrentIndex(counts.index(count))
            self.combo_layout.blockSignals(False)

    def _on_tile_double_clicked(self, channel_id: str) -> None:
        """Toggles 1-up maximization for clicked tile."""
        if self._maximized_tile_id == channel_id:
            self.set_grid_layout(self._previous_layout)
        else:
            self._previous_layout = self.current_layout_size
            self._maximized_tile_id = channel_id
            for i in reversed(range(self.grid_layout.count())):
                item = self.grid_layout.itemAt(i)
                if item and item.widget():
                    item.widget().setParent(None)

            target_tile = next((t for t in self.tiles if t.channel_id == channel_id), self.tiles[0])
            self.grid_layout.addWidget(target_tile, 0, 0)
            target_tile.show()
            for t in self.tiles:
                if t != target_tile:
                    t.hide()

    def _init_frame_timer(self) -> None:
        """Starts 30 FPS timer to fetch decoded frames and push to visible tiles."""
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self._refresh_frames)
        self.frame_timer.start(33)  # ~30 FPS

    def _refresh_frames(self) -> None:
        """Pulls latest decoded frame from StreamManager for each active visible tile."""
        if self._is_paused:
            return

        for idx, tile in enumerate(self.tiles):
            if not tile.isVisible():
                continue

            frame_data = stream_manager.get_latest_frame(tile.channel_id)
            if frame_data:
                frame, ts = frame_data
                tile.update_frame(frame, ts)
                if self._detached_window and self._detached_window.isVisible() and idx < 4:
                    self._detached_window.update_tile_frame(idx, frame, ts)

            telemetry = stream_manager.get_telemetry(tile.channel_id)
            if telemetry:
                tile.update_telemetry(telemetry)

    def _toggle_test_streams(self) -> None:
        """Starts or stops synthetic surveillance test streams."""
        if stream_manager.active_stream_count() > 0:
            stream_manager.stop_all()
            self.btn_test_streams.setText("Start Test Streams (1-4)")
            self.btn_test_streams.setStyleSheet("background-color: #238636; color: #ffffff; font-weight: 600; padding: 4px 12px; border-radius: 4px;")
        else:
            count = min(self.current_layout_size, 16)
            for i in range(1, count + 1):
                ch_id = f"ch_{i}"
                stream_manager.start_stream(
                    channel_id=ch_id,
                    rtsp_url=f"test://simulated_camera_{i}",
                    channel_name=f"Perimeter Cam {i}",
                    is_test_stream=True,
                )
                ptz_controller.register_camera(channel_id=ch_id, is_simulated=True)
            self.btn_test_streams.setText("Stop Active Streams")
            self.btn_test_streams.setStyleSheet("background-color: #f85149; color: #ffffff; font-weight: 600; padding: 4px 12px; border-radius: 4px;")

