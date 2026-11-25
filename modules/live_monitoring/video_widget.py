"""
High-Performance Video Display Tile Widget.
Renders decoded surveillance frames using QPainter with aspect-ratio preservation,
interactive digital zoom (1.0x-5.0x), drag-and-drop camera assignment,
OSD metadata overlays (camera title, FPS, resolution, latency, recording/AI/PTZ badges),
visual snapshot flash feedback, and context menus for stream profile selection.
"""

import os
import cv2
import numpy as np
from datetime import datetime, timezone
from typing import Optional, Tuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QMenu, QMessageBox, QDialog
)
from PySide6.QtCore import Qt, Signal, QRect, QPoint, QTimer
from PySide6.QtGui import (
    QPainter, QImage, QColor, QFont, QPen, QBrush, QAction, QCursor
)

from engines.video_engine.stream_metrics import StreamState, StreamTelemetry
from core.config.settings import settings
from core.logging.logger import get_logger

logger = get_logger("video_widget")


class VideoTileWidget(QWidget):
    """Individual camera display tile inside multi-camera monitoring grid."""

    double_clicked = Signal(str)          # Emits channel_id when double-clicked
    snapshot_captured = Signal(str, str)  # Emits (channel_id, file_path)
    camera_dropped = Signal(str, str)     # Emits (target_tile_id, dropped_channel_id)
    ptz_requested = Signal(str)           # Emits channel_id to trigger PTZ controller
    profile_switched = Signal(str, str)   # Emits (channel_id, profile_type)
    tile_selected = Signal(str)           # Emits channel_id when clicked

    def __init__(self, channel_id: str = "ch_1", channel_name: str = "Camera 1", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.channel_id = channel_id
        self.channel_name = channel_name
        self._current_qimage: Optional[QImage] = None
        self._telemetry: Optional[StreamTelemetry] = None
        self._is_maximized = False

        # Phase 3: Digital Zoom state (1.0x - 5.0x)
        self._zoom_factor: float = 1.0
        self._pan_x: float = 0.5  # Normalized center 0.0 to 1.0
        self._pan_y: float = 0.5
        self._is_dragging: bool = False
        self._drag_start: Optional[QPoint] = None

        # Phase 3: Overlays and status badges
        self.is_recording: bool = False
        self.is_ai_active: bool = False
        self.has_ptz: bool = False
        self._is_selected: bool = False
        self._flash_active: bool = False

        # Snapshot flash timer
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._clear_flash)

        # Enable drag-and-drop
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setMinimumSize(180, 120)
        self.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d;")

    def set_selected(self, selected: bool) -> None:
        self._is_selected = selected
        self.update()

    def update_frame(self, frame_bgr: np.ndarray, timestamp: float) -> None:
        """Converts raw OpenCV numpy frame into Qt QImage and triggers paint event."""
        if frame_bgr is None:
            return

        h, w, ch = frame_bgr.shape
        bytes_per_line = ch * w
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        qimage = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
        self._current_qimage = qimage
        self.update()

    def update_telemetry(self, telemetry: StreamTelemetry) -> None:
        self._telemetry = telemetry
        self.update()

    def set_badges(self, recording: Optional[bool] = None, ai_active: Optional[bool] = None, ptz: Optional[bool] = None) -> None:
        if recording is not None:
            self.is_recording = recording
        if ai_active is not None:
            self.is_ai_active = ai_active
        if ptz is not None:
            self.has_ptz = ptz
        self.update()

    def reset_digital_zoom(self) -> None:
        """Resets digital zoom back to 1.0x native view."""
        self._zoom_factor = 1.0
        self._pan_x = 0.5
        self._pan_y = 0.5
        self.update()

    def capture_snapshot(self) -> Optional[str]:
        """Saves current frame to storage/snapshots/ and triggers visual flash."""
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
            self._flash_active = True
            self._flash_timer.start(150)  # 150ms visual flash
            self.update()
            self.snapshot_captured.emit(self.channel_id, filepath)
            return filepath
        return None

    def _clear_flash(self) -> None:
        self._flash_active = False
        self.update()

    # --- Mouse & Interaction Events ---

    def wheelEvent(self, event) -> None:
        """Handles mouse wheel digital zooming (1.0x to 5.0x)."""
        delta = event.angleDelta().y()
        if delta > 0:
            self._zoom_factor = min(5.0, round(self._zoom_factor + 0.25, 2))
        elif delta < 0:
            self._zoom_factor = max(1.0, round(self._zoom_factor - 0.25, 2))
        self.update()
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._is_maximized = not self._is_maximized
            self.double_clicked.emit(self.channel_id)
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.tile_selected.emit(self.channel_id)
            # Check if click is on snapshot button region (bottom-right 32x28)
            rect_snap = QRect(self.width() - 40, self.height() - 36, 32, 28)
            if rect_snap.contains(event.pos()):
                self.capture_snapshot()
                return

            # Check if click is on zoom reset badge region (bottom-left)
            if self._zoom_factor > 1.0:
                rect_zoom = QRect(8, self.height() - 32, 90, 24)
                if rect_zoom.contains(event.pos()):
                    self.reset_digital_zoom()
                    return

            if self._zoom_factor > 1.0:
                self._is_dragging = True
                self._drag_start = event.pos()
                self.setCursor(QCursor(Qt.ClosedHandCursor))
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._is_dragging and self._drag_start and self._zoom_factor > 1.0:
            dx = (event.pos().x() - self._drag_start.x()) / max(1, self.width())
            dy = (event.pos().y() - self._drag_start.y()) / max(1, self.height())
            # Pan inversely to mouse drag
            self._pan_x = max(0.0, min(1.0, self._pan_x - dx / self._zoom_factor))
            self._pan_y = max(0.0, min(1.0, self._pan_y - dy / self._zoom_factor))
            self._drag_start = event.pos()
            self.update()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._is_dragging:
            self._is_dragging = False
            self._drag_start = None
            self.setCursor(QCursor(Qt.ArrowCursor))
        super().mouseReleaseEvent(event)

    # --- Drag & Drop Camera Assignment ---

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        dropped_text = event.mimeData().text().strip()
        if dropped_text:
            logger.info("Camera drag-dropped onto [%s]: %s", self.channel_id, dropped_text)
            self.camera_dropped.emit(self.channel_id, dropped_text)
            event.acceptProposedAction()

    # --- Context Menu ---

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #161b22; color: #e6edf3; border: 1px solid #30363d; padding: 4px; }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background-color: #1f6feb; color: #ffffff; }
        """)

        # Stream Profile Submenu
        profile_menu = menu.addMenu("Stream Profile")
        act_main = profile_menu.addAction("Main Stream (High Resolution)")
        act_sub = profile_menu.addAction("Substream (Low Latency / AI)")

        cur_profile = self._telemetry.current_profile if self._telemetry else "MAIN"
        act_main.setCheckable(True)
        act_main.setChecked(cur_profile == "MAIN")
        act_sub.setCheckable(True)
        act_sub.setChecked(cur_profile == "SUB")

        act_main.triggered.connect(lambda: self.profile_switched.emit(self.channel_id, "MAIN"))
        act_sub.triggered.connect(lambda: self.profile_switched.emit(self.channel_id, "SUB"))

        menu.addSeparator()

        # PTZ Action
        act_ptz = menu.addAction("PTZ Control Panel...")
        act_ptz.triggered.connect(lambda: self.ptz_requested.emit(self.channel_id))

        # Snapshot Action
        act_snap = menu.addAction("Capture Snapshot (S)")
        act_snap.triggered.connect(self.capture_snapshot)

        # Digital Zoom Reset
        if self._zoom_factor > 1.0:
            act_reset_zoom = menu.addAction(f"Reset Zoom ({self._zoom_factor:.1f}x -> 1.0x)")
            act_reset_zoom.triggered.connect(self.reset_digital_zoom)

        # Maximize Action
        act_max = menu.addAction("Restore View" if self._is_maximized else "Maximize Tile")
        act_max.triggered.connect(lambda: self.double_clicked.emit(self.channel_id))

        menu.exec_(event.globalPos())

    # --- Rendering ---

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        # 1. Background
        painter.fillRect(0, 0, w, h, QColor("#0d1117"))

        # 2. Render Video Frame (handling Digital Zoom & aspect ratio)
        if self._current_qimage is not None and not self._current_qimage.isNull():
            img = self._current_qimage
            iw, ih = img.width(), img.height()

            if self._zoom_factor > 1.0:
                # Calculate zoomed crop rectangle
                crop_w = int(iw / self._zoom_factor)
                crop_h = int(ih / self._zoom_factor)
                cx = int(self._pan_x * iw)
                cy = int(self._pan_y * ih)
                crop_x = max(0, min(iw - crop_w, cx - crop_w // 2))
                crop_y = max(0, min(ih - crop_h, cy - crop_h // 2))
                cropped_img = img.copy(crop_x, crop_y, crop_w, crop_h)
                scaled = cropped_img.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            else:
                scaled = img.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            x = (w - scaled.width()) // 2
            y = (h - scaled.height()) // 2
            painter.drawImage(x, y, scaled)
        else:
            # Standby / No Signal placeholder
            painter.setPen(QPen(QColor("#484f58"), 1))
            painter.setFont(QFont("Segoe UI", 11))
            painter.drawText(QRect(0, 0, w, h), Qt.AlignCenter, f"{self.channel_name}\n[NO VIDEO SIGNAL]")

        # 3. Snapshot Visual Flash Effect
        if self._flash_active:
            painter.fillRect(0, 0, w, h, QColor(255, 255, 255, 120))
            painter.setPen(QPen(QColor("#ffffff"), 3))
            painter.drawRect(1, 1, w - 2, h - 2)

        # 4. Selection Highlight Border
        if self._is_selected:
            painter.setPen(QPen(QColor("#58a6ff"), 2))
            painter.drawRect(1, 1, w - 2, h - 2)

        # 5. OSD Header Bar (Top Bar Gradient / Semi-transparent)
        painter.fillRect(0, 0, w, 28, QColor(0, 0, 0, 180))

        # Camera Name & Status Dot
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.setPen(QColor("#ffffff"))
        painter.drawText(26, 19, self.channel_name)

        # Status Dot
        state = self._telemetry.state if self._telemetry else StreamState.OFFLINE
        if state == StreamState.ONLINE:
            dot_color = QColor("#238636")  # Green
        elif state == StreamState.RECONNECTING or state == StreamState.CONNECTING:
            dot_color = QColor("#d29922")  # Yellow
        elif state == StreamState.FROZEN:
            dot_color = QColor("#db61a2")  # Magenta for frozen
        else:
            dot_color = QColor("#f85149")  # Red

        painter.setBrush(QBrush(dot_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(10, 9, 10, 10)

        # Status Badges: [REC], [AI], [PTZ]
        badge_x = 28 + len(self.channel_name) * 8 + 10
        if self.is_recording:
            painter.setBrush(QBrush(QColor("#da3633")))
            painter.drawRoundedRect(badge_x, 6, 38, 16, 3, 3)
            painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(QRect(badge_x, 6, 38, 16), Qt.AlignCenter, "REC")
            badge_x += 44

        if self.is_ai_active:
            painter.setBrush(QBrush(QColor("#1f6feb")))
            painter.drawRoundedRect(badge_x, 6, 26, 16, 3, 3)
            painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(QRect(badge_x, 6, 26, 16), Qt.AlignCenter, "AI")
            badge_x += 32

        if self.has_ptz:
            painter.setBrush(QBrush(QColor("#8957e5")))
            painter.drawRoundedRect(badge_x, 6, 34, 16, 3, 3)
            painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(QRect(badge_x, 6, 34, 16), Qt.AlignCenter, "PTZ")

        # Top-Right Telemetry (Resolution, FPS, Profile)
        fps_text = f"{self._telemetry.current_fps:.1f} FPS" if self._telemetry else "0.0 FPS"
        res_text = f"{self._telemetry.detected_width}x{self._telemetry.detected_height}" if self._telemetry and self._telemetry.detected_width > 0 else ""
        prof_text = f"[{self._telemetry.current_profile}]" if self._telemetry else ""
        telemetry_str = f"{prof_text} {res_text} {fps_text}".strip()

        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#58a6ff"))
        painter.drawText(QRect(w - 200, 0, 192, 28), Qt.AlignRight | Qt.AlignVCenter, telemetry_str)

        # 6. Bottom-Left Digital Zoom Badge (if zoomed in)
        if self._zoom_factor > 1.0:
            zoom_rect = QRect(8, h - 30, 84, 22)
            painter.setBrush(QBrush(QColor(22, 27, 34, 220)))
            painter.setPen(QPen(QColor("#1f6feb"), 1))
            painter.drawRoundedRect(zoom_rect, 4, 4)
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.setPen(QColor("#58a6ff"))
            painter.drawText(zoom_rect, Qt.AlignCenter, f"ZOOM {self._zoom_factor:.1f}x")

        # 7. Bottom-Right Snapshot Button Overlay
        rect_snap = QRect(w - 38, h - 34, 30, 26)
        painter.setBrush(QBrush(QColor(22, 27, 34, 200)))
        painter.setPen(QPen(QColor("#30363d"), 1))
        painter.drawRoundedRect(rect_snap, 4, 4)

        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.setPen(QColor("#e6edf3"))
        painter.drawText(rect_snap, Qt.AlignCenter, "SNAP")

