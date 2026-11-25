"""
Integration and UI Smoke Tests for PySide6 Command Center.
Runs headless using Qt offscreen platform plugin.
"""

import os
import sys
import pytest

# Ensure headless Qt execution
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from app.main import MainWindow
from app.bootstrap import bootstrap_application


@pytest.fixture(scope="session")
def qapp():
    """Provides a single persistent QApplication instance."""
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    return app


def test_main_window_smoke(qapp, tmp_path):
    # Ensure bootstrap runs cleanly
    bootstrap_application()

    # Create Main Window
    window = MainWindow()
    assert window is not None
    assert window.windowTitle().startswith("CCTV AI Intelligence")

    # Verify 15 navigation views in stacked widget
    assert window.stack.count() == 15
    assert len(window._nav_buttons) == 15

    # Test switching views
    for idx in range(15):
        window._switch_view(idx)
        assert window.stack.currentIndex() == idx
        assert window._nav_buttons[idx].isChecked() is True

    # Switch back to dashboard (index 0)
    window._switch_view(0)
    assert window.stack.currentIndex() == 0

    # Test telemetry update
    window._update_telemetry()
    assert window.lbl_uptime.text().startswith("Uptime:")

    # Clean shutdown
    window.close()
    window.deleteLater()
    qapp.processEvents()
