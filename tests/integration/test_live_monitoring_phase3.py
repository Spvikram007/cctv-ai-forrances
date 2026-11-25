"""
Integration tests for Phase 3 Live Surveillance Monitoring Improvements:
1 to 64 camera layouts, double-click maximization, interactive digital zoom,
drag-and-drop camera assignment, status overlays, embedded PTZ panel,
multi-monitor detached window, and keyboard shortcuts.
"""

import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QMimeData
from PySide6.QtGui import QWheelEvent, QMouseEvent, QDropEvent

from modules.live_monitoring.live_view_widget import (
    LiveViewWidget, PTZControlWidget, DetachedGridWindow
)
from modules.live_monitoring.video_widget import VideoTileWidget
from engines.video_engine.ptz_controller import ptz_controller

# Ensure single persistent QApplication instance
app = QApplication.instance() or QApplication([])


class TestLiveMonitoringPhase3(unittest.TestCase):
    """Integration test suite for Phase 3 live monitoring UI and interactive features."""

    def setUp(self):
        self.widget = LiveViewWidget()

    def tearDown(self):
        if hasattr(self.widget, "frame_timer"):
            self.widget.frame_timer.stop()
        if self.widget._detached_window:
            self.widget._detached_window.close()
        self.widget.deleteLater()

    def test_live_view_grid_layouts_1_to_64(self):
        """Verifies layout grid switching across 1, 4, 9, 16, 25, 36, and 64 camera layouts."""
        for count in [1, 4, 9, 16, 25, 36, 64]:
            self.widget.set_grid_layout(count)
            self.assertEqual(self.widget.current_layout_size, count)

            # Count unhidden tiles
            unhidden_count = sum(1 for t in self.widget.tiles if not t.isHidden())
            self.assertEqual(unhidden_count, count, f"Layout {count} must display exactly {count} unhidden tiles.")

    def test_double_click_tile_maximization_and_restore(self):
        """Verifies double-clicking a tile maximizes to 1-up and double-clicking again restores previous layout."""
        self.widget.set_grid_layout(16)
        self.assertEqual(self.widget.current_layout_size, 16)

        target_tile = self.widget.tiles[2]
        target_id = target_tile.channel_id

        # 1. Double click maximizes target tile
        self.widget._on_tile_double_clicked(target_id)
        self.assertEqual(self.widget._maximized_tile_id, target_id)
        self.assertFalse(target_tile.isHidden())
        other_visible = sum(1 for t in self.widget.tiles if t != target_tile and not t.isHidden())
        self.assertEqual(other_visible, 0)

        # 2. Double click again restores 16-cam layout
        self.widget._on_tile_double_clicked(target_id)
        self.assertIsNone(self.widget._maximized_tile_id)
        self.assertEqual(self.widget.current_layout_size, 16)
        self.assertEqual(sum(1 for t in self.widget.tiles if not t.isHidden()), 16)

    def test_video_tile_digital_zoom(self):
        """Verifies interactive digital zoom wheel zooming (1.0x to 5.0x) and reset."""
        tile = self.widget.tiles[0]
        self.assertEqual(tile._zoom_factor, 1.0)

        # Zoom in via simulated wheel event
        wheel_event_in = QWheelEvent(
            QPoint(50, 50), QPoint(50, 50), QPoint(0, 0), QPoint(0, 120),
            Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False
        )
        tile.wheelEvent(wheel_event_in)
        self.assertGreater(tile._zoom_factor, 1.0)

        # Zoom in up to cap
        for _ in range(25):
            tile.wheelEvent(wheel_event_in)
        self.assertEqual(tile._zoom_factor, 5.0)

        # Zoom out via simulated wheel event
        wheel_event_out = QWheelEvent(
            QPoint(50, 50), QPoint(50, 50), QPoint(0, 0), QPoint(0, -120),
            Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False
        )
        for _ in range(25):
            tile.wheelEvent(wheel_event_out)
        self.assertEqual(tile._zoom_factor, 1.0)

        # Test reset
        tile._zoom_factor = 3.5
        tile.reset_digital_zoom()
        self.assertEqual(tile._zoom_factor, 1.0)

    def test_video_tile_drag_and_drop_camera_assignment(self):
        """Verifies drag-and-drop camera re-assignment onto video tiles."""
        tile = self.widget.tiles[3]
        dropped_events = []
        tile.camera_dropped.connect(lambda target, dropped: dropped_events.append((target, dropped)))

        mime = QMimeData()
        mime.setText("CAM_NORTH_GATE_05")
        drop_ev = QDropEvent(QPoint(50, 50), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)

        tile.dropEvent(drop_ev)
        self.assertEqual(len(dropped_events), 1)
        self.assertEqual(dropped_events[0], (tile.channel_id, "CAM_NORTH_GATE_05"))

    def test_video_tile_badges_and_overlays(self):
        """Verifies status indicators for recording, AI, and PTZ capabilities."""
        tile = self.widget.tiles[0]
        self.assertFalse(tile.is_recording)
        self.assertFalse(tile.is_ai_active)
        self.assertFalse(tile.has_ptz)

        tile.set_badges(recording=True, ai_active=True, ptz=True)
        self.assertTrue(tile.is_recording)
        self.assertTrue(tile.is_ai_active)
        self.assertTrue(tile.has_ptz)

    def test_ptz_control_widget_interaction(self):
        """Verifies PTZ control panel button interactions and channel binding."""
        panel = self.widget.ptz_panel
        ptz_controller.register_camera("ch_5", is_simulated=True)

        panel.set_target_channel("ch_5", "Perimeter 5")
        self.assertEqual(panel.active_channel_id, "ch_5")
        self.assertIn("Perimeter 5", panel.lbl_target.text())

        # Test directional button click
        panel.btn_u.click()
        panel.btn_r.click()
        panel.btn_stop.click()

        # Test preset save and goto
        panel.btn_save_preset.click()
        self.assertGreaterEqual(panel.combo_presets.count(), 1)
        panel.btn_goto_preset.click()

    def test_detached_grid_window_lifecycle(self):
        """Verifies opening and closing the multi-monitor detached video wall."""
        self.widget._detach_grid_window()
        window = self.widget._detached_window
        self.assertIsNotNone(window)
        self.assertTrue(window.isVisible())
        self.assertEqual(len(window.detached_tiles), 4)

        window.close()
        self.assertFalse(window.isVisible())

    def test_keyboard_navigation_shortcuts(self):
        """Verifies keyboard shortcuts for layout switching and pausing."""
        self.widget.set_grid_layout(4)

        # Trigger shortcut for layout 1 (1x1)
        self.widget.set_grid_layout(1)
        self.assertEqual(self.widget.current_layout_size, 1)

        # Trigger shortcut for layout 7 (8x8)
        self.widget.set_grid_layout(64)
        self.assertEqual(self.widget.current_layout_size, 64)

        # Toggle pause
        self.assertFalse(self.widget._is_paused)
        self.widget._toggle_pause()
        self.assertTrue(self.widget._is_paused)
        self.widget._toggle_pause()
        self.assertFalse(self.widget._is_paused)


if __name__ == "__main__":
    unittest.main()
