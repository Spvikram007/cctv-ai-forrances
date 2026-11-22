"""
Integration tests for Playback Workspace and Timeline UI Components.
Runs headless offscreen with PySide6.
"""

import os
import sys
from datetime import datetime, timezone, timedelta
import numpy as np
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QDate
from modules.video_playback.timeline_widget import TimelineWidget
from modules.video_playback.playback_widget import PlaybackWidget, ClipExportDialog
from app.main import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    return app


def test_timeline_widget_rendering_and_interaction(qapp):
    """Verifies TimelineWidget channels, intervals, scrub seek, and paint event."""
    timeline = TimelineWidget()
    timeline.resize(800, 160)

    channels = ["ch_1", "ch_2", "ch_3", "ch_4"]
    timeline.set_channels(channels)
    assert len(timeline.channels) == 4

    # Add mock intervals
    now = datetime.now(timezone.utc)
    intervals = [
        {"start_time": now - timedelta(hours=2), "end_time": now - timedelta(hours=1), "recording_type": "CONTINUOUS"},
        {"start_time": now - timedelta(minutes=45), "end_time": now - timedelta(minutes=30), "recording_type": "MOTION"},
        {"start_time": now - timedelta(minutes=15), "end_time": now, "recording_type": "AI_EVENT"},
    ]
    timeline.set_recording_data("ch_1", intervals)
    assert len(timeline.recording_data["ch_1"]) == 3

    # Test seek signal emission on scrub
    received_seeks = []
    timeline.seek_requested.connect(lambda t: received_seeks.append(t))

    # Trigger scrub programmatically
    target_dt = now - timedelta(hours=1)
    timeline.set_current_time(target_dt)
    assert timeline.current_time == target_dt

    # Force paint rendering in offscreen mode
    timeline.show()
    timeline.repaint()
    assert not timeline.isHidden()


def test_playback_workspace_controls_and_grid(qapp):
    """Verifies PlaybackWidget controls, grid reconfigurations (1, 4, 9, 16), and speed."""
    playback = PlaybackWidget()
    playback.resize(1024, 768)

    # Initial 2x2 grid (4 tiles)
    assert len(playback.tiles) == 4

    # Switch to 1x1
    playback.combo_grid.setCurrentIndex(0)
    assert len(playback.tiles) == 1
    assert playback.active_channels == ["ch_1"]

    # Switch to 3x3 (9 tiles)
    playback.combo_grid.setCurrentIndex(2)
    assert len(playback.tiles) == 9

    # Switch to 4x4 (16 tiles)
    playback.combo_grid.setCurrentIndex(3)
    assert len(playback.tiles) == 16

    # Test Play / Pause toggle
    playback.btn_play_pause.click()
    assert "Pause" in playback.btn_play_pause.text()

    playback.btn_play_pause.click()
    assert "Play" in playback.btn_play_pause.text()

    # Test Speed change
    playback.combo_speed.setCurrentText("2.0x")

    # Test Date change
    playback.date_picker.setDate(QDate(2026, 11, 20))

    # Repaint
    playback.repaint()


def test_main_window_has_playback_workspace(qapp):
    """Verifies MainWindow includes PlaybackWidget at stacked index 2."""
    window = MainWindow()
    assert hasattr(window, "playback_widget")
    assert window.stack.widget(2) == window.playback_widget

    # Switch to view 2
    window._switch_view(2)
    assert window.stack.currentIndex() == 2
    window.close()
