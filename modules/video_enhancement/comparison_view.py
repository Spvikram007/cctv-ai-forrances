"""
Interactive Comparative Split-View Widget (Phase 9 - F-045).
Renders original and enhanced frames with an interactive draggable split-screen slider
or side-by-side dual viewport. Supports 60 FPS QPainter rendering with aspect ratio preservation.
"""

from typing import Optional, Tuple
import cv2
import numpy as np

from PySide6.QtCore import Qt, QPoint, QRect, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QImage, QPixmap, QMouseEvent, QPaintEvent
from PySide6.QtWidgets import QWidget, QSizePolicy


class ComparisonSplitView(QWidget):
    """
    Split-view comparative canvas.
    Modes:
    - 'split': Draggable vertical divider splitting the viewport into Original (left) and Enhanced (right).
    - 'side_by_side': Dual pane showing Original on left and Enhanced on right.
    """

    split_position_changed = Signal(float)

    MODE_SPLIT = "split"
    MODE_SIDE_BY_SIDE = "side_by_side"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(480, 320)

        self._orig_frame: Optional[np.ndarray] = None
        self._enh_frame: Optional[np.ndarray] = None
        self._orig_pixmap: Optional[QPixmap] = None
        self._enh_pixmap: Optional[QPixmap] = None

        self._split_ratio: float = 0.50  # 0.0 to 1.0
        self._mode: str = self.MODE_SPLIT
        self._is_dragging: bool = False
        self._divider_width: int = 4
        self._handle_radius: int = 14

    def set_images(self, orig_frame: Optional[np.ndarray], enh_frame: Optional[np.ndarray]) -> None:
        """Sets source and enhanced frames."""
        self._orig_frame = orig_frame
        self._enh_frame = enh_frame

        if orig_frame is not None and orig_frame.size > 0:
            self._orig_pixmap = self._cv_to_qpixmap(orig_frame)
        else:
            self._orig_pixmap = None

        if enh_frame is not None and enh_frame.size > 0:
            self._enh_pixmap = self._cv_to_qpixmap(enh_frame)
        else:
            self._enh_pixmap = None

        self.update()

    def set_split_ratio(self, ratio: float) -> None:
        """Sets split divider position (0.0 to 1.0)."""
        self._split_ratio = float(np.clip(ratio, 0.02, 0.98))
        self.update()
        self.split_position_changed.emit(self._split_ratio)

    @property
    def split_ratio(self) -> float:
        return self._split_ratio

    def set_view_mode(self, mode: str) -> None:
        """Sets view mode: 'split' or 'side_by_side'."""
        if mode in (self.MODE_SPLIT, self.MODE_SIDE_BY_SIDE):
            self._mode = mode
            self.update()

    @property
    def view_mode(self) -> str:
        return self._mode

    @staticmethod
    def _cv_to_qpixmap(frame: np.ndarray) -> QPixmap:
        """Converts BGR numpy image to QPixmap."""
        h, w = frame.shape[:2]
        if len(frame.shape) == 2:
            rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
        else:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
        return QPixmap.fromImage(qimg)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Background
        painter.fillRect(self.rect(), QColor("#0d1117"))

        if self._orig_pixmap is None and self._enh_pixmap is None:
            painter.setPen(QColor("#8b949e"))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(self.rect(), Qt.AlignCenter, "No Media Loaded\nLoad a recording clip or snapshot to begin enhancement")
            return

        if self._mode == self.MODE_SIDE_BY_SIDE:
            self._paint_side_by_side(painter)
        else:
            self._paint_split(painter)

    def _paint_split(self, painter: QPainter) -> None:
        """Draws split slider comparative view."""
        w = self.width()
        h = self.height()
        divider_x = int(w * self._split_ratio)

        # 1. Draw Original on Left
        if self._orig_pixmap is not None:
            scaled_orig = self._orig_pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            ox = (w - scaled_orig.width()) // 2
            oy = (h - scaled_orig.height()) // 2
            target_rect = QRect(ox, oy, scaled_orig.width(), scaled_orig.height())

            painter.save()
            painter.setClipRect(0, 0, divider_x, h)
            painter.drawPixmap(target_rect, scaled_orig)
            painter.restore()

        # 2. Draw Enhanced on Right
        pix_to_draw = self._enh_pixmap if self._enh_pixmap is not None else self._orig_pixmap
        if pix_to_draw is not None:
            scaled_enh = pix_to_draw.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            ex = (w - scaled_enh.width()) // 2
            ey = (h - scaled_enh.height()) // 2
            target_rect = QRect(ex, ey, scaled_enh.width(), scaled_enh.height())

            painter.save()
            painter.setClipRect(divider_x, 0, w - divider_x, h)
            painter.drawPixmap(target_rect, scaled_enh)
            painter.restore()

        # 3. Draw Divider Line
        painter.setPen(QPen(QColor("#58a6ff"), self._divider_width))
        painter.drawLine(divider_x, 0, divider_x, h)

        # 4. Draw Center Handle Button
        handle_y = h // 2
        painter.setBrush(QBrush(QColor("#1f6feb")))
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawEllipse(QPoint(divider_x, handle_y), self._handle_radius, self._handle_radius)

        # Arrows inside handle
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(
            QRect(divider_x - self._handle_radius, handle_y - self._handle_radius, self._handle_radius * 2, self._handle_radius * 2),
            Qt.AlignCenter,
            "⮂ ⮃"
        )

        # 5. Badges
        # Original Badge (top-left)
        painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
        painter.setPen(QPen(QColor("#8b949e"), 1))
        painter.drawRoundedRect(16, 16, 110, 26, 4, 4)
        painter.setPen(QColor("#c9d1d9"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(QRect(16, 16, 110, 26), Qt.AlignCenter, "ORIGINAL")

        # Enhanced Badge (top-right)
        painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
        painter.setPen(QPen(QColor("#238636"), 1))
        painter.drawRoundedRect(w - 146, 16, 130, 26, 4, 4)
        painter.setPen(QColor("#3fb950"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(QRect(w - 146, 16, 130, 26), Qt.AlignCenter, "AI ENHANCED")

    def _paint_side_by_side(self, painter: QPainter) -> None:
        """Draws two equal side-by-side viewports."""
        w = self.width()
        h = self.height()
        half_w = w // 2

        # Left: Original
        if self._orig_pixmap is not None:
            scaled_orig = self._orig_pixmap.scaled(half_w - 4, h - 8, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            ox = (half_w - scaled_orig.width()) // 2
            oy = (h - scaled_orig.height()) // 2
            painter.drawPixmap(ox, oy, scaled_orig)

        # Right: Enhanced
        pix_to_draw = self._enh_pixmap if self._enh_pixmap is not None else self._orig_pixmap
        if pix_to_draw is not None:
            scaled_enh = pix_to_draw.scaled(half_w - 4, h - 8, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            ex = half_w + 4 + (half_w - 4 - scaled_enh.width()) // 2
            ey = (h - scaled_enh.height()) // 2
            painter.drawPixmap(ex, ey, scaled_enh)

        # Center separator
        painter.setPen(QPen(QColor("#30363d"), 2))
        painter.drawLine(half_w, 0, half_w, h)

        # Labels
        painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
        painter.setPen(QPen(QColor("#8b949e"), 1))
        painter.drawRoundedRect(16, 16, 110, 26, 4, 4)
        painter.setPen(QColor("#c9d1d9"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(QRect(16, 16, 110, 26), Qt.AlignCenter, "ORIGINAL")

        painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
        painter.setPen(QPen(QColor("#238636"), 1))
        painter.drawRoundedRect(half_w + 16, 16, 130, 26, 4, 4)
        painter.setPen(QColor("#3fb950"))
        painter.drawText(QRect(half_w + 16, 16, 130, 26), Qt.AlignCenter, "AI ENHANCED")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._mode == self.MODE_SPLIT and event.button() == Qt.LeftButton:
            divider_x = int(self.width() * self._split_ratio)
            if abs(event.position().x() - divider_x) < 25:
                self._is_dragging = True
                self.setCursor(Qt.SplitHCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._mode == self.MODE_SPLIT:
            divider_x = int(self.width() * self._split_ratio)
            if abs(event.position().x() - divider_x) < 25:
                self.setCursor(Qt.SplitHCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

            if self._is_dragging:
                new_ratio = event.position().x() / float(self.width())
                self.set_split_ratio(new_ratio)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            self.setCursor(Qt.ArrowCursor)
