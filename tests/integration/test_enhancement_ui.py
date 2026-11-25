"""
Integration Tests for Video Enhancement UI & Comparative Split-View (Phase 9 - F-045).
"""

import sys
import pytest
import numpy as np
import cv2

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent

from modules.video_enhancement.comparison_view import ComparisonSplitView
from modules.video_enhancement.enhancement_widget import VideoEnhancementWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def sample_pair():
    h, w = 240, 320
    orig = np.full((h, w, 3), 30, dtype=np.uint8)
    cv2.putText(orig, "ORIGINAL", (30, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)

    enh = orig.copy()
    enh = cv2.addWeighted(enh, 1.5, np.zeros_like(enh), 0, 40)
    return orig, enh


def test_comparison_split_view_modes_and_slider(qapp, sample_pair) -> None:
    """Verifies split view slider adjustments and mode toggling."""
    orig, enh = sample_pair
    view = ComparisonSplitView()
    view.resize(640, 480)
    view.set_images(orig, enh)

    # Default mode is split
    assert view.view_mode == ComparisonSplitView.MODE_SPLIT
    assert view.split_ratio == 0.50

    # Adjust split ratio
    view.set_split_ratio(0.75)
    assert abs(view.split_ratio - 0.75) < 1e-4

    # Switch to side-by-side
    view.set_view_mode(ComparisonSplitView.MODE_SIDE_BY_SIDE)
    assert view.view_mode == ComparisonSplitView.MODE_SIDE_BY_SIDE

    # Mouse drag simulation
    view.set_view_mode(ComparisonSplitView.MODE_SPLIT)
    from PySide6.QtCore import QPointF, QEvent
    pos_press = QPointF(int(640 * 0.75), 240)
    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos_press,
        pos_press,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mousePressEvent(press_event)
    assert view._is_dragging is True

    # Drag to 320 (0.50 ratio)
    pos_move = QPointF(320, 240)
    move_event = QMouseEvent(
        QEvent.Type.MouseMove,
        pos_move,
        pos_move,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mouseMoveEvent(move_event)
    assert abs(view.split_ratio - 0.50) < 0.05

    release_event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pos_move,
        pos_move,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mouseReleaseEvent(release_event)
    assert view._is_dragging is False


def test_video_enhancement_widget_initialization_and_presets(qapp) -> None:
    """Verifies VideoEnhancementWidget constructs controls and applies presets."""
    widget = VideoEnhancementWidget()
    widget.resize(1024, 768)

    # Initial frame should be loaded
    assert widget._current_orig_frame is not None
    assert widget._current_enh_frame is not None

    # Test preset changing
    # Index 1: Night Vision
    widget.cmb_preset.setCurrentIndex(1)
    assert widget.chk_low_light.isChecked() is True
    assert widget.chk_denoise.isChecked() is True

    # Index 2: Fog & Smoke
    widget.cmb_preset.setCurrentIndex(2)
    assert widget.chk_dehaze.isChecked() is True

    # Index 3: License Plate
    widget.cmb_preset.setCurrentIndex(3)
    assert widget.chk_sharpen.isChecked() is True
    assert widget.chk_sr.isChecked() is True

    # Index 0: Reset Neutral
    widget.cmb_preset.setCurrentIndex(0)
    assert widget.chk_low_light.isChecked() is False
    assert widget.chk_dehaze.isChecked() is False
    assert widget.chk_denoise.isChecked() is False
    assert widget.chk_sharpen.isChecked() is False
    assert widget.chk_sr.isChecked() is False
