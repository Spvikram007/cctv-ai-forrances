"""
High-Performance Video Display Tile Widget.
Renders decoded surveillance frames using QPainter with aspect-ratio preservation,
OSD metadata overlays (camera title, FPS, resolution, online status), and snapshot capture.
"""

import os
import cv2
import numpy as np
from datetime import datetime, timezone
from typing import Optional, Tuple

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QPainter, QImage, QColor, QFont, QPen, QBrush

from engines.video_engine.stream_metrics import StreamState, StreamTelemetry
from core.config.settings import settings
from core.logging.logger import get_logger

logger = get_logger("video_widget")


class VideoTileWidget(QWidget):
    """Individual camera display tile inside multi-camera monitoring grid."""

    double_clicked = Signal(str)  # Emits channel_id when double-clicked
    snapshot_captured = Signal(str, str)  # Emits (channel_id, file_path)

    def __init__(self, channel_id: str = "ch_1", channel_name: str = "Camera 1", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.channel_id = channel_id
        self.channel_name = channel_name
        self._current_qimage: Optional[QImage] = None
        self._telemetry: Optional[StreamTelemetry] = None
        self._is_maximized = False

        self.setMinimumSize(240, 160)
        self.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d;")

    def update_frame(self, frame_bgr: np.ndarray, timestamp: float) -> None:
        """Converts raw OpenCV numpy frame into Qt QImage and triggers paint event."""
        if frame_bgr is None:
            return

        h, w, ch = frame_bgr.shape
        bytes_per_line = ch * w
        # Fast in-place or contiguous RGB conversion
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        # Create QImage from buffer
        qimage = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
        self._current_qimage = qimage
        self.update()

    def update_telemetry(self, telemetry: StreamTelemetry) -> None:
        self._telemetry = telemetry
        self.update()

    def capture_snapshot(self) -> Optional[str]:
        """Saves current frame to storage/snapshots/ and emits signal."""
        if self._current_qimage is None:
            return None

        snapshots_dir = settings.storage.snapshots_dir
        os.makedirs(snapshots_dir, exist_ok=True)

        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"snap_{self.channel_id}_{now_str}.jpg"
        filepath = os.path.join(snapshots_dir, filename)

        success = self._current_qimage.save(filepath, "JPG", quality=95)
        if success:
            logger.info("Snapshot captured for [%s]: %s", self.channel_id, filepath)
            self.snapshot_captured.emit(self.channel_id, filepath)
            return filepath
        return None

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._is_maximized = not self._is_maximized
            self.double_clicked.emit(self.channel_id)
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        # Check if click is on snapshot button region (bottom-right 30x30)
        if event.button() == Qt.LeftButton:
            rect_snap = QRect(self.width() - 40, self.height() - 36, 32, 28)
            if rect_snap.contains(event.pos()):
                self.capture_snapshot()
                return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        # 1. Background
        painter.fillRect(0, 0, w, h, QColor("#0d1117"))

        # 2. Render Video Frame (preserving aspect ratio)
        if self._current_qimage is not None and not self._current_qimage.isNull():
            scaled = self._current_qimage.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (w - scaled.width()) // 2
            y = (h - scaled.height()) // 2
            painter.drawImage(x, y, scaled)
        else:
            # Standby / No Signal placeholder
            painter.setPen(QPen(QColor("#484f58"), 1))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(QRect(0, 0, w, h), Qt.AlignCenter, f"{self.channel_name}\n[NO VIDEO SIGNAL]")

        # 3. OSD Header Overlay (Top Bar Gradient / Background)
        painter.fillRect(0, 0, w, 28, QColor(0, 0, 0, 160))

        # Camera Name & Status Dot
        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        painter.setPen(QColor("#ffffff"))
        painter.drawText(26, 19, self.channel_name)

        # Status Dot
        state = self._telemetry.state if self._telemetry else StreamState.OFFLINE
        if state == StreamState.ONLINE:
            dot_color = QColor("#238636")  # Green
        elif state == StreamState.RECONNECTING or state == StreamState.CONNECTING:
            dot_color = QColor("#d29922")  # Yellow
        else:
            dot_color = QColor("#f85149")  # Red

        painter.setBrush(QBrush(dot_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(10, 9, 10, 10)

        # Top-Right FPS and Resolution
        fps_text = f"{self._telemetry.current_fps:.1f} FPS" if self._telemetry else "0.0 FPS"
        res_text = f"{self._telemetry.detected_width}x{self._telemetry.detected_height}" if self._telemetry and self._telemetry.detected_width > 0 else ""
        telemetry_str = f"{res_text}  {fps_text}" if res_text else fps_text

        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor("#58a6ff"))
        painter.drawText(QRect(w - 180, 0, 170, 28), Qt.AlignRight | Qt.AlignVCenter, telemetry_str)

        # 4. Snapshot Icon Button Overlay (Bottom-Right)
        rect_snap = QRect(w - 38, h - 34, 30, 26)
        painter.setBrush(QBrush(QColor(22, 27, 34, 200)))
        painter.setPen(QPen(QColor("#30363d"), 1))
        painter.drawRoundedRect(rect_snap, 4, 4)

        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.setPen(QColor("#e6edf3"))
        painter.drawText(rect_snap, Qt.AlignCenter, "SNAP")
