"""
Interactive Multi-Channel Timeline Widget.
Renders 24-hour / multi-hour video recording tracks, color-coded recording modes
(Continuous, Motion, AI Event, Manual), recording gaps, and scrub cursor with
zoom and click/drag seeking.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QPolygonF, QMouseEvent, QWheelEvent


class TimelineWidget(QWidget):
    """
    Custom QPainter timeline for multi-camera video playback.
    Provides visual recording density, gaps, interactive scrubbing, and zoom.
    """

    seek_requested = Signal(object)  # Emits datetime (UTC) when user scrubs
    range_changed = Signal(object, object)  # Emits (start_time, end_time)

    # Color definitions (Dark surveillance palette)
    COLOR_BG = QColor("#161b22")
    COLOR_RULER_BG = QColor("#21262d")
    COLOR_TRACK_BG = QColor("#0d1117")
    COLOR_GRID_LINE = QColor("#30363d")
    COLOR_RULER_TEXT = QColor("#8b949e")
    COLOR_LABEL_TEXT = QColor("#c9d1d9")
    COLOR_PLAYHEAD = QColor("#f85149")  # Bright red scrub cursor
    COLOR_PLAYHEAD_BADGE = QColor("#f85149")

    # Mode Colors
    MODE_COLORS = {
        "CONTINUOUS": QColor("#238636"),   # Green
        "MOTION": QColor("#d29922"),       # Amber
        "AI_EVENT": QColor("#388bfd"),     # Cyan / Blue
        "MANUAL": QColor("#a371f7"),       # Purple
        "DEFAULT": QColor("#238636"),
    }

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumHeight(130)
        self.setMouseTracking(True)

        now = datetime.now(timezone.utc)
        self.view_start: datetime = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)
        self.view_end: datetime = self.view_start + timedelta(hours=24)
        self.current_time: datetime = now

        self.channels: List[str] = ["ch_1"]
        self.channel_names: Dict[str, str] = {"ch_1": "Camera 1"}
        # Map: channel_id -> list of {"start_time": dt, "end_time": dt, "recording_type": str}
        self.recording_data: Dict[str, List[Dict[str, Any]]] = {}

        self._is_scrubbing = False
        self._ruler_height = 26
        self._label_width = 80
        self._track_height = 22
        self._track_spacing = 4

    def set_channels(self, channels: List[str], names: Optional[Dict[str, str]] = None) -> None:
        """Sets the channels displayed on the timeline rows."""
        self.channels = channels
        if names:
            self.channel_names.update(names)
        # Adjust height based on number of channels
        req_height = self._ruler_height + len(self.channels) * (self._track_height + self._track_spacing) + 16
        self.setMinimumHeight(max(req_height, 120))
        self.update()

    def set_recording_data(self, channel_id: str, intervals: List[Dict[str, Any]]) -> None:
        """Sets the recording intervals for a given channel."""
        self.recording_data[channel_id] = intervals
        self.update()

    def set_all_recording_data(self, all_data: Dict[str, List[Dict[str, Any]]]) -> None:
        """Sets recording intervals for all channels at once."""
        self.recording_data = all_data
        self.update()

    def set_current_time(self, ts: datetime) -> None:
        """Updates the scrub playhead position without emitting seek_requested."""
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        self.current_time = ts
        self.update()

    def set_view_range(self, start_time: datetime, end_time: datetime) -> None:
        """Sets the visible timeline time range."""
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        if end_time > start_time:
            self.view_start = start_time
            self.view_end = end_time
            self.range_changed.emit(self.view_start, self.view_end)
            self.update()

    def _time_to_x(self, t: datetime, total_width: float) -> float:
        """Calculates X pixel coordinate for a given timestamp."""
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        total_sec = (self.view_end - self.view_start).total_seconds()
        if total_sec <= 0:
            return float(self._label_width)
        elapsed_sec = (t - self.view_start).total_seconds()
        ratio = elapsed_sec / total_sec
        return self._label_width + ratio * (total_width - self._label_width)

    def _x_to_time(self, x: float, total_width: float) -> datetime:
        """Calculates timestamp for a given X pixel coordinate."""
        usable_width = total_width - self._label_width
        if usable_width <= 0:
            return self.view_start
        ratio = max(0.0, min(1.0, (x - self._label_width) / usable_width))
        total_sec = (self.view_end - self.view_start).total_seconds()
        return self.view_start + timedelta(seconds=ratio * total_sec)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            x = event.position().x()
            if x >= self._label_width:
                self._is_scrubbing = True
                new_time = self._x_to_time(x, self.width())
                self.current_time = new_time
                self.seek_requested.emit(new_time)
                self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_scrubbing:
            x = event.position().x()
            new_time = self._x_to_time(x, self.width())
            self.current_time = new_time
            self.seek_requested.emit(new_time)
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._is_scrubbing = False
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zooms timeline in or out centered at cursor."""
        angle = event.angleDelta().y()
        if angle == 0:
            return

        cursor_x = event.position().x()
        center_time = self._x_to_time(cursor_x, self.width())

        current_span_sec = (self.view_end - self.view_start).total_seconds()
        zoom_factor = 0.8 if angle > 0 else 1.25
        new_span_sec = max(300.0, min(current_span_sec * zoom_factor, 172800.0))  # 5 mins to 48 hours

        ratio = (center_time - self.view_start).total_seconds() / current_span_sec
        new_start = center_time - timedelta(seconds=ratio * new_span_sec)
        new_end = new_start + timedelta(seconds=new_span_sec)

        self.set_view_range(new_start, new_end)
        event.accept()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())

        # 1. Background
        painter.fillRect(QRectF(0, 0, w, h), self.COLOR_BG)

        # 2. Ruler Background
        painter.fillRect(QRectF(0, 0, w, self._ruler_height), self.COLOR_RULER_BG)

        # Draw Ruler Divider
        painter.setPen(QPen(self.COLOR_GRID_LINE, 1))
        painter.drawLine(QPointF(0, self._ruler_height), QPointF(w, self._ruler_height))
        painter.drawLine(QPointF(self._label_width, 0), QPointF(self._label_width, h))

        # 3. Ruler Ticks & Time Labels
        total_span_sec = (self.view_end - self.view_start).total_seconds()
        if total_span_sec > 43200:      # > 12h: 2h step
            step_sec = 7200
        elif total_span_sec > 14400:    # > 4h: 1h step
            step_sec = 3600
        elif total_span_sec > 3600:     # > 1h: 15m step
            step_sec = 900
        elif total_span_sec > 900:      # > 15m: 5m step
            step_sec = 300
        else:                           # <= 15m: 1m step
            step_sec = 60

        # Align first tick to round step
        start_ts = self.view_start.timestamp()
        first_tick = (int(start_ts) // step_sec) * step_sec
        curr_tick = first_tick

        painter.setFont(QFont("Segoe UI", 8))
        while curr_tick <= self.view_end.timestamp() + step_sec:
            tick_dt = datetime.fromtimestamp(curr_tick, tz=timezone.utc)
            tick_x = self._time_to_x(tick_dt, w)
            if self._label_width <= tick_x <= w:
                # Vertical grid guide
                painter.setPen(QPen(self.COLOR_GRID_LINE, 1, Qt.DotLine))
                painter.drawLine(QPointF(tick_x, self._ruler_height), QPointF(tick_x, h))

                # Tick mark on ruler
                painter.setPen(QPen(self.COLOR_RULER_TEXT, 1))
                painter.drawLine(QPointF(tick_x, self._ruler_height - 6), QPointF(tick_x, self._ruler_height))

                # Label
                time_str = tick_dt.strftime("%H:%M")
                painter.drawText(QRectF(tick_x - 20, 4, 40, 16), Qt.AlignCenter, time_str)

            curr_tick += step_sec

        # 4. Tracks & Recording Intervals
        curr_y = self._ruler_height + 4
        for ch in self.channels:
            # Channel Label
            name = self.channel_names.get(ch, ch.upper())
            painter.setPen(self.COLOR_LABEL_TEXT)
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            painter.drawText(QRectF(6, curr_y, self._label_width - 12, self._track_height), Qt.AlignLeft | Qt.AlignVCenter, name)

            # Track Background (Gap indicator)
            track_rect = QRectF(self._label_width, curr_y, w - self._label_width, self._track_height)
            painter.fillRect(track_rect, self.COLOR_TRACK_BG)
            painter.setPen(QPen(self.COLOR_GRID_LINE, 1))
            painter.drawRect(track_rect)

            # Draw intervals
            intervals = self.recording_data.get(ch, [])
            for item in intervals:
                s_dt = item.get("start_time")
                e_dt = item.get("end_time")
                rec_type = item.get("recording_type", "CONTINUOUS")

                if s_dt and e_dt:
                    if s_dt.tzinfo is None:
                        s_dt = s_dt.replace(tzinfo=timezone.utc)
                    if e_dt.tzinfo is None:
                        e_dt = e_dt.replace(tzinfo=timezone.utc)

                    if e_dt >= self.view_start and s_dt <= self.view_end:
                        x1 = max(self._time_to_x(s_dt, w), float(self._label_width))
                        x2 = min(self._time_to_x(e_dt, w), w)
                        block_w = max(x2 - x1, 2.0)

                        color = self.MODE_COLORS.get(rec_type, self.MODE_COLORS["DEFAULT"])
                        painter.fillRect(QRectF(x1, curr_y + 2, block_w, self._track_height - 4), color)

            curr_y += self._track_height + self._track_spacing

        # 5. Playhead / Scrub Cursor
        cursor_x = self._time_to_x(self.current_time, w)
        if self._label_width <= cursor_x <= w:
            # Red vertical line
            painter.setPen(QPen(self.COLOR_PLAYHEAD, 2))
            painter.drawLine(QPointF(cursor_x, 0), QPointF(cursor_x, h))

            # Triangle handle on ruler
            triangle = QPolygonF([
                QPointF(cursor_x - 6, 0),
                QPointF(cursor_x + 6, 0),
                QPointF(cursor_x, 10),
            ])
            painter.setBrush(QBrush(self.COLOR_PLAYHEAD))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(triangle)

            # Time badge at cursor
            badge_time_str = self.current_time.strftime("%H:%M:%S")
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.setPen(QColor("#ffffff"))
            badge_rect = QRectF(cursor_x - 26, 11, 52, 14)
            painter.fillRect(badge_rect, self.COLOR_PLAYHEAD_BADGE)
            painter.drawText(badge_rect, Qt.AlignCenter, badge_time_str)
