"""
Automatic Number Plate Recognition (ANPR) Command Workspace.
Provides live plate detection monitoring, cropped plate inspection,
parametric historical searches, and intelligence report exports.
"""

import time
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPixmap
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
    QCheckBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QGroupBox,
    QFormLayout,
    QFileDialog,
    QMessageBox,
)

import cv2
import numpy as np

from database.database_manager import db_manager
from database.models.biometrics import ANPRDetection
from engines.anpr_engine.anpr_search import ANPRSearchEngine
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("anpr_workspace")


class ANPRWorkspaceWidget(QWidget):
    """
    ANPR Live Monitoring and Investigation Workspace.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._init_ui()
        self._load_recent_detections()
        self._subscribe_events()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header
        header_layout = QHBoxLayout()
        lbl_title = QLabel("AUTOMATIC NUMBER PLATE RECOGNITION (ANPR)")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #58a6ff;")
        header_layout.addWidget(lbl_title)
        header_layout.addStretch()

        btn_refresh = QPushButton("Refresh Detections")
        btn_refresh.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 4px 10px; border-radius: 4px;")
        btn_refresh.clicked.connect(self._load_recent_detections)
        header_layout.addWidget(btn_refresh)

        main_layout.addLayout(header_layout)

        # Filter & Search Bar
        filter_box = QGroupBox("Investigation & Plate Search Filters")
        filter_box.setStyleSheet("QGroupBox { color: #8b949e; font-weight: 600; border: 1px solid #30363d; border-radius: 4px; margin-top: 6px; padding: 8px; }")
        filter_layout = QHBoxLayout(filter_box)

        self.edit_plate_search = QLineEdit()
        self.edit_plate_search.setPlaceholderText("Search plate (e.g. KA01* or ABC-1234)")
        filter_layout.addWidget(QLabel("Plate:"))
        filter_layout.addWidget(self.edit_plate_search, stretch=2)

        self.combo_cam = QComboBox()
        self.combo_cam.addItems(["ALL", "CAM_01", "CAM_02", "CAM_03", "CAM_04"])
        filter_layout.addWidget(QLabel("Camera:"))
        filter_layout.addWidget(self.combo_cam)

        self.combo_vclass = QComboBox()
        self.combo_vclass.addItems(["ALL", "car", "truck", "bus", "motorcycle"])
        filter_layout.addWidget(QLabel("Vehicle:"))
        filter_layout.addWidget(self.combo_vclass)

        self.chk_review_only = QCheckBox("Review Flagged Only")
        filter_layout.addWidget(self.chk_review_only)

        btn_search = QPushButton("Search")
        btn_search.setStyleSheet("background-color: #1f6feb; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        btn_search.clicked.connect(self._execute_search)
        filter_layout.addWidget(btn_search)

        btn_export = QPushButton("Export CSV")
        btn_export.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        btn_export.clicked.connect(self._export_csv)
        filter_layout.addWidget(btn_export)

        main_layout.addWidget(filter_box)

        # Splitter: Table on Left, Details & Crop Preview on Right
        splitter = QSplitter(Qt.Horizontal)

        # Left Table
        self.tbl_detections = QTableWidget(0, 7)
        self.tbl_detections.setHorizontalHeaderLabels([
            "Time (UTC)", "Camera", "Vehicle", "Plate Text", "Confidence", "Format", "Status"
        ])
        self.tbl_detections.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_detections.setStyleSheet("background-color: #0d1117; color: #c9d1d9; gridline-color: #21262d;")
        self.tbl_detections.itemSelectionChanged.connect(self._on_row_selected)
        splitter.addWidget(self.tbl_detections)

        # Right Inspector Card
        right_panel = QFrame()
        right_panel.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 12px;")
        right_layout = QVBoxLayout(right_panel)

        lbl_ins = QLabel("PLATE INSPECTOR")
        lbl_ins.setStyleSheet("font-size: 13px; font-weight: bold; color: #58a6ff;")
        right_layout.addWidget(lbl_ins)

        self.lbl_plate_preview = QLabel("Select a detection row to inspect cropped plate.")
        self.lbl_plate_preview.setAlignment(Qt.AlignCenter)
        self.lbl_plate_preview.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; border-radius: 4px; min-height: 120px; color: #8b949e;")
        right_layout.addWidget(self.lbl_plate_preview)

        self.lbl_details = QLabel("No detection selected.")
        self.lbl_details.setStyleSheet("color: #c9d1d9; font-size: 12px; margin-top: 8px;")
        self.lbl_details.setWordWrap(True)
        right_layout.addWidget(self.lbl_details)

        right_layout.addStretch()
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter, stretch=1)

    def _subscribe_events(self) -> None:
        bus.subscribe("anpr.plate_detected", self._on_live_plate_event)

    def _on_live_plate_event(self, data: Dict[str, Any]) -> None:
        try:
            # Prepend to table
            row = 0
            self.tbl_detections.insertRow(row)
            dt_str = datetime.fromtimestamp(data.get("timestamp", time.time()), tz=timezone.utc).strftime("%H:%M:%S")
            self.tbl_detections.setItem(row, 0, QTableWidgetItem(dt_str))
            self.tbl_detections.setItem(row, 1, QTableWidgetItem(data.get("channel_id", "")))
            self.tbl_detections.setItem(row, 2, QTableWidgetItem(data.get("vehicle_class", "")))

            item_plate = QTableWidgetItem(data.get("plate_text", ""))
            item_plate.setFont(QFont("Consolas", 11, QFont.Bold))
            self.tbl_detections.setItem(row, 3, item_plate)

            conf = data.get("confidence", 0.0)
            self.tbl_detections.setItem(row, 4, QTableWidgetItem(f"{conf:.1%}"))
            self.tbl_detections.setItem(row, 5, QTableWidgetItem("STANDARD"))

            status = "Manual Review" if data.get("requires_manual_review") else "Verified"
            status_item = QTableWidgetItem(status)
            if data.get("requires_manual_review"):
                status_item.setForeground(QColor("#f85149"))
            else:
                status_item.setForeground(QColor("#3fb950"))
            self.tbl_detections.setItem(row, 6, status_item)
        except RuntimeError:
            pass

    def _load_recent_detections(self) -> None:
        results = ANPRSearchEngine.search(limit=50)
        self._populate_table(results)

    def _execute_search(self) -> None:
        q = self.edit_plate_search.text().strip() or None
        cam = self.combo_cam.currentText()
        vclass = self.combo_vclass.currentText()
        review = self.chk_review_only.isChecked()

        results = ANPRSearchEngine.search(
            plate_query=q,
            channel_id=cam,
            vehicle_class=vclass,
            review_only=review,
            limit=100,
        )
        self._populate_table(results)

    def _populate_table(self, results: List[Dict[str, Any]]) -> None:
        self.current_results = results
        self.tbl_detections.setRowCount(len(results))

        for row, r in enumerate(results):
            self.tbl_detections.setItem(row, 0, QTableWidgetItem(str(r.get("timestamp", ""))[:19]))
            self.tbl_detections.setItem(row, 1, QTableWidgetItem(r.get("channel_id", "")))
            self.tbl_detections.setItem(row, 2, QTableWidgetItem(r.get("vehicle_class", "")))

            item_plate = QTableWidgetItem(r.get("plate_text", ""))
            item_plate.setFont(QFont("Consolas", 11, QFont.Bold))
            self.tbl_detections.setItem(row, 3, item_plate)

            conf = r.get("confidence", 0.0)
            self.tbl_detections.setItem(row, 4, QTableWidgetItem(f"{conf:.1%}"))
            self.tbl_detections.setItem(row, 5, QTableWidgetItem(r.get("plate_format", "STANDARD")))

            status = "Review Required" if r.get("requires_manual_review") else "Verified"
            status_item = QTableWidgetItem(status)
            if r.get("requires_manual_review"):
                status_item.setForeground(QColor("#f85149"))
            else:
                status_item.setForeground(QColor("#3fb950"))
            self.tbl_detections.setItem(row, 6, status_item)

    def _on_row_selected(self) -> None:
        selected_rows = self.tbl_detections.selectedItems()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        if hasattr(self, "current_results") and row < len(self.current_results):
            r = self.current_results[row]
            self.lbl_details.setText(
                f"Plate: {r.get('plate_text')}\n"
                f"Vehicle Class: {r.get('vehicle_class')}\n"
                f"Confidence: {r.get('confidence', 0.0):.1%}\n"
                f"Format: {r.get('plate_format')}\n"
                f"Channel: {r.get('channel_id')}\n"
                f"Track ID: {r.get('track_id')}\n"
                f"Crop Path: {r.get('plate_crop_path', 'None')}"
            )

    def _export_csv(self) -> None:
        if not hasattr(self, "current_results") or not self.current_results:
            QMessageBox.information(self, "Export", "No detection records to export.")
            return

        csv_text = ANPRSearchEngine.export_to_csv(self.current_results)
        path, _ = QFileDialog.getSaveFileName(self, "Export ANPR Report", "anpr_report.csv", "CSV Files (*.csv)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(csv_text)
            QMessageBox.information(self, "Export", f"Report exported successfully to {path}")
