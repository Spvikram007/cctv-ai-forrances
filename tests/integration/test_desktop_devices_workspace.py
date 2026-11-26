"""
Integration and UI Tests for PySide6 Desktop Device Management Workspace (View 7).
Verifies:
  1. Devices workspace is mounted at View 7.
  2. Existing database camera records are displayed in the inventory table.
  3. Dynamic inventory auto-refreshes when a camera is registered.
  4. Manual refresh preserves camera list.
  5. Search text and status dropdown filters operate correctly.
  6. Passwords in RTSP URLs are masked.
  7. Live View (View 1) continues to operate cleanly.
"""

import os
import sys
import uuid
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QLabel
from app.main import MainWindow
from app.bootstrap import bootstrap_application
from modules.camera_management.devices_widget import DeviceManagementWidget
from database.database_manager import db_manager
from database.models.devices import Device, DeviceChannel, StreamProfile


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    return app


def test_desktop_devices_workspace_lifecycle(qapp):
    bootstrap_application()

    window = MainWindow()
    assert window is not None

    # 1. Open Devices workspace (View index 7)
    window._switch_view(7)
    assert window.stack.currentIndex() == 7
    devices_widget = window.devices_widget
    assert isinstance(devices_widget, DeviceManagementWidget)

    # 2. Verify existing database records are displayed
    devices_widget.refresh_devices()
    initial_row_count = devices_widget.table.rowCount()
    assert initial_row_count >= 5  # At least the 5 pre-existing cameras

    # Verify KPI card reflects total count
    lbl_total = devices_widget.card_total.findChild(QLabel, "val")
    assert lbl_total is not None
    assert int(lbl_total.text()) == initial_row_count

    # 3. Add a new camera directly to database and emit registered signal
    unique_suffix = uuid.uuid4().hex[:6]
    cam_name = f"Unique PTZ {unique_suffix}"
    new_ip = f"192.168.130.{uuid.uuid4().int % 200 + 10}"
    with db_manager.get_session() as session:
        new_dev = Device(
            name=cam_name,
            device_type="CAMERA",
            manufacturer="HIKVISION",
            ip_address=new_ip,
            port=80,
            rtsp_port=554,
            is_online=True,
            is_deleted=False
        )
        session.add(new_dev)
        session.flush()
        ch = DeviceChannel(device_id=new_dev.id, channel_number=1, name="PTZ Ch 1")
        session.add(ch)
        session.flush()
        prof = StreamProfile(
            channel_id=ch.id,
            profile_type="MAIN",
            rtsp_url=f"rtsp://admin:secret123@{new_ip}:554/live"
        )
        session.add(prof)
        dev_id = new_dev.id

    # 4. Trigger slot (simulates discovery_dialog.camera_registered)
    devices_widget._on_camera_registered(dev_id)
    new_row_count = devices_widget.table.rowCount()
    assert new_row_count == initial_row_count + 1

    # 5. Refresh the list and confirm it remains visible
    devices_widget.refresh_devices()
    assert devices_widget.table.rowCount() == new_row_count

    # 6. Verify RTSP password masking in table
    found_masked = False
    for r in range(devices_widget.table.rowCount()):
        item_url = devices_widget.table.item(r, 6)
        item_name = devices_widget.table.item(r, 1)
        assert item_url is not None
        assert item_name is not None
        assert "secret123" not in item_url.text()
        if item_name.text() == cam_name:
            assert f"rtsp://***:***@{new_ip}:554/live" == item_url.text()
            found_masked = True
    assert found_masked is True

    # 7. Verify search filter
    devices_widget.txt_search.setText(cam_name)
    assert devices_widget.table.rowCount() == 1
    item_res = devices_widget.table.item(0, 1)
    assert item_res is not None
    assert item_res.text() == cam_name

    # Clear search
    devices_widget.txt_search.setText("")
    assert devices_widget.table.rowCount() == new_row_count

    # Verify status filter
    devices_widget.combo_status.setCurrentIndex(1)  # Online Only
    online_count = devices_widget.table.rowCount()
    devices_widget.combo_status.setCurrentIndex(0)  # All
    assert devices_widget.table.rowCount() == new_row_count

    # 8. Confirm desktop Live View continues to work
    window._switch_view(1)
    assert window.stack.currentIndex() == 1
    assert window.live_view_widget is not None
    # Toggle test streams
    window.live_view_widget._toggle_test_streams()
    window.live_view_widget._toggle_test_streams()

    # Clean shutdown
    window.close()
    window.deleteLater()
    qapp.processEvents()
