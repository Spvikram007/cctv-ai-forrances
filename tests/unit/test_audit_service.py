"""
Unit Tests for Audit Reporting and Hash-Chained Integrity (Phase 14 - Module C).
"""

import pytest
import json
from sqlalchemy import text
from datetime import datetime, timezone

from database.database_manager import db_manager
from database.models.users import AuditLog
from core.security.audit_service import (
    audit_service,
    scrub_sensitive_dict,
    GENESIS_HASH
)


def test_audit_secret_scrubbing():
    """Verifies that password and token fields are automatically redacted before logging."""
    raw_payload = {
        "username": "operator1",
        "password": "SecretPassword123!",
        "session_token": "secret_session_token_xyz",
        "nested": {
            "api_key": "sensitive_api_key",
            "safe_param": "1080p"
        }
    }
    cleaned = scrub_sensitive_dict(raw_payload)
    assert cleaned["username"] == "operator1"
    assert cleaned["password"] == "[REDACTED_SECRET]"
    assert cleaned["session_token"] == "[REDACTED_SECRET]"
    assert cleaned["nested"]["api_key"] == "[REDACTED_SECRET]"
    assert cleaned["nested"]["safe_param"] == "1080p"


def test_audit_event_logging_and_hash_chain():
    """Verifies that audit events generate a valid sequential SHA-256 hash chain."""
    eid1 = audit_service.log_event(
        action="TEST_ACTION_A",
        category="SYSTEM",
        status="SUCCESS",
        username="test_auditor",
        details={"param": "value1"}
    )
    assert eid1 is not None

    eid2 = audit_service.log_event(
        action="TEST_ACTION_B",
        category="CAMERA",
        status="SUCCESS",
        username="test_auditor",
        details={"param": "value2"}
    )
    assert eid2 is not None

    with db_manager.get_session() as session:
        log1 = session.query(AuditLog).filter_by(id=eid1).first()
        log2 = session.query(AuditLog).filter_by(id=eid2).first()

        assert log1 is not None and log2 is not None
        assert log1.record_hash is not None
        assert log2.record_hash is not None
        # log2's prev_hash must match log1's record_hash!
        assert log2.prev_hash == log1.record_hash


def test_audit_query_and_filtering():
    """Verifies multi-condition querying, pagination, and Asia/Kolkata formatting."""
    unique_tag = f"tag_{datetime.now().microsecond}"
    audit_service.log_event(
        action="FILTER_TEST_EVENT",
        category="ALARM",
        status="SUCCESS",
        username="filter_user",
        details={"tag": unique_tag}
    )

    records, total = audit_service.query_logs(
        category="ALARM",
        status="SUCCESS",
        search_text=unique_tag
    )
    assert total >= 1
    found = any(r["details"].get("tag") == unique_tag for r in records)
    assert found
    assert records[0]["timestamp_ist"] != ""


def test_audit_integrity_verification_and_tamper_detection():
    """Verifies that verify_audit_integrity detects any direct unauthorized modification."""
    # 1. Clean verification should pass
    is_valid, count, msg = audit_service.verify_audit_integrity()
    assert is_valid
    assert count > 0

    # 2. Simulate unauthorized attacker directly tampering with an audit record in SQLite
    with db_manager.get_session() as session:
        target = session.query(AuditLog).filter(AuditLog.record_hash.isnot(None)).first()
        assert target is not None
        target_id = target.id
        original_details = target.details_json

        # Tamper with the details without re-hashing
        target.details_json = json.dumps({"tampered_by": "attacker", "evidence_erased": True})
        session.commit()

    # 3. verify_audit_integrity MUST detect this tampering!
    is_valid_after, bad_idx, err_msg = audit_service.verify_audit_integrity()
    assert not is_valid_after
    assert "tampering detected" in err_msg.lower() or "broken" in err_msg.lower()

    # 4. Restore original details to restore integrity
    with db_manager.get_session() as session:
        restored = session.query(AuditLog).filter_by(id=target_id).first()
        restored.details_json = original_details
        session.commit()

    # 5. Integrity is restored
    is_restored, _, _ = audit_service.verify_audit_integrity()
    assert is_restored
