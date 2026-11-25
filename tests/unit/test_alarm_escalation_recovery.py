"""
Unit Tests for SLA Escalation Recovery and Duplicate Suppression.
Phase 12.1 (F-046, Change ID: CHG-20261125-010).

Verifies startup recovery of pending SLA deadlines across simulated restarts,
tier advancement bounding, and suppression of duplicate escalations.
"""

import uuid
from datetime import datetime, timezone, timedelta
import pytest

from database.database_manager import db_manager
from database.models.alarms import Alarm, AlarmHistory
from engines.alarm_engine.escalator import AlarmEscalationManager
from engines.alarm_engine.alarm_service import alarm_service
from engines.alarm_engine.enums import AlarmStatus, AlarmSeverity, AlarmPriority, AlarmCategory, AlarmAction


def test_escalation_startup_recovery():
    """
    Simulates application restart where an alarm's SLA expired while the system was down.
    Verifies that recover_pending_escalations immediately detects and escalates it.
    """
    now = datetime.now(timezone.utc)
    past_time = now - timedelta(seconds=1200)

    # Insert an overdue alarm directly into DB simulating pre-restart state
    alarm_id = str(uuid.uuid4())
    with db_manager.get_session() as session:
        alarm = Alarm(
            id=alarm_id,
            title="Pre-Restart Unacknowledged Intrusion",
            category=AlarmCategory.SECURITY.value,
            source_subsystem="ANALYTICS",
            severity=AlarmSeverity.HIGH.value,
            priority=AlarmPriority.P1_URGENT.value,
            status=AlarmStatus.NEW.value,
            first_detected_at=past_time,
            last_detected_at=past_time,
            escalation_level=0,
            next_escalation_deadline=past_time + timedelta(seconds=300),  # expired 900s ago
        )
        session.add(alarm)
        session.flush()

        # Add genesis history entry
        alarm_service._append_history_entry(
            session=session,
            alarm_id=alarm_id,
            previous_status=None,
            new_status=AlarmStatus.NEW.value,
            operator="SYSTEM",
            timestamp=past_time,
            action=AlarmAction.CREATED.value,
            reason="Pre-restart event",
            comments="Simulated existing incident",
        )

    # Execute startup recovery
    escalated_ids = AlarmEscalationManager.recover_pending_escalations(current_time=now)
    assert alarm_id in escalated_ids

    # Verify escalated state and cryptographic hash chain
    with db_manager.get_session() as session:
        recovered_alarm = session.query(Alarm).filter(Alarm.id == alarm_id).first()
        assert recovered_alarm.escalation_level == 1
        deadline = recovered_alarm.next_escalation_deadline
        now_cmp = now.replace(tzinfo=None) if deadline.tzinfo is None else now
        assert deadline > now_cmp

    # Verify audit history
    verification = alarm_service.verify_history_integrity(alarm_id)
    assert verification["valid"] is True
    assert verification["total_entries"] == 2


def test_duplicate_escalation_suppression():
    """
    Verifies that running escalation checks repeatedly within the SLA window
    does NOT duplicate escalations.
    """
    now = datetime.now(timezone.utc)
    past_time = now - timedelta(seconds=600)

    alarm_id = str(uuid.uuid4())
    with db_manager.get_session() as session:
        alarm = Alarm(
            id=alarm_id,
            title="Duplicate Suppression Test Alarm",
            category=AlarmCategory.SECURITY.value,
            source_subsystem="ANALYTICS",
            severity=AlarmSeverity.HIGH.value,
            priority=AlarmPriority.P2_HIGH.value,
            status=AlarmStatus.NEW.value,
            first_detected_at=past_time,
            last_detected_at=past_time,
            escalation_level=0,
            next_escalation_deadline=past_time + timedelta(seconds=120),
        )
        session.add(alarm)
        session.flush()
        alarm_service._append_history_entry(
            session=session,
            alarm_id=alarm_id,
            previous_status=None,
            new_status=AlarmStatus.NEW.value,
            operator="SYSTEM",
            timestamp=past_time,
            action=AlarmAction.CREATED.value,
        )

    # First check: escalates to Tier 1
    escalated_1 = AlarmEscalationManager.check_and_escalate_pending_alarms(current_time=now)
    assert alarm_id in escalated_1

    # Second immediate check at now + 5 seconds: deadline is now + 600s, must NOT escalate again
    escalated_2 = AlarmEscalationManager.check_and_escalate_pending_alarms(current_time=now + timedelta(seconds=5))
    assert alarm_id not in escalated_2


def test_max_tier_capping_at_tier_3():
    """
    Verifies that alarms cannot exceed Tier 3, and next_escalation_deadline is cleared.
    """
    now = datetime.now(timezone.utc)
    alarm_id = str(uuid.uuid4())

    with db_manager.get_session() as session:
        alarm = Alarm(
            id=alarm_id,
            title="Max Tier Capping Test",
            category=AlarmCategory.SECURITY.value,
            source_subsystem="ANALYTICS",
            severity=AlarmSeverity.CRITICAL.value,
            priority=AlarmPriority.P1_URGENT.value,
            status=AlarmStatus.NEW.value,
            first_detected_at=now - timedelta(hours=2),
            last_detected_at=now - timedelta(hours=2),
            escalation_level=2,
            next_escalation_deadline=now - timedelta(minutes=5),  # expired
        )
        session.add(alarm)
        session.flush()
        alarm_service._append_history_entry(
            session=session,
            alarm_id=alarm_id,
            previous_status=None,
            new_status=AlarmStatus.NEW.value,
            operator="SYSTEM",
            timestamp=now - timedelta(hours=2),
            action=AlarmAction.CREATED.value,
        )

    # Escalate to Tier 3
    escalated = AlarmEscalationManager.check_and_escalate_pending_alarms(current_time=now)
    assert alarm_id in escalated

    with db_manager.get_session() as session:
        alarm_tier3 = session.query(Alarm).filter(Alarm.id == alarm_id).first()
        assert alarm_tier3.escalation_level == 3
        # When tier 3 is reached, deadline is cleared (None)
        assert alarm_tier3.next_escalation_deadline is None

    # Another check even further in the future cannot escalate beyond Tier 3
    future_escalated = AlarmEscalationManager.check_and_escalate_pending_alarms(current_time=now + timedelta(hours=1))
    assert alarm_id not in future_escalated
