"""
Secure CSV Export Engine with Formula Injection Protection (Phase 14 - Module D).
Implements RFC 4180 compliance, UTF-8 BOM encoding for Microsoft Excel,
strict credential redaction, and spreadsheet formula-injection neutralization (CWE-1236).
"""

import io
import csv
from typing import List, Dict, Any, Sequence
from datetime import datetime, timezone, timedelta

# Indian Standard Time (UTC+5:30)
IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30))

FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r", "|", "%")


def sanitize_csv_cell(value: Any) -> str:
    """
    Sanitizes a cell value to prevent CSV Spreadsheet Formula Injection (CWE-1236).
    If a string starts with formula operators (=, +, -, @, etc.), it is prefixed
    with a single quote (') so spreadsheet applications treat it strictly as literal text.
    """
    if value is None:
        return ""
    val_str = str(value)
    if val_str and val_str[0] in FORMULA_TRIGGERS:
        return f"'{val_str}"
    return val_str


class CSVExporter:
    """Generates sanitized, secure CSV exports for surveillance audit and operational data."""

    @staticmethod
    def export_to_string(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
        """
        Exports headers and rows to a sanitized CSV string with UTF-8 encoding.
        """
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")

        # Write sanitized header row
        writer.writerow([sanitize_csv_cell(h) for h in headers])

        # Write sanitized data rows
        for row in rows:
            writer.writerow([sanitize_csv_cell(cell) for cell in row])

        return output.getvalue()

    @staticmethod
    def export_to_file(filepath: str, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
        """
        Writes sanitized CSV content to a file with UTF-8 BOM encoding for Excel compatibility.
        """
        content = CSVExporter.export_to_string(headers, rows)
        # UTF-8 BOM is '\ufeff' so Excel opens unicode characters seamlessly
        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            f.write(content)
        return filepath

    @staticmethod
    def export_audit_logs(audit_records: List[Dict[str, Any]], filepath: str) -> str:
        """Exports sanitized audit log records."""
        headers = [
            "Event ID", "Timestamp (IST)", "Timestamp (UTC)", "Username", "Action",
            "Category", "Resource Type", "Resource ID", "Status", "IP Address",
            "Correlation ID", "Details", "Record Hash"
        ]
        rows = []
        for r in audit_records:
            rows.append([
                r.get("id", ""),
                r.get("timestamp_ist", ""),
                r.get("timestamp_utc", ""),
                r.get("username", ""),
                r.get("action", ""),
                r.get("category", ""),
                r.get("resource_type", ""),
                r.get("resource_id", ""),
                r.get("status", ""),
                r.get("ip_address", ""),
                r.get("correlation_id", ""),
                str(r.get("details", "")),
                r.get("record_hash", ""),
            ])
        return CSVExporter.export_to_file(filepath, headers, rows)

    @staticmethod
    def export_users(users: List[Dict[str, Any]], filepath: str) -> str:
        """Exports sanitized user accounts with zero password or secret exposure."""
        headers = [
            "User ID", "Username", "Full Name", "Email", "Role", "Active",
            "Account Locked", "Failed Attempts", "Last Login (UTC)", "Created At"
        ]
        rows = []
        for u in users:
            rows.append([
                u.get("id", ""),
                u.get("username", ""),
                u.get("full_name", ""),
                u.get("email", ""),
                u.get("role_name", ""),
                "Yes" if u.get("is_active") else "No",
                "Yes" if u.get("is_locked") else "No",
                u.get("failed_attempts", 0),
                u.get("last_login_at", ""),
                u.get("created_at", ""),
            ])
        return CSVExporter.export_to_file(filepath, headers, rows)

    @staticmethod
    def export_cameras(cameras: List[Dict[str, Any]], filepath: str) -> str:
        """Exports camera device inventory."""
        headers = [
            "Camera ID", "Name", "IP Address", "Port", "Manufacturer", "Model",
            "ONVIF Enabled", "Channels", "Status", "Created At"
        ]
        rows = []
        for c in cameras:
            rows.append([
                c.get("id", ""),
                c.get("name", ""),
                c.get("ip_address", ""),
                c.get("port", ""),
                c.get("manufacturer", ""),
                c.get("model", ""),
                "Yes" if c.get("is_onvif") else "No",
                c.get("channel_count", 1),
                c.get("status", ""),
                c.get("created_at", ""),
            ])
        return CSVExporter.export_to_file(filepath, headers, rows)
