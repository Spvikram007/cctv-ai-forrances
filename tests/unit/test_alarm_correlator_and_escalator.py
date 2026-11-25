"""
Unit tests for Alarm Correlator and Escalation Manager (Phase 12 - F-046).
"""

from datetime import datetime, timezone, timedelta
import pytest

from engines.alarm_engine.correlator import AlarmCorrelator
from engines.alarm_engine.escalator import AlarmEscalationManager
from engines.alarm_engine.normalizer import NormalizedAlarmEvent
from engines.alarm_engine.enums import (
    AlarmSeverity,
    AlarmPriority,
    AlarmCategory,
    AlarmStatus,
)
from database.database_manager import db_manager
from database.models.alarms import Alarm, AlarmHistory


def test_alarm_correlator_network_and_recovery():
    correlator = AlarmCorrelator(correlation_window_sec=60.0)

    # Register parent gateway outage
    correlator.register_parent_incident("NETWORK:GATEWAY:192.168.1.1", "parent_net_alarm_01")

    # Camera disconnect arrives
    cam_event = NormalizedAlarmEvent(
        event_id="evt_cam_disc",
        source_subsystem="STREAM",
        event_type="STREAM_DISCONNECTED",
        title="Camera Disconnect",
        description="Stream lost",
        category=AlarmCategory.HARDWARE,
        severity=AlarmSeverity.HIGH,
        priority=AlarmPriority.P2_HIGH,
        camera_id="cam_01",
    )
    correlated_id = correlator.find_correlation(cam_event)
    assert correlated_id == "parent_net_alarm_01"

    # Register camera offline for recovery pairing
    correlator.register_camera_offline("cam_02", "alarm_cam_02_offline")

    recov_event = NormalizedAlarmEvent(
        event_id="evt_recov",
        source_subsystem="STREAM",
        event_type="STREAM_RECOVERED",
        title="Camera Recovered",
        description="Stream restored",
        category=AlarmCategory.OPERATIONAL,
        severity=AlarmSeverity.INFORMATIONAL,
        priority=AlarmPriority.P4_LOW,
        camera_id="cam_02",
    )
    paired_alarm = correlator.find_correlation(recov_event)
    assert paired_alarm == "alarm_cam_02_offline"


def test_alarm_escalation_manager_deadline_and_advancement():
    now = datetime.now(timezone.utc)
    # Deadline 300 seconds from now
    deadline = AlarmEscalationManager.calculate_deadline(now, 300)
    assert (deadline - now).total_seconds() == 300

    # Create an overdue alarm in DB
    past_time = now - timedelta(seconds=600)
    with db_manager.get_session() as session:
        alarm = Alarm(
            title="SLA Breach Test Alarm",
            category=AlarmCategory.SECURITY.value,
            source_subsystem="ANALYTICS",
            severity=AlarmSeverity.HIGH.value,
            priority=AlarmPriority.P1_URGENT.value,
            status=AlarmStatus.NEW.value,
            first_detected_at=past_time,
            last_detected_at=past_time,
            escalation_level=0,
            next_escalation_deadline=past_time + timedelta(seconds=120),  # expired 480s ago
        )
        session.add(alarm)
        session.flush()
        alarm_id = alarm.id

    # Run escalation watchdog check
    escalated = AlarmEscalationManager.check_and_escalate_pending_alarms(current_time=now)
    assert alarm_id in escalated

    # Verify escalated state in DB
    with db_manager.get_session() as session:
        esc_alarm = session.query(Alarm).filter(Alarm.id == alarm_id).first()
        assert esc_alarm.escalation_level == 1
        assert esc_alarm.escalated_at is not None

        # Check history audit entry
        hist = (
            session.query(AlarmHistory)
            .filter(AlarmHistory.alarm_id == alarm_id, AlarmHistory.action == "ESCALATED")
            .first()
        )
        assert hist is not None
        assert "Escalated to Tier 1" in hist.reason
