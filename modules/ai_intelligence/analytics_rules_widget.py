"""
Analytics Rules & Video Analytics Management Interface.
Provides interactive polygon zone drawing, virtual tripwire configuration,
rule scheduling, alarm parameters, counting dashboards, and heatmap generation.
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
from database.models.analytics import AnalyticsZone, TripwireLine, AnalyticsRule
from engines.analytics_engine.analytics_pipeline import (
    analytics_manager,
    ZoneConfig,
    TripwireConfig,
    AnalyticsRuleConfig,
)
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("analytics_rules_widget")


class InteractiveAnalyticsCanvas(QWidget):
    """
    Interactive drawing canvas for surveillance polygon zones and tripwires.
    Renders over the video feed or synthetic reference frame in normalized [0, 1] space.
    """

    drawing_completed = Signal(str, list)  # type ("ZONE" or "TRIPWIRE"), points

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(480, 270)
        self.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; border-radius: 6px;")

        self.mode: str = "VIEW"  # "VIEW", "DRAW_ZONE", "DRAW_TRIPWIRE"
        self._current_points: List[Tuple[float, float]] = []
        self._zones: List[ZoneConfig] = []
        self._tripwires: List[TripwireConfig] = []
        self._background_image: Optional[QImage] = None

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self._current_points.clear()
        self.update()

    def set_entities(self, zones: List[ZoneConfig], tripwires: List[TripwireConfig]) -> None:
        self._zones = list(zones)
        self._tripwires = list(tripwires)
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
        if event.button() == Qt.LeftButton:
            w = max(self.width(), 1)
            h = max(self.height(), 1)
            nx = max(0.0, min(1.0, event.position().x() / w))
            ny = max(0.0, min(1.0, event.position().y() / h))

            if self.mode == "DRAW_ZONE":
                self._current_points.append((nx, ny))
                self.update()
            elif self.mode == "DRAW_TRIPWIRE":
                self._current_points.append((nx, ny))
                if len(self._current_points) >= 2:
                    pts = list(self._current_points[:2])
                    self.drawing_completed.emit("TRIPWIRE", pts)
                    self._current_points.clear()
                    self.mode = "VIEW"
                self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        if self.mode == "DRAW_ZONE" and len(self._current_points) >= 3:
            pts = list(self._current_points)
            self.drawing_completed.emit("ZONE", pts)
            self._current_points.clear()
            self.mode = "VIEW"
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # 1. Background Frame
        if self._background_image:
            scaled = self._background_image.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            bx = (w - scaled.width()) // 2
            by = (h - scaled.height()) // 2
            painter.drawImage(bx, by, scaled)
        else:
            # Grid pattern
            painter.fillRect(0, 0, w, h, QColor("#0d1117"))
            painter.setPen(QPen(QColor("#161b22"), 1, Qt.DotLine))
            for x in range(0, w, 40):
                painter.drawLine(x, 0, x, h)
            for y in range(0, h, 40):
                painter.drawLine(0, y, w, y)

        # 2. Render Existing Zones
        for zone in self._zones:
            if not zone.polygon:
                continue
            poly = QPolygonF()
            for px, py in zone.polygon:
                poly.append(QPointF(px * w, py * h))

            col = QColor(zone.color_hex if zone.color_hex else "#FF0000")
            fill_col = QColor(col)
            fill_col.setAlpha(60)

            painter.setBrush(QBrush(fill_col))
            painter.setPen(QPen(col, 2, Qt.DashLine if not zone.is_active else Qt.SolidLine))
            painter.drawPolygon(poly)

            # Draw Zone Label
            first_pt = poly[0]
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(int(first_pt.x() + 4), int(first_pt.y() - 4), f"Zone: {zone.name}")

        # 3. Render Existing Tripwires
        for tw in self._tripwires:
            p1 = QPointF(tw.pt1[0] * w, tw.pt1[1] * h)
            p2 = QPointF(tw.pt2[0] * w, tw.pt2[1] * h)

            col = QColor(tw.color_hex if tw.color_hex else "#00FF00")
            painter.setPen(QPen(col, 3, Qt.SolidLine))
            painter.drawLine(p1, p2)

            # Draw Endpoints
            painter.setBrush(QBrush(col))
            painter.drawEllipse(p1, 5, 5)
            painter.drawEllipse(p2, 5, 5)

            # Label & Direction
            mid = (p1 + p2) / 2
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(int(mid.x() + 6), int(mid.y() - 6), f"{tw.name} ({tw.direction})")

        # 4. Render Active In-Progress Drawing
        if self.mode == "DRAW_ZONE" and self._current_points:
            painter.setPen(QPen(QColor("#58a6ff"), 2, Qt.DashLine))
            painter.setBrush(QBrush(QColor(88, 166, 255, 40)))
            poly = QPolygonF()
            for px, py in self._current_points:
                pt = QPointF(px * w, py * h)
                poly.append(pt)
                painter.drawEllipse(pt, 4, 4)
            painter.drawPolyline(poly)
        elif self.mode == "DRAW_TRIPWIRE" and self._current_points:
            pt = QPointF(self._current_points[0][0] * w, self._current_points[0][1] * h)
            painter.setPen(QPen(QColor("#3fb950"), 3))
            painter.drawEllipse(pt, 5, 5)


class AnalyticsRulesWidget(QWidget):
    """
    Complete Video Analytics & Intelligent Surveillance Rules Management Workspace.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.selected_channel_id = "CAM_01"
        self._init_ui()
        self._load_cameras()
        self._refresh_channel_data()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header bar
        header_bar = QHBoxLayout()
        lbl_title = QLabel("VIDEO ANALYTICS & INTELLIGENT SURVEILLANCE RULES")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #58a6ff;")
        header_bar.addWidget(lbl_title)
        header_bar.addStretch()

        lbl_cam = QLabel("Camera:")
        lbl_cam.setStyleSheet("color: #8b949e; font-weight: 600;")
        header_bar.addWidget(lbl_cam)

        self.combo_camera = QComboBox()
        self.combo_camera.setMinimumWidth(160)
        self.combo_camera.currentTextChanged.connect(self._on_camera_changed)
        header_bar.addWidget(self.combo_camera)

        main_layout.addLayout(header_bar)

        # Content Splitter (Left: Live Canvas & Controls, Right: Configuration & Tables)
        splitter = QSplitter(Qt.Horizontal)

        # Left Column: Canvas & Drawing Tools
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.canvas = InteractiveAnalyticsCanvas()
        self.canvas.drawing_completed.connect(self._on_drawing_completed)
        left_layout.addWidget(self.canvas, stretch=1)

        # Canvas Action Toolbar
        tool_layout = QHBoxLayout()
        self.btn_draw_zone = QPushButton("+ Draw Polygon Zone")
        self.btn_draw_zone.setStyleSheet("background-color: #238636; color: white; padding: 6px 12px; font-weight: 600; border-radius: 4px;")
        self.btn_draw_zone.clicked.connect(lambda: self.canvas.set_mode("DRAW_ZONE"))
        tool_layout.addWidget(self.btn_draw_zone)

        self.btn_draw_line = QPushButton("+ Draw Tripwire Line")
        self.btn_draw_line.setStyleSheet("background-color: #1f6feb; color: white; padding: 6px 12px; font-weight: 600; border-radius: 4px;")
        self.btn_draw_line.clicked.connect(lambda: self.canvas.set_mode("DRAW_TRIPWIRE"))
        tool_layout.addWidget(self.btn_draw_line)

        self.btn_clear_canvas = QPushButton("Cancel Drawing")
        self.btn_clear_canvas.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; color: #8b949e; padding: 6px 12px; border-radius: 4px;")
        self.btn_clear_canvas.clicked.connect(lambda: self.canvas.set_mode("VIEW"))
        tool_layout.addWidget(self.btn_clear_canvas)

        tool_layout.addStretch()
        left_layout.addLayout(tool_layout)

        # Real-time Occupancy & Counting Metric Bar
        occ_frame = QFrame()
        occ_frame.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 10px;")
        occ_layout = QHBoxLayout(occ_frame)

        self.lbl_occ = QLabel("Current Occupancy: 0")
        self.lbl_occ.setStyleSheet("font-size: 13px; font-weight: bold; color: #3fb950;")
        occ_layout.addWidget(self.lbl_occ)

        self.lbl_counts = QLabel("In: 0 | Out: 0 (Persons: 0 | Vehicles: 0)")
        self.lbl_counts.setStyleSheet("color: #8b949e;")
        occ_layout.addWidget(self.lbl_counts)

        occ_layout.addStretch()
        self.btn_reset_counter = QPushButton("Reset Counters")
        self.btn_reset_counter.setStyleSheet("background-color: #da3633; color: white; border-radius: 4px; padding: 4px 8px; font-size: 11px;")
        self.btn_reset_counter.clicked.connect(self._reset_counters)
        occ_layout.addWidget(self.btn_reset_counter)

        left_layout.addWidget(occ_frame)
        splitter.addWidget(left_widget)

        # Right Column: Tabs (Rules, Counting, Heatmap)
        right_tabs = QTabWidget()
        right_tabs.setStyleSheet("QTabBar::tab { background: #161b22; color: #8b949e; padding: 8px 16px; border: 1px solid #30363d; } QTabBar::tab:selected { background: #21262d; color: #58a6ff; font-weight: bold; }")

        # Tab 1: Rules Configuration & Management
        tab_rules = QWidget()
        rules_layout = QVBoxLayout(tab_rules)
        rules_layout.setContentsMargins(8, 8, 8, 8)

        # Rule Creation Form
        form_box = QGroupBox("Create Surveillance Rule")
        form_box.setStyleSheet("QGroupBox { color: #8b949e; font-weight: 600; border: 1px solid #30363d; border-radius: 4px; margin-top: 10px; padding-top: 10px; }")
        form_layout = QFormLayout(form_box)

        self.edit_rule_name = QLineEdit()
        self.edit_rule_name.setPlaceholderText("e.g. Front Gate Intrusion")
        form_layout.addRow("Rule Name:", self.edit_rule_name)

        self.combo_rule_type = QComboBox()
        self.combo_rule_type.addItems(["INTRUSION", "LINE_CROSSING", "LOITERING", "COUNTING"])
        form_layout.addRow("Rule Type:", self.combo_rule_type)

        self.combo_target_entity = QComboBox()
        form_layout.addRow("Bound Zone / Line:", self.combo_target_entity)

        # Class Selection
        class_layout = QHBoxLayout()
        self.chk_person = QCheckBox("Person")
        self.chk_person.setChecked(True)
        self.chk_vehicle = QCheckBox("Vehicles")
        self.chk_vehicle.setChecked(True)
        class_layout.addWidget(self.chk_person)
        class_layout.addWidget(self.chk_vehicle)
        form_layout.addRow("Target Classes:", class_layout)

        # Thresholds
        thresh_layout = QHBoxLayout()
        self.spin_confidence = QDoubleSpinBox()
        self.spin_confidence.setRange(0.1, 1.0)
        self.spin_confidence.setValue(0.50)
        self.spin_confidence.setSingleStep(0.05)
        thresh_layout.addWidget(QLabel("Min Conf:"))
        thresh_layout.addWidget(self.spin_confidence)

        self.spin_dwell = QDoubleSpinBox()
        self.spin_dwell.setRange(1.0, 300.0)
        self.spin_dwell.setValue(5.0)
        thresh_layout.addWidget(QLabel("Dwell (s):"))
        thresh_layout.addWidget(self.spin_dwell)
        form_layout.addRow("Parameters:", thresh_layout)

        # Severity & Actions
        action_layout = QHBoxLayout()
        self.combo_severity = QComboBox()
        self.combo_severity.addItems(["INFO", "WARNING", "CRITICAL"])
        self.combo_severity.setCurrentText("WARNING")
        action_layout.addWidget(QLabel("Severity:"))
        action_layout.addWidget(self.combo_severity)

        self.chk_trigger_rec = QCheckBox("Trigger Recording")
        self.chk_trigger_rec.setChecked(True)
        action_layout.addWidget(self.chk_trigger_rec)
        form_layout.addRow("Action:", action_layout)

        btn_save_rule = QPushButton("Save Rule")
        btn_save_rule.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 6px; border-radius: 4px;")
        btn_save_rule.clicked.connect(self._save_rule)
        form_layout.addRow(btn_save_rule)

        rules_layout.addWidget(form_box)

        # Existing Rules Table
        rules_layout.addWidget(QLabel("Configured Camera Rules:"))
        self.tbl_rules = QTableWidget(0, 6)
        self.tbl_rules.setHorizontalHeaderLabels(["Name", "Type", "Target", "Severity", "Active", "Actions"])
        self.tbl_rules.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_rules.setStyleSheet("background-color: #0d1117; color: #c9d1d9; gridline-color: #30363d;")
        rules_layout.addWidget(self.tbl_rules)

        right_tabs.addTab(tab_rules, "Surveillance Rules")

        # Tab 2: Movement Heatmaps
        tab_heatmap = QWidget()
        hm_layout = QVBoxLayout(tab_heatmap)
        hm_layout.setContentsMargins(8, 8, 8, 8)

        hm_controls = QHBoxLayout()
        hm_controls.addWidget(QLabel("Time Range:"))
        self.combo_hm_range = QComboBox()
        self.combo_hm_range.addItems(["Last 15 Minutes", "Last 1 Hour", "Last 24 Hours", "All Available"])
        hm_controls.addWidget(self.combo_hm_range)

        btn_gen_hm = QPushButton("Generate Heatmap")
        btn_gen_hm.setStyleSheet("background-color: #1f6feb; color: white; padding: 6px 12px; border-radius: 4px;")
        btn_gen_hm.clicked.connect(self._generate_heatmap)
        hm_controls.addWidget(btn_gen_hm)

        btn_export_hm = QPushButton("Export Heatmap Image")
        btn_export_hm.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 6px 12px; border-radius: 4px;")
        btn_export_hm.clicked.connect(self._export_heatmap)
        hm_controls.addWidget(btn_export_hm)

        hm_controls.addStretch()
        hm_layout.addLayout(hm_controls)

        self.lbl_heatmap_view = QLabel("Click 'Generate Heatmap' to compute movement density matrix.")
        self.lbl_heatmap_view.setAlignment(Qt.AlignCenter)
        self.lbl_heatmap_view.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; border-radius: 6px; min-height: 240px; color: #8b949e;")
        hm_layout.addWidget(self.lbl_heatmap_view, stretch=1)

        right_tabs.addTab(tab_heatmap, "Movement Heatmap")

        splitter.addWidget(right_tabs)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter, stretch=1)

    def _load_cameras(self) -> None:
        self.combo_camera.clear()
        # Default logical cameras
        self.combo_camera.addItems(["CAM_01", "CAM_02", "CAM_03", "CAM_04"])

    def _on_camera_changed(self, cam_id: str) -> None:
        if not cam_id:
            return
        self.selected_channel_id = cam_id
        self._refresh_channel_data()

    def _refresh_channel_data(self) -> None:
        pipeline = analytics_manager.get_pipeline(self.selected_channel_id)

        # Update canvas
        zones = list(pipeline.zones.values())
        tripwires = list(pipeline.tripwires.values())
        self.canvas.set_entities(zones, tripwires)

        # Populate target entity dropdown
        self.combo_target_entity.clear()
        for z in zones:
            self.combo_target_entity.addItem(f"Zone: {z.name}", f"ZONE:{z.id}")
        for tw in tripwires:
            self.combo_target_entity.addItem(f"Tripwire: {tw.name}", f"TW:{tw.id}")

        # Update rules table
        rules = list(pipeline.rules.values())
        self.tbl_rules.setRowCount(len(rules))
        for r_idx, r in enumerate(rules):
            self.tbl_rules.setItem(r_idx, 0, QTableWidgetItem(r.name))
            self.tbl_rules.setItem(r_idx, 1, QTableWidgetItem(r.rule_type))
            target_desc = r.zone_id or r.tripwire_id or "General"
            self.tbl_rules.setItem(r_idx, 2, QTableWidgetItem(target_desc))
            self.tbl_rules.setItem(r_idx, 3, QTableWidgetItem(r.severity))
            self.tbl_rules.setItem(r_idx, 4, QTableWidgetItem("Active" if r.is_active else "Disabled"))

            btn_del = QPushButton("Delete")
            btn_del.setStyleSheet("background-color: #da3633; color: white; font-size: 11px;")
            rule_id = r.id
            btn_del.clicked.connect(lambda _, rid=rule_id: self._delete_rule(rid))
            self.tbl_rules.setCellWidget(r_idx, 5, btn_del)

        # Update occupancy bar
        summary = pipeline.counting_manager.get_summary()
        self.lbl_occ.setText(f"Current Occupancy: {summary['current_occupancy']}")
        self.lbl_counts.setText(
            f"In: {summary['total_entered']} | Out: {summary['total_exited']} "
            f"(Persons: {summary['person_entered']} | Vehicles: {summary['vehicle_entered']})"
        )

    def _on_drawing_completed(self, draw_type: str, points: list) -> None:
        pipeline = analytics_manager.get_pipeline(self.selected_channel_id)
        now_ts = int(time.time() * 1000)

        if draw_type == "ZONE":
            zone_id = f"zone_{now_ts}"
            name = f"Zone {len(pipeline.zones) + 1}"
            zone_cfg = ZoneConfig(
                id=zone_id,
                name=name,
                zone_type="INTRUSION",
                polygon=points,
                color_hex="#FF5555",
                is_active=True,
            )
            pipeline.add_zone(zone_cfg)

            # Persist to DB
            try:
                with db_manager.get_session() as session:
                    rec = AnalyticsZone(
                        id=zone_id,
                        channel_id=self.selected_channel_id,
                        name=name,
                        zone_type="INTRUSION",
                        polygon_json=json.dumps(points),
                        color_hex="#FF5555",
                        is_active=True,
                    )
                    session.add(rec)
                    session.commit()
                analytics_manager.audit_change(
                    user_id="offline_admin",
                    action="CREATE_ZONE",
                    entity_type="analytics_zone",
                    entity_id=zone_id,
                    details=f"Created polygon zone '{name}' on channel {self.selected_channel_id}",
                )
            except Exception as e:
                logger.error("DB error saving zone: %s", e)

        elif draw_type == "TRIPWIRE":
            tw_id = f"tw_{now_ts}"
            name = f"Line {len(pipeline.tripwires) + 1}"
            tw_cfg = TripwireConfig(
                id=tw_id,
                name=name,
                pt1=points[0],
                pt2=points[1],
                direction="BIDIRECTIONAL",
                color_hex="#00FF88",
                is_active=True,
            )
            pipeline.add_tripwire(tw_cfg)

            # Persist to DB
            try:
                with db_manager.get_session() as session:
                    rec = TripwireLine(
                        id=tw_id,
                        channel_id=self.selected_channel_id,
                        name=name,
                        line_coords_json=json.dumps({"pt1": list(points[0]), "pt2": list(points[1])}),
                        direction="BIDIRECTIONAL",
                        color_hex="#00FF88",
                        is_active=True,
                    )
                    session.add(rec)
                    session.commit()
                analytics_manager.audit_change(
                    user_id="offline_admin",
                    action="CREATE_TRIPWIRE",
                    entity_type="tripwire_line",
                    entity_id=tw_id,
                    details=f"Created tripwire line '{name}' on channel {self.selected_channel_id}",
                )
            except Exception as e:
                logger.error("DB error saving tripwire: %s", e)

        self._refresh_channel_data()

    def _save_rule(self) -> None:
        name = self.edit_rule_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Please specify a Rule Name.")
            return

        pipeline = analytics_manager.get_pipeline(self.selected_channel_id)
        rule_type = self.combo_rule_type.currentText()
        target_data = self.combo_target_entity.currentData()
        zone_id = None
        tripwire_id = None

        if target_data:
            if target_data.startswith("ZONE:"):
                zone_id = target_data.split(":", 1)[1]
            elif target_data.startswith("TW:"):
                tripwire_id = target_data.split(":", 1)[1]

        target_classes = []
        if self.chk_person.isChecked():
            target_classes.append("person")
        if self.chk_vehicle.isChecked():
            target_classes.extend(["car", "bus", "truck", "motorcycle", "bicycle"])

        rule_id = f"rule_{int(time.time() * 1000)}"
        rule_cfg = AnalyticsRuleConfig(
            id=rule_id,
            name=name,
            rule_type=rule_type,
            channel_id=self.selected_channel_id,
            zone_id=zone_id,
            tripwire_id=tripwire_id,
            target_classes=target_classes,
            confidence_threshold=self.spin_confidence.value(),
            min_dwell_time_sec=self.spin_dwell.value(),
            severity=self.combo_severity.currentText(),
            trigger_recording=self.chk_trigger_rec.isChecked(),
            is_active=True,
        )
        pipeline.add_rule(rule_cfg)

        # Persist to DB
        try:
            with db_manager.get_session() as session:
                rec = AnalyticsRule(
                    id=rule_id,
                    channel_id=self.selected_channel_id,
                    name=name,
                    rule_type=rule_type,
                    zone_id=zone_id,
                    tripwire_id=tripwire_id,
                    target_classes_json=json.dumps(target_classes),
                    confidence_threshold=self.spin_confidence.value(),
                    min_dwell_time_sec=self.spin_dwell.value(),
                    severity=self.combo_severity.currentText(),
                    trigger_recording=self.chk_trigger_rec.isChecked(),
                    is_active=True,
                )
                session.add(rec)
                session.commit()
            analytics_manager.audit_change(
                user_id="offline_admin",
                action="CREATE_RULE",
                entity_type="analytics_rule",
                entity_id=rule_id,
                details=f"Created {rule_type} rule '{name}' on channel {self.selected_channel_id}",
            )
        except Exception as e:
            logger.error("DB error saving rule: %s", e)

        self.edit_rule_name.clear()
        self._refresh_channel_data()

    def _delete_rule(self, rule_id: str) -> None:
        pipeline = analytics_manager.get_pipeline(self.selected_channel_id)
        pipeline.remove_rule(rule_id)

        try:
            with db_manager.get_session() as session:
                rule_rec = session.query(AnalyticsRule).filter_by(id=rule_id).first()
                if rule_rec:
                    rule_rec.is_deleted = True
                    session.commit()
            analytics_manager.audit_change(
                user_id="offline_admin",
                action="DELETE_RULE",
                entity_type="analytics_rule",
                entity_id=rule_id,
                details=f"Deleted rule {rule_id}",
            )
        except Exception as e:
            logger.error("DB error deleting rule: %s", e)

        self._refresh_channel_data()

    def _reset_counters(self) -> None:
        pipeline = analytics_manager.get_pipeline(self.selected_channel_id)
        pipeline.counting_manager.reset_counters()
        pipeline.tripwire_detector.reset_counters()
        analytics_manager.audit_change(
            user_id="offline_admin",
            action="RESET_COUNTERS",
            entity_type="counting_manager",
            entity_id=self.selected_channel_id,
            details=f"Manual counter reset on channel {self.selected_channel_id}",
        )
        self._refresh_channel_data()

    def _generate_heatmap(self) -> None:
        pipeline = analytics_manager.get_pipeline(self.selected_channel_id)
        now = time.time()
        range_choice = self.combo_hm_range.currentText()
        if "15 Min" in range_choice:
            t_start = now - 900
        elif "1 Hour" in range_choice:
            t_start = now - 3600
        elif "24 Hours" in range_choice:
            t_start = now - 86400
        else:
            t_start = 0.0

        hm_img = pipeline.heatmap_generator.render_heatmap_image(
            output_width=640, output_height=360, start_time=t_start, end_time=now
        )
        if hm_img is not None and hm_img.size > 0:
            rgb = cv2.cvtColor(hm_img, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            q_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            self.lbl_heatmap_view.setPixmap(QPixmap.fromImage(q_img).scaled(
                self.lbl_heatmap_view.width(), self.lbl_heatmap_view.height(), Qt.KeepAspectRatio
            ))
            self._current_heatmap_img = hm_img
        else:
            self.lbl_heatmap_view.setText("No trajectory data available in selected time range.")

    def _export_heatmap(self) -> None:
        if getattr(self, "_current_heatmap_img", None) is None:
            QMessageBox.information(self, "Export", "Please generate a heatmap before exporting.")
            return

        export_path = f"heatmap_{self.selected_channel_id}_{int(time.time())}.png"
        cv2.imwrite(export_path, self._current_heatmap_img)
        QMessageBox.information(self, "Export Successful", f"Heatmap image exported to {export_path}")
