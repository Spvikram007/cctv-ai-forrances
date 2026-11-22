"""
Integration tests for Phase 1 & Phase 2 UI Components.
Runs headless offscreen using PySide6.
"""

import os
import sys
import numpy as np
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from modules.live_monitoring.video_widget import VideoTileWidget
from modules.live_monitoring.live_view_widget import LiveViewWidget
from modules.camera_management.discovery_dialog import DeviceDiscoveryDialog
from app.bootstrap import bootstrap_application


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    return app


def test_video_tile_widget(qapp, tmp_path):
    tile = VideoTileWidget(channel_id="test_tile_1", channel_name="Test Tile 1")
    assert tile is not None
    assert tile.channel_id == "test_tile_1"

    # Push a test frame
    dummy_frame = np.zeros((360, 640, 3), dtype=np.uint8)
    dummy_frame[:] = (100, 150, 200)
    tile.update_frame(dummy_frame, 123456.78)

    assert tile._current_qimage is not None
    assert tile._current_qimage.width() == 640
    assert tile._current_qimage.height() == 360

    # Test snapshot capture
    snap_path = tile.capture_snapshot()
    assert snap_path is not None
    assert os.path.exists(snap_path)
    os.remove(snap_path)


def test_live_view_grid_switching(qapp):
    live_view = LiveViewWidget()
    live_view.show()
    assert live_view is not None
    assert len(live_view.tiles) == 16

    # Verify 1x1 (1 tile visible)
    live_view.set_grid_layout(1)
    visible_tiles = [t for t in live_view.tiles if not t.isHidden()]
    assert len(visible_tiles) == 1

    # Verify 2x2 (4 tiles visible)
    live_view.set_grid_layout(4)
    visible_tiles = [t for t in live_view.tiles if not t.isHidden()]
    assert len(visible_tiles) == 4

    # Verify 3x3 (9 tiles visible)
    live_view.set_grid_layout(9)
    visible_tiles = [t for t in live_view.tiles if not t.isHidden()]
    assert len(visible_tiles) == 9

    # Verify 4x4 (16 tiles visible)
    live_view.set_grid_layout(16)
    visible_tiles = [t for t in live_view.tiles if not t.isHidden()]
    assert len(visible_tiles) == 16

    # Test double-click maximization
    live_view._on_tile_double_clicked("ch_3")
    visible_tiles_max = [t for t in live_view.tiles if not t.isHidden()]
    assert len(visible_tiles_max) == 1
    assert visible_tiles_max[0].channel_id == "ch_3"

    # Double click again restores previous layout (16)
    live_view._on_tile_double_clicked("ch_3")
    visible_tiles_restored = [t for t in live_view.tiles if not t.isHidden()]
    assert len(visible_tiles_restored) == 16

    live_view.frame_timer.stop()
    live_view.close()


def test_discovery_dialog_initialization(qapp):
    dialog = DeviceDiscoveryDialog()
    assert dialog is not None
    assert dialog.windowTitle().startswith("Camera Discovery")
    assert dialog.table.columnCount() == 6
    dialog.close()
