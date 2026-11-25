"""
Unit Tests for Alarm History Cryptographic Hash Chaining and Integrity Verification.
Phase 12.1 (F-046, Change ID: CHG-20261125-010).

Verifies genesis block creation, rolling SHA-256 hash chaining across lifecycle
transitions, tamper detection (modifications, omissions, linkage breaks), and audit trail integrity.
"""

import uuid
import hashlib
from datetime import datetime, timezone
import pytest

from database.database_manager import db_manager
from database.models.alarms import Alarm, AlarmHistory
from engines.alarm_engine.alarm_service import alarm_service, AlarmEngineService
from engines.alarm_engine.normalizer import NormalizedAlarmEvent
from engines.alarm_engine.enums import (
    AlarmSeverity,
    AlarmPriority,
    AlarmStatus,
    AlarmCategory,
    AlarmAction,
)


def test_history_genesis_hash_computation():
    """Verifies deterministic SHA-256 computation for genesis block."""
    now = datetime(2026, 11, 25, 12, 0, 0, tzinfo=timezone.utc)
    entry_index = 0
    alarm_id = str(uuid.uuid4())
    prev_hash = "0" * 64
    action = AlarmAction.CREATED.value
    status = AlarmStatus.NEW.value

    digest = AlarmEngineService.compute_history_hash(
        entry_index=entry_index,
        alarm_id=alarm_id,
        prev_hash=prev_hash,
        previous_status=None,
        new_status=status,
        operator="SYSTEM",
        action=action,
        timestamp=now,
        reason="Initial ingestion",
        comments="Genesis block",
    )
    assert isinstance(digest, str)
    assert len(digest) == 64
    # Re-computing with identical inputs yields identical hash
    digest_repeat = AlarmEngineService.compute_history_hash(
        entry_index=entry_index,
        alarm_id=alarm_id,
        prev_hash=prev_hash,
        previous_status=None,
        new_status=status,
        operator="SYSTEM",
        action=action,
        timestamp=now,
        reason="Initial ingestion",
        comments="Genesis block",
    )
    assert digest == digest_repeat


def test_alarm_lifecycle_creates_unbroken_hash_chain():
    """
    Simulates a full incident lifecycle:
    Created -> Acknowledged -> In Progress -> Escalated -> Resolved -> Reopened -> Closed.
    Verifies that every entry increments entry_index and links prev_hash accurately.
    """
    event = NormalizedAlarmEvent(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        source_subsystem="ANALYTICS",
        event_type="INTRUSION",
        title="Perimeter Breach Zone 1",
        description="Motion detected in restricted zone",
        category=AlarmCategory.SECURITY,
        severity=AlarmSeverity.HIGH,
        priority=AlarmPriority.P2_HIGH,
        camera_id=f"cam_{uuid.uuid4().hex[:6]}",
    )

    # 1. Created (Genesis)
    alarm_id = alarm_service.process_normalized_event(event)
    assert alarm_id

    # 2. Acknowledged
    assert alarm_service.acknowledge_alarm(alarm_id, operator="operator_alice", role="OPERATOR", comments="Reviewing stream")

    # 3. In Progress
    assert alarm_service.start_investigation(alarm_id, operator="operator_alice", role="OPERATOR", comments="Dispatching patrol")

    # 4. Add Note
    assert alarm_service.add_operator_note(alarm_id, operator="operator_alice", note_text="Security team on site", role="OPERATOR")

    # 5. Escalate Manually
    assert alarm_service.escalate_manually(alarm_id, operator="supervisor_bob", role="SUPERVISOR", reason="SOP Level 2 protocol")

    # 6. Resolved
    assert alarm_service.resolve_alarm(alarm_id, operator="operator_alice", role="OPERATOR", reason="Area secured", comments="False alarm confirmed")

    # 7. Reopened
    assert alarm_service.reopen_alarm(alarm_id, operator="supervisor_bob", role="SUPERVISOR", reason="Secondary motion reported")

    # 8. Closed
    assert alarm_service.close_alarm(alarm_id, operator="supervisor_bob", role="SUPERVISOR", comments="Final closure approved")

    # Retrieve history
    history = alarm_service.get_alarm_history(alarm_id)
    assert len(history) == 8

    # Verify genesis entry
    assert history[0]["entry_index"] == 0
    assert history[0]["prev_hash"] == "0" * 64
    assert history[0]["action"] == AlarmAction.CREATED.value
    assert len(history[0]["entry_hash"]) == 64

    # Verify sequential linkage
    for i in range(1, len(history)):
        assert history[i]["entry_index"] == i
        assert history[i]["prev_hash"] == history[i - 1]["entry_hash"]
        assert len(history[i]["entry_hash"]) == 64

    # Cryptographic integrity verification must succeed
    integrity = alarm_service.verify_history_integrity(alarm_id)
    assert integrity["valid"] is True
    assert integrity["total_entries"] == 8
    assert integrity["broken_at_index"] is None


def test_tamper_detection_on_modified_content():
    """
    Artificially alters the comments of an audit entry in the database.
    Verifies that verify_history_integrity detects the modification and returns valid=False.
    """
    event = NormalizedAlarmEvent(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        source_subsystem="BEHAVIOUR",
        event_type="FALL_DETECTED",
        title="Fall Detected Corridor 3",
        description="Worker fell near machinery",
        category=AlarmCategory.SAFETY,
        severity=AlarmSeverity.HIGH,
        priority=AlarmPriority.P1_URGENT,
        camera_id=f"cam_{uuid.uuid4().hex[:6]}",
    )
    alarm_id = alarm_service.process_normalized_event(event)
    alarm_service.acknowledge_alarm(alarm_id, operator="operator_carol", role="OPERATOR")

    # Pre-tamper verification passes
    assert alarm_service.verify_history_integrity(alarm_id)["valid"] is True

    # Tamper with the acknowledgment comments in SQLite
    with db_manager.get_session() as session:
        entry = (
            session.query(AlarmHistory)
            .filter(AlarmHistory.alarm_id == alarm_id, AlarmHistory.entry_index == 1)
            .first()
        )
        assert entry is not None
        entry.comments = "MALICIOUSLY TAMPERED COMMENT WITHOUT RE-HASHING"

    # Post-tamper verification must detect discrepancy
    tamper_result = alarm_service.verify_history_integrity(alarm_id)
    assert tamper_result["valid"] is False
    assert tamper_result["broken_at_index"] == 1
    assert "Cryptographic digest mismatch" in tamper_result["details"]


def test_tamper_detection_on_omitted_entry():
    """
    Simulates malicious deletion of an intermediate audit entry.
    Verifies that verify_history_integrity detects the index discontinuity.
    """
    event = NormalizedAlarmEvent(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        source_subsystem="ANALYTICS",
        event_type="TRIPWIRE",
        title="Tripwire Line 1",
        description="Direction South",
        category=AlarmCategory.SECURITY,
        severity=AlarmSeverity.MEDIUM,
        priority=AlarmPriority.P3_NORMAL,
        camera_id=f"cam_{uuid.uuid4().hex[:6]}",
    )
    alarm_id = alarm_service.process_normalized_event(event)
    alarm_service.acknowledge_alarm(alarm_id, operator="operator_dan", role="OPERATOR")
    alarm_service.start_investigation(alarm_id, operator="operator_dan", role="OPERATOR")

    # Delete the middle entry (entry_index == 1)
    with db_manager.get_session() as session:
        mid_entry = (
            session.query(AlarmHistory)
            .filter(AlarmHistory.alarm_id == alarm_id, AlarmHistory.entry_index == 1)
            .first()
        )
        if mid_entry:
            session.delete(mid_entry)

    # Verification must fail due to index discontinuity or hash mismatch
    result = alarm_service.verify_history_integrity(alarm_id)
    assert result["valid"] is False
    assert result["broken_at_index"] == 1
