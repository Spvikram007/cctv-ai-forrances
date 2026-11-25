"""
Report Orchestration and Export Service (Phase 14 - Module D).
Coordinates data extraction from database, verifies RBAC export permissions,
and routes report generation to PDF or sanitized CSV generators.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path

from core.logging.logger import get_logger
from core.security.rbac import rbac_service
from core.security.audit_service import audit_service
from core.security.user_service import user_service
from database.database_manager import db_manager
from database.models.alarms import Alarm, AlarmHistory
from database.models.devices import Device
from modules.reporting.pdf_generator import pdf_generator
from modules.reporting.csv_exporter import CSVExporter

logger = get_logger("report_service")


class ReportService:
    """Orchestrates system audit and surveillance report generation."""

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self.output_dir = output_dir or Path("storage/reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_audit_report(
        self,
        operator_user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        file_format: str = "PDF"
    ) -> str:
        """
        Generates an Audit Log Report in PDF or CSV format.
        Requires 'audit:export' permission.
        """
        if operator_user_id:
            rbac_service.require_permission(operator_user_id, "audit:export")

        records, total_count = audit_service.query_logs(
            start_time=start_time,
            end_time=end_time,
            category=category,
            status=status,
            page=1,
            page_size=1000
        )

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        username = "system"
        if operator_user_id:
            with db_manager.get_session() as session:
                from database.models.users import User
                op = session.query(User).filter_by(id=operator_user_id).first()
                if op:
                    username = op.username

        if file_format.upper() == "CSV":
            filepath = str(self.output_dir / f"audit_report_{timestamp_str}.csv")
            out_file = CSVExporter.export_audit_logs(records, filepath)
        else:
            out_file = pdf_generator.generate_audit_report(
                audit_records=records,
                generated_by=username
            )

        audit_service.log_event(
            action="REPORT_GENERATED",
            category="AUDIT",
            resource_type="report",
            resource_id=Path(out_file).name,
            status="SUCCESS",
            user_id=operator_user_id,
            username=username,
            details={"type": "AUDIT_LOGS", "format": file_format.upper(), "record_count": len(records)}
        )
        return out_file

    def generate_user_report(
        self,
        operator_user_id: Optional[str] = None,
        file_format: str = "PDF"
    ) -> str:
        """
        Generates a User & RBAC Administration Report in PDF or CSV format.
        Requires 'user:manage' or 'audit:view' permission.
        """
        if operator_user_id:
            if not rbac_service.has_permission(operator_user_id, "user:manage") and \
               not rbac_service.has_permission(operator_user_id, "audit:view"):
                rbac_service.require_permission(operator_user_id, "user:manage")

        users = user_service.list_users()
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        username = "system"
        if operator_user_id:
            with db_manager.get_session() as session:
                from database.models.users import User
                op = session.query(User).filter_by(id=operator_user_id).first()
                if op:
                    username = op.username

        if file_format.upper() == "CSV":
            filepath = str(self.output_dir / f"user_report_{timestamp_str}.csv")
            out_file = CSVExporter.export_users(users, filepath)
        else:
            out_file = pdf_generator.generate_user_report(
                users=users,
                generated_by=username
            )

        audit_service.log_event(
            action="REPORT_GENERATED",
            category="USER",
            resource_type="report",
            resource_id=Path(out_file).name,
            status="SUCCESS",
            user_id=operator_user_id,
            username=username,
            details={"type": "USER_ADMINISTRATION", "format": file_format.upper(), "user_count": len(users)}
        )
        return out_file

    def generate_incident_report(
        self,
        alarm_id: str,
        operator_user_id: Optional[str] = None,
        file_format: str = "PDF"
    ) -> str:
        """
        Generates a single Incident / Alarm Dossier report in PDF format.
        Requires 'alarm:view' permission.
        """
        if operator_user_id:
            rbac_service.require_permission(operator_user_id, "alarm:view")

        with db_manager.get_session() as session:
            alarm = session.query(Alarm).filter_by(id=alarm_id).first()
            if not alarm:
                raise ValueError(f"Incident / Alarm with ID '{alarm_id}' not found.")

            history_entries = session.query(AlarmHistory).filter_by(alarm_id=alarm.id).order_by(AlarmHistory.created_at.asc()).all()

            history_list = [
                {
                    "timestamp": h.created_at.strftime("%Y-%m-%d %H:%M:%S") if h.created_at else "",
                    "actor": h.actor or "system",
                    "action": f"{h.action} ({h.from_state} -> {h.to_state})",
                    "notes": h.notes or "State transition recorded.",
                }
                for h in history_entries
            ]

            incident_data = {
                "id": alarm.id,
                "title": alarm.title,
                "severity": alarm.severity,
                "status": alarm.status,
                "camera_name": alarm.device_id or "Camera 1",
                "first_detected_at": alarm.first_detected_at.strftime("%Y-%m-%d %H:%M:%S") if alarm.first_detected_at else "",
                "description": alarm.description,
                "history": history_list,
            }

        username = "system"
        if operator_user_id:
            with db_manager.get_session() as session:
                from database.models.users import User
                op = session.query(User).filter_by(id=operator_user_id).first()
                if op:
                    username = op.username

        out_file = pdf_generator.generate_incident_report(
            incident_data=incident_data,
            generated_by=username
        )

        audit_service.log_event(
            action="REPORT_GENERATED",
            category="ALARM",
            resource_type="report",
            resource_id=Path(out_file).name,
            status="SUCCESS",
            user_id=operator_user_id,
            username=username,
            details={"type": "INCIDENT_REPORT", "alarm_id": alarm_id, "format": file_format.upper()}
        )
        return out_file


# Global Report singleton
report_service = ReportService()
