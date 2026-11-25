"""
Audit Logging and Cryptographic Hash-Chained Integrity Service (Phase 14 - Module C).
Provides multi-category operational activity tracking, automated secret scrubbing,
rolling SHA-256 Merkle hash chaining, tamper detection, and Asia/Kolkata timezone support.
"""

import os
import json
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import desc

from core.logging.logger import get_logger
from core.config.settings import settings
from database.database_manager import db_manager
from database.models.users import AuditLog

logger = get_logger("audit_service")

# Indian Standard Time (UTC+5:30)
IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30))
GENESIS_HASH = "GENESIS_AUDIT_BLOCK_000000000000000000000000000000000000000000000"


def canon_ts(dt: datetime) -> str:
    """Returns canonical, timezone-independent UTC ISO timestamp string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

SENSITIVE_KEYS = {
    "password", "password_hash", "new_password", "old_password",
    "token", "session_token", "jwt", "secret", "private_key",
    "credential", "api_key", "auth_header"
}


def scrub_sensitive_dict(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Recursively redacts passwords, tokens, and private keys from audit payloads."""
    if not data or not isinstance(data, dict):
        return {}
    cleaned = {}
    for k, v in data.items():
        if any(sens in k.lower() for sens in SENSITIVE_KEYS):
            cleaned[k] = "[REDACTED_SECRET]"
        elif isinstance(v, dict):
            cleaned[k] = scrub_sensitive_dict(v)
        elif isinstance(v, list):
            cleaned[k] = [
                scrub_sensitive_dict(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            cleaned[k] = v
    return cleaned


class AuditService:
    """Manages system audit logs, tamper-evident hash chaining, and integrity verification."""

    def __init__(self, ledger_file: Optional[Path] = None) -> None:
        self.ledger_file = ledger_file or Path("storage/logs/audit_ledger.jsonl")
        self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
        self._last_known_hash: Optional[str] = None
        self._init_last_hash()

    def _init_last_hash(self) -> None:
        """Initializes last known hash from the persistent database or file."""
        try:
            with db_manager.get_session() as session:
                last_entry = session.query(AuditLog).order_by(desc(AuditLog.created_at)).first()
                if last_entry and last_entry.record_hash:
                    self._last_known_hash = last_entry.record_hash
                else:
                    self._last_known_hash = GENESIS_HASH
        except Exception:
            self._last_known_hash = GENESIS_HASH

    def log_event(
        self,
        action: str,
        category: str = "SYSTEM",
        resource_type: str = "system",
        resource_id: Optional[str] = None,
        status: str = "SUCCESS",  # SUCCESS, FAILED, DENIED
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = "127.0.0.1",
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Records an audit event with automated secret scrubbing and rolling hash chaining.
        Returns the unique record ID.
        """
        now = datetime.now(timezone.utc)
        ts_str = canon_ts(now)
        clean_details = scrub_sensitive_dict(details or {})
        details_str = json.dumps(clean_details, sort_keys=True)
        corr_id = correlation_id or str(uuid.uuid4())[:8]

        with db_manager.get_session() as session:
            # Query the latest record to get accurate prev_hash
            last_record = session.query(AuditLog).filter(AuditLog.record_hash.isnot(None)).order_by(desc(AuditLog.created_at)).first()
            prev_hash = last_record.record_hash if (last_record and last_record.record_hash) else GENESIS_HASH

            # Compute SHA-256 Merkle chain hash
            payload_str = f"{prev_hash}:{ts_str}:{user_id or 'none'}:{username or 'system'}:{action}:{category}:{resource_type}:{resource_id or 'none'}:{status}:{details_str}"
            record_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

            log_entry = AuditLog(
                user_id=user_id,
                username=username or "system",
                action=action,
                category=category,
                resource_type=resource_type,
                resource_id=resource_id,
                status=status,
                details_json=details_str,
                ip_address=ip_address,
                session_id=session_id,
                correlation_id=corr_id,
                prev_hash=prev_hash,
                record_hash=record_hash,
                created_at=now,
            )
            session.add(log_entry)
            session.commit()
            self._last_known_hash = record_hash
            record_id = log_entry.id

        # Also write append-only JSONL ledger line
        try:
            line_data = {
                "id": record_id,
                "timestamp_utc": now.isoformat(),
                "timestamp_ist": now.astimezone(IST_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S IST"),
                "username": username or "system",
                "user_id": user_id,
                "action": action,
                "category": category,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "status": status,
                "ip_address": ip_address,
                "session_id": session_id,
                "correlation_id": corr_id,
                "details": clean_details,
                "prev_hash": prev_hash,
                "record_hash": record_hash,
            }
            with open(self.ledger_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(line_data) + "\n")
        except Exception as e:
            logger.warning("Failed to write append-only audit JSONL entry: %s", e)

        return record_id

    def query_logs(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        username: Optional[str] = None,
        search_text: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Queries audit logs with multi-condition filtering, pagination, and Asia/Kolkata formatting.
        Returns: (records, total_count)
        """
        with db_manager.get_session() as session:
            query = session.query(AuditLog).filter_by(is_deleted=False)

            if start_time:
                query = query.filter(AuditLog.created_at >= start_time)
            if end_time:
                query = query.filter(AuditLog.created_at <= end_time)
            if category and category != "ALL":
                query = query.filter(AuditLog.category == category)
            if status and status != "ALL":
                query = query.filter(AuditLog.status == status)
            if username:
                query = query.filter(AuditLog.username.ilike(f"%{username}%"))
            if search_text:
                query = query.filter(
                    (AuditLog.action.ilike(f"%{search_text}%")) |
                    (AuditLog.details_json.ilike(f"%{search_text}%")) |
                    (AuditLog.resource_id.ilike(f"%{search_text}%"))
                )

            total_count = query.count()
            offset = max(0, (page - 1) * page_size)
            logs = query.order_by(desc(AuditLog.created_at)).offset(offset).limit(page_size).all()

            results = []
            for log in logs:
                dt_utc = log.created_at
                dt_ist = dt_utc.astimezone(IST_TIMEZONE) if dt_utc else None
                details_parsed = {}
                if log.details_json:
                    try:
                        details_parsed = json.loads(log.details_json)
                    except Exception:
                        details_parsed = {"raw": log.details_json}

                results.append({
                    "id": log.id,
                    "timestamp_utc": dt_utc.isoformat() if dt_utc else "",
                    "timestamp_ist": dt_ist.strftime("%Y-%m-%d %H:%M:%S") if dt_ist else "",
                    "username": log.username or (log.user.username if log.user else "system"),
                    "user_id": log.user_id,
                    "action": log.action,
                    "category": log.category or "SYSTEM",
                    "resource_type": log.resource_type,
                    "resource_id": log.resource_id or "",
                    "status": log.status or "SUCCESS",
                    "ip_address": log.ip_address or "127.0.0.1",
                    "session_id": log.session_id or "",
                    "correlation_id": log.correlation_id or "",
                    "details": details_parsed,
                    "prev_hash": log.prev_hash or "",
                    "record_hash": log.record_hash or "",
                })

            return results, total_count

    def verify_audit_integrity(self) -> Tuple[bool, int, Optional[str]]:
        """
        Verifies the cryptographic Merkle hash chain across all stored audit records.
        Returns: (is_valid, record_count, error_message)
        """
        with db_manager.get_session() as session:
            logs = session.query(AuditLog).filter(AuditLog.record_hash.isnot(None)).order_by(AuditLog.created_at.asc()).all()
            if not logs:
                return True, 0, "No chained audit records to verify."

            expected_prev_hash = logs[0].prev_hash or GENESIS_HASH
            for idx, log in enumerate(logs):
                # Check link to previous hash
                if log.prev_hash != expected_prev_hash:
                    return False, idx, f"Hash chain broken at record {idx} (ID: {log.id}): prev_hash mismatch. Expected {expected_prev_hash[:16]}..., found {log.prev_hash[:16]}..."

                # Verify recalculation of record_hash
                ts_str = canon_ts(log.created_at)
                details_str = log.details_json or "{}"
                recalculated = hashlib.sha256(
                    f"{log.prev_hash}:{ts_str}:{log.user_id or 'none'}:{log.username or 'system'}:{log.action}:{log.category or 'SYSTEM'}:{log.resource_type}:{log.resource_id or 'none'}:{log.status or 'SUCCESS'}:{details_str}".encode("utf-8")
                ).hexdigest()

                if recalculated != log.record_hash:
                    return False, idx, f"Record hash tampering detected at index {idx} (ID: {log.id}). Record content has been altered!"

                expected_prev_hash = log.record_hash

            return True, len(logs), f"Audit chain verified successfully across {len(logs)} records with zero tampering."


# Global Audit singleton
audit_service = AuditService()
