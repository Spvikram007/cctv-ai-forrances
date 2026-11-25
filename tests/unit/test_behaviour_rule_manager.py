"""
Unit tests for Advanced Behaviour Rule Engine and Composite Conditions (F-039).
Tests composite AND/OR rules, schedule active checks, multi-camera channel isolation,
and detector state reset.
"""

from dataclasses import dataclass
from typing import Tuple
import pytest

from engines.analytics_engine.behaviour_detectors import (
    BehaviourAnalyticsManager,
    BehaviourRuleConfig,
    CrowdDensityConfig,
)
from engines.analytics_engine.rule_evaluator import ZoneConfig


@dataclass
class MockTrack:
    track_id: int
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]


def test_composite_rule_and_operator():
    mgr = BehaviourAnalyticsManager("CAM-01")

    # Set up crowd detector with short persistence for testing
    mgr.crowd_detector.config = CrowdDensityConfig(
        warning_density_people_per_m2=2.0,
        alert_persistence_sec=1.0,
    )
    # Set up directional detector to trigger wrong way
    mgr.directional_detector.config.allowed_angle_deg = 0.0  # East
    mgr.directional_detector.config.confirmation_duration_sec = 1.0

    # Composite Rule: Crowd Density > threshold AND Wrong-Way detected
    comp_rule = BehaviourRuleConfig(
        id="COMP_01",
        name="Crowd Stampede in Restricted Direction",
        channel_id="CAM-01",
        rule_type="COMPOSITE",
        conditions=[
            {"type": "CROWD_DENSITY"},
            {"type": "WRONG_WAY"},
        ],
        logical_operator="AND",
        severity="CRITICAL",
        suppression_cooldown_sec=10.0,
    )
    mgr.add_rule(comp_rule)

    zone = ZoneConfig("Z1", "Plaza", "CROWD", [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
    setattr(zone, "surface_area_m2", 5.0)

    # 1. First tick t=100.0: High crowd (15 people), moving East (allowed)
    tracks_crowd = [
        MockTrack(i + 1, "person", 0.9, (0.2 + (i * 0.03), 0.3, 0.05, 0.15))
        for i in range(15)
    ]
    events_t1 = mgr.evaluate_frame([zone], tracks_crowd, timestamp=100.0)
    # Composite rule not triggered because WRONG_WAY condition is not met
    assert not any(ev.rule_type == "COMPOSITE_BEHAVIOUR" for ev in events_t1)

    # 2. Tick t=101.0: Car starts moving West (Wrong-Way, x=0.8 to x=0.6)
    car_wrong_way = MockTrack(99, "car", 0.95, (0.80, 0.70, 0.10, 0.08))
    mgr.evaluate_frame([], [car_wrong_way], timestamp=100.0)

    car_wrong_way2 = MockTrack(99, "car", 0.95, (0.60, 0.70, 0.10, 0.08))
    mgr.evaluate_frame([], [car_wrong_way2], timestamp=101.0)

    # 3. Tick t=102.5: Crowd continues (> 1.0s) AND Car sustains wrong-way (> 1.0s confirmation)
    car_wrong_way3 = MockTrack(99, "car", 0.95, (0.40, 0.70, 0.10, 0.08))
    all_tracks = tracks_crowd + [car_wrong_way3]
    events_t3 = mgr.evaluate_frame([zone], all_tracks, timestamp=102.5)

    # Both conditions met! Composite rule triggers
    comp_events = [ev for ev in events_t3 if ev.rule_type == "COMPOSITE_BEHAVIOUR"]
    assert len(comp_events) == 1
    assert comp_events[0].severity == "CRITICAL"
    assert comp_events[0].rule_name == "Crowd Stampede in Restricted Direction"


def test_composite_rule_or_operator():
    mgr = BehaviourAnalyticsManager("CAM-02")
    mgr.fall_detector.config.rapid_descent_window_sec = 1.0
    mgr.fall_detector.config.prone_confirmation_sec = 1.0

    # Composite Rule with OR: Fall Detection OR Abandoned Object
    comp_rule = BehaviourRuleConfig(
        id="COMP_02",
        name="Emergency Incident",
        channel_id="CAM-02",
        rule_type="COMPOSITE",
        conditions=[
            {"type": "FALL_DETECTION"},
            {"type": "ABANDONED_OBJECT"},
        ],
        logical_operator="OR",
        severity="CRITICAL",
    )
    mgr.add_rule(comp_rule)

    # Simulate only Fall Detection
    upright = MockTrack(1, "person", 0.9, (0.40, 0.10, 0.10, 0.35))
    mgr.evaluate_frame([], [upright], timestamp=200.0)

    fallen = MockTrack(1, "person", 0.9, (0.40, 0.50, 0.35, 0.10))
    mgr.evaluate_frame([], [fallen], timestamp=200.5)

    # After prone confirmation
    events = mgr.evaluate_frame([], [fallen], timestamp=202.0)
    # OR rule triggers because FALL_DETECTION occurred
    comp_events = [ev for ev in events if ev.rule_type == "COMPOSITE_BEHAVIOUR"]
    assert len(comp_events) == 1
    assert comp_events[0].rule_id == "COMP_02"


def test_behaviour_rule_schedule_filtering():
    rule = BehaviourRuleConfig(
        id="SCHED_01",
        name="Night Only Rule",
        channel_id="CAM-01",
        rule_type="FALL_DETECTION",
        schedule={"days": [0, 1, 2, 3, 4, 5, 6], "start_time": "22:00", "end_time": "23:59"},
    )
    # Test at 12:00 UTC (not within 22:00-23:59)
    # 2026-11-25 12:00:00 UTC = timestamp 1795608000
    from datetime import datetime, timezone
    dt_noon = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc).timestamp()
    assert rule.is_schedule_active(dt_noon) is False

    dt_night = datetime(2026, 11, 25, 23, 15, tzinfo=timezone.utc).timestamp()
    assert rule.is_schedule_active(dt_night) is True


def test_multi_camera_channel_isolation():
    mgr1 = BehaviourAnalyticsManager("CAM-01")
    mgr2 = BehaviourAnalyticsManager("CAM-02")

    # Person falls on CAM-01
    upright = MockTrack(1, "person", 0.9, (0.40, 0.10, 0.10, 0.35))
    mgr1.evaluate_frame([], [upright], timestamp=10.0)
    mgr2.evaluate_frame([], [], timestamp=10.0)

    fallen = MockTrack(1, "person", 0.9, (0.40, 0.50, 0.35, 0.10))
    mgr1.fall_detector.config.rapid_descent_window_sec = 1.0
    mgr1.fall_detector.config.prone_confirmation_sec = 1.0
    mgr1.evaluate_frame([], [fallen], timestamp=10.5)

    events_cam1 = mgr1.evaluate_frame([], [fallen], timestamp=12.0)
    events_cam2 = mgr2.evaluate_frame([], [], timestamp=12.0)

    # CAM-01 has fall event, CAM-02 has 0 events (strict channel isolation)
    assert len(events_cam1) >= 1
    assert all(ev.channel_id == "CAM-01" for ev in events_cam1)
    assert len(events_cam2) == 0


def test_detector_reset():
    mgr = BehaviourAnalyticsManager("CAM-03")
    upright = MockTrack(1, "person", 0.9, (0.40, 0.10, 0.10, 0.35))
    mgr.evaluate_frame([], [upright], timestamp=50.0)

    assert len(mgr.fall_detector._candidates) == 1
    mgr.reset()
    assert len(mgr.fall_detector._candidates) == 0
    assert len(mgr.stationary_detector._candidates) == 0
    assert len(mgr.directional_detector._sessions) == 0
