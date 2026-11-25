"""
Unit tests for Alarm Database Models and Schema (Phase 12 - F-046).
"""

import uuid
from datetime import datetime, timezone
import pytest

from database.database_manager import db_manager
from database.models.alarms import (
    Alarm,
    AlarmEvent,
    AlarmHistory,
    AlarmPolicy,
    AlarmAssignment,
    AlarmNotification,
)
from engines.alarm_engine.enums import (
    AlarmSeverity,
    AlarmPriority,
    AlarmStatus,
    AlarmCategory,
    AlarmAction,
)


def test_alarm_model_crud(tmp_path):
    """Verifies Alarm entity creation, querying, updating, and soft-delete."""
    with db_manager.get_session() as session:
        now = datetime.now(timezone.utc)
        alarm = Alarm(
            event_id="evt_test_01",
            title="Test Perimeter Intrusion",
            description="Unauthorized person in sector 4",
            category=AlarmCategory.SECURITY.value,
            source_subsystem="ANALYTICS",
            severity=AlarmSeverity.HIGH.value,
            priority=AlarmPriority.P2_HIGH.value,
            status=AlarmStatus.NEW.value,
            camera_id="cam_01",
            site_id="site_hq",
            first_detected_at=now,
            last_detected_at=now,
            occurrence_count=1,
            dedup_key="ANALYTICS:INTRUSION:cam_01",
        )
        session.add(alarm)
        session.flush()
        alarm_id = alarm.id
        assert alarm_id is not None

        # Query back
        queried = session.query(Alarm).filter(Alarm.id == alarm_id).first()
        assert queried is not None
        assert queried.title == "Test Perimeter Intrusion"
        assert queried.severity == AlarmSeverity.HIGH.value
        assert queried.occurrence_count == 1
        assert queried.is_deleted is False

        # Update status
        queried.status = AlarmStatus.ACKNOWLEDGED.value
        queried.acknowledged_by = "Officer_Smith"
        queried.acknowledged_at = datetime.now(timezone.utc)
        session.flush()

        updated = session.query(Alarm).filter(Alarm.id == alarm_id).first()
        assert updated.status == AlarmStatus.ACKNOWLEDGED.value
        assert updated.acknowledged_by == "Officer_Smith"

        # Soft delete
        updated.is_deleted = True
        session.flush()
        assert session.query(Alarm).filter(Alarm.id == alarm_id, Alarm.is_deleted == False).first() is None


def test_alarm_event_provenance_link():
    """Verifies AlarmEvent atomic provenance linkage to Alarm."""
    with db_manager.get_session() as session:
        alarm = Alarm(
            title="ANPR Watchlist Vehicle",
            category=AlarmCategory.SECURITY.value,
            source_subsystem="ANPR",
            severity=AlarmSeverity.HIGH.value,
            priority=AlarmPriority.P1_URGENT.value,
            status=AlarmStatus.NEW.value,
        )
        session.add(alarm)
        session.flush()

        raw_event = AlarmEvent(
            alarm_id=alarm.id,
            source_event_id="anpr_evt_999",
            source_subsystem="ANPR",
            event_type="WATCHLIST_ALERT",
            camera_id="cam_gate_01",
            confidence=0.98,
            processing_status="PROCESSED",
        )
        session.add(raw_event)
        session.flush()

        events = session.query(AlarmEvent).filter(AlarmEvent.alarm_id == alarm.id).all()
        assert len(events) == 1
        assert events[0].source_event_id == "anpr_evt_999"
        assert events[0].confidence == 0.98


def test_alarm_history_audit_trail():
    """Verifies chronological lifecycle audit entries."""
    with db_manager.get_session() as session:
        alarm = Alarm(
            title="Camera Stream Disconnect",
            category=AlarmCategory.HARDWARE.value,
            source_subsystem="STREAM",
            severity=AlarmSeverity.HIGH.value,
            priority=AlarmPriority.P2_HIGH.value,
            status=AlarmStatus.NEW.value,
        )
        session.add(alarm)
        session.flush()

        # History entry
        h1 = AlarmHistory(
            alarm_id=alarm.id,
            previous_status=None,
            new_status=AlarmStatus.NEW.value,
            operator="SYSTEM",
            action=AlarmAction.CREATED.value,
            reason="Stream heartbeat failure",
        )
        h2 = AlarmHistory(
            alarm_id=alarm.id,
            previous_status=AlarmStatus.NEW.value,
            new_status=AlarmStatus.ACKNOWLEDGED.value,
            operator="Operator_Jane",
            action=AlarmAction.ACKNOWLEDGED.value,
            reason="Manual confirmation",
        )
        session.add_all([h1, h2])
        session.flush()

        hist_records = (
            session.query(AlarmHistory)
            .filter(AlarmHistory.alarm_id == alarm.id)
            .order_by(AlarmHistory.timestamp.asc())
            .all()
        )
        assert len(hist_records) == 2
        assert hist_records[0].action == AlarmAction.CREATED.value
        assert hist_records[1].action == AlarmAction.ACKNOWLEDGED.value
        assert hist_records[1].operator == "Operator_Jane"
