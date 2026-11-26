"""
Integration tests for Storage Workspace and MainWindow Shutdown Lifecycle.
Verifies:
  1. StorageManagementWidget graceful worker thread termination on stop().
  2. Immediate window close while background storage telemetry is actively probing disks.
  3. No access violation (0xC0000005) or orphaned thread during application shutdown.
"""

import os
import sys
import time
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from app.main import MainWindow
from app.bootstrap import bootstrap_application
from modules.storage_management.storage_workspace_widget import StorageManagementWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    return app


def test_storage_widget_standalone_shutdown(qapp):
    """Verifies StorageManagementWidget worker thread stops cleanly via stop()."""
    bootstrap_application()

    widget = StorageManagementWidget()
    assert widget is not None

    # Verify that background worker thread was registered
    assert hasattr(widget, "_workers")
    assert hasattr(widget, "_shutdown_event")

    # Stop the widget explicitly
    t0 = time.time()
    clean = widget.stop(timeout=2.0)
    elapsed = time.time() - t0

    # Must complete promptly without blocking indefinitely
    assert elapsed < 2.5
    assert clean is True
    assert widget._shutdown_event.is_set() is True

    # No worker threads remain alive, and list pruned
    assert len(widget._workers) == 0

    widget.close()
    widget.deleteLater()
    qapp.processEvents()


def test_mainwindow_close_during_storage_discovery(qapp):
    """Verifies MainWindow.closeEvent() cleanly terminates storage discovery and all workers."""
    bootstrap_application()

    window = MainWindow()
    assert window is not None

    # Switch to Storage Workspace (View 10) to ensure active engagement
    window._switch_view(10)
    assert window.stack.currentIndex() == 10
    assert hasattr(window, "storage_widget")

    # Immediately close the window while storage discovery might be in flight
    t0 = time.time()
    window.close()
    elapsed = time.time() - t0

    # Must not hang or exceed 3.0s
    assert elapsed < 3.0

    # Confirm storage widget stopped
    assert window.storage_widget._shutdown_event.is_set() is True
    alive_storage_workers = [t for t in window.storage_widget._workers if t.is_alive()]
    assert len(alive_storage_workers) == 0

    window.deleteLater()
    qapp.processEvents()


def test_mainwindow_close_is_idempotent(qapp):
    """Verifies that duplicate closeEvent calls are cleanly ignored without error."""
    bootstrap_application()

    window = MainWindow()
    assert window is not None

    # First close
    window.close()
    assert bool(window._is_shutting_down)

    # Second close (must be completely safe and idempotent)
    window.close()
    assert bool(window._is_shutting_down)

    window.deleteLater()
    qapp.processEvents()
