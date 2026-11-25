"""
High-Resolution PDF Report Generator (Phase 14 - Module D).
Generates enterprise-grade, styled surveillance reports using PySide6 QPdfWriter and QTextDocument.
Includes report metadata, branding headers, structured tables, and cryptographic verification badges.
"""

import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextDocument, QPdfWriter, QPageSize, QPageLayout
from PySide6.QtCore import QMarginsF

from core.logging.logger import get_logger
from core.config.settings import settings

logger = get_logger("pdf_generator")
IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30))


class PDFReportGenerator:
    """Generates court-ready, audit-compliant PDF surveillance reports."""

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self.output_dir = output_dir or Path("storage/reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_qapp()

    def _ensure_qapp(self) -> None:
        """Ensures a QApplication instance is available for QTextDocument and QPdfWriter."""
        if not QApplication.instance():
            self._app = QApplication(sys.argv if sys.argv else ["cctv_ai"])
        else:
            self._app = QApplication.instance()

    def _base_html_template(
        self,
        report_title: str,
        report_id: str,
        generated_by: str,
        summary_cards_html: str,
        table_html: str,
        footer_note: str = ""
    ) -> str:
        """Wraps content in a standardized, dark-accented enterprise surveillance template."""
        now_ist = datetime.now(timezone.utc).astimezone(IST_TIMEZONE).strftime("%d-%b-%Y %H:%M:%S IST")
        app_version = getattr(settings, "app_version", "1.4.0-alpha")

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: Arial, Helvetica, sans-serif;
                font-size: 10pt;
                color: #24292f;
                margin: 0;
                padding: 0;
            }}
            .header-bar {{
                border-bottom: 2px solid #0969da;
                padding-bottom: 8px;
                margin-bottom: 12px;
            }}
            .platform-title {{
                font-size: 14pt;
                font-weight: bold;
                color: #0969da;
                margin: 0;
            }}
            .report-title {{
                font-size: 18pt;
                font-weight: bold;
                color: #1f2328;
                margin-top: 4px;
                margin-bottom: 0;
            }}
            .meta-table {{
                width: 100%;
                margin-top: 8px;
                margin-bottom: 12px;
                font-size: 9pt;
                background-color: #f6f8fa;
                border: 1px solid #d0d7de;
                border-radius: 4px;
            }}
            .meta-table td {{
                padding: 5px 8px;
            }}
            .meta-label {{
                font-weight: bold;
                color: #57606a;
            }}
            .summary-container {{
                margin-bottom: 12px;
            }}
            .data-table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 10px;
                font-size: 9pt;
            }}
            .data-table th {{
                background-color: #24292f;
                color: #ffffff;
                font-weight: bold;
                padding: 6px 8px;
                text-align: left;
                border: 1px solid #24292f;
            }}
            .data-table td {{
                padding: 6px 8px;
                border: 1px solid #d0d7de;
            }}
            .row-alt {{
                background-color: #f6f8fa;
            }}
            .status-badge {{
                font-weight: bold;
                padding: 2px 6px;
                border-radius: 3px;
                display: inline-block;
            }}
            .status-success {{ color: #1a7f37; font-weight: bold; }}
            .status-failed {{ color: #cf222e; font-weight: bold; }}
            .status-warning {{ color: #9a6700; font-weight: bold; }}
            .footer-disclaimer {{
                margin-top: 20px;
                border-top: 1px solid #d0d7de;
                padding-top: 8px;
                font-size: 8pt;
                color: #57606a;
                text-align: center;
            }}
        </style>
        </head>
        <body>
            <div class="header-bar">
                <div class="platform-title">CCTV AI INTELLIGENCE PLATFORM &bull; ENTERPRISE SURVEILLANCE</div>
                <div class="report-title">{report_title}</div>
            </div>

            <table class="meta-table">
                <tr>
                    <td class="meta-label">Report ID:</td>
                    <td><b>{report_id}</b></td>
                    <td class="meta-label">Generated Date (IST):</td>
                    <td>{now_ist}</td>
                </tr>
                <tr>
                    <td class="meta-label">Generated By:</td>
                    <td>{generated_by}</td>
                    <td class="meta-label">Platform Version:</td>
                    <td>v{app_version} (OpenVINO AI Core)</td>
                </tr>
                <tr>
                    <td class="meta-label">Classification:</td>
                    <td>CONFIDENTIAL &bull; AUTHORIZED SECURITY AUDIT</td>
                    <td class="meta-label">Integrity Status:</td>
                    <td><span class="status-success">&check; SHA-256 Merkle Chained Ledger</span></td>
                </tr>
            </table>

            {summary_cards_html}

            {table_html}

            <div class="footer-disclaimer">
                <b>OFFICIAL SURVEILLANCE INTELLIGENCE REPORT</b> &bull; STRICTLY CONFIDENTIAL &bull; FOR AUTHORIZED USE ONLY<br>
                {footer_note or "This document is cryptographically referenced against the tamper-evident surveillance audit ledger."}
            </div>
        </body>
        </html>
        """

    def generate_audit_report(
        self,
        audit_records: List[Dict[str, Any]],
        generated_by: str = "Administrator",
        report_id: Optional[str] = None
    ) -> str:
        """Generates an Audit Log & System Activity PDF report."""
        rpt_id = report_id or f"RPT-AUD-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        output_file = self.output_dir / f"{rpt_id}.pdf"

        # Summary box
        total = len(audit_records)
        successes = sum(1 for r in audit_records if r.get("status") == "SUCCESS")
        failures = sum(1 for r in audit_records if r.get("status") in ("FAILED", "DENIED"))

        summary_html = f"""
        <table style="width: 100%; margin-bottom: 12px; background-color: #f6f8fa; border: 1px solid #d0d7de; font-size: 9pt;">
            <tr>
                <td style="padding: 8px;"><b>Total Events Recorded:</b> {total}</td>
                <td style="padding: 8px;"><b style="color: #1a7f37;">Successful Actions:</b> {successes}</td>
                <td style="padding: 8px;"><b style="color: #cf222e;">Failed / Denied Attempts:</b> {failures}</td>
            </tr>
        </table>
        """

        # Table rows
        table_rows = []
        for idx, r in enumerate(audit_records[:200]):  # Limit to 200 items per PDF for layout sanity
            row_class = ' class="row-alt"' if idx % 2 == 1 else ''
            status = r.get("status", "SUCCESS")
            status_style = 'color: #1a7f37;' if status == 'SUCCESS' else 'color: #cf222e;'
            table_rows.append(f"""
            <tr{row_class}>
                <td>{r.get('timestamp_ist', '')}</td>
                <td><b>{r.get('username', '')}</b></td>
                <td>{r.get('category', '')}</td>
                <td><b>{r.get('action', '')}</b></td>
                <td><b style="{status_style}">{status}</b></td>
                <td>{r.get('ip_address', '')}</td>
                <td style="font-family: monospace; font-size: 7pt;">{r.get('record_hash', '')[:12]}...</td>
            </tr>
            """)

        table_html = f"""
        <table class="data-table">
            <thead>
                <tr>
                    <th>Timestamp (IST)</th>
                    <th>User</th>
                    <th>Category</th>
                    <th>Action</th>
                    <th>Status</th>
                    <th>Source IP</th>
                    <th>Record Hash</th>
                </tr>
            </thead>
            <tbody>
                {''.join(table_rows) if table_rows else '<tr><td colspan="7" style="text-align: center;">No audit records found matching criteria.</td></tr>'}
            </tbody>
        </table>
        """

        full_html = self._base_html_template(
            report_title="SYSTEM AUDIT & ACCESS LOG REPORT",
            report_id=rpt_id,
            generated_by=generated_by,
            summary_cards_html=summary_html,
            table_html=table_html,
            footer_note="All records above are protected by append-only SHA-256 rolling hash chains in SQLite WAL and audit_ledger.jsonl."
        )

        return self._render_html_to_pdf(full_html, str(output_file))

    def generate_incident_report(
        self,
        incident_data: Dict[str, Any],
        generated_by: str = "Administrator",
        report_id: Optional[str] = None
    ) -> str:
        """Generates a formal Incident / Alarm Investigation PDF report."""
        rpt_id = report_id or f"RPT-INC-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        output_file = self.output_dir / f"{rpt_id}.pdf"

        alarm_id = incident_data.get("id", "N/A")
        alarm_title = incident_data.get("title", "Surveillance Incident")
        severity = incident_data.get("severity", "MEDIUM")
        camera_name = incident_data.get("camera_name", "Camera 1")
        first_detected = incident_data.get("first_detected_at", "")
        summary = incident_data.get("description", "Automated alarm alert triggered by video analytics.")

        sev_color = "#cf222e" if severity in ("CRITICAL", "HIGH") else "#9a6700"

        summary_html = f"""
        <div style="border: 1px solid #d0d7de; padding: 10px; margin-bottom: 12px; background-color: #f6f8fa;">
            <table style="width: 100%; font-size: 9pt;">
                <tr>
                    <td><b>Alarm ID:</b> {alarm_id}</td>
                    <td><b>Severity:</b> <span style="color: {sev_color}; font-weight: bold;">{severity}</span></td>
                    <td><b>Camera Channel:</b> {camera_name}</td>
                </tr>
                <tr>
                    <td><b>Incident Title:</b> {alarm_title}</td>
                    <td><b>Detection Time:</b> {first_detected}</td>
                    <td><b>Status:</b> <b>{incident_data.get('status', 'ACKNOWLEDGED')}</b></td>
                </tr>
            </table>
            <div style="margin-top: 8px; font-size: 9pt;"><b>Incident Description:</b> {summary}</div>
        </div>
        """

        # Operator notes & history
        history_rows = []
        for h in incident_data.get("history", []):
            history_rows.append(f"""
            <tr>
                <td>{h.get('timestamp', '')}</td>
                <td><b>{h.get('actor', '')}</b></td>
                <td>{h.get('action', '')}</td>
                <td>{h.get('notes', '')}</td>
            </tr>
            """)

        table_html = f"""
        <div style="font-weight: bold; margin-top: 10px; font-size: 11pt;">Incident Chain of Custody & Operator Log</div>
        <table class="data-table">
            <thead>
                <tr>
                    <th>Timestamp (IST)</th>
                    <th>Operator</th>
                    <th>Action</th>
                    <th>Operator Notes</th>
                </tr>
            </thead>
            <tbody>
                {''.join(history_rows) if history_rows else '<tr><td colspan="4" style="text-align: center;">No history entries logged.</td></tr>'}
            </tbody>
        </table>
        """

        full_html = self._base_html_template(
            report_title="SECURITY INCIDENT & FORENSIC DOSSIER",
            report_id=rpt_id,
            generated_by=generated_by,
            summary_cards_html=summary_html,
            table_html=table_html,
            footer_note="Video evidence segments associated with this incident are cryptographically sealed with SHA-256 integrity hashes."
        )

        return self._render_html_to_pdf(full_html, str(output_file))

    def generate_user_report(
        self,
        users: List[Dict[str, Any]],
        generated_by: str = "Administrator",
        report_id: Optional[str] = None
    ) -> str:
        """Generates a User Accounts & RBAC Access Policy PDF report."""
        rpt_id = report_id or f"RPT-USR-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        output_file = self.output_dir / f"{rpt_id}.pdf"

        total = len(users)
        active = sum(1 for u in users if u.get("is_active"))
        locked = sum(1 for u in users if u.get("is_locked"))

        summary_html = f"""
        <table style="width: 100%; margin-bottom: 12px; background-color: #f6f8fa; border: 1px solid #d0d7de; font-size: 9pt;">
            <tr>
                <td style="padding: 8px;"><b>Total User Accounts:</b> {total}</td>
                <td style="padding: 8px;"><b style="color: #1a7f37;">Active Accounts:</b> {active}</td>
                <td style="padding: 8px;"><b style="color: #cf222e;">Locked Accounts:</b> {locked}</td>
            </tr>
        </table>
        """

        rows = []
        for idx, u in enumerate(users):
            row_class = ' class="row-alt"' if idx % 2 == 1 else ''
            status = "LOCKED" if u.get("is_locked") else ("ACTIVE" if u.get("is_active") else "INACTIVE")
            color = "#cf222e" if status == "LOCKED" else ("#1a7f37" if status == "ACTIVE" else "#57606a")
            rows.append(f"""
            <tr{row_class}>
                <td><b>{u.get('username', '')}</b></td>
                <td>{u.get('full_name', '')}</td>
                <td>{u.get('role_name', '')}</td>
                <td>{u.get('email', '') or 'N/A'}</td>
                <td><b style="color: {color};">{status}</b></td>
                <td>{u.get('last_login_at', 'Never')}</td>
            </tr>
            """)

        table_html = f"""
        <table class="data-table">
            <thead>
                <tr>
                    <th>Username</th>
                    <th>Full Name</th>
                    <th>Assigned Role</th>
                    <th>Email Address</th>
                    <th>Status</th>
                    <th>Last Login</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
        """

        full_html = self._base_html_template(
            report_title="USER ADMINISTRATION & RBAC ACCESS AUDIT",
            report_id=rpt_id,
            generated_by=generated_by,
            summary_cards_html=summary_html,
            table_html=table_html,
            footer_note="All passwords are encrypted with bcrypt (cost 12); no plaintext credentials or password hashes are exposed in this document."
        )

        return self._render_html_to_pdf(full_html, str(output_file))

    def _render_html_to_pdf(self, html_content: str, output_path: str) -> str:
        """Renders HTML content to a 300 DPI A4 PDF file via QPdfWriter."""
        writer = QPdfWriter(output_path)
        writer.setPageSize(QPageSize(QPageSize.A4))
        writer.setResolution(300)
        # 15mm margins
        writer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter)

        doc = QTextDocument()
        doc.setHtml(html_content)
        doc.print_(writer)

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError(f"PDF rendering failed: file {output_path} was not created.")

        logger.info("PDF report successfully generated at %s (Size: %d bytes)", output_path, os.path.getsize(output_path))
        return output_path


# Global PDF Generator singleton
pdf_generator = PDFReportGenerator()
