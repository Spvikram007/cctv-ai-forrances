"""
Integration and UI tests for PySide6 Alarm Management Command Center Widget (Phase 12 - F-046).
Runs headless using Qt offscreen plugin.
"""

import os
import sys
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from modules.alarm_management.alarm_workspace_widget import AlarmManagementWidget
from engines.alarm_engine.alarm_service import alarm_service
from engines.alarm_engine.normalizer import NormalizedAlarmEvent
from engines.alarm_engine.enums import AlarmSeverity, AlarmPriority, AlarmCategory


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    return app


def test_alarm_management_widget_lifecycle(qapp):
    # Ensure at least 1 alarm exists to populate table
    event = NormalizedAlarmEvent(
        event_id="ui_test_event_01",
        source_subsystem="ANALYTICS",
        event_type="INTRUSION",
        title="UI Perimeter Breach",
        description="Testing UI widget controls and detail view",
        category=AlarmCategory.SECURITY,
        severity=AlarmSeverity.HIGH,
        priority=AlarmPriority.P2_HIGH,
        camera_id="cam_ui_01",
    )
    alarm_id = alarm_service.process_normalized_event(event)

    widget = AlarmManagementWidget()
    assert widget is not None
    assert widget.tabs.count() == 5

    # Check metric cards
    assert widget.card_total is not None
    assert widget.card_critical is not None

    # Refresh data
    widget.refresh_data()
    assert widget.table_alarms.rowCount() >= 1

    # Select first row
    widget.table_alarms.selectRow(0)
    assert widget._selected_alarm_id is not None

    # Check Detail labels updated
    assert widget.lbl_det_title.text() != "None"

    # Test Add Note button
    widget.txt_new_note.setText("UI smoke test verification note")
    widget._on_add_note()
    assert widget.txt_new_note.text() == ""

    # Test playback seek signal emission
    seek_signals = []
    widget.request_playback_seek.connect(lambda cam, ts: seek_signals.append((cam, ts)))
    widget._on_seek_playback()
    assert len(seek_signals) == 1

    # Clean shutdown
    widget.close()
    widget.deleteLater()
    qapp.processEvents()

