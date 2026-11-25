"""
Unified Alarm Management & Incident Command Center Workspace Widget.
Phase 12 (F-046, Change ID: CHG-20261125-009).

Mounts at View 9 in PySide6 MainWindow.
Provides real-time incident monitoring, multi-filter alarm feeds, detailed evidence
investigation, chronological lifecycle audit trails, SLA escalation tracking,
policy administration, and operational shift analytics.
"""

import os
import json
import csv
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTabWidget,
    QGroupBox,
    QFormLayout,
    QFileDialog,
    QMessageBox,
    QLineEdit,
    QComboBox,
    QTextEdit,
    QFrame,
    QSpinBox,
    QCheckBox,
    QInputDialog,
)

from core.logging.logger import get_logger
from core.events.event_bus import bus, Event
from engines.alarm_engine.enums import (
    AlarmSeverity,
    AlarmPriority,
    AlarmStatus,
    AlarmCategory,
)
from engines.alarm_engine.alarm_service import alarm_service

logger = get_logger("alarm_workspace_widget")


class AlarmMetricCard(QFrame):
    """Visual KPI summary card displaying key alarm counts."""

    def __init__(self, title: str, value: str = "0", color: str = "#3b82f6", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(f"""
            AlarmMetricCard {{
                background-color: #1a1a24;
                border: 1px solid #2e2e3e;
                border-radius: 6px;
                padding: 10px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        self.lbl_title = QLabel(title.upper())
        self.lbl_title.setStyleSheet("color: #888899; font-size: 11px; font-weight: bold; letter-spacing: 1px;")

        self.lbl_value = QLabel(value)
        self.lbl_value.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold;")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)

    def set_value(self, val: Any) -> None:
        self.lbl_value.setText(str(val))


class AlarmManagementWidget(QWidget):
    """
    Unified Alarm Management and Incident Command Center Workspace.
    """

    # Signal to request seeking in playback view (View 2)
    request_playback_seek = Signal(str, str)  # (camera_id, timestamp_iso)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_operator = "Operator_1"
        self.current_role = "OPERATOR"
        self._selected_alarm_id: Optional[str] = None

        self._init_ui()
        self._setup_event_listeners()

        # Auto-refresh timer every 5 seconds
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh_data)
        self._refresh_timer.start(5000)

        # Initial data load
        QTimer.singleShot(100, self.refresh_data)

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. Header Toolbar & Telemetry
        header_layout = QHBoxLayout()

        title_vbox = QVBoxLayout()
        lbl_header = QLabel("ALARM MANAGEMENT & INCIDENT COMMAND CENTER")
        lbl_header.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold; letter-spacing: 1px;")
        lbl_sub = QLabel("Central real-time incident classification, SLA escalation, evidence verification & lifecycle tracking")
        lbl_sub.setStyleSheet("color: #888899; font-size: 12px;")
        title_vbox.addWidget(lbl_header)
        title_vbox.addWidget(lbl_sub)
        header_layout.addLayout(title_vbox)

        header_layout.addStretch()

        # RBAC Testing Controls
        lbl_role = QLabel("Active Role:")
        lbl_role.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        self.combo_role = QComboBox()
        self.combo_role.addItems(["OPERATOR", "SUPERVISOR", "INVESTIGATOR", "ADMIN", "VIEWER"])
        self.combo_role.setCurrentText(self.current_role)
        self.combo_role.currentTextChanged.connect(self._on_role_changed)
        self.combo_role.setStyleSheet("background-color: #262636; color: #ffffff; padding: 4px; border: 1px solid #3c3c4f;")

        lbl_op = QLabel("Operator:")
        lbl_op.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        self.txt_operator = QLineEdit(self.current_operator)
        self.txt_operator.setFixedWidth(130)
        self.txt_operator.textChanged.connect(self._on_operator_changed)
        self.txt_operator.setStyleSheet("background-color: #262636; color: #ffffff; padding: 4px; border: 1px solid #3c3c4f;")

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setStyleSheet("background-color: #3b82f6; color: #ffffff; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        self.btn_refresh.clicked.connect(self.refresh_data)

        header_layout.addWidget(lbl_role)
        header_layout.addWidget(self.combo_role)
        header_layout.addWidget(lbl_op)
        header_layout.addWidget(self.txt_operator)
        header_layout.addWidget(self.btn_refresh)

        main_layout.addLayout(header_layout)

        # 2. Executive KPI Cards Bar
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(10)

        self.card_total = AlarmMetricCard("Active Incidents", "0", "#3b82f6")
        self.card_critical = AlarmMetricCard("Critical Alarms", "0", "#ef4444")
        self.card_unack = AlarmMetricCard("Unacknowledged", "0", "#f59e0b")
        self.card_in_progress = AlarmMetricCard("In Progress", "0", "#a855f7")
        self.card_escalated = AlarmMetricCard("SLA Escalated", "0", "#ec4899")
        self.card_resolved = AlarmMetricCard("Resolved Today", "0", "#10b981")

        cards_layout.addWidget(self.card_total)
        cards_layout.addWidget(self.card_critical)
        cards_layout.addWidget(self.card_unack)
        cards_layout.addWidget(self.card_in_progress)
        cards_layout.addWidget(self.card_escalated)
        cards_layout.addWidget(self.card_resolved)

        main_layout.addLayout(cards_layout)

        # 3. Main Multi-Tab Interface
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #2e2e3e;
                background-color: #12121a;
            }
            QTabBar::tab {
                background-color: #1a1a24;
                color: #888899;
                padding: 8px 18px;
                font-weight: bold;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #242436;
                color: #ffffff;
                border-bottom: 2px solid #3b82f6;
            }
        """)

        # Tab 1: Live Alarm Feed
        self.tab_feed = QWidget()
        self._init_feed_tab()
        self.tabs.addTab(self.tab_feed, "Incident Monitor")

        # Tab 2: Detail & Evidence
        self.tab_detail = QWidget()
        self._init_detail_tab()
        self.tabs.addTab(self.tab_detail, "Alarm Detail & Evidence")

        # Tab 3: Policies & SLA Rules
        self.tab_policies = QWidget()
        self._init_policies_tab()
        self.tabs.addTab(self.tab_policies, "Alarm Policies & Rules")

        # Tab 4: Shift Analytics & Reporting
        self.tab_stats = QWidget()
        self._init_stats_tab()
        self.tabs.addTab(self.tab_stats, "Analytics & SLA Reports")

        # Tab 5: Event Simulation
        self.tab_sim = QWidget()
        self._init_sim_tab()
        self.tabs.addTab(self.tab_sim, "Event Simulator")

        main_layout.addWidget(self.tabs)

    # -------------------------------------------------------------------------
    # TAB 1: Incident Monitor (Table + Filters + Quick Actions)
    # -------------------------------------------------------------------------
    def _init_feed_tab(self) -> None:
        layout = QVBoxLayout(self.tab_feed)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Filters row
        filter_box = QHBoxLayout()

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search title or description...")
        self.txt_search.textChanged.connect(self.refresh_data)
        self.txt_search.setStyleSheet("background-color: #1a1a24; color: #ffffff; padding: 6px; border: 1px solid #2e2e3e; border-radius: 4px;")
        filter_box.addWidget(self.txt_search, stretch=2)

        self.combo_sev_filter = QComboBox()
        self.combo_sev_filter.addItem("Severity: All", None)
        for s in AlarmSeverity:
            self.combo_sev_filter.addItem(s.value, s.value)
        self.combo_sev_filter.currentIndexChanged.connect(self.refresh_data)
        self.combo_sev_filter.setStyleSheet("background-color: #1a1a24; color: #ffffff; padding: 6px; border: 1px solid #2e2e3e;")
        filter_box.addWidget(self.combo_sev_filter)

        self.combo_stat_filter = QComboBox()
        self.combo_stat_filter.addItem("Status: All", None)
        for st in AlarmStatus:
            self.combo_stat_filter.addItem(st.value, st.value)
        self.combo_stat_filter.currentIndexChanged.connect(self.refresh_data)
        self.combo_stat_filter.setStyleSheet("background-color: #1a1a24; color: #ffffff; padding: 6px; border: 1px solid #2e2e3e;")
        filter_box.addWidget(self.combo_stat_filter)

        self.combo_cat_filter = QComboBox()
        self.combo_cat_filter.addItem("Category: All", None)
        for c in AlarmCategory:
            self.combo_cat_filter.addItem(c.value, c.value)
        self.combo_cat_filter.currentIndexChanged.connect(self.refresh_data)
        self.combo_cat_filter.setStyleSheet("background-color: #1a1a24; color: #ffffff; padding: 6px; border: 1px solid #2e2e3e;")
        filter_box.addWidget(self.combo_cat_filter)

        layout.addLayout(filter_box)

        # Alarm Table (11 columns)
        self.table_alarms = QTableWidget()
        self.table_alarms.setColumnCount(11)
        self.table_alarms.setHorizontalHeaderLabels([
            "Alarm ID", "Last Detected", "Severity", "Priority", "Category",
            "Camera / Device", "Title & Incident Details", "Status", "Operator", "Count", "Escalation"
        ])
        self.table_alarms.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_alarms.horizontalHeader().setStretchLastSection(True)
        self.table_alarms.setColumnWidth(0, 90)
        self.table_alarms.setColumnWidth(1, 140)
        self.table_alarms.setColumnWidth(2, 90)
        self.table_alarms.setColumnWidth(3, 90)
        self.table_alarms.setColumnWidth(4, 100)
        self.table_alarms.setColumnWidth(5, 110)
        self.table_alarms.setColumnWidth(6, 260)
        self.table_alarms.setColumnWidth(7, 110)
        self.table_alarms.setColumnWidth(8, 110)
        self.table_alarms.setColumnWidth(9, 60)
        self.table_alarms.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_alarms.setSelectionMode(QTableWidget.SingleSelection)
        self.table_alarms.setStyleSheet("""
            QTableWidget {
                background-color: #14141e;
                color: #e0e0e0;
                gridline-color: #242434;
                border: 1px solid #242434;
            }
            QTableWidget::item:selected {
                background-color: #2d3748;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #1a1a26;
                color: #888899;
                font-weight: bold;
                padding: 6px;
                border: 1px solid #242434;
            }
        """)
        self.table_alarms.itemSelectionChanged.connect(self._on_alarm_selected)
        layout.addWidget(self.table_alarms)

        # Quick Actions Toolbar below Table
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        self.btn_ack = QPushButton("Acknowledge")
        self.btn_ack.setStyleSheet("background-color: #0284c7; color: #ffffff; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_ack.clicked.connect(self._on_action_acknowledge)

        self.btn_investigate = QPushButton("Start Investigation")
        self.btn_investigate.setStyleSheet("background-color: #7c3aed; color: #ffffff; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_investigate.clicked.connect(self._on_action_investigate)

        self.btn_assign = QPushButton("Assign Operator")
        self.btn_assign.setStyleSheet("background-color: #3b82f6; color: #ffffff; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_assign.clicked.connect(self._on_action_assign)

        self.btn_resolve = QPushButton("Resolve")
        self.btn_resolve.setStyleSheet("background-color: #16a34a; color: #ffffff; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_resolve.clicked.connect(self._on_action_resolve)

        self.btn_close = QPushButton("Close Incident")
        self.btn_close.setStyleSheet("background-color: #475569; color: #ffffff; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_close.clicked.connect(self._on_action_close)

        self.btn_reopen = QPushButton("Reopen")
        self.btn_reopen.setStyleSheet("background-color: #db2777; color: #ffffff; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_reopen.clicked.connect(self._on_action_reopen)

        self.btn_escalate = QPushButton("Escalate Tier")
        self.btn_escalate.setStyleSheet("background-color: #e11d48; color: #ffffff; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_escalate.clicked.connect(self._on_action_escalate)

        self.btn_export_csv = QPushButton("Export CSV")
        self.btn_export_csv.setStyleSheet("background-color: #1e293b; color: #cbd5e1; padding: 6px 12px; border: 1px solid #475569; border-radius: 4px;")
        self.btn_export_csv.clicked.connect(self._on_export_csv)

        action_bar.addWidget(self.btn_ack)
        action_bar.addWidget(self.btn_investigate)
        action_bar.addWidget(self.btn_assign)
        action_bar.addWidget(self.btn_resolve)
        action_bar.addWidget(self.btn_close)
        action_bar.addWidget(self.btn_reopen)
        action_bar.addWidget(self.btn_escalate)
        action_bar.addStretch()
        action_bar.addWidget(self.btn_export_csv)

        layout.addLayout(action_bar)

    # -------------------------------------------------------------------------
    # TAB 2: Alarm Detail & Evidence
    # -------------------------------------------------------------------------
    def _init_detail_tab(self) -> None:
        layout = QVBoxLayout(self.tab_detail)
        layout.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background-color: #242434; }")

        # Left Column: Metadata & Evidence
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(10)

        grp_meta = QGroupBox("Incident Information")
        grp_meta.setStyleSheet("QGroupBox { color: #ffffff; font-weight: bold; border: 1px solid #2e2e3e; border-radius: 4px; padding-top: 14px; margin-top: 6px; }")
        meta_form = QFormLayout(grp_meta)

        self.lbl_det_id = QLabel("None")
        self.lbl_det_title = QLabel("None")
        self.lbl_det_desc = QLabel("None")
        self.lbl_det_desc.setWordWrap(True)
        self.lbl_det_cam = QLabel("None")
        self.lbl_det_cat = QLabel("None")
        self.lbl_det_sev = QLabel("None")
        self.lbl_det_first = QLabel("None")
        self.lbl_det_last = QLabel("None")
        self.lbl_det_status = QLabel("None")
        self.lbl_det_op = QLabel("Unassigned")
        self.lbl_det_sla = QLabel("Level 0")

        meta_form.addRow("Alarm UUID:", self.lbl_det_id)
        meta_form.addRow("Title:", self.lbl_det_title)
        meta_form.addRow("Description:", self.lbl_det_desc)
        meta_form.addRow("Camera Channel:", self.lbl_det_cam)
        meta_form.addRow("Category:", self.lbl_det_cat)
        meta_form.addRow("Severity:", self.lbl_det_sev)
        meta_form.addRow("First Detected:", self.lbl_det_first)
        meta_form.addRow("Last Detected:", self.lbl_det_last)
        meta_form.addRow("Current Status:", self.lbl_det_status)
        meta_form.addRow("Assigned To:", self.lbl_det_op)
        meta_form.addRow("Escalation Tier:", self.lbl_det_sla)

        left_layout.addWidget(grp_meta)

        # Evidence Group
        grp_evidence = QGroupBox("Associated Surveillance Evidence")
        grp_evidence.setStyleSheet("QGroupBox { color: #ffffff; font-weight: bold; border: 1px solid #2e2e3e; border-radius: 4px; padding-top: 14px; margin-top: 6px; }")
        ev_layout = QVBoxLayout(grp_evidence)

        self.txt_evidence = QTextEdit()
        self.txt_evidence.setReadOnly(True)
        self.txt_evidence.setStyleSheet("background-color: #14141e; color: #93c5fd; font-family: monospace; border: 1px solid #242434;")
        ev_layout.addWidget(self.txt_evidence)

        ev_btn_layout = QHBoxLayout()
        self.btn_open_playback = QPushButton("Seek to Playback (View 2)")
        self.btn_open_playback.setStyleSheet("background-color: #2563eb; color: #ffffff; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_open_playback.clicked.connect(self._on_seek_playback)
        ev_btn_layout.addWidget(self.btn_open_playback)
        ev_layout.addLayout(ev_btn_layout)

        left_layout.addWidget(grp_evidence)
        splitter.addWidget(left_widget)

        # Right Column: Operator Notes & Chronological Audit History
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(10)

        # Add Note Box
        grp_note = QGroupBox("Operator Investigation Log")
        grp_note.setStyleSheet("QGroupBox { color: #ffffff; font-weight: bold; border: 1px solid #2e2e3e; border-radius: 4px; padding-top: 14px; margin-top: 6px; }")
        note_layout = QVBoxLayout(grp_note)

        self.txt_new_note = QLineEdit()
        self.txt_new_note.setPlaceholderText("Enter operator observation or action note...")
        self.txt_new_note.setStyleSheet("background-color: #14141e; color: #ffffff; padding: 6px; border: 1px solid #2e2e3e; border-radius: 4px;")
        note_layout.addWidget(self.txt_new_note)

        self.btn_add_note = QPushButton("Add Note to Audit Trail")
        self.btn_add_note.setStyleSheet("background-color: #3b82f6; color: #ffffff; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_add_note.clicked.connect(self._on_add_note)
        note_layout.addWidget(self.btn_add_note)

        right_layout.addWidget(grp_note)

        # Audit History Table
        grp_history = QGroupBox("Chronological Lifecycle Audit History")
        grp_history.setStyleSheet("QGroupBox { color: #ffffff; font-weight: bold; border: 1px solid #2e2e3e; border-radius: 4px; padding-top: 14px; margin-top: 6px; }")
        hist_layout = QVBoxLayout(grp_history)

        self.table_history = QTableWidget()
        self.table_history.setColumnCount(6)
        self.table_history.setHorizontalHeaderLabels(["Timestamp (UTC)", "Action", "Operator", "Prev Status", "New Status", "Comments"])
        self.table_history.horizontalHeader().setStretchLastSection(True)
        self.table_history.setStyleSheet("""
            QTableWidget {
                background-color: #14141e;
                color: #e0e0e0;
                gridline-color: #242434;
                border: 1px solid #242434;
            }
            QHeaderView::section {
                background-color: #1a1a26;
                color: #888899;
                font-weight: bold;
                padding: 4px;
                border: 1px solid #242434;
            }
        """)
        hist_layout.addWidget(self.table_history)

        right_layout.addWidget(grp_history)
        splitter.addWidget(right_widget)

        layout.addWidget(splitter)

    # -------------------------------------------------------------------------
    # TAB 3: Alarm Policies & Rules
    # -------------------------------------------------------------------------
    def _init_policies_tab(self) -> None:
        layout = QVBoxLayout(self.tab_policies)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        lbl_desc = QLabel("Pre-configured classification policies, deduplication burst windows, and escalation SLAs.")
        lbl_desc.setStyleSheet("color: #888899; font-size: 12px;")
        layout.addWidget(lbl_desc)

        self.table_policies = QTableWidget()
        self.table_policies.setColumnCount(8)
        self.table_policies.setHorizontalHeaderLabels([
            "Rule Name", "Subsystem", "Event Type", "Severity", "Priority", "Dedup Window (s)", "SLA Timeout (s)", "Target Role"
        ])
        self.table_policies.horizontalHeader().setStretchLastSection(True)
        self.table_policies.setStyleSheet("""
            QTableWidget {
                background-color: #14141e;
                color: #e0e0e0;
                gridline-color: #242434;
                border: 1px solid #242434;
            }
            QHeaderView::section {
                background-color: #1a1a26;
                color: #888899;
                font-weight: bold;
                padding: 6px;
                border: 1px solid #242434;
            }
        """)
        layout.addWidget(self.table_policies)

    # -------------------------------------------------------------------------
    # TAB 4: Shift Analytics & SLA Reporting
    # -------------------------------------------------------------------------
    def _init_stats_tab(self) -> None:
        layout = QVBoxLayout(self.tab_stats)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Top Stats Cards
        stat_cards = QHBoxLayout()
        self.card_mtta = AlarmMetricCard("Mean Time to Acknowledge (MTTA)", "0.0 min", "#38bdf8")
        self.card_mttr = AlarmMetricCard("Mean Time to Resolve (MTTR)", "0.0 min", "#4ade80")
        stat_cards.addWidget(self.card_mtta)
        stat_cards.addWidget(self.card_mttr)
        layout.addLayout(stat_cards)

        # Breakdown splits
        breakdown_layout = QHBoxLayout()

        # Severity breakdown table
        grp_sev = QGroupBox("Active Alarms by Severity")
        grp_sev.setStyleSheet("QGroupBox { color: #ffffff; font-weight: bold; border: 1px solid #2e2e3e; border-radius: 4px; padding-top: 14px; margin-top: 6px; }")
        vbox_sev = QVBoxLayout(grp_sev)
        self.table_sev_breakdown = QTableWidget()
        self.table_sev_breakdown.setColumnCount(2)
        self.table_sev_breakdown.setHorizontalHeaderLabels(["Severity Level", "Active Count"])
        self.table_sev_breakdown.horizontalHeader().setStretchLastSection(True)
        self.table_sev_breakdown.setStyleSheet("background-color: #14141e; color: #ffffff;")
        vbox_sev.addWidget(self.table_sev_breakdown)
        breakdown_layout.addWidget(grp_sev)

        # Top cameras table
        grp_cams = QGroupBox("Top Incident Locations")
        grp_cams.setStyleSheet("QGroupBox { color: #ffffff; font-weight: bold; border: 1px solid #2e2e3e; border-radius: 4px; padding-top: 14px; margin-top: 6px; }")
        vbox_cams = QVBoxLayout(grp_cams)
        self.table_top_cams = QTableWidget()
        self.table_top_cams.setColumnCount(2)
        self.table_top_cams.setHorizontalHeaderLabels(["Camera Channel", "Total Alarms"])
        self.table_top_cams.horizontalHeader().setStretchLastSection(True)
        self.table_top_cams.setStyleSheet("background-color: #14141e; color: #ffffff;")
        vbox_cams.addWidget(self.table_top_cams)
        breakdown_layout.addWidget(grp_cams)

        layout.addLayout(breakdown_layout)

    # -------------------------------------------------------------------------
    # TAB 5: Event Simulation (Live Operator Testing)
    # -------------------------------------------------------------------------
    def _init_sim_tab(self) -> None:
        layout = QVBoxLayout(self.tab_sim)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        lbl_sim = QLabel("Operator Simulation Console: Trigger synthetic events to verify ingestion, deduplication, and notifications.")
        lbl_sim.setStyleSheet("color: #888899; font-size: 12px;")
        layout.addWidget(lbl_sim)

        btn_grid = QHBoxLayout()
        btn_grid.setSpacing(10)

        btn_sim_intrusion = QPushButton("Simulate Intrusion (Cam 1)")
        btn_sim_intrusion.setStyleSheet("background-color: #dc2626; color: #ffffff; font-weight: bold; padding: 10px; border-radius: 4px;")
        btn_sim_intrusion.clicked.connect(lambda: self._simulate_event("ANALYTICS", "INTRUSION", {"channel_id": "cam_01", "rule_type": "INTRUSION", "zone_id": "North_Perimeter"}))

        btn_sim_fall = QPushButton("Simulate Fall Detection (Cam 2)")
        btn_sim_fall.setStyleSheet("background-color: #ea580c; color: #ffffff; font-weight: bold; padding: 10px; border-radius: 4px;")
        btn_sim_fall.clicked.connect(lambda: self._simulate_event("BEHAVIOUR", "FALL_DETECTED", {"channel_id": "cam_02", "confidence": 0.94}))

        btn_sim_plate = QPushButton("Simulate Watchlist Plate (Cam 3)")
        btn_sim_plate.setStyleSheet("background-color: #d97706; color: #ffffff; font-weight: bold; padding: 10px; border-radius: 4px;")
        btn_sim_plate.clicked.connect(lambda: self._simulate_event("ANPR", "WATCHLIST_ALERT", {"channel_id": "cam_03", "plate_text": "MH12AB1234", "watchlist_category": "Stolen Vehicle"}))

        btn_sim_disc = QPushButton("Simulate Camera Disconnect (Cam 4)")
        btn_sim_disc.setStyleSheet("background-color: #7c2d12; color: #ffffff; font-weight: bold; padding: 10px; border-radius: 4px;")
        btn_sim_disc.clicked.connect(lambda: self._simulate_event("STREAM", "STREAM_DISCONNECTED", {"channel_id": "cam_04"}))

        btn_sim_tamper = QPushButton("Simulate Forensic Seal Tamper")
        btn_sim_tamper.setStyleSheet("background-color: #991b1b; color: #ffffff; font-weight: bold; padding: 10px; border-radius: 4px;")
        btn_sim_tamper.clicked.connect(lambda: self._simulate_event("FORENSICS", "INTEGRITY_FAILURE", {"details": "Chunk hash mismatch on evidence recording 1024.mp4"}))

        btn_grid.addWidget(btn_sim_intrusion)
        btn_grid.addWidget(btn_sim_fall)
        btn_grid.addWidget(btn_sim_plate)
        btn_grid.addWidget(btn_sim_disc)
        btn_grid.addWidget(btn_sim_tamper)
        layout.addLayout(btn_grid)

        layout.addStretch()

    def _show_info(self, title: str, msg: str) -> None:
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            QMessageBox.information(self, title, msg)

    def _show_warning(self, title: str, msg: str) -> None:
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            QMessageBox.warning(self, title, msg)

    def _show_critical(self, title: str, msg: str) -> None:
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            QMessageBox.critical(self, title, msg)

    def _simulate_event(self, source: str, event_type: str, data: Dict[str, Any]) -> None:
        alarm_id = alarm_service.process_raw_event(source, event_type, data)
        self.refresh_data()
        self._show_info("Event Simulated", f"Dispatched {source}:{event_type}.\nAlarm ID: {alarm_id}")

    # -------------------------------------------------------------------------
    # Data Refresh & Table Population
    # -------------------------------------------------------------------------
    def refresh_data(self) -> None:
        """Fetches current alarm records and refreshes UI widgets."""
        # 1. Update KPI metrics
        metrics = alarm_service.get_dashboard_metrics()
        self.card_total.set_value(metrics.get("total_active", 0))
        self.card_critical.set_value(metrics.get("critical_count", 0))
        self.card_unack.set_value(metrics.get("unacknowledged_count", 0))
        self.card_in_progress.set_value(metrics.get("in_progress_count", 0))
        self.card_escalated.set_value(metrics.get("escalated_count", 0))
        self.card_resolved.set_value(metrics.get("resolved_today", 0))

        # 2. Query filtered alarms
        search_txt = self.txt_search.text().strip() or None
        sev_filter = self.combo_sev_filter.currentData()
        stat_filter = self.combo_stat_filter.currentData()
        cat_filter = self.combo_cat_filter.currentData()

        alarms, total = alarm_service.get_alarms(
            status=stat_filter,
            severity=sev_filter,
            category=cat_filter,
            search=search_txt,
            limit=100,
        )

        self.table_alarms.setRowCount(len(alarms))
        for row, a in enumerate(alarms):
            item_id = QTableWidgetItem(a["id"][:8] + "...")
            item_id.setData(Qt.UserRole, a["id"])
            item_id.setForeground(QColor("#93c5fd"))

            item_time = QTableWidgetItem(a["last_detected_at"].replace("T", " ")[:19] if a["last_detected_at"] else "")
            
            # Severity badge
            sev = a["severity"]
            item_sev = QTableWidgetItem(sev)
            item_sev.setTextAlignment(Qt.AlignCenter)
            if sev == "CRITICAL":
                item_sev.setForeground(QColor("#f87171"))
            elif sev == "HIGH":
                item_sev.setForeground(QColor("#fb923c"))
            elif sev == "MEDIUM":
                item_sev.setForeground(QColor("#facc15"))
            else:
                item_sev.setForeground(QColor("#60a5fa"))

            item_prio = QTableWidgetItem(a["priority"])
            item_cat = QTableWidgetItem(a["category"])
            item_cam = QTableWidgetItem(a.get("camera_id") or "System")
            item_title = QTableWidgetItem(a["title"])
            
            # Status badge
            stat = a["status"]
            item_stat = QTableWidgetItem(stat)
            item_stat.setTextAlignment(Qt.AlignCenter)
            if stat == "NEW":
                item_stat.setForeground(QColor("#f59e0b"))
            elif stat == "ACKNOWLEDGED":
                item_stat.setForeground(QColor("#38bdf8"))
            elif stat == "IN_PROGRESS":
                item_stat.setForeground(QColor("#c084fc"))
            elif stat == "RESOLVED":
                item_stat.setForeground(QColor("#4ade80"))
            else:
                item_stat.setForeground(QColor("#94a3b8"))

            item_op = QTableWidgetItem(a.get("assigned_operator") or "Unassigned")
            item_cnt = QTableWidgetItem(str(a.get("occurrence_count", 1)))
            item_cnt.setTextAlignment(Qt.AlignCenter)

            esc_tier = f"Tier {a.get('escalation_level', 0)}" if a.get("escalation_level", 0) > 0 else "Normal"
            item_esc = QTableWidgetItem(esc_tier)
            item_esc.setTextAlignment(Qt.AlignCenter)
            if a.get("escalation_level", 0) > 0:
                item_esc.setForeground(QColor("#f43f5e"))

            self.table_alarms.setItem(row, 0, item_id)
            self.table_alarms.setItem(row, 1, item_time)
            self.table_alarms.setItem(row, 2, item_sev)
            self.table_alarms.setItem(row, 3, item_prio)
            self.table_alarms.setItem(row, 4, item_cat)
            self.table_alarms.setItem(row, 5, item_cam)
            self.table_alarms.setItem(row, 6, item_title)
            self.table_alarms.setItem(row, 7, item_stat)
            self.table_alarms.setItem(row, 8, item_op)
            self.table_alarms.setItem(row, 9, item_cnt)
            self.table_alarms.setItem(row, 10, item_esc)

        # 3. Refresh Policies Tab
        self._refresh_policies_table()

        # 4. Refresh Stats Tab
        self._refresh_stats_tab(metrics)

    def _refresh_policies_table(self) -> None:
        from engines.alarm_engine.policy_engine import DEFAULT_POLICIES
        self.table_policies.setRowCount(len(DEFAULT_POLICIES))
        for row, p in enumerate(DEFAULT_POLICIES):
            self.table_policies.setItem(row, 0, QTableWidgetItem(p.rule_name))
            self.table_policies.setItem(row, 1, QTableWidgetItem(p.event_source))
            self.table_policies.setItem(row, 2, QTableWidgetItem(p.event_type))
            self.table_policies.setItem(row, 3, QTableWidgetItem(p.severity.value))
            self.table_policies.setItem(row, 4, QTableWidgetItem(p.priority.value))
            self.table_policies.setItem(row, 5, QTableWidgetItem(str(p.dedup_window_seconds)))
            self.table_policies.setItem(row, 6, QTableWidgetItem(str(p.escalation_timeout_seconds)))
            self.table_policies.setItem(row, 7, QTableWidgetItem(p.escalation_target_role))

    def _refresh_stats_tab(self, metrics: Dict[str, Any]) -> None:
        stats = alarm_service.get_alarm_statistics()
        self.card_mtta.set_value(f"{stats.get('mtta_minutes', 0.0):.1f} min")
        self.card_mttr.set_value(f"{stats.get('mttr_minutes', 0.0):.1f} min")

        # Severity breakdown
        sev_dist = metrics.get("severity_distribution", {})
        self.table_sev_breakdown.setRowCount(len(sev_dist))
        for idx, (sev, count) in enumerate(sev_dist.items()):
            self.table_sev_breakdown.setItem(idx, 0, QTableWidgetItem(sev))
            self.table_sev_breakdown.setItem(idx, 1, QTableWidgetItem(str(count)))

        # Top cameras
        top_cams = stats.get("top_cameras", [])
        self.table_top_cams.setRowCount(len(top_cams))
        for idx, cam_info in enumerate(top_cams):
            self.table_top_cams.setItem(idx, 0, QTableWidgetItem(cam_info["camera_id"]))
            self.table_top_cams.setItem(idx, 1, QTableWidgetItem(str(cam_info["alarm_count"])))

    # -------------------------------------------------------------------------
    # Alarm Selection & Detail Viewer
    # -------------------------------------------------------------------------
    def _on_alarm_selected(self) -> None:
        selected_rows = self.table_alarms.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        item = self.table_alarms.item(row, 0)
        if not item:
            return

        alarm_id = item.data(Qt.UserRole)
        self._selected_alarm_id = alarm_id
        self._load_alarm_detail(alarm_id)

    def _load_alarm_detail(self, alarm_id: str) -> None:
        data = alarm_service.get_alarm_by_id(alarm_id)
        if not data:
            return

        self.lbl_det_id.setText(data["id"])
        self.lbl_det_title.setText(data["title"])
        self.lbl_det_desc.setText(data.get("description") or "No description")
        self.lbl_det_cam.setText(data.get("camera_id") or "N/A")
        self.lbl_det_cat.setText(data["category"])
        self.lbl_det_sev.setText(data["severity"])
        self.lbl_det_first.setText(data.get("first_detected_at", "")[:19])
        self.lbl_det_last.setText(data.get("last_detected_at", "")[:19])
        self.lbl_det_status.setText(data["status"])
        self.lbl_det_op.setText(data.get("assigned_operator") or "Unassigned")
        self.lbl_det_sla.setText(f"Tier {data.get('escalation_level', 0)}")

        # Evidence references JSON
        ev_refs = data.get("evidence_refs", {})
        self.txt_evidence.setText(json.dumps(ev_refs, indent=2) if ev_refs else "No associated evidence records.")

        # Load Chronological History
        history = alarm_service.get_alarm_history(alarm_id)
        self.table_history.setRowCount(len(history))
        for r, h in enumerate(history):
            self.table_history.setItem(r, 0, QTableWidgetItem(h["timestamp"][:19]))
            self.table_history.setItem(r, 1, QTableWidgetItem(h["action"]))
            self.table_history.setItem(r, 2, QTableWidgetItem(h["operator"]))
            self.table_history.setItem(r, 3, QTableWidgetItem(h.get("previous_status") or "-"))
            self.table_history.setItem(r, 4, QTableWidgetItem(h["new_status"]))
            self.table_history.setItem(r, 5, QTableWidgetItem(f"{h.get('reason','')}: {h.get('comments','')}"))

    # -------------------------------------------------------------------------
    # Lifecycle Actions & RBAC Execution
    # -------------------------------------------------------------------------
    def _get_active_alarm_id(self) -> Optional[str]:
        if not self._selected_alarm_id:
            self._show_warning("No Selection", "Please select an incident from the table first.")
            return None
        return self._selected_alarm_id

    def _on_action_acknowledge(self) -> None:
        alarm_id = self._get_active_alarm_id()
        if not alarm_id:
            return
        try:
            alarm_service.acknowledge_alarm(alarm_id, self.current_operator, self.current_role)
            self.refresh_data()
            self._load_alarm_detail(alarm_id)
        except Exception as e:
            self._show_critical("Permission Denied / Error", str(e))

    def _on_action_investigate(self) -> None:
        alarm_id = self._get_active_alarm_id()
        if not alarm_id:
            return
        try:
            alarm_service.start_investigation(alarm_id, self.current_operator, self.current_role)
            self.refresh_data()
            self._load_alarm_detail(alarm_id)
        except Exception as e:
            self._show_critical("Permission Denied / Error", str(e))

    def _on_action_assign(self) -> None:
        alarm_id = self._get_active_alarm_id()
        if not alarm_id:
            return
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            user, ok = "Auto_Investigator", True
        else:
            user, ok = QInputDialog.getText(self, "Assign Operator", "Assign incident to operator username:")
        if ok and user.strip():
            try:
                alarm_service.assign_alarm(alarm_id, user.strip(), self.current_operator, self.current_role)
                self.refresh_data()
                self._load_alarm_detail(alarm_id)
            except Exception as e:
                self._show_critical("Permission Denied / Error", str(e))

    def _on_action_resolve(self) -> None:
        alarm_id = self._get_active_alarm_id()
        if not alarm_id:
            return
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            reason, ok = "Resolved in test", True
        else:
            reason, ok = QInputDialog.getText(self, "Resolve Incident", "Enter resolution reason:")
        if ok:
            try:
                alarm_service.resolve_alarm(alarm_id, self.current_operator, self.current_role, reason=reason)
                self.refresh_data()
                self._load_alarm_detail(alarm_id)
            except Exception as e:
                self._show_critical("Permission Denied / Error", str(e))

    def _on_action_close(self) -> None:
        alarm_id = self._get_active_alarm_id()
        if not alarm_id:
            return
        try:
            alarm_service.close_alarm(alarm_id, self.current_operator, self.current_role)
            self.refresh_data()
            self._load_alarm_detail(alarm_id)
        except Exception as e:
            self._show_critical("Permission Denied / Error", str(e))

    def _on_action_reopen(self) -> None:
        alarm_id = self._get_active_alarm_id()
        if not alarm_id:
            return
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            reason, ok = "Reopened in test", True
        else:
            reason, ok = QInputDialog.getText(self, "Reopen Incident", "Enter reopening reason:")
        if ok:
            try:
                alarm_service.reopen_alarm(alarm_id, self.current_operator, self.current_role, reason=reason)
                self.refresh_data()
                self._load_alarm_detail(alarm_id)
            except Exception as e:
                self._show_critical("Permission Denied / Error", str(e))

    def _on_action_escalate(self) -> None:
        alarm_id = self._get_active_alarm_id()
        if not alarm_id:
            return
        try:
            alarm_service.escalate_manually(alarm_id, self.current_operator, self.current_role)
            self.refresh_data()
            self._load_alarm_detail(alarm_id)
        except Exception as e:
            self._show_critical("Permission Denied / Error", str(e))

    def _on_add_note(self) -> None:
        alarm_id = self._get_active_alarm_id()
        if not alarm_id:
            return
        note = self.txt_new_note.text().strip()
        if not note:
            return
        try:
            alarm_service.add_operator_note(alarm_id, self.current_operator, note, self.current_role)
            self.txt_new_note.clear()
            self._load_alarm_detail(alarm_id)
        except Exception as e:
            self._show_critical("Permission Denied / Error", str(e))

    def _on_seek_playback(self) -> None:
        alarm_id = self._get_active_alarm_id()
        if not alarm_id:
            return
        data = alarm_service.get_alarm_by_id(alarm_id)
        if not data or not data.get("camera_id") or not data.get("first_detected_at"):
            self._show_info("No Playback Link", "Selected alarm lacks camera or timestamp reference.")
            return

        cam = data["camera_id"]
        ts = data["first_detected_at"]
        self.request_playback_seek.emit(cam, ts)
        self._show_info("Playback Sync", f"Synchronized Playback (View 2) to camera {cam} at {ts[:19]}.")

    def _on_export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Alarms CSV", "alarms_export.csv", "CSV Files (*.csv)")
        if not path:
            return
        try:
            alarms, _ = alarm_service.get_alarms(limit=1000)
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["ID", "Timestamp", "Severity", "Priority", "Category", "Camera", "Title", "Status", "Operator", "Count"])
                for a in alarms:
                    writer.writerow([
                        a["id"], a["last_detected_at"], a["severity"], a["priority"],
                        a["category"], a.get("camera_id", ""), a["title"], a["status"],
                        a.get("assigned_operator", ""), a.get("occurrence_count", 1)
                    ])
            self._show_info("Export Complete", f"Exported {len(alarms)} records to {path}")
        except Exception as e:
            self._show_critical("Export Failed", str(e))

    def _on_role_changed(self, role: str) -> None:
        self.current_role = role

    def _on_operator_changed(self, text: str) -> None:
        self.current_operator = text.strip() or "Operator_1"

    def closeEvent(self, event) -> None:
        self._refresh_timer.stop()
        self._teardown_event_listeners()
        super().closeEvent(event)

    def _setup_event_listeners(self) -> None:
        """Subscribes to live platform alarm events to update dashboard in real time."""
        self._event_handler = lambda event: QTimer.singleShot(0, self.refresh_data) if self.isVisible() else None
        bus.subscribe("alarm.created", self._event_handler)
        bus.subscribe("alarm.acknowledged", self._event_handler)
        bus.subscribe("alarm.resolved", self._event_handler)
        bus.subscribe("alarm.escalated", self._event_handler)

    def _teardown_event_listeners(self) -> None:
        if hasattr(self, "_event_handler") and self._event_handler:
            for topic in ["alarm.created", "alarm.acknowledged", "alarm.resolved", "alarm.escalated"]:
                bus.unsubscribe(topic, self._event_handler)
            self._event_handler = None
