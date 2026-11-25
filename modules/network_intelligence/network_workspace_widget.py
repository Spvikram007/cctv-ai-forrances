"""
Network Intelligence & Security Audit Workspace Widget.
Phase 11 (F-019, Release 1.1.0-alpha).
Integrates subnet scanning, interactive topology visualization, CCTV diagnostics,
continuous performance telemetry, automated fault isolation, and security vulnerability auditing.
"""

import os
import json
import csv
from typing import List, Dict, Any, Optional

from PySide6.QtCore import Qt, QThread, Signal, QTimer
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
    QProgressBar,
)

from core.logging.logger import get_logger
from engines.network_engine.scanner import (
    NetworkScanner,
    DiscoveredNetworkDevice,
    DeviceType,
    DeviceStatus,
    ScanScope,
    validate_cidr_block,
    compute_scan_scope,
    get_default_gateway,
    get_local_subnets,
)
from engines.network_engine.diagnostics import (
    DeviceDiagnosticEngine,
    ComprehensiveDeviceAuditReport,
    DiagnosticResult,
)
from engines.network_engine.monitor import (
    NetworkPerformanceMonitor,
    DeviceTelemetryHistory,
    TelemetrySample,
)
from engines.network_engine.security_audit import (
    NetworkSecurityAuditor,
    SecurityAuditReport,
    AuditSeverity,
    CVEConfidence,
)
from engines.network_engine.fault_analyzer import (
    AutomatedFaultAnalyzer,
    FaultAnalysisReport,
    FaultType,
)
from modules.network_intelligence.topology_view import InteractiveTopologyCanvas

logger = get_logger("network_workspace_widget")


class ScanWorker(QThread):
    """Asynchronous background worker for subnet scanning."""
    progress = Signal(int, int, list)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, cidr: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.cidr = cidr
        self.scanner = NetworkScanner(max_threads=40, socket_timeout=0.6)

    def run(self) -> None:
        try:
            def on_progress(done: int, total: int, dev_list: List[DiscoveredNetworkDevice]) -> None:
                self.progress.emit(done, total, dev_list)

            devices = self.scanner.scan_network(self.cidr, progress_callback=on_progress)
            self.finished.emit(devices)
        except Exception as e:
            self.error.emit(str(e))


class DiagnosticsWorker(QThread):
    """Asynchronous background worker for CCTV protocol diagnostics."""
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, devices: List[DiscoveredNetworkDevice], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.devices = devices

    def run(self) -> None:
        try:
            reports: List[ComprehensiveDeviceAuditReport] = []
            for dev in self.devices:
                rep = DeviceDiagnosticEngine.audit_device(
                    ip_address=dev.ip_address,
                    rtsp_port=554,
                    onvif_port=80,
                    vendor=dev.vendor,
                    mac_address=dev.mac_address,
                    timeout_sec=1.5,
                )
                reports.append(rep)
            self.finished.emit(reports)
        except Exception as e:
            self.error.emit(str(e))


class SecurityAuditWorker(QThread):
    """Asynchronous background worker for vulnerability auditing."""
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, devices: List[DiscoveredNetworkDevice], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.devices = devices

    def run(self) -> None:
        try:
            reports: List[SecurityAuditReport] = []
            for dev in self.devices:
                rep = NetworkSecurityAuditor.audit_device(
                    ip_address=dev.ip_address,
                    open_ports=dev.open_ports,
                    protocols=dev.protocols,
                    vendor=dev.vendor,
                    firmware_version=dev.firmware_version,
                )
                reports.append(rep)
            self.finished.emit(reports)
        except Exception as e:
            self.error.emit(str(e))


class NetworkIntelligenceWidget(QWidget):
    """
    Main PySide6 command center widget for network intelligence,
    topology mapping, diagnostics, performance telemetry, and security auditing.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.discovered_devices: List[DiscoveredNetworkDevice] = []
        self.diagnostic_reports: List[ComprehensiveDeviceAuditReport] = []
        self.security_reports: List[SecurityAuditReport] = []
        self.fault_reports: List[FaultAnalysisReport] = []

        self.monitor = NetworkPerformanceMonitor(poll_interval_sec=3.0)
        self.fault_analyzer = AutomatedFaultAnalyzer()
        self.default_gateway = get_default_gateway() or "192.168.1.1"

        self._scan_worker: Optional[ScanWorker] = None
        self._diag_worker: Optional[DiagnosticsWorker] = None
        self._sec_worker: Optional[SecurityAuditWorker] = None

        self._init_ui()
        self._populate_initial_data()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. Header Control Bar
        header = self._build_header_toolbar()
        main_layout.addWidget(header)

        # 2. Summary Statistics Cards
        stats_cards = self._build_stats_cards()
        main_layout.addWidget(stats_cards)

        # 3. Main Workspace Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            """
            QTabWidget::pane { border: 1px solid #30363d; background: #0d1117; }
            QTabBar::tab { background: #161b22; color: #8b949e; padding: 8px 16px; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #21262d; color: #58a6ff; font-weight: bold; border-bottom: 2px solid #58a6ff; }
            """
        )

        # Tab 0: Device Inventory Table
        self.tab_inventory = self._build_inventory_tab()
        self.tabs.addTab(self.tab_inventory, "Device Inventory")

        # Tab 1: Interactive Topology Map
        self.tab_topology = self._build_topology_tab()
        self.tabs.addTab(self.tab_topology, "Topology Map")

        # Tab 2: Performance Telemetry
        self.tab_telemetry = self._build_telemetry_tab()
        self.tabs.addTab(self.tab_telemetry, "Performance & Bandwidth")

        # Tab 3: Diagnostics & Fault Isolation
        self.tab_diagnostics = self._build_diagnostics_tab()
        self.tabs.addTab(self.tab_diagnostics, "CCTV Diagnostics & Faults")

        # Tab 4: Security & CVE Audit
        self.tab_security = self._build_security_tab()
        self.tabs.addTab(self.tab_security, "Security & Vulnerability Audit")

        main_layout.addWidget(self.tabs, stretch=1)

        # 4. Progress Bar & Status Footer
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background: #161b22; border: 1px solid #30363d; height: 12px; border-radius: 6px; text-align: center; color: #ffffff; font-size: 10px; } QProgressBar::chunk { background: #238636; border-radius: 5px; }"
        )
        main_layout.addWidget(self.progress_bar)

    def _build_header_toolbar(self) -> QWidget:
        toolbar = QFrame()
        toolbar.setStyleSheet("background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 6px;")
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        lbl_target = QLabel("Authorized CIDR:")
        lbl_target.setStyleSheet("color: #c9d1d9; font-weight: 600;")
        layout.addWidget(lbl_target)

        subnets = get_local_subnets()
        self.txt_cidr = QLineEdit(subnets[0] if subnets else "192.168.1.0/24")
        self.txt_cidr.setFixedWidth(160)
        self.txt_cidr.setStyleSheet("background: #0d1117; border: 1px solid #30363d; color: #58a6ff; font-weight: bold; padding: 4px 8px; border-radius: 4px;")
        layout.addWidget(self.txt_cidr)

        self.btn_scan = QPushButton(" Scan Network")
        self.btn_scan.setStyleSheet("background: #238636; color: #ffffff; font-weight: bold; padding: 6px 14px; border-radius: 4px; border: none;")
        self.btn_scan.clicked.connect(self._start_network_scan)
        layout.addWidget(self.btn_scan)

        self.btn_diagnostics = QPushButton(" Run Diagnostics")
        self.btn_diagnostics.setStyleSheet("background: #1f6feb; color: #ffffff; font-weight: bold; padding: 6px 14px; border-radius: 4px; border: none;")
        self.btn_diagnostics.clicked.connect(self._start_diagnostics_audit)
        layout.addWidget(self.btn_diagnostics)

        self.btn_sec_audit = QPushButton(" Security Audit")
        self.btn_sec_audit.setStyleSheet("background: #8957e5; color: #ffffff; font-weight: bold; padding: 6px 14px; border-radius: 4px; border: none;")
        self.btn_sec_audit.clicked.connect(self._start_security_audit)
        layout.addWidget(self.btn_sec_audit)

        layout.addStretch()

        self.btn_export = QPushButton(" Export Report")
        self.btn_export.setStyleSheet("background: #21262d; border: 1px solid #30363d; color: #c9d1d9; font-weight: 600; padding: 6px 12px; border-radius: 4px;")
        self.btn_export.clicked.connect(self._export_report_dialog)
        layout.addWidget(self.btn_export)

        return toolbar

    def _build_stats_cards(self) -> QWidget:
        cards_widget = QWidget()
        layout = QHBoxLayout(cards_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.card_total = self._create_stat_card("TOTAL HOSTS", "0", "#58a6ff")
        self.card_cameras = self._create_stat_card("IP CAMERAS", "0", "#3fb950")
        self.card_nvrs = self._create_stat_card("NVRS / RECORDERS", "0", "#bc8cff")
        self.card_switches = self._create_stat_card("SWITCHES / GW", "0", "#38bdf8")
        self.card_alerts = self._create_stat_card("ANOMALIES / ALERTS", "0", "#f85149")

        layout.addWidget(self.card_total)
        layout.addWidget(self.card_cameras)
        layout.addWidget(self.card_nvrs)
        layout.addWidget(self.card_switches)
        layout.addWidget(self.card_alerts)
        return cards_widget

    def _create_stat_card(self, title: str, value: str, color: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 8px 12px;")
        l = QVBoxLayout(card)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(2)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600;")
        lbl_v = QLabel(value)
        lbl_v.setObjectName("val")
        lbl_v.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: bold;")
        l.addWidget(lbl_t)
        l.addWidget(lbl_v)
        return card

    # Tab 0: Inventory
    def _build_inventory_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Filter bar
        filter_layout = QHBoxLayout()
        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("Filter by IP, MAC, or Vendor...")
        self.txt_filter.setStyleSheet("background: #161b22; border: 1px solid #30363d; color: #c9d1d9; padding: 4px 8px; border-radius: 4px;")
        self.txt_filter.textChanged.connect(self._apply_inventory_filter)
        filter_layout.addWidget(self.txt_filter)

        self.cmb_type_filter = QComboBox()
        self.cmb_type_filter.addItems(["All Device Types", "IP_CAMERA", "NVR", "GATEWAY", "SWITCH", "HOST"])
        self.cmb_type_filter.setStyleSheet("background: #161b22; border: 1px solid #30363d; color: #c9d1d9; padding: 4px 8px; border-radius: 4px;")
        self.cmb_type_filter.currentTextChanged.connect(self._apply_inventory_filter)
        filter_layout.addWidget(self.cmb_type_filter)
        layout.addLayout(filter_layout)

        # Inventory Table
        self.tbl_inventory = QTableWidget()
        self.tbl_inventory.setColumnCount(8)
        self.tbl_inventory.setHorizontalHeaderLabels([
            "IP Address", "MAC Address", "Vendor / OUI", "Device Type", "Status", "Latency (ms)", "Open Ports", "Details"
        ])
        self.tbl_inventory.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_inventory.setStyleSheet(
            "QTableWidget { background: #0d1117; color: #c9d1d9; gridline-color: #21262d; border: 1px solid #30363d; } QHeaderView::section { background: #161b22; color: #8b949e; padding: 6px; border: 1px solid #30363d; font-weight: bold; }"
        )
        layout.addWidget(self.tbl_inventory)
        return widget

    # Tab 1: Topology
    def _build_topology_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)

        # Left: Canvas
        self.topology_canvas = InteractiveTopologyCanvas()
        self.topology_canvas.node_selected.connect(self._on_topology_node_selected)
        splitter.addWidget(self.topology_canvas)

        # Right: Inspector Panel
        inspector = QFrame()
        inspector.setFixedWidth(280)
        inspector.setStyleSheet("background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 8px;")
        insp_layout = QVBoxLayout(inspector)

        lbl_insp_title = QLabel("DEVICE INSPECTOR")
        lbl_insp_title.setStyleSheet("color: #58a6ff; font-weight: bold; font-size: 13px; margin-bottom: 8px;")
        insp_layout.addWidget(lbl_insp_title)

        self.form_insp = QFormLayout()
        self.lbl_insp_ip = QLabel("-")
        self.lbl_insp_mac = QLabel("-")
        self.lbl_insp_vendor = QLabel("-")
        self.lbl_insp_type = QLabel("-")
        self.lbl_insp_status = QLabel("-")
        self.lbl_insp_latency = QLabel("-")

        for lbl in (self.lbl_insp_ip, self.lbl_insp_mac, self.lbl_insp_vendor, self.lbl_insp_type, self.lbl_insp_status, self.lbl_insp_latency):
            lbl.setStyleSheet("color: #c9d1d9; font-weight: 500;")

        self.form_insp.addRow("IP Address:", self.lbl_insp_ip)
        self.form_insp.addRow("MAC:", self.lbl_insp_mac)
        self.form_insp.addRow("Vendor:", self.lbl_insp_vendor)
        self.form_insp.addRow("Device Type:", self.lbl_insp_type)
        self.form_insp.addRow("Status:", self.lbl_insp_status)
        self.form_insp.addRow("Latency:", self.lbl_insp_latency)
        insp_layout.addLayout(self.form_insp)

        insp_layout.addStretch()

        self.btn_reset_view = QPushButton("Reset Topology View")
        self.btn_reset_view.setStyleSheet("background: #21262d; border: 1px solid #30363d; color: #58a6ff; padding: 6px; border-radius: 4px;")
        self.btn_reset_view.clicked.connect(self.topology_canvas.reset_view)
        insp_layout.addWidget(self.btn_reset_view)

        splitter.addWidget(inspector)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)
        return widget

    # Tab 2: Performance Telemetry
    def _build_telemetry_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        lbl_info = QLabel("Real-Time Telemetry & Bounded Performance History (Bandwidth, Jitter, Packet Loss)")
        lbl_info.setStyleSheet("color: #8b949e; font-size: 12px;")
        layout.addWidget(lbl_info)

        self.tbl_telemetry = QTableWidget()
        self.tbl_telemetry.setColumnCount(8)
        self.tbl_telemetry.setHorizontalHeaderLabels([
            "IP Address", "Avg Latency (ms)", "Mean Latency Var (ms)", "Packet Loss (%)", "Measured BW (Mbps)", "Bitrate Source", "Uptime (%)", "Congestion State"
        ])
        self.tbl_telemetry.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_telemetry.setStyleSheet(
            "QTableWidget { background: #0d1117; color: #c9d1d9; gridline-color: #21262d; border: 1px solid #30363d; } QHeaderView::section { background: #161b22; color: #8b949e; padding: 6px; border: 1px solid #30363d; font-weight: bold; }"
        )
        layout.addWidget(self.tbl_telemetry)
        return widget

    # Tab 3: Diagnostics & Faults
    def _build_diagnostics_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Fault Isolation Matrix Card
        fault_box = QGroupBox("Automated Fault Isolation Matrix")
        fault_box.setStyleSheet("QGroupBox { color: #f85149; font-weight: bold; border: 1px solid #30363d; margin-top: 8px; padding-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; }")
        fault_layout = QVBoxLayout(fault_box)

        self.txt_fault_summary = QTextEdit()
        self.txt_fault_summary.setReadOnly(True)
        self.txt_fault_summary.setFixedHeight(120)
        self.txt_fault_summary.setStyleSheet("background: #161b22; color: #c9d1d9; border: 1px solid #30363d; border-radius: 4px; font-family: Consolas, monospace;")
        self.txt_fault_summary.setText("No active network faults detected. Run diagnostics to evaluate network state.")
        fault_layout.addWidget(self.txt_fault_summary)
        layout.addWidget(fault_box)

        # Diagnostic Probes Table
        lbl_probes = QLabel("CCTV Protocol Reachability & Root-Cause Analysis")
        lbl_probes.setStyleSheet("color: #8b949e; font-size: 12px; font-weight: bold;")
        layout.addWidget(lbl_probes)

        self.tbl_diagnostics = QTableWidget()
        self.tbl_diagnostics.setColumnCount(6)
        self.tbl_diagnostics.setHorizontalHeaderLabels([
            "IP Address", "Protocol", "Port", "Health Status", "Root Cause", "Technical Details"
        ])
        self.tbl_diagnostics.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_diagnostics.setStyleSheet(
            "QTableWidget { background: #0d1117; color: #c9d1d9; gridline-color: #21262d; border: 1px solid #30363d; } QHeaderView::section { background: #161b22; color: #8b949e; padding: 6px; border: 1px solid #30363d; font-weight: bold; }"
        )
        layout.addWidget(self.tbl_diagnostics)
        return widget

    # Tab 4: Security Audit
    def _build_security_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Security Posture Header
        score_frame = QFrame()
        score_frame.setStyleSheet("background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 10px;")
        score_layout = QHBoxLayout(score_frame)

        self.lbl_sec_grade = QLabel("A")
        self.lbl_sec_grade.setStyleSheet("color: #3fb950; font-size: 32px; font-weight: 900; padding: 0 16px;")
        score_layout.addWidget(self.lbl_sec_grade)

        v_score = QVBoxLayout()
        self.lbl_sec_score_txt = QLabel("Security Posture Score: 100/100")
        self.lbl_sec_score_txt.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: bold;")
        self.lbl_sec_summary = QLabel("All evaluated devices comply with local transport security baselines.")
        self.lbl_sec_summary.setStyleSheet("color: #8b949e; font-size: 12px;")
        v_score.addWidget(self.lbl_sec_score_txt)
        v_score.addWidget(self.lbl_sec_summary)
        score_layout.addLayout(v_score, stretch=1)
        layout.addWidget(score_frame)

        # CVE Findings Table
        lbl_cve = QLabel("Known CCTV CVE Vulnerabilities & Strict Confidence Mapping")
        lbl_cve.setStyleSheet("color: #8b949e; font-size: 12px; font-weight: bold;")
        layout.addWidget(lbl_cve)

        self.tbl_cve = QTableWidget()
        self.tbl_cve.setColumnCount(9)
        self.tbl_cve.setHorizontalHeaderLabels([
            "Host IP", "CVE ID", "CVSS", "Vendor Profile", "Confidence", "Advisory Date", "Vulnerability Details", "Mitigation", "Source URL"
        ])
        self.tbl_cve.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_cve.setStyleSheet(
            "QTableWidget { background: #0d1117; color: #c9d1d9; gridline-color: #21262d; border: 1px solid #30363d; } QHeaderView::section { background: #161b22; color: #8b949e; padding: 6px; border: 1px solid #30363d; font-weight: bold; }"
        )
        layout.addWidget(self.tbl_cve)
        return widget

    def _populate_initial_data(self) -> None:
        """Populates default local gateway and initial empty state."""
        gw_ip = self.default_gateway
        self.topology_canvas.set_devices([], gateway_ip=gw_ip)

    # Actions & Worker Handlers
    def _start_network_scan(self) -> None:
        cidr = self.txt_cidr.text().strip()
        try:
            scope = compute_scan_scope(cidr)
        except ValueError as e:
            QMessageBox.warning(self, "Invalid Scan Target", str(e))
            return

        if scope.requires_operator_confirmation:
            confirm_msg = (
                f"Target CIDR: {scope.cidr}\n"
                f"Total Usable Hosts: {scope.total_hosts}\n"
                f"IP Range: {scope.first_usable_ip} - {scope.last_usable_ip}\n"
                f"Execution Batches: {scope.batch_count} (Safety limit: 1024 hosts/batch)\n\n"
                f"Notice: This scan scope exceeds the single standard C-class subnet or touches non-local ranges. "
                f"Do you confirm initiating this bounded network scan?"
            )
            reply = QMessageBox.question(
                self,
                "Operator Authorization Required",
                confirm_msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self.btn_scan.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)

        self._scan_worker = ScanWorker(cidr)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _on_scan_progress(self, done: int, total: int, dev_list: List[DiscoveredNetworkDevice]) -> None:
        pct = int((done / (total or 1)) * 100)
        self.progress_bar.setValue(pct)
        self._update_devices(dev_list)

    def _on_scan_finished(self, devices: List[DiscoveredNetworkDevice]) -> None:
        self.btn_scan.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._update_devices(devices)
        QMessageBox.information(
            self,
            "Scan Complete",
            f"Network scan finished.\nDiscovered {len(devices)} active host(s) on target subnet.",
        )

    def _on_scan_error(self, err_msg: str) -> None:
        self.btn_scan.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Scan Error", f"Network scan failed:\n{err_msg}")

    def _update_devices(self, devices: List[DiscoveredNetworkDevice]) -> None:
        self.discovered_devices = devices

        # Update Statistics
        total_count = len(devices)
        cam_count = sum(1 for d in devices if d.device_type == DeviceType.IP_CAMERA)
        nvr_count = sum(1 for d in devices if d.device_type == DeviceType.NVR)
        sw_count = sum(1 for d in devices if d.device_type in (DeviceType.SWITCH, DeviceType.GATEWAY))
        alert_count = sum(1 for d in devices if d.is_duplicate_ip or d.status == DeviceStatus.DEGRADED)

        self.card_total.findChild(QLabel, "val").setText(str(total_count))
        self.card_cameras.findChild(QLabel, "val").setText(str(cam_count))
        self.card_nvrs.findChild(QLabel, "val").setText(str(nvr_count))
        self.card_switches.findChild(QLabel, "val").setText(str(sw_count))
        self.card_alerts.findChild(QLabel, "val").setText(str(alert_count))

        # Update Inventory Table
        self.tbl_inventory.setRowCount(len(devices))
        for row, d in enumerate(devices):
            item_ip = QTableWidgetItem(d.ip_address)
            item_mac = QTableWidgetItem(d.mac_address)
            item_vendor = QTableWidgetItem(d.vendor)
            item_type = QTableWidgetItem(d.device_type.value)
            item_status = QTableWidgetItem(d.status.value)
            item_lat = QTableWidgetItem(f"{d.latency_ms:.1f}")
            item_ports = QTableWidgetItem(", ".join(str(p) for p in d.open_ports) or "None")

            # Color code status
            if d.status == DeviceStatus.ONLINE:
                item_status.setForeground(QColor("#3fb950"))
            elif d.status == DeviceStatus.DEGRADED:
                item_status.setForeground(QColor("#d29922"))
            else:
                item_status.setForeground(QColor("#f85149"))

            item_details = QTableWidgetItem("Duplicate IP!" if d.is_duplicate_ip else "Verified")
            if d.is_duplicate_ip:
                item_details.setForeground(QColor("#f85149"))

            self.tbl_inventory.setItem(row, 0, item_ip)
            self.tbl_inventory.setItem(row, 1, item_mac)
            self.tbl_inventory.setItem(row, 2, item_vendor)
            self.tbl_inventory.setItem(row, 3, item_type)
            self.tbl_inventory.setItem(row, 4, item_status)
            self.tbl_inventory.setItem(row, 5, item_lat)
            self.tbl_inventory.setItem(row, 6, item_ports)
            self.tbl_inventory.setItem(row, 7, item_details)

        # Update Topology View
        self.topology_canvas.set_devices(devices, gateway_ip=self.default_gateway)

        # Update Telemetry Monitor
        for d in devices:
            self.monitor.record_external_sample(
                ip_address=d.ip_address,
                latency_ms=d.latency_ms,
                bandwidth_bps=4_194_304.0 if d.device_type == DeviceType.IP_CAMERA else 100_000.0,
                is_online=d.status != DeviceStatus.OFFLINE,
            )
        self._refresh_telemetry_table()

    def _apply_inventory_filter(self) -> None:
        query = self.txt_filter.text().lower()
        selected_type = self.cmb_type_filter.currentText()

        for row in range(self.tbl_inventory.rowCount()):
            ip = self.tbl_inventory.item(row, 0).text().lower()
            mac = self.tbl_inventory.item(row, 1).text().lower()
            vendor = self.tbl_inventory.item(row, 2).text().lower()
            dtype = self.tbl_inventory.item(row, 3).text()

            text_match = (query in ip) or (query in mac) or (query in vendor)
            type_match = (selected_type == "All Device Types") or (dtype == selected_type)

            self.tbl_inventory.setRowHidden(row, not (text_match and type_match))

    def _on_topology_node_selected(self, node_info: Dict[str, Any]) -> None:
        self.lbl_insp_ip.setText(node_info.get("ip", "-"))
        self.lbl_insp_mac.setText(node_info.get("mac", "-"))
        self.lbl_insp_vendor.setText(node_info.get("vendor", "-"))
        self.lbl_insp_type.setText(node_info.get("device_type", "-"))
        self.lbl_insp_status.setText(node_info.get("status", "-"))
        self.lbl_insp_latency.setText(f"{node_info.get('latency_ms', 0.0):.1f} ms")

    def _refresh_telemetry_table(self) -> None:
        histories = self.monitor.get_all_histories()
        self.tbl_telemetry.setRowCount(len(histories))
        for row, (ip, hist) in enumerate(histories.items()):
            latest = hist.get_latest_sample()
            bw_source = latest.bandwidth_source if latest else "UNKNOWN"
            measured_mbps = hist.get_current_measured_bandwidth_mbps()
            bw_disp = f"{measured_mbps:.2f}" if measured_mbps > 0 else f"{hist.get_current_bandwidth_mbps():.2f}"

            item_ip = QTableWidgetItem(ip)
            item_lat = QTableWidgetItem(f"{hist.get_average_latency():.1f}")
            item_jit = QTableWidgetItem(f"{hist.get_mean_latency_variation_ms():.1f}")
            item_loss = QTableWidgetItem(f"{hist.get_average_packet_loss():.1f}%")
            item_bw = QTableWidgetItem(bw_disp)
            item_source = QTableWidgetItem(bw_source)
            item_up = QTableWidgetItem(f"{hist.get_uptime_percentage():.1f}%")

            is_cong = hist.is_congested()
            item_cong = QTableWidgetItem("CONGESTED" if is_cong else "NORMAL")
            item_cong.setForeground(QColor("#f85149" if is_cong else "#3fb950"))

            self.tbl_telemetry.setItem(row, 0, item_ip)
            self.tbl_telemetry.setItem(row, 1, item_lat)
            self.tbl_telemetry.setItem(row, 2, item_jit)
            self.tbl_telemetry.setItem(row, 3, item_loss)
            self.tbl_telemetry.setItem(row, 4, item_bw)
            self.tbl_telemetry.setItem(row, 5, item_source)
            self.tbl_telemetry.setItem(row, 6, item_up)
            self.tbl_telemetry.setItem(row, 7, item_cong)

    # Diagnostics & Faults
    def _start_diagnostics_audit(self) -> None:
        if not self.discovered_devices:
            QMessageBox.information(self, "No Devices", "Perform a network scan first to discover devices to audit.")
            return

        self.btn_diagnostics.setEnabled(False)
        self._diag_worker = DiagnosticsWorker(self.discovered_devices)
        self._diag_worker.finished.connect(self._on_diagnostics_finished)
        self._diag_worker.error.connect(lambda e: QMessageBox.critical(self, "Diagnostic Error", str(e)))
        self._diag_worker.start()

    def _on_diagnostics_finished(self, reports: List[ComprehensiveDeviceAuditReport]) -> None:
        self.btn_diagnostics.setEnabled(True)
        self.diagnostic_reports = reports

        # Populate Probes Table
        all_probes = []
        for rep in reports:
            for p in rep.probes:
                all_probes.append((rep.ip_address, p))

        self.tbl_diagnostics.setRowCount(len(all_probes))
        for row, (ip, p) in enumerate(all_probes):
            item_ip = QTableWidgetItem(ip)
            item_proto = QTableWidgetItem(p.protocol)
            item_port = QTableWidgetItem(str(p.port))
            item_health = QTableWidgetItem("HEALTHY" if p.is_healthy else "ALERT")
            item_health.setForeground(QColor("#3fb950" if p.is_healthy else "#f85149"))
            item_cause = QTableWidgetItem(p.root_cause.value)
            item_det = QTableWidgetItem(p.details)

            self.tbl_diagnostics.setItem(row, 0, item_ip)
            self.tbl_diagnostics.setItem(row, 1, item_proto)
            self.tbl_diagnostics.setItem(row, 2, item_port)
            self.tbl_diagnostics.setItem(row, 3, item_health)
            self.tbl_diagnostics.setItem(row, 4, item_cause)
            self.tbl_diagnostics.setItem(row, 5, item_det)

        # Run Automated Fault Analyzer
        dev_dicts = [
            {
                "ip_address": rep.ip_address,
                "is_online": rep.overall_healthy,
                "auth_failed": any(p.root_cause.value == "AUTHENTICATION_FAILURE" for p in rep.probes),
                "rtsp_failed": any(p.protocol == "RTSP" and not p.is_healthy for p in rep.probes),
            }
            for rep in reports
        ]
        self.fault_reports = self.fault_analyzer.analyze_network_state(
            gateway_ip=self.default_gateway,
            gateway_online=True,
            devices=dev_dicts,
        )

        # Update Fault Summary Text
        summary_lines = []
        for f in self.fault_reports:
            summary_lines.append(f"[{f.severity}] {f.fault_type.value}: {f.root_cause_explanation}")
            summary_lines.append(f"  Recommended Remediation: {f.recommended_remediation}\n")
        self.txt_fault_summary.setText("\n".join(summary_lines))

        self.tabs.setCurrentIndex(3)
        QMessageBox.information(self, "Diagnostics Complete", f"Audited {len(reports)} devices.")

    # Security Audit
    def _start_security_audit(self) -> None:
        if not self.discovered_devices:
            QMessageBox.information(self, "No Devices", "Perform a network scan first to discover devices.")
            return

        self.btn_sec_audit.setEnabled(False)
        self._sec_worker = SecurityAuditWorker(self.discovered_devices)
        self._sec_worker.finished.connect(self._on_security_finished)
        self._sec_worker.error.connect(lambda e: QMessageBox.critical(self, "Audit Error", str(e)))
        self._sec_worker.start()

    def _on_security_finished(self, reports: List[SecurityAuditReport]) -> None:
        self.btn_sec_audit.setEnabled(True)
        self.security_reports = reports

        # Calculate average score & grade
        if reports:
            avg_score = int(sum(r.security_score for r in reports) / len(reports))
        else:
            avg_score = 100

        grade = "A" if avg_score >= 90 else "B" if avg_score >= 80 else "C" if avg_score >= 70 else "D" if avg_score >= 60 else "F"
        grade_color = "#3fb950" if grade in ("A", "B") else "#d29922" if grade == "C" else "#f85149"

        self.lbl_sec_grade.setText(grade)
        self.lbl_sec_grade.setStyleSheet(f"color: {grade_color}; font-size: 32px; font-weight: 900; padding: 0 16px;")
        self.lbl_sec_score_txt.setText(f"Security Posture Score: {avg_score}/100")
        self.lbl_sec_summary.setText(f"Evaluated {len(reports)} network hosts. Identified {sum(len(r.cve_findings) for r in reports)} potential CVE mapping(s).")

        # Populate CVE Table
        all_cves = []
        for rep in reports:
            for cve in rep.cve_findings:
                all_cves.append((rep.ip_address, cve))

        self.tbl_cve.setRowCount(len(all_cves))
        for row, (ip, cve) in enumerate(all_cves):
            item_ip = QTableWidgetItem(ip)
            item_id = QTableWidgetItem(cve.cve_id)
            item_cvss = QTableWidgetItem(f"{cve.cvss_score:.1f}")
            item_vendor = QTableWidgetItem(cve.vendor)
            item_conf = QTableWidgetItem(cve.confidence)

            # Color code confidence
            if cve.confidence in (CVEConfidence.CONFIRMED_VULNERABLE.value, "HIGH"):
                item_conf.setForeground(QColor("#f85149"))
            elif cve.confidence in (CVEConfidence.POTENTIALLY_VULNERABLE.value, "MEDIUM"):
                item_conf.setForeground(QColor("#d29922"))
            else:
                item_conf.setForeground(QColor("#3fb950"))

            item_date = QTableWidgetItem(getattr(cve, "advisory_date", "N/A"))
            item_desc = QTableWidgetItem(cve.description)
            item_mit = QTableWidgetItem(cve.mitigation)
            item_url = QTableWidgetItem(getattr(cve, "source_url", "N/A"))

            self.tbl_cve.setItem(row, 0, item_ip)
            self.tbl_cve.setItem(row, 1, item_id)
            self.tbl_cve.setItem(row, 2, item_cvss)
            self.tbl_cve.setItem(row, 3, item_vendor)
            self.tbl_cve.setItem(row, 4, item_conf)
            self.tbl_cve.setItem(row, 5, item_date)
            self.tbl_cve.setItem(row, 6, item_desc)
            self.tbl_cve.setItem(row, 7, item_mit)
            self.tbl_cve.setItem(row, 8, item_url)

        self.tabs.setCurrentIndex(4)
        QMessageBox.information(self, "Security Audit Complete", f"Audited {len(reports)} hosts.")

    # Export Dialog
    def _export_report_dialog(self) -> None:
        if not self.discovered_devices:
            QMessageBox.warning(self, "Export Warning", "No network discovery data available to export.")
            return

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Network Intelligence Report",
            os.path.join(os.getcwd(), "network_intelligence_report.json"),
            "JSON Files (*.json);;CSV Files (*.csv)",
        )
        if not file_path:
            return

        try:
            if file_path.endswith(".csv"):
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["IP Address", "MAC Address", "Vendor", "Device Type", "Status", "Latency (ms)", "Open Ports"])
                    for d in self.discovered_devices:
                        writer.writerow([d.ip_address, d.mac_address, d.vendor, d.device_type.value, d.status.value, d.latency_ms, ";".join(str(p) for p in d.open_ports)])
            else:
                report_payload = {
                    "scan_cidr": self.txt_cidr.text(),
                    "default_gateway": self.default_gateway,
                    "devices": [d.to_dict() for d in self.discovered_devices],
                    "diagnostics": [r.to_dict() for r in self.diagnostic_reports],
                    "security_reports": [s.to_dict() for s in self.security_reports],
                    "fault_reports": [f.to_dict() for f in self.fault_reports],
                }
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(report_payload, f, indent=2)

            QMessageBox.information(self, "Export Successful", f"Report successfully saved to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed saving report: {e}")
