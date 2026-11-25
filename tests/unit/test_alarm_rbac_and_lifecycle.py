"""
Unit tests for Alarm Service Lifecycle Transitions and RBAC Enforcement (Phase 12 - F-046).
"""

import pytest
from datetime import datetime, timezone

from engines.alarm_engine.alarm_service import alarm_service
from engines.alarm_engine.normalizer import NormalizedAlarmEvent
from engines.alarm_engine.enums import (
    AlarmSeverity,
    AlarmPriority,
    AlarmCategory,
    AlarmStatus,
    AlarmAction,
)
from database.database_manager import db_manager
from database.models.alarms import Alarm, AlarmHistory


@pytest.fixture
def sample_alarm_id():
    """Helper fixture to create a clean test alarm."""
    event = NormalizedAlarmEvent(
        event_id="test_rbac_evt",
        source_subsystem="ANALYTICS",
        event_type="INTRUSION",
        title="RBAC Intrusion Test",
        description="Testing state transitions and role enforcement",
        category=AlarmCategory.SECURITY,
        severity=AlarmSeverity.HIGH,
        priority=AlarmPriority.P2_HIGH,
        camera_id="cam_test_rbac",
    )
    return alarm_service.process_normalized_event(event)


def test_rbac_viewer_restricted(sample_alarm_id):
    """Verifies that VIEWER role cannot perform state modifications."""
    # Viewer cannot acknowledge
    with pytest.raises(PermissionError, match="Role 'VIEWER' lacks permission 'ACKNOWLEDGE'"):
        alarm_service.acknowledge_alarm(sample_alarm_id, operator="Viewer_Bob", role="VIEWER")

    # Viewer cannot resolve
    with pytest.raises(PermissionError, match="Role 'VIEWER' lacks permission 'RESOLVE'"):
        alarm_service.resolve_alarm(sample_alarm_id, operator="Viewer_Bob", role="VIEWER")

    # Viewer cannot add note
    with pytest.raises(PermissionError, match="Role 'VIEWER' lacks permission 'ADD_NOTE'"):
        alarm_service.add_operator_note(sample_alarm_id, operator="Viewer_Bob", note_text="Test Note", role="VIEWER")


def test_rbac_operator_permissions_and_limits(sample_alarm_id):
    """Verifies OPERATOR can acknowledge and resolve, but cannot close without supervisor role."""
    # Operator acknowledges
    res_ack = alarm_service.acknowledge_alarm(sample_alarm_id, operator="Op_Alice", role="OPERATOR", comments="Confirmed intrusion")
    assert res_ack is True

    alarm_data = alarm_service.get_alarm_by_id(sample_alarm_id)
    assert alarm_data["status"] == AlarmStatus.ACKNOWLEDGED.value
    assert alarm_data["acknowledged_by"] == "Op_Alice"

    # Operator starts investigation
    res_inv = alarm_service.start_investigation(sample_alarm_id, operator="Op_Alice", role="OPERATOR")
    assert res_inv is True
    alarm_data = alarm_service.get_alarm_by_id(sample_alarm_id)
    assert alarm_data["status"] == AlarmStatus.IN_PROGRESS.value

    # Operator resolves
    res_res = alarm_service.resolve_alarm(sample_alarm_id, operator="Op_Alice", role="OPERATOR", reason="False trigger (wildlife)")
    assert res_res is True
    alarm_data = alarm_service.get_alarm_by_id(sample_alarm_id)
    assert alarm_data["status"] == AlarmStatus.RESOLVED.value

    # Operator attempts to permanently close -> raises PermissionError (Supervisor/Admin only)
    with pytest.raises(PermissionError, match="Role 'OPERATOR' lacks permission 'CLOSE'"):
        alarm_service.close_alarm(sample_alarm_id, operator="Op_Alice", role="OPERATOR")


def test_supervisor_close_and_reopen(sample_alarm_id):
    """Verifies SUPERVISOR can close and reopen alarms."""
    # Acknowledge first
    alarm_service.acknowledge_alarm(sample_alarm_id, operator="Sup_Carol", role="SUPERVISOR")
    alarm_service.resolve_alarm(sample_alarm_id, operator="Sup_Carol", role="SUPERVISOR")

    # Supervisor closes
    res_close = alarm_service.close_alarm(sample_alarm_id, operator="Sup_Carol", role="SUPERVISOR", comments="Reviewed and confirmed closed.")
    assert res_close is True
    alarm_data = alarm_service.get_alarm_by_id(sample_alarm_id)
    assert alarm_data["status"] == AlarmStatus.CLOSED.value

    # Supervisor reopens
    res_reopen = alarm_service.reopen_alarm(sample_alarm_id, operator="Sup_Carol", role="SUPERVISOR", reason="New evidence discovered")
    assert res_reopen is True
    alarm_data = alarm_service.get_alarm_by_id(sample_alarm_id)
    assert alarm_data["status"] == AlarmStatus.REOPENED.value


def test_investigator_evidence_and_notes(sample_alarm_id):
    """Verifies INVESTIGATOR can add notes and investigate."""
    res_note = alarm_service.add_operator_note(sample_alarm_id, operator="Inv_Dave", note_text="Reviewing bounding box coordinates at frame 450", role="INVESTIGATOR")
    assert res_note is True

    history = alarm_service.get_alarm_history(sample_alarm_id)
    note_entries = [h for h in history if h["action"] == AlarmAction.NOTE_ADDED.value]
    assert len(note_entries) >= 1
    assert "frame 450" in note_entries[-1]["comments"]


def test_admin_full_override(sample_alarm_id):
    """Verifies ADMIN has complete override authority."""
    res_esc = alarm_service.escalate_manually(sample_alarm_id, operator="Admin_Root", role="ADMIN", reason="Executive directive")
    assert res_esc is True
    alarm_data = alarm_service.get_alarm_by_id(sample_alarm_id)
    assert alarm_data["escalation_level"] >= 1

