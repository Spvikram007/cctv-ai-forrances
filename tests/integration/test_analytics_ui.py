"""
Headless Qt Tests for Analytics UI Components.
Tests InteractiveAnalyticsCanvas drawing, mode switching, and AnalyticsRulesWidget.
"""

import sys
import numpy as np
import pytest

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from modules.ai_intelligence.analytics_rules_widget import (
    InteractiveAnalyticsCanvas,
    AnalyticsRulesWidget,
)
from engines.analytics_engine.rule_evaluator import ZoneConfig, TripwireConfig


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_interactive_canvas_modes_and_entities(qapp):
    canvas = InteractiveAnalyticsCanvas()
    canvas.resize(640, 360)

    # 1. Test setting entities
    z = ZoneConfig(id="z1", name="Zone 1", polygon=[(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)])
    tw = TripwireConfig(id="tw1", name="Line 1", pt1=(0.1, 0.5), pt2=(0.9, 0.5))
    canvas.set_entities([z], [tw])
    assert len(canvas._zones) == 1
    assert len(canvas._tripwires) == 1

    # 2. Test setting background frame
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    canvas.set_background_frame(frame)
    assert canvas._background_image is not None

    # 3. Test mode switching
    canvas.set_mode("DRAW_ZONE")
    assert canvas.mode == "DRAW_ZONE"
    assert len(canvas._current_points) == 0

    canvas.set_mode("VIEW")
    assert canvas.mode == "VIEW"


def test_analytics_rules_widget_interaction(qapp):
    widget = AnalyticsRulesWidget()
    widget.resize(1000, 600)

    # Camera selector
    assert widget.combo_camera.count() >= 1
    widget.combo_camera.setCurrentText("CAM_01")
    assert widget.selected_channel_id == "CAM_01"

    # Fill rule form
    widget.edit_rule_name.setText("Test Perimeter Intrusion")
    widget.combo_rule_type.setCurrentText("INTRUSION")
    widget.chk_person.setChecked(True)
    widget.spin_confidence.setValue(0.65)
    widget.spin_dwell.setValue(10.0)

    # Save rule
    widget._save_rule()

    # Rule table should now show the rule
    assert widget.tbl_rules.rowCount() >= 1

    # Reset counters
    widget._reset_counters()
    assert "0" in widget.lbl_occ.text()
