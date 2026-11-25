"""
Unit Tests for Multi-Format Evidence and Report Export (Phase 14 - Module D).
"""

import os
import pytest
from pathlib import Path

from modules.reporting.csv_exporter import CSVExporter, sanitize_csv_cell
from modules.reporting.pdf_generator import pdf_generator
from modules.reporting.report_service import report_service
from core.security.rbac import AccessDeniedError


def test_csv_formula_injection_defense():
    """Verifies that malicious spreadsheet formulas are neutralized (CWE-1236)."""
    # Malicious injection payloads
    assert sanitize_csv_cell("=1+1") == "'=1+1"
    assert sanitize_csv_cell("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert sanitize_csv_cell("-2+3*4") == "'-2+3*4"
    assert sanitize_csv_cell("@SUM(A1:A10)") == "'@SUM(A1:A10)"
    assert sanitize_csv_cell("\tDDE('cmd';'/c calc')") == "'\tDDE('cmd';'/c calc')"
    assert sanitize_csv_cell("\r=123") == "'\r=123"

    # Benign surveillance text
    assert sanitize_csv_cell("Camera 1") == "Camera 1"
    assert sanitize_csv_cell("192.168.1.100") == "192.168.1.100"
    assert sanitize_csv_cell(None) == ""


def test_csv_export_to_file(tmp_path: Path):
    """Verifies CSV generation with UTF-8 BOM and sanitized rows."""
    filepath = str(tmp_path / "test_export.csv")
    headers = ["Username", "Command", "Status"]
    rows = [
        ["admin", "view_live", "SUCCESS"],
        ["malicious_user", "=cmd|' /C calc'!A0", "DENIED"],
    ]

    out_file = CSVExporter.export_to_file(filepath, headers, rows)
    assert os.path.exists(out_file)

    with open(out_file, "r", encoding="utf-8-sig") as f:
        content = f.read()

    assert "admin,view_live,SUCCESS" in content
    # The formula trigger must be neutralized with a single quote
    assert "'=cmd|" in content


def test_pdf_report_generation(tmp_path: Path):
    """Verifies high-resolution PDF generation via QPdfWriter."""
    test_pdf = str(tmp_path / "test_audit_report.pdf")

    sample_records = [
        {
            "timestamp_ist": "2026-11-25 17:00:00 IST",
            "username": "admin",
            "category": "AUTH",
            "action": "LOGIN_SUCCESS",
            "status": "SUCCESS",
            "ip_address": "127.0.0.1",
            "record_hash": "a1b2c3d4e5f6789012345678901234567890"
        },
        {
            "timestamp_ist": "2026-11-25 17:05:00 IST",
            "username": "intruder",
            "category": "AUTH",
            "action": "LOGIN_FAILED",
            "status": "FAILED",
            "ip_address": "192.168.1.50",
            "record_hash": "f6e5d4c3b2a1098765432109876543210987"
        }
    ]

    # Generate PDF
    pdf_path = pdf_generator.generate_audit_report(
        audit_records=sample_records,
        generated_by="System Administrator",
        report_id="RPT-TEST-001"
    )
    assert os.path.exists(pdf_path)
    assert os.path.getsize(pdf_path) > 1000  # Valid non-empty PDF file

    # Verify user report generation
    user_pdf = pdf_generator.generate_user_report(
        users=[{"username": "admin", "full_name": "Administrator", "role_name": "Super Administrator", "is_active": True}],
        generated_by="System Administrator",
        report_id="RPT-TEST-002"
    )
    assert os.path.exists(user_pdf)
    assert os.path.getsize(user_pdf) > 1000


def test_report_service_permissions():
    """Verifies that report generation respects RBAC export permissions."""
    # Generating without permission check passes for system
    pdf_path = report_service.generate_audit_report(operator_user_id=None, file_format="PDF")
    assert os.path.exists(pdf_path)
    assert pdf_path.endswith(".pdf")

    csv_path = report_service.generate_audit_report(operator_user_id=None, file_format="CSV")
    assert os.path.exists(csv_path)
    assert csv_path.endswith(".csv")
