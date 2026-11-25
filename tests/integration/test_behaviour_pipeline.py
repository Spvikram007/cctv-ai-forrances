"""
Integration tests for Behaviour Analytics Pipeline & UI (Phase 8).
Tests end-to-end CameraAnalyticsPipeline integration, synthetic video sequences,
occlusion & tracking-loss resilience, camera disconnect/reconnect, day/night transitions,
and BehaviourAnalyticsWidget UI event handling.
"""

from dataclasses import dataclass
from typing import Tuple, List
import time
import pytest
import numpy as np
import cv2
from PySide6.QtWidgets import QApplication

from engines.analytics_engine.analytics_pipeline import (
    CameraAnalyticsPipeline,
    ZoneConfig,
    AnalyticsRuleConfig,
)
from engines.analytics_engine.behaviour_detectors import (
    BehaviourRuleConfig,
    CrowdDensityConfig,
)
from modules.ai_intelligence.behaviour_analytics_widget import (
    BehaviourAnalyticsWidget,
    InteractiveBehaviourCanvas,
)
from core.events.event_bus import bus


@dataclass
class MockTrack:
    track_id: int
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_pipeline_behaviour_end_to_end():
    pipeline = CameraAnalyticsPipeline("CAM-01", persist_to_db=False)
    pipeline.behaviour_manager.crowd_detector.config = CrowdDensityConfig(
        warning_density_people_per_m2=2.0,
        alert_persistence_sec=1.0,
    )

    zone = ZoneConfig("Z_MAIN", "Main Hall", "CROWD", [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
    setattr(zone, "surface_area_m2", 5.0)
    pipeline.add_zone(zone)

    # Synthetic frame
    frame = np.zeros((360, 640, 3), dtype=np.uint8)

    # 15 people in zone (density = 3.0 people/m²)
    tracks = [
        MockTrack(i + 1, "person", 0.9, (0.2 + (i * 0.04), 0.3, 0.05, 0.15))
        for i in range(15)
    ]

    # Initial frame at t=100.0
    events_1 = pipeline.process(tracks, frame=frame, timestamp=100.0)
    assert len(events_1) == 0

    # Frame after persistence duration at t=101.5
    events_2 = pipeline.process(tracks, frame=frame, timestamp=101.5)
    crowd_events = [ev for ev in events_2 if ev.rule_type == "CROWD_DENSITY"]
    assert len(crowd_events) == 1
    assert crowd_events[0].channel_id == "CAM-01"


def test_occlusion_and_tracking_loss_resilience():
    pipeline = CameraAnalyticsPipeline("CAM-02", persist_to_db=False)
    pipeline.behaviour_manager.fall_detector.config.rapid_descent_window_sec = 1.0
    pipeline.behaviour_manager.fall_detector.config.prone_confirmation_sec = 2.0

    # Person upright at t=10.0
    upright = MockTrack(10, "person", 0.9, (0.50, 0.20, 0.10, 0.35))
    pipeline.process([upright], timestamp=10.0)

    # Falls at t=10.5
    fallen = MockTrack(10, "person", 0.9, (0.50, 0.60, 0.35, 0.10))
    pipeline.process([fallen], timestamp=10.5)

    # Transient occlusion at t=11.0: frame has 0 detections (person occluded by pillar/vehicle)
    pipeline.process([], timestamp=11.0)

    # Person re-detected prone at t=11.5
    pipeline.process([fallen], timestamp=11.5)

    # At t=13.0: prone duration sustained
    events = pipeline.process([fallen], timestamp=13.0)
    # The pipeline gracefully handles transient occlusion without crashing
    assert isinstance(events, list)


def test_camera_disconnect_and_reconnect():
    pipeline = CameraAnalyticsPipeline("CAM-03", persist_to_db=False)

    # Normal feed
    p = MockTrack(1, "person", 0.9, (0.3, 0.3, 0.1, 0.3))
    pipeline.process([p], timestamp=50.0)

    # Stream disconnects -> reset pipeline tracking state
    pipeline.reset()
    assert len(pipeline.behaviour_manager.fall_detector._candidates) == 0

    # Camera reconnects and resumes
    events = pipeline.process([p], timestamp=60.0)
    assert isinstance(events, list)


def test_day_night_transition_resilience():
    pipeline = CameraAnalyticsPipeline("CAM-04", persist_to_db=False)

    # Daytime bright frame (mean pixel ~ 180)
    day_frame = np.full((360, 640, 3), 180, dtype=np.uint8)
    p = MockTrack(1, "person", 0.9, (0.4, 0.4, 0.1, 0.35))
    events_day = pipeline.process([p], frame=day_frame, timestamp=100.0)
    assert len(events_day) == 0

    # Sudden night transition (mean pixel ~ 25)
    night_frame = np.full((360, 640, 3), 25, dtype=np.uint8)
    events_night = pipeline.process([p], frame=night_frame, timestamp=101.0)
    # Sudden drop in scene illumination must not trigger false positive fall/wrong-way alarms
    assert len(events_night) == 0


def test_behaviour_analytics_ui_smoke(qapp):
    widget = BehaviourAnalyticsWidget()
    assert widget.channel_combo.count() == 16
    assert widget.card_crowd is not None
    assert widget.card_abandoned is not None
    assert widget.card_falls is not None
    assert widget.card_wrong_way is not None

    # Simulate EventBus event delivery
    event_data = {
        "channel_id": "CAM-01",
        "rule_type": "FALL_DETECTION",
        "severity": "CRITICAL",
        "confidence": 0.88,
        "timestamp": time.time(),
        "details": {
            "requires_human_review": True,
            "disclaimer": "AI fall suspicion",
            "aspect_ratio": 3.2,
        },
    }
    widget._on_event_received(event_data)

    # Check that incident row was added to table
    assert widget.table_events.rowCount() >= 1
    # Check that fall counter incremented
    assert int(widget.card_falls._val_label.text()) >= 1

    # Test verify incident action
    widget.table_events.selectRow(0)
    widget._verify_selected_incident()
    item = widget.table_events.item(0, 5)
    assert "CONFIRMED" in item.text()

    # Test canvas drawing
    canvas = widget.canvas
    canvas.set_mode("DRAW_ZONE")
    canvas.set_entities([], [])
    assert canvas.mode == "DRAW_ZONE"
