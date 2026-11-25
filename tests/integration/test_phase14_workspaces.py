"""
Integration Tests for Phase 14 PySide6 Workspaces (Modules A, B, C, D).
Tests UserManagementWidget (View 13), ReportingWorkspaceWidget (View 11),
and MainWindow integration using Qt offscreen platform plugin.
"""

import os
import sys
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from app.bootstrap import bootstrap_application
from app.main import MainWindow
from modules.user_management.user_management_widget import UserManagementWidget
from modules.reporting.reporting_widget import ReportingWorkspaceWidget


@pytest.fixture(scope="session")
def qapp():
    """Provides a single persistent QApplication instance."""
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    return app


def test_user_management_widget_smoke(qapp):
    """Verifies that UserManagementWidget initializes, populates users & roles, and switches tabs."""
    widget = UserManagementWidget()
    assert widget is not None
    assert widget.tabs.count() == 3

    # Verify users table populated (admin should be present)
    assert widget.table_users.rowCount() >= 1

    # Verify roles table populated (at least 10 roles)
    assert widget.table_roles.rowCount() >= 10

    # Switch to Roles tab
    widget.tabs.setCurrentIndex(1)
    assert widget.tabs.currentIndex() == 1

    # Select first role and verify permissions tree
    widget.table_roles.selectRow(0)
    assert widget.tree_permissions.topLevelItemCount() > 0

    # Switch to Sessions tab
    widget.tabs.setCurrentIndex(2)
    assert widget.tabs.currentIndex() == 2

    # Clean teardown
    widget.close()
    widget.deleteLater()
    qapp.processEvents()


def test_reporting_workspace_widget_smoke(qapp):
    """Verifies that ReportingWorkspaceWidget initializes, loads audit logs, and runs integrity checks."""
    widget = ReportingWorkspaceWidget()
    assert widget is not None
    assert widget.tabs.count() == 3

    # Verify audit table has entries
    assert widget.table_audit.rowCount() >= 1

    # Switch to Report Generator tab
    widget.tabs.setCurrentIndex(1)
    assert widget.tabs.currentIndex() == 1
    assert widget.combo_report_type.count() >= 3

    # Switch to Cryptographic Ledger Verification tab
    widget.tabs.setCurrentIndex(2)
    assert widget.tabs.currentIndex() == 2

    # Run verification button without blocking modal
    widget._verify_ledger_integrity(show_dialog=False)
    assert "VERIFICATION SUCCESS" in widget.txt_integrity_log.toPlainText() or "verified" in widget.txt_integrity_log.toPlainText().lower()

    # Clean teardown
    widget.close()
    widget.deleteLater()
    qapp.processEvents()


def test_main_window_phase14_integration(qapp):
    """Verifies that MainWindow mounts ReportingWorkspaceWidget at View 11 and UserManagementWidget at View 13."""
    window = MainWindow()
    assert window is not None

    # View 11: Reports
    view11 = window.stack.widget(11)
    assert isinstance(view11, ReportingWorkspaceWidget)

    # View 13: Administration / User Management
    view13 = window.stack.widget(13)
    assert isinstance(view13, UserManagementWidget)

    # Switch to View 11
    window._switch_view(11)
    assert window.stack.currentIndex() == 11
    assert window._nav_buttons[11].isChecked() is True

    # Switch to View 13
    window._switch_view(13)
    assert window.stack.currentIndex() == 13
    assert window._nav_buttons[13].isChecked() is True

    # Clean teardown
    window.close()
    window.deleteLater()
    qapp.processEvents()
