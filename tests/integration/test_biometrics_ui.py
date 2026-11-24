"""
Headless Qt Tests for Phase 7 Biometrics and ANPR UI Workspaces:
- ANPRWorkspaceWidget (Live feed, search filters, plate inspector, CSV export)
- FaceWorkspaceWidget (Candidate matches & review, enrollment, catalog, audit trail)
"""

import sys
import os
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from modules.anpr_intelligence.anpr_workspace_widget import ANPRWorkspaceWidget
from modules.face_intelligence.face_workspace_widget import FaceWorkspaceWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class TestANPRWorkspaceWidget:
    def test_anpr_widget_init_and_search_trigger(self, qapp):
        widget = ANPRWorkspaceWidget()
        assert widget is not None
        assert widget.edit_plate_search is not None
        assert widget.tbl_detections is not None

        # Set plate search query
        widget.edit_plate_search.setText("MH12*")
        widget._execute_search()

        # Check table headers
        headers = [
            widget.tbl_detections.horizontalHeaderItem(i).text()
            for i in range(widget.tbl_detections.columnCount())
        ]
        assert "Plate Text" in headers
        assert "Camera" in headers
        assert "Confidence" in headers

        # Test populating result
        mock_result = {
            "id": "rec_ui_1",
            "channel_id": "cam_01",
            "plate_text": "MH12AB1234",
            "vehicle_class": "car",
            "confidence": 0.92,
            "plate_format": "INDIA",
            "timestamp": "2026-11-24 12:00:00",
            "requires_manual_review": False,
            "plate_crop_path": None,
            "vehicle_snapshot_path": None,
        }
        widget._populate_table([mock_result])
        assert widget.tbl_detections.rowCount() == 1
        assert widget.tbl_detections.item(0, 3).text() == "MH12AB1234"

        # Select row -> updates details panel
        widget.tbl_detections.selectRow(0)
        widget._on_row_selected()
        assert "MH12AB1234" in widget.lbl_details.text()


class TestFaceWorkspaceWidget:
    def test_face_widget_init_and_tabs(self, qapp):
        widget = FaceWorkspaceWidget()
        assert widget is not None
        assert widget.tabs.count() == 4

        tab_titles = [widget.tabs.tabText(i) for i in range(widget.tabs.count())]
        assert any("Candidate Matches" in t for t in tab_titles)
        assert any("Authorized Enrollment" in t for t in tab_titles)
        assert any("Identity Catalog" in t for t in tab_titles)
        assert any("Audit Trail" in t for t in tab_titles)

        # Tab 1: Enrollment controls
        assert widget.edit_enroll_name is not None
        assert widget.btn_submit_enroll is not None
        assert widget.lbl_quality_metrics is not None

        # Tab 0: Candidate review table
        assert widget.tbl_matches is not None
        widget._load_candidate_matches()

        # Tab 2: Catalog table
        assert hasattr(widget, "tbl_identities")
        widget._load_identities()

        # Tab 3: Audit log table
        assert hasattr(widget, "tbl_audit")
        widget._load_audit_logs()
