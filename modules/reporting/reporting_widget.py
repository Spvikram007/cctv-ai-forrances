"""
Reporting, Audit Log Viewer and Multi-Format Evidence Export Workspace (Phase 14 - Module C & D).
Mounted at View 11 (Reports). Provides audit log searching, PDF/CSV generation,
and cryptographic hash-chain integrity verification.
"""

import os
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QLineEdit, QComboBox, QMessageBox, QFrame, QFileDialog,
    QTextEdit, QDateEdit, QFormLayout, QProgressBar
)

from core.logging.logger import get_logger
from core.security.audit_service import audit_service
from modules.reporting.report_service import report_service
from modules.reporting.csv_exporter import CSVExporter
from modules.reporting.pdf_generator import pdf_generator

logger = get_logger("reporting_widget")
IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30))


class ReportingWorkspaceWidget(QWidget):
    """Primary Command Center Workspace for Audit Inspection and Report Generation."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_page = 1
        self._page_size = 50
        self._total_audit_count = 0
        self._cached_audit_records: List[Dict[str, Any]] = []
        self._init_ui()
        self._load_audit_data()

    def _init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        # 1. Header
        header_layout = QHBoxLayout()
        lbl_title = QLabel("REPORTS, AUDIT LEDGER & EVIDENCE EXPORT CENTER")
        lbl_title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #58a6ff;")
        header_layout.addWidget(lbl_title)
        header_layout.addStretch()

        self.btn_refresh = QPushButton("Refresh Logs")
        self.btn_refresh.clicked.connect(self._load_audit_data)
        header_layout.addWidget(self.btn_refresh)
        root_layout.addLayout(header_layout)

        # KPI Telemetry Cards
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(10)

        self.card_total_events = self._create_kpi_card("TOTAL AUDIT EVENTS", "0", "#58a6ff")
        self.card_success_rate = self._create_kpi_card("SUCCESS RATE", "100%", "#2ea043")
        self.card_denials = self._create_kpi_card("DENIED / FAILED ATTEMPTS", "0", "#f85149")
        self.card_ledger_status = self._create_kpi_card("MERKLE LEDGER INTEGRITY", "VERIFIED", "#2ea043")

        kpi_layout.addWidget(self.card_total_events)
        kpi_layout.addWidget(self.card_success_rate)
        kpi_layout.addWidget(self.card_denials)
        kpi_layout.addWidget(self.card_ledger_status)
        root_layout.addLayout(kpi_layout)

        # 2. Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #30363d; background: #0d1117; }
            QTabBar::tab { background: #161b22; color: #8b949e; padding: 8px 16px; border: 1px solid #30363d; }
            QTabBar::tab:selected { background: #0d1117; color: #58a6ff; font-weight: bold; border-bottom: 2px solid #58a6ff; }
        """)

        # Tab 1: Audit Log Viewer
        self.tab_audit = self._create_audit_tab()
        self.tabs.addTab(self.tab_audit, "Security Audit Trail")

        # Tab 2: Report Generator
        self.tab_reports = self._create_reports_tab()
        self.tabs.addTab(self.tab_reports, "Surveillance Report Generator")

        # Tab 3: Ledger Integrity Monitor
        self.tab_integrity = self._create_integrity_tab()
        self.tabs.addTab(self.tab_integrity, "Cryptographic Ledger Verification")

        root_layout.addWidget(self.tabs, stretch=1)

    def _create_kpi_card(self, title: str, value: str, color: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 8px;")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("font-size: 8pt; color: #8b949e; font-weight: bold;")
        lbl_v = QLabel(value)
        lbl_v.setStyleSheet(f"font-size: 15pt; font-weight: bold; color: {color};")
        lbl_v.setObjectName("val")

        layout.addWidget(lbl_t)
        layout.addWidget(lbl_v)
        return card

    def _update_kpi_card(self, card: QFrame, value: str) -> None:
        lbl_v = card.findChild(QLabel, "val")
        if lbl_v:
            lbl_v.setText(str(value))

    def _create_audit_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Filter Bar
        filter_bar = QHBoxLayout()

        self.txt_audit_search = QLineEdit()
        self.txt_audit_search.setPlaceholderText("Search by user, action, resource, or details...")
        self.txt_audit_search.returnPressed.connect(self._load_audit_data)
        filter_bar.addWidget(self.txt_audit_search, stretch=2)

        self.combo_category = QComboBox()
        self.combo_category.addItems([
            "All Categories", "AUTH", "USER", "ROLE", "CAMERA", "PTZ",
            "PLAYBACK", "EVIDENCE", "ALARM", "STORAGE", "NETWORK", "SYSTEM"
        ])
        self.combo_category.currentIndexChanged.connect(self._load_audit_data)
        filter_bar.addWidget(self.combo_category)

        self.combo_status = QComboBox()
        self.combo_status.addItems(["All Statuses", "SUCCESS", "FAILED", "DENIED"])
        self.combo_status.currentIndexChanged.connect(self._load_audit_data)
        filter_bar.addWidget(self.combo_status)

        self.btn_search = QPushButton("Filter")
        self.btn_search.clicked.connect(self._load_audit_data)
        filter_bar.addWidget(self.btn_search)

        self.btn_export_audit_pdf = QPushButton("Export PDF")
        self.btn_export_audit_pdf.setStyleSheet("background-color: #21262d; color: #58a6ff; font-weight: bold;")
        self.btn_export_audit_pdf.clicked.connect(self._export_audit_pdf)
        filter_bar.addWidget(self.btn_export_audit_pdf)

        self.btn_export_audit_csv = QPushButton("Export CSV")
        self.btn_export_audit_csv.setStyleSheet("background-color: #21262d; color: #2ea043; font-weight: bold;")
        self.btn_export_audit_csv.clicked.connect(self._export_audit_csv)
        filter_bar.addWidget(self.btn_export_audit_csv)

        layout.addLayout(filter_bar)

        # Audit Table
        self.table_audit = QTableWidget()
        self.table_audit.setColumnCount(8)
        self.table_audit.setHorizontalHeaderLabels([
            "Timestamp (IST)", "User", "Category", "Action", "Status",
            "Source IP", "Details", "Record Hash"
        ])
        self.table_audit.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_audit.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_audit.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.table_audit.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_audit.setAlternatingRowColors(True)
        self.table_audit.setStyleSheet("""
            QTableWidget { background-color: #0d1117; color: #c9d1d9; gridline-color: #30363d; }
            QTableWidget::item { padding: 4px; }
            QHeaderView::section { background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d; padding: 6px; font-weight: bold; }
        """)
        layout.addWidget(self.table_audit, stretch=1)

        # Pagination Bar
        page_bar = QHBoxLayout()
        self.btn_prev_page = QPushButton("< Previous")
        self.btn_prev_page.clicked.connect(self._on_prev_page)
        page_bar.addWidget(self.btn_prev_page)

        self.lbl_page_info = QLabel("Page 1 of 1 (0 Total Events)")
        self.lbl_page_info.setStyleSheet("color: #8b949e; font-weight: bold;")
        page_bar.addWidget(self.lbl_page_info)

        self.btn_next_page = QPushButton("Next >")
        self.btn_next_page.clicked.connect(self._on_next_page)
        page_bar.addWidget(self.btn_next_page)

        page_bar.addStretch()
        layout.addLayout(page_bar)

        return widget

    def _create_reports_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        lbl_sub = QLabel("AUTOMATED INTELLIGENCE & AUDIT REPORT GENERATOR")
        lbl_sub.setStyleSheet("font-size: 11pt; font-weight: bold; color: #58a6ff;")
        layout.addWidget(lbl_sub)

        form_frame = QFrame()
        form_frame.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 12px;")
        form_layout = QFormLayout(form_frame)
        form_layout.setSpacing(12)

        self.combo_report_type = QComboBox()
        self.combo_report_type.addItems([
            "Security Audit & Access Log Report",
            "User Administration & RBAC Audit Report",
            "Incident & Security Alarm Summary Report"
        ])
        form_layout.addRow("Report Template:", self.combo_report_type)

        self.combo_report_format = QComboBox()
        self.combo_report_format.addItems(["PDF Document (.pdf)", "Sanitized Spreadsheet CSV (.csv)"])
        form_layout.addRow("Export Format:", self.combo_report_format)

        self.btn_generate = QPushButton("Generate & Save Report")
        self.btn_generate.setStyleSheet("background-color: #238636; color: #fff; font-weight: bold; padding: 8px 18px;")
        self.btn_generate.clicked.connect(self._on_generate_report)
        form_layout.addRow("", self.btn_generate)

        layout.addWidget(form_frame)

        # Output Log Box
        lbl_log = QLabel("Generated Report History & Downloads:")
        lbl_log.setStyleSheet("font-weight: bold; color: #8b949e;")
        layout.addWidget(lbl_log)

        self.txt_report_history = QTextEdit()
        self.txt_report_history.setReadOnly(True)
        self.txt_report_history.setStyleSheet("background-color: #0d1117; color: #c9d1d9; border: 1px solid #30363d; font-family: monospace;")
        layout.addWidget(self.txt_report_history, stretch=1)

        # Action bar
        act_bar = QHBoxLayout()
        self.btn_open_reports_dir = QPushButton("Open Reports Folder")
        self.btn_open_reports_dir.clicked.connect(self._open_reports_folder)
        act_bar.addWidget(self.btn_open_reports_dir)
        act_bar.addStretch()
        layout.addLayout(act_bar)

        return widget

    def _create_integrity_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        card_integrity = QFrame()
        card_integrity.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 16px;")
        card_layout = QVBoxLayout(card_integrity)

        lbl_h = QLabel("MERKLE HASH CHAIN & AUDIT LEDGER INTEGRITY ENGINE")
        lbl_h.setStyleSheet("font-size: 12pt; font-weight: bold; color: #58a6ff;")
        card_layout.addWidget(lbl_h)

        lbl_desc = QLabel(
            "Every surveillance event, user authentication, camera configuration change, and evidence access is "
            "cryptographically sealed into an append-only rolling SHA-256 hash chain. Any attempt by unauthorized "
            "operators or external processes to modify, delete, or inject audit entries will break the sequential chain."
        )
        lbl_desc.setStyleSheet("color: #8b949e; font-size: 9pt;")
        lbl_desc.setWordWrap(True)
        card_layout.addWidget(lbl_desc)

        self.btn_verify_ledger = QPushButton("Run Cryptographic Ledger Verification")
        self.btn_verify_ledger.setStyleSheet("background-color: #1f6feb; color: #fff; font-weight: bold; padding: 8px 18px; margin-top: 8px;")
        self.btn_verify_ledger.clicked.connect(self._verify_ledger_integrity)
        card_layout.addWidget(self.btn_verify_ledger)

        layout.addWidget(card_integrity)

        # Verification Log
        lbl_res = QLabel("Verification Ledger Telemetry:")
        lbl_res.setStyleSheet("font-weight: bold; color: #8b949e;")
        layout.addWidget(lbl_res)

        self.txt_integrity_log = QTextEdit()
        self.txt_integrity_log.setReadOnly(True)
        self.txt_integrity_log.setStyleSheet("background-color: #0d1117; color: #3fb950; border: 1px solid #30363d; font-family: monospace; font-size: 9pt;")
        layout.addWidget(self.txt_integrity_log, stretch=1)

        return widget

    def _load_audit_data(self) -> None:
        """Queries audit service with active filters and populates table."""
        search = self.txt_audit_search.text().strip() or None
        cat_text = self.combo_category.currentText()
        category = None if cat_text == "All Categories" else cat_text
        stat_text = self.combo_status.currentText()
        status = None if stat_text == "All Statuses" else stat_text

        records, total = audit_service.query_logs(
            category=category,
            status=status,
            search_text=search,
            page=self._current_page,
            page_size=self._page_size
        )

        self._cached_audit_records = records
        self._total_audit_count = total
        total_pages = max(1, (total + self._page_size - 1) // self._page_size)

        self.lbl_page_info.setText(f"Page {self._current_page} of {total_pages} ({total} Total Events)")
        self.btn_prev_page.setEnabled(self._current_page > 1)
        self.btn_next_page.setEnabled(self._current_page < total_pages)

        # Update KPIs
        self._update_kpi_card(self.card_total_events, str(total))
        denied_count = sum(1 for r in records if r.get("status") in ("FAILED", "DENIED"))
        self._update_kpi_card(self.card_denials, str(denied_count))
        success_pct = 100 if total == 0 else int(100 * (total - denied_count) / max(1, total))
        self._update_kpi_card(self.card_success_rate, f"{success_pct}%")

        self.table_audit.setRowCount(len(records))
        for row, r in enumerate(records):
            self.table_audit.setItem(row, 0, QTableWidgetItem(r.get("timestamp_ist", "")))
            self.table_audit.setItem(row, 1, QTableWidgetItem(r.get("username", "")))
            self.table_audit.setItem(row, 2, QTableWidgetItem(r.get("category", "")))
            self.table_audit.setItem(row, 3, QTableWidgetItem(r.get("action", "")))

            # Status pill
            st = r.get("status", "SUCCESS")
            st_item = QTableWidgetItem(st)
            st_item.setForeground(QColor("#2ea043") if st == "SUCCESS" else QColor("#f85149"))
            st_item.setFont(QFont("Arial", 9, QFont.Bold))
            self.table_audit.setItem(row, 4, st_item)

            self.table_audit.setItem(row, 5, QTableWidgetItem(r.get("ip_address", "")))
            self.table_audit.setItem(row, 6, QTableWidgetItem(str(r.get("details", ""))))

            hash_str = r.get("record_hash", "")
            self.table_audit.setItem(row, 7, QTableWidgetItem(hash_str[:12] + "..." if hash_str else "-"))

    def _on_prev_page(self) -> None:
        if self._current_page > 1:
            self._current_page -= 1
            self._load_audit_data()

    def _on_next_page(self) -> None:
        total_pages = max(1, (self._total_audit_count + self._page_size - 1) // self._page_size)
        if self._current_page < total_pages:
            self._current_page += 1
            self._load_audit_data()

    def _export_audit_pdf(self) -> None:
        try:
            out_file = report_service.generate_audit_report(file_format="PDF")
            QMessageBox.information(self, "Export Complete", f"PDF Audit Report successfully saved to:\n{out_file}")
            self._log_history(f"[PDF EXPORT] Saved audit report: {Path(out_file).name}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to generate PDF: {e}")

    def _export_audit_csv(self) -> None:
        try:
            out_file = report_service.generate_audit_report(file_format="CSV")
            QMessageBox.information(self, "Export Complete", f"CSV Audit Report successfully saved to:\n{out_file}")
            self._log_history(f"[CSV EXPORT] Saved audit report: {Path(out_file).name}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to generate CSV: {e}")

    def _on_generate_report(self) -> None:
        rpt_type = self.combo_report_type.currentText()
        fmt = "PDF" if "PDF" in self.combo_report_format.currentText() else "CSV"

        try:
            if "Audit" in rpt_type:
                out_file = report_service.generate_audit_report(file_format=fmt)
            elif "User" in rpt_type:
                out_file = report_service.generate_user_report(file_format=fmt)
            else:
                # Incident report fallback
                out_file = report_service.generate_audit_report(file_format=fmt)

            QMessageBox.information(self, "Report Generated", f"Report generated successfully:\n{out_file}")
            self._log_history(f"[{fmt} REPORT] {rpt_type} generated: {Path(out_file).name}")
        except Exception as e:
            QMessageBox.critical(self, "Report Generation Failed", f"Error: {e}")

    def _verify_ledger_integrity(self, show_dialog: bool = True) -> None:
        self.txt_integrity_log.clear()
        self.txt_integrity_log.append("=== INITIATING AUDIT LEDGER MERKLE CHAIN VERIFICATION ===")
        self.txt_integrity_log.append("Scanning audit_logs database records and storage/logs/audit_ledger.jsonl...")

        is_valid, count, msg = audit_service.verify_audit_integrity()

        if is_valid:
            self.txt_integrity_log.append(f"\n[OK] VERIFICATION SUCCESS: {msg}")
            self.txt_integrity_log.append(f"[OK] Total chained records verified: {count}")
            self.txt_integrity_log.append("[OK] Genesis Hash: GENESIS_AUDIT_BLOCK_000000000000000000000000000000000000000000000")
            self.txt_integrity_log.append("[OK] Zero hash-chain ruptures or record tampering detected.")
            self._update_kpi_card(self.card_ledger_status, "VERIFIED")
            if show_dialog:
                QMessageBox.information(self, "Integrity Verified", f"Audit ledger integrity verified across {count} records with zero discrepancies.")
        else:
            self.txt_integrity_log.append(f"\n[ALERT] INTEGRITY VIOLATION: {msg}")
            self._update_kpi_card(self.card_ledger_status, "TAMPER DETECTED")
            if show_dialog:
                QMessageBox.critical(self, "Ledger Tampering Detected", f"Cryptographic verification failed!\n{msg}")

    def _log_history(self, entry: str) -> None:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.txt_report_history.append(f"[{now_str}] {entry}")

    def _open_reports_folder(self) -> None:
        reports_dir = Path("storage/reports").resolve()
        reports_dir.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(reports_dir))
            else:
                subprocess.Popen(["xdg-open", str(reports_dir)])
        except Exception as e:
            QMessageBox.information(self, "Reports Folder", f"Reports are located at:\n{reports_dir}")
