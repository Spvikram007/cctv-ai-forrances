"""
Advanced Behaviour Analytics Interface (Phase 8).
Provides configuration and real-time visualization for:
- F-035: Crowd Density & Occupancy Estimation
- F-036: Abandoned & Removed Object Detection
- F-037: Fall Detection & Posture Analysis
- F-038: Directional & Wrong-Way Movement
- F-039: Advanced Behaviour Rule Engine & Incident Management
"""

import time
import json
from typing import Optional, List, Dict, Tuple, Any
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPen,
    QBrush,
    QPolygonF,
    QFont,
    QImage,
    QPixmap,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QGroupBox,
    QFormLayout,
    QTabWidget,
    QMessageBox,
)

import cv2
import numpy as np

from database.database_manager import db_manager
from database.models.analytics import AnalyticsRule, AnalyticsEvent
from engines.analytics_engine.analytics_pipeline import (
    analytics_manager,
    ZoneConfig,
)
from engines.analytics_engine.behaviour_detectors import (
    BehaviourRuleConfig,
    CrowdDensityConfig,
    StationaryObjectConfig,
    FallDetectionConfig,
    DirectionalConfig,
)
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("behaviour_analytics_widget")


class InteractiveBehaviourCanvas(QWidget):
    """
    Interactive drawing canvas for behaviour surveillance zones and directional arrows.
    Renders over video feeds or reference frames in normalized [0.0, 1.0] coordinate space.
    """

    drawing_completed = Signal(str, list)  # type ("ZONE" or "DIRECTION_ARROW"), points

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(480, 270)
        self.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; border-radius: 6px;")

        self.mode: str = "VIEW"  # "VIEW", "DRAW_ZONE", "DRAW_ARROW"
        self._current_points: List[Tuple[float, float]] = []
        self._zones: List[ZoneConfig] = []
        self._arrows: List[Tuple[Tuple[float, float], Tuple[float, float], str]] = []  # [(pt1, pt2, label)]
        self._background_image: Optional[QImage] = None

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self._current_points.clear()
        self.update()

    def set_entities(self, zones: List[ZoneConfig], arrows: Optional[List[Any]] = None) -> None:
        self._zones = list(zones)
        self._arrows = list(arrows or [])
        self.update()

    def set_background_frame(self, frame_bgr: np.ndarray) -> None:
        if frame_bgr is None or frame_bgr.size == 0:
            return
        h, w, ch = frame_bgr.shape
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        bytes_per_line = ch * w
        self._background_image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return

        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        nx = max(0.0, min(1.0, event.position().x() / float(w)))
        ny = max(0.0, min(1.0, event.position().y() / float(h)))

        if self.mode == "DRAW_ZONE":
            self._current_points.append((nx, ny))
            self.update()
        elif self.mode == "DRAW_ARROW":
            self._current_points.append((nx, ny))
            if len(self._current_points) >= 2:
                points = list(self._current_points[:2])
                self._current_points.clear()
                self.mode = "VIEW"
                self.drawing_completed.emit("DIRECTION_ARROW", points)
            self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        if self.mode == "DRAW_ZONE" and len(self._current_points) >= 3:
            points = list(self._current_points)
            self._current_points.clear()
            self.mode = "VIEW"
            self.drawing_completed.emit("ZONE", points)
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())

        # Render background frame
        if self._background_image:
            scaled = self._background_image.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x_offset = int((self.width() - scaled.width()) / 2)
            y_offset = int((self.height() - scaled.height()) / 2)
            painter.drawImage(x_offset, y_offset, scaled)
        else:
            painter.fillRect(self.rect(), QColor("#0d1117"))

        # Render zones
        for zone in self._zones:
            if not zone.polygon:
                continue
            poly = QPolygonF()
            for pt in zone.polygon:
                poly.append(QPointF(pt[0] * w, pt[1] * h))
            pen = QPen(QColor(zone.color_hex), 2)
            painter.setPen(pen)
            brush_color = QColor(zone.color_hex)
            brush_color.setAlpha(45)
            painter.setBrush(QBrush(brush_color))
            painter.drawPolygon(poly)

            # Zone label
            if zone.polygon:
                p1 = zone.polygon[0]
                painter.setPen(QColor("#ffffff"))
                painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
                painter.drawText(int(p1[0] * w), int(p1[1] * h) - 6, f"[{zone.zone_type}] {zone.name}")

        # Render direction arrows
        for pt1, pt2, label in self._arrows:
            p1 = QPointF(pt1[0] * w, pt1[1] * h)
            p2 = QPointF(pt2[0] * w, pt2[1] * h)
            pen = QPen(QColor("#f0883e"), 2, Qt.SolidLine)
            painter.setPen(pen)
            painter.drawLine(p1, p2)

            # Draw arrowhead
            painter.setBrush(QBrush(QColor("#f0883e")))
            painter.drawEllipse(p2, 4, 4)

            # Draw label
            mid_x = int((pt1[0] + pt2[0]) / 2.0 * w)
            mid_y = int((pt1[1] + pt2[1]) / 2.0 * h)
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.drawText(mid_x, mid_y - 4, label)

        # Render active drawing in progress
        if self._current_points:
            pen = QPen(QColor("#58a6ff"), 2, Qt.DashLine)
            painter.setPen(pen)
            for i in range(len(self._current_points) - 1):
                p_a = QPointF(self._current_points[i][0] * w, self._current_points[i][1] * h)
                p_b = QPointF(self._current_points[i + 1][0] * w, self._current_points[i + 1][1] * h)
                painter.drawLine(p_a, p_b)

            # Draw vertex handles
            painter.setBrush(QBrush(QColor("#58a6ff")))
            for pt in self._current_points:
                painter.drawEllipse(QPointF(pt[0] * w, pt[1] * h), 3, 3)

        painter.end()


class BehaviourAnalyticsWidget(QWidget):
    """
    Advanced Behaviour Analytics Workspace.
    Configures and monitors Crowd Density, Abandoned Objects, Falls, and Wrong-Way movements.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_channel_id: str = "CAM-01"
        self._init_ui()
        self._subscribe_events()

    def _init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        # Header bar
        header_bar = QHBoxLayout()
        title = QLabel("ADVANCED BEHAVIOUR ANALYTICS (PHASE 8)")
        title.setStyleSheet("color: #58a6ff; font-size: 16px; font-weight: 700;")
        header_bar.addWidget(title)

        header_bar.addStretch()

        ch_lbl = QLabel("Active Camera:")
        ch_lbl.setStyleSheet("color: #8b949e; font-weight: 600;")
        header_bar.addWidget(ch_lbl)

        self.channel_combo = QComboBox()
        self.channel_combo.addItems([f"CAM-{i:02d}" for i in range(1, 17)])
        self.channel_combo.setStyleSheet("background-color: #21262d; color: #c9d1d9; border: 1px solid #30363d; padding: 4px 10px; border-radius: 4px;")
        self.channel_combo.currentTextChanged.connect(self._on_channel_changed)
        header_bar.addWidget(self.channel_combo)

        root_layout.addLayout(header_bar)

        # Metric summary row
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(10)

        self.card_crowd = self._create_card("CROWD ALERTS", "0", "#58a6ff")
        self.card_abandoned = self._create_card("ABANDONED ITEMS", "0", "#d29922")
        self.card_falls = self._create_card("FALL INCIDENTS", "0", "#f85149")
        self.card_wrong_way = self._create_card("WRONG-WAY TRANSITS", "0", "#a371f7")

        metrics_layout.addWidget(self.card_crowd)
        metrics_layout.addWidget(self.card_abandoned)
        metrics_layout.addWidget(self.card_falls)
        metrics_layout.addWidget(self.card_wrong_way)
        root_layout.addLayout(metrics_layout)

        # Main splitter: Left (Canvas & Authoring) | Right (Events & Review)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background: #30363d; width: 2px; }")

        # Left panel: Visual Canvas + Parameter Controls
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.setSpacing(8)

        # Canvas toolbar
        tool_bar = QHBoxLayout()
        self.btn_draw_zone = QPushButton("Draw Zone (Double-Click Finish)")
        self.btn_draw_zone.setStyleSheet("background: #238636; color: white; padding: 6px 12px; border-radius: 4px; font-weight: 600;")
        self.btn_draw_zone.clicked.connect(lambda: self.canvas.set_mode("DRAW_ZONE"))

        self.btn_draw_arrow = QPushButton("Draw Direction Arrow")
        self.btn_draw_arrow.setStyleSheet("background: #1f6feb; color: white; padding: 6px 12px; border-radius: 4px; font-weight: 600;")
        self.btn_draw_arrow.clicked.connect(lambda: self.canvas.set_mode("DRAW_ARROW"))

        self.btn_clear = QPushButton("Clear Canvas")
        self.btn_clear.setStyleSheet("background: #30363d; color: #c9d1d9; padding: 6px 12px; border-radius: 4px;")
        self.btn_clear.clicked.connect(self._clear_canvas)

        tool_bar.addWidget(self.btn_draw_zone)
        tool_bar.addWidget(self.btn_draw_arrow)
        tool_bar.addWidget(self.btn_clear)
        tool_bar.addStretch()
        left_layout.addLayout(tool_bar)

        self.canvas = InteractiveBehaviourCanvas()
        self.canvas.drawing_completed.connect(self._on_drawing_completed)
        left_layout.addWidget(self.canvas, stretch=2)

        # Rule parameters configuration group
        config_group = QGroupBox("RULE & THRESHOLD PARAMETERS")
        config_group.setStyleSheet("QGroupBox { background: #161b22; border: 1px solid #30363d; border-radius: 6px; color: #c9d1d9; font-weight: 600; padding: 12px; }")
        config_form = QFormLayout(config_group)
        config_form.setSpacing(6)

        self.rule_type_combo = QComboBox()
        self.rule_type_combo.addItems(["CROWD_DENSITY", "ABANDONED_OBJECT", "FALL_DETECTION", "WRONG_WAY", "COMPOSITE"])
        self.rule_type_combo.setStyleSheet("background: #21262d; color: #c9d1d9; border: 1px solid #30363d; padding: 4px;")
        config_form.addRow("Rule Type:", self.rule_type_combo)

        self.spin_crowd_warn = QDoubleSpinBox()
        self.spin_crowd_warn.setRange(1.0, 20.0)
        self.spin_crowd_warn.setValue(3.0)
        self.spin_crowd_warn.setSuffix(" people/m²")
        self.spin_crowd_warn.setStyleSheet("background: #21262d; color: #c9d1d9; border: 1px solid #30363d;")
        config_form.addRow("Crowd Warning Density:", self.spin_crowd_warn)

        self.spin_crowd_crit = QDoubleSpinBox()
        self.spin_crowd_crit.setRange(1.0, 30.0)
        self.spin_crowd_crit.setValue(5.0)
        self.spin_crowd_crit.setSuffix(" people/m²")
        self.spin_crowd_crit.setStyleSheet("background: #21262d; color: #c9d1d9; border: 1px solid #30363d;")
        config_form.addRow("Crowd Critical Density:", self.spin_crowd_crit)

        self.spin_abandoned_dwell = QDoubleSpinBox()
        self.spin_abandoned_dwell.setRange(5.0, 600.0)
        self.spin_abandoned_dwell.setValue(60.0)
        self.spin_abandoned_dwell.setSuffix(" s")
        self.spin_abandoned_dwell.setStyleSheet("background: #21262d; color: #c9d1d9; border: 1px solid #30363d;")
        config_form.addRow("Abandoned Object Dwell:", self.spin_abandoned_dwell)

        self.spin_owner_dist = QDoubleSpinBox()
        self.spin_owner_dist.setRange(1.0, 20.0)
        self.spin_owner_dist.setValue(3.0)
        self.spin_owner_dist.setSuffix(" m")
        self.spin_owner_dist.setStyleSheet("background: #21262d; color: #c9d1d9; border: 1px solid #30363d;")
        config_form.addRow("Owner Separation Dist:", self.spin_owner_dist)

        self.spin_wrong_way_tol = QDoubleSpinBox()
        self.spin_wrong_way_tol.setRange(5.0, 90.0)
        self.spin_wrong_way_tol.setValue(30.0)
        self.spin_wrong_way_tol.setSuffix(" °")
        self.spin_wrong_way_tol.setStyleSheet("background: #21262d; color: #c9d1d9; border: 1px solid #30363d;")
        config_form.addRow("Wrong-Way Tolerance:", self.spin_wrong_way_tol)

        self.chk_human_review = QCheckBox("Require Human Review for Critical Alarms")
        self.chk_human_review.setChecked(True)
        self.chk_human_review.setStyleSheet("color: #8b949e;")
        config_form.addRow("", self.chk_human_review)

        self.btn_save_rule = QPushButton("Save & Deploy Rule")
        self.btn_save_rule.setStyleSheet("background: #1f6feb; color: white; padding: 6px; border-radius: 4px; font-weight: 600;")
        self.btn_save_rule.clicked.connect(self._save_rule)
        config_form.addRow("", self.btn_save_rule)

        left_layout.addWidget(config_group, stretch=1)
        splitter.addWidget(left_widget)

        # Right panel: Real-time Incident Feed & Review
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(6, 0, 0, 0)
        right_layout.setSpacing(8)

        incidents_lbl = QLabel("LIVE BEHAVIOUR INCIDENTS & EVIDENCE AUDIT")
        incidents_lbl.setStyleSheet("color: #c9d1d9; font-weight: 700; font-size: 13px;")
        right_layout.addWidget(incidents_lbl)

        self.table_events = QTableWidget()
        self.table_events.setColumnCount(7)
        self.table_events.setHorizontalHeaderLabels(["Time", "Camera", "Type", "Severity", "Confidence", "Human Review", "Evidence Summary"])
        self.table_events.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table_events.horizontalHeader().setStretchLastSection(True)
        self.table_events.setStyleSheet("""
            QTableWidget { background-color: #0d1117; color: #c9d1d9; border: 1px solid #30363d; gridline-color: #21262d; }
            QHeaderView::section { background-color: #161b22; color: #8b949e; font-weight: 600; border: 1px solid #21262d; padding: 4px; }
        """)
        self.table_events.verticalHeader().setVisible(False)
        right_layout.addWidget(self.table_events, stretch=1)

        # Action bar
        action_bar = QHBoxLayout()
        self.btn_verify = QPushButton("Verify Incident (Human Confirmed)")
        self.btn_verify.setStyleSheet("background: #238636; color: white; padding: 6px 12px; border-radius: 4px; font-weight: 600;")
        self.btn_verify.clicked.connect(self._verify_selected_incident)

        self.btn_dismiss = QPushButton("Dismiss (False Positive)")
        self.btn_dismiss.setStyleSheet("background: #da3633; color: white; padding: 6px 12px; border-radius: 4px; font-weight: 600;")
        self.btn_dismiss.clicked.connect(self._dismiss_selected_incident)

        action_bar.addWidget(self.btn_verify)
        action_bar.addWidget(self.btn_dismiss)
        action_bar.addStretch()
        right_layout.addLayout(action_bar)

        splitter.addWidget(right_widget)
        splitter.setSizes([500, 600])

        root_layout.addWidget(splitter, stretch=1)

    def _create_card(self, title: str, value: str, color_hex: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("QFrame { background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 8px; }")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("color: #8b949e; font-size: 10px; font-weight: 600;")
        lbl_v = QLabel(value)
        lbl_v.setStyleSheet(f"color: {color_hex}; font-size: 20px; font-weight: 700;")
        frame._val_label = lbl_v

        layout.addWidget(lbl_t)
        layout.addWidget(lbl_v)
        return frame

    def _subscribe_events(self) -> None:
        bus.subscribe("analytics.event", self._on_event_received)

    def _on_event_received(self, event) -> None:
        data = getattr(event, "data", event) if hasattr(event, "data") else event
        if not isinstance(data, dict):
            return

        rule_type = data.get("rule_type", "")
        if rule_type in ("CROWD_DENSITY", "ABANDONED_OBJECT", "UNATTENDED_OBJECT", "REMOVED_OBJECT", "FALL_DETECTION", "WRONG_WAY", "COMPOSITE_BEHAVIOUR"):
            self._insert_event_row(data)
            self._update_metric_counters(rule_type)

    def _update_metric_counters(self, rule_type: str) -> None:
        if rule_type == "CROWD_DENSITY":
            cur = int(self.card_crowd._val_label.text())
            self.card_crowd._val_label.setText(str(cur + 1))
        elif rule_type in ("ABANDONED_OBJECT", "UNATTENDED_OBJECT", "REMOVED_OBJECT"):
            cur = int(self.card_abandoned._val_label.text())
            self.card_abandoned._val_label.setText(str(cur + 1))
        elif rule_type == "FALL_DETECTION":
            cur = int(self.card_falls._val_label.text())
            self.card_falls._val_label.setText(str(cur + 1))
        elif rule_type == "WRONG_WAY":
            cur = int(self.card_wrong_way._val_label.text())
            self.card_wrong_way._val_label.setText(str(cur + 1))

    def _insert_event_row(self, data: Dict[str, Any]) -> None:
        row = self.table_events.rowCount()
        self.table_events.insertRow(row)

        ts = data.get("timestamp", time.time())
        t_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M:%S")

        details = data.get("details", {})
        summary = str(details)

        self.table_events.setItem(row, 0, QTableWidgetItem(t_str))
        self.table_events.setItem(row, 1, QTableWidgetItem(str(data.get("channel_id", ""))))
        self.table_events.setItem(row, 2, QTableWidgetItem(str(data.get("rule_type", ""))))

        sev_item = QTableWidgetItem(str(data.get("severity", "")))
        sev = data.get("severity", "").upper()
        if sev == "CRITICAL":
            sev_item.setForeground(QColor("#f85149"))
        elif sev == "WARNING":
            sev_item.setForeground(QColor("#d29922"))
        else:
            sev_item.setForeground(QColor("#58a6ff"))
        self.table_events.setItem(row, 3, sev_item)

        conf = data.get("confidence", 0.0)
        self.table_events.setItem(row, 4, QTableWidgetItem(f"{conf * 100.0:.1f}%"))

        review_req = details.get("requires_human_review", False)
        rev_item = QTableWidgetItem("PENDING REVIEW" if review_req else "AUTOMATED")
        rev_item.setForeground(QColor("#f0883e") if review_req else QColor("#8b949e"))
        self.table_events.setItem(row, 5, rev_item)

        self.table_events.setItem(row, 6, QTableWidgetItem(summary))
        self.table_events.scrollToBottom()

    def _verify_selected_incident(self) -> None:
        sel = self.table_events.selectedItems()
        if not sel:
            return
        row = sel[0].row()
        item = self.table_events.item(row, 5)
        if item:
            item.setText("CONFIRMED (HUMAN)")
            item.setForeground(QColor("#238636"))

    def _dismiss_selected_incident(self) -> None:
        sel = self.table_events.selectedItems()
        if not sel:
            return
        row = sel[0].row()
        item = self.table_events.item(row, 5)
        if item:
            item.setText("DISMISSED (FALSE POSITIVE)")
            item.setForeground(QColor("#8b949e"))

    def _on_channel_changed(self, channel_id: str) -> None:
        self.current_channel_id = channel_id

    def _on_drawing_completed(self, draw_type: str, points: list) -> None:
        if draw_type == "ZONE":
            zone_cfg = ZoneConfig(
                id=f"zone_{int(time.time())}",
                name=f"Behaviour Zone {len(self.canvas._zones) + 1}",
                zone_type="CROWD",
                polygon=points,
                color_hex="#d29922",
            )
            self.canvas._zones.append(zone_cfg)
            self.canvas.update()
        elif draw_type == "DIRECTION_ARROW":
            self.canvas._arrows.append((points[0], points[1], "ALLOWED FLOW"))
            self.canvas.update()

    def _clear_canvas(self) -> None:
        self.canvas.set_entities([], [])

    def _save_rule(self) -> None:
        pipeline = analytics_manager.get_pipeline(self.current_channel_id)
        rule_type = self.rule_type_combo.currentText()

        rule = BehaviourRuleConfig(
            id=f"brule_{int(time.time())}",
            name=f"{rule_type} Rule ({self.current_channel_id})",
            channel_id=self.current_channel_id,
            rule_type=rule_type,
            severity="CRITICAL" if rule_type in ("FALL_DETECTION", "ABANDONED_OBJECT") else "WARNING",
            trigger_recording=True,
        )
        pipeline.add_behaviour_rule(rule)
        QMessageBox.information(self, "Rule Saved", f"Behaviour rule '{rule.name}' saved and deployed successfully.")
