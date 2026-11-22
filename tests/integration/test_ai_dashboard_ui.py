"""
Integration and UI tests for AI Intelligence Dashboard Widget
and Command Center MainWindow integration.
"""

import pytest
from PySide6.QtWidgets import QApplication

from modules.ai_intelligence.ai_dashboard_widget import (
    AIDashboardWidget,
    MetricCard,
)
from app.main import MainWindow


@pytest.fixture(scope="module")
def qapp():
    """Headless Qt Application fixture."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_metric_card_widget(qapp):
    """Verifies MetricCard label updates and color changes."""
    card = MetricCard("TEST METRIC", "Initial")
    assert card._title_label.text() == "TEST METRIC"
    assert card._value_label.text() == "Initial"

    card.set_value("42 FPS", "#3fb950")
    assert card._value_label.text() == "42 FPS"


def test_ai_dashboard_widget_rendering(qapp):
    """Verifies that AIDashboardWidget renders all tables, cards, and groups."""
    widget = AIDashboardWidget()
    assert widget.card_device is not None
    assert widget.card_active_channels is not None
    assert widget.card_total_detections is not None
    assert widget.channel_table.columnCount() == 5
    assert widget.class_table.columnCount() == 2
    assert widget.events_table.columnCount() == 6

    # Refresh data without errors
    widget.refresh_data()


def test_main_window_has_ai_workspace(qapp, test_db_manager):
    """Verifies that MainWindow hosts AIDashboardWidget at stacked index 3."""
    window = MainWindow()
    # View 0: Dashboard, 1: Live View, 2: Playback, 3: AI Intelligence
    ai_widget = window.stack.widget(3)
    assert isinstance(ai_widget, AIDashboardWidget)
    assert window.NAV_ITEMS[3][0] == "AI Intelligence"

    window.close()
