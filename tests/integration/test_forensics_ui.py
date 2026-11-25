"""
Integration Tests for Video Forensics Workspace UI (Phase 10 - F-018 & F-023).
"""

import sys
import os
import tempfile
import pytest
import numpy as np
import cv2

from PySide6.QtWidgets import QApplication

from modules.video_forensics.forensics_workspace_widget import VideoForensicsWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def create_dummy_video(path: str) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, 25.0, (160, 120))
    for i in range(12):
        frame = np.full((120, 160, 3), 40 + i * 2, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_forensics_ui_initialization_and_table_population(qapp) -> None:
    """Verifies VideoForensicsWidget initializes tabs, headers, and loads evidence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        widget = VideoForensicsWidget()
        widget.resize(1024, 768)

        # Ingest one dummy item directly into the widget's locker
        vid_p = os.path.join(tmpdir, "ui_test_raw.mp4")
        create_dummy_video(vid_p)

        manifest = widget.locker.ingest_recording(
            source_file_path=vid_p,
            case_number="CASE-UI-001",
            channel_id="CAM-01",
            operator_username="investigator_ui",
            operator_role="INVESTIGATOR",
        )

        widget._refresh_evidence_list()

        assert widget.tbl_evidence.rowCount() >= 1

        # Select row 0
        widget.tbl_evidence.selectRow(0)
        widget._on_evidence_selected()

        assert widget._active_manifest is not None
        assert widget.lbl_sha256.text() == manifest.file_sha256
        assert "ORIGINAL" in widget.lbl_source_link.text()
        assert widget.tbl_custody.rowCount() >= 1


def test_forensics_ui_tabs_and_chain_verification(qapp) -> None:
    """Verifies detail tabs and custody chain verification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        widget = VideoForensicsWidget()
        vid_p = os.path.join(tmpdir, "ui_test_2.mp4")
        create_dummy_video(vid_p)

        manifest = widget.locker.ingest_recording(
            source_file_path=vid_p,
            case_number="CASE-UI-002",
            channel_id="CAM-02",
            operator_username="investigator_ui",
            operator_role="INVESTIGATOR",
        )
        widget._refresh_evidence_list()
        widget.tbl_evidence.selectRow(0)
        widget._on_evidence_selected()

        # Check tabs exist
        assert widget.tabs.count() == 4
        assert "Integrity" in widget.tabs.tabText(0)
        assert "Custody" in widget.tabs.tabText(1)
        assert "Signature" in widget.tabs.tabText(2)
        assert "Legal" in widget.tabs.tabText(3)

        # Check chain status label updated
        assert "VERIFIED" in widget.lbl_chain_status.text()
