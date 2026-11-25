"""
Unit tests for Directional Trajectory Analysis and Wrong-Way Detection (F-038).
Tests heading angle calculation, angle tolerance boundaries, minimum displacement filtering,
confirmation duration, and allowed flow compliance.
"""

from dataclasses import dataclass
from typing import Tuple
import pytest

from engines.analytics_engine.behaviour_detectors import (
    DirectionalDetector,
    DirectionalConfig,
)


@dataclass
class MockTrack:
    track_id: int
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]


def test_wrong_way_detection_and_confirmation_window():
    # Corridor allows travel East (0.0 deg) with +-30.0 deg tolerance
    # Wrong-way confirmation window is 2.0 seconds
    detector = DirectionalDetector(
        DirectionalConfig(
            allowed_angle_deg=0.0,
            tolerance_deg=30.0,
            min_trajectory_displacement_norm=0.05,
            confirmation_duration_sec=2.0,
            suppression_cooldown_sec=30.0,
        )
    )

    # Vehicle (Track 1) enters and moves West (180 deg) at t=100.0:
    # Starts at x=0.80, moves towards x=0.20
    v1 = MockTrack(1, "car", 0.95, (0.80, 0.50, 0.10, 0.08))
    events_t1 = detector.evaluate([], [], [v1], timestamp=100.0)
    assert len(events_t1) == 0

    # Frame t=101.0: Vehicle moves to x=0.60 (displacement = 0.20 >= 0.05, heading = 180 deg)
    # Duration = 0s since wrong-way started at 101.0 -> No alert yet
    v2 = MockTrack(1, "car", 0.95, (0.60, 0.50, 0.10, 0.08))
    events_t2 = detector.evaluate([], [], [v2], timestamp=101.0)
    assert len(events_t2) == 0

    sess = detector._sessions.get(1)
    assert sess is not None
    assert sess.wrong_way_start_time == 101.0

    # Frame t=102.0: Wrong-way sustained for 1.0s (< 2.0s confirmation) -> No alert yet
    v3 = MockTrack(1, "car", 0.95, (0.40, 0.50, 0.10, 0.08))
    events_t3 = detector.evaluate([], [], [v3], timestamp=102.0)
    assert len(events_t3) == 0

    # Frame t=103.2: Wrong-way sustained for 2.2s (>= 2.0s confirmation) -> WRONG_WAY alert!
    v4 = MockTrack(1, "car", 0.95, (0.25, 0.50, 0.10, 0.08))
    events_t4 = detector.evaluate([], [], [v4], timestamp=103.2)
    assert len(events_t4) == 1
    ev = events_t4[0]
    assert ev.rule_type == "WRONG_WAY"
    assert ev.severity == "WARNING"
    assert ev.track_id == 1
    assert ev.details["heading_angle_deg"] == pytest.approx(180.0, abs=5.0)
    assert ev.details["angular_deviation_deg"] == pytest.approx(180.0, abs=5.0)
    assert ev.details["wrong_way_duration_sec"] >= 2.0


def test_allowed_direction_no_alert():
    # Corridor allows travel East (0.0 deg) +- 30 deg
    detector = DirectionalDetector(
        DirectionalConfig(
            allowed_angle_deg=0.0,
            tolerance_deg=30.0,
            min_trajectory_displacement_norm=0.05,
            confirmation_duration_sec=2.0,
        )
    )

    # Car moving East (from x=0.20 to x=0.70)
    for i in range(5):
        t = 200.0 + (i * 1.0)
        x = 0.20 + (i * 0.10)
        v = MockTrack(2, "car", 0.95, (x, 0.50, 0.10, 0.08))
        events = detector.evaluate([], [], [v], timestamp=t)
        assert len(events) == 0


def test_stationary_jitter_suppressed():
    detector = DirectionalDetector(
        DirectionalConfig(
            allowed_angle_deg=0.0,
            min_trajectory_displacement_norm=0.05,
            confirmation_duration_sec=2.0,
        )
    )

    # Person hovering in place (displacement < 0.01 between frames)
    for i in range(10):
        t = 300.0 + (i * 0.5)
        # Small jitter
        jitter = 0.002 if (i % 2 == 0) else -0.002
        p = MockTrack(3, "person", 0.9, (0.50 + jitter, 0.50, 0.05, 0.15))
        events = detector.evaluate([], [], [p], timestamp=t)
        # Displacement is below 0.05 -> Never triggers wrong-way
        assert len(events) == 0
