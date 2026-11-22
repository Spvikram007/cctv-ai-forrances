"""
Live Surveillance Monitoring Workspace.
Supports 1, 4, 9, 16 multi-camera dynamic grid layouts (scalable to 25, 36, 64),
camera switching, PTZ controls, snapshot triggers, and unblocked frame updates.
"""

from typing import List, Dict, Optional
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QFrame, QComboBox, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer

from modules.live_monitoring.video_widget import VideoTileWidget
from engines.video_engine.stream_manager import stream_manager
from engines.video_engine.stream_metrics import StreamTelemetry


class LiveViewWidget(QWidget):
    """Dynamic multi-channel live surveillance grid."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.current_layout_size = 4  # Default: 4-camera grid (2x2)
        self.max_capacity = 16
        self.tiles: List[VideoTileWidget] = []
        self._previous_layout = 4
        self._maximized_tile_id: Optional[str] = None

        self._init_ui()
        self._init_frame_timer()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 1. Top Control Toolbar
        toolbar = QFrame()
        toolbar.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 4px;")
        tool_layout = QHBoxLayout(toolbar)
        tool_layout.setContentsMargins(8, 4, 8, 4)
        tool_layout.setSpacing(8)

        lbl_grid = QLabel("Layout:")
        lbl_grid.setStyleSheet("color: #8b949e; font-weight: 600;")
        tool_layout.addWidget(lbl_grid)

        self.btn_1x1 = QPushButton("1x1 (Single)")
        self.btn_2x2 = QPushButton("2x2 (4-Cam)")
        self.btn_3x3 = QPushButton("3x3 (9-Cam)")
        self.btn_4x4 = QPushButton("4x4 (16-Cam)")

        for btn in [self.btn_1x1, self.btn_2x2, self.btn_3x3, self.btn_4x4]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #21262d; color: #c9d1d9; border: 1px solid #30363d;
                    border-radius: 4px; padding: 4px 10px; font-weight: 500;
                }
                QPushButton:hover { background-color: #30363d; color: #58a6ff; }
                QPushButton:checked { background-color: #1f6feb; color: #ffffff; font-weight: 600; }
            """)
            btn.setCheckable(True)
            tool_layout.addWidget(btn)

        self.btn_1x1.clicked.connect(lambda: self.set_grid_layout(1))
        self.btn_2x2.clicked.connect(lambda: self.set_grid_layout(4))
        self.btn_3x3.clicked.connect(lambda: self.set_grid_layout(9))
        self.btn_4x4.clicked.connect(lambda: self.set_grid_layout(16))
        self.btn_2x2.setChecked(True)

        tool_layout.addStretch()

        self.btn_test_streams = QPushButton("Start Simulated Test Streams (1-4)")
        self.btn_test_streams.setStyleSheet("background-color: #238636; color: #ffffff; font-weight: 600; padding: 4px 12px; border-radius: 4px;")
        self.btn_test_streams.clicked.connect(self._toggle_test_streams)
        tool_layout.addWidget(self.btn_test_streams)

        main_layout.addWidget(toolbar)

        # 2. Central Video Grid Container
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(6)

        # Pre-instantiate up to 16 video tiles
        for i in range(16):
            ch_num = i + 1
            ch_id = f"ch_{ch_num}"
            tile = VideoTileWidget(channel_id=ch_id, channel_name=f"Camera {ch_num}")
            tile.double_clicked.connect(self._on_tile_double_clicked)
            self.tiles.append(tile)

        self._arrange_grid(self.current_layout_size)
        main_layout.addWidget(self.grid_container, stretch=1)

    def _arrange_grid(self, count: int) -> None:
        """Positions tiles according to grid count (1, 4, 9, 16)."""
        # Clear existing layout items
        for i in reversed(range(self.grid_layout.count())):
            item = self.grid_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)

        cols = 1
        if count == 4:
            cols = 2
        elif count == 9:
            cols = 3
        elif count == 16:
            cols = 4

        for idx in range(16):
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

        self.btn_1x1.setChecked(count == 1)
        self.btn_2x2.setChecked(count == 4)
        self.btn_3x3.setChecked(count == 9)
        self.btn_4x4.setChecked(count == 16)

    def _on_tile_double_clicked(self, channel_id: str) -> None:
        """Toggles 1-up maximization for clicked tile."""
        if self._maximized_tile_id == channel_id:
            # Restore previous layout
            self.set_grid_layout(self._previous_layout)
        else:
            self._previous_layout = self.current_layout_size
            self._maximized_tile_id = channel_id
            # Show only this tile in 1x1 mode
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
        for tile in self.tiles:
            if not tile.isVisible():
                continue

            frame_data = stream_manager.get_latest_frame(tile.channel_id)
            if frame_data:
                frame, ts = frame_data
                tile.update_frame(frame, ts)

            telemetry = stream_manager.get_telemetry(tile.channel_id)
            if telemetry:
                tile.update_telemetry(telemetry)

    def _toggle_test_streams(self) -> None:
        """Starts or stops 4 synthetic surveillance test streams for demonstration and testing."""
        if stream_manager.active_stream_count() > 0:
            stream_manager.stop_all()
            self.btn_test_streams.setText("Start Simulated Test Streams (1-4)")
            self.btn_test_streams.setStyleSheet("background-color: #238636; color: #ffffff; font-weight: 600; padding: 4px 12px; border-radius: 4px;")
        else:
            for i in range(1, 5):
                ch_id = f"ch_{i}"
                stream_manager.start_stream(
                    channel_id=ch_id,
                    rtsp_url=f"test://simulated_camera_{i}",
                    channel_name=f"Perimeter Cam {i}",
                    is_test_stream=True,
                )
            self.btn_test_streams.setText("Stop Active Streams")
            self.btn_test_streams.setStyleSheet("background-color: #f85149; color: #ffffff; font-weight: 600; padding: 4px 12px; border-radius: 4px;")
