"""
Unit tests for Stationary, Abandoned & Removed Object Detection with Owner Association (F-036).
Tests stationary dwell, owner association, owner separation, unattended alerts,
abandoned alerts, and removed object confirmation.
"""

from dataclasses import dataclass
from typing import Tuple
import pytest

from engines.analytics_engine.behaviour_detectors import (
    StationaryObjectDetector,
    StationaryObjectConfig,
)


@dataclass
class MockTrack:
    track_id: int
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]


def test_owner_association_and_separation_unattended_alert():
    detector = StationaryObjectDetector(
        StationaryObjectConfig(
            stationary_dwell_sec=60.0,
            owner_separation_dist_norm=0.15,
            owner_separation_duration_sec=30.0,
            suppression_cooldown_sec=30.0,
        )
    )

    # Initial frame t=100.0: Person (Track 1) deposits Backpack (Track 2) right beside them (dist < 0.15)
    person = MockTrack(1, "person", 0.9, (0.50, 0.50, 0.10, 0.30))  # bottom center ~ (0.55, 0.80)
    backpack = MockTrack(2, "backpack", 0.85, (0.52, 0.70, 0.08, 0.10))  # center ~ (0.56, 0.75)

    events_t1 = detector.evaluate([], [], [person, backpack], timestamp=100.0)
    assert len(events_t1) == 0

    # Verify owner association
    cand = detector._candidates.get(2)
    assert cand is not None
    assert cand.owner_track_id == 1

    # Frame t=110.0: Person walks away to (0.10, 0.10) (distance > 0.15)
    person_far = MockTrack(1, "person", 0.9, (0.10, 0.10, 0.10, 0.30))
    detector.evaluate([], [], [person_far, backpack], timestamp=110.0)
    assert cand.owner_separated_start_time == 110.0

    # Frame t=130.0: Separated for 20s (< 30s threshold) -> No alert
    events_t2 = detector.evaluate([], [], [person_far, backpack], timestamp=130.0)
    assert len(events_t2) == 0

    # Frame t=140.5: Separated for 30.5s (>= 30s threshold) -> UNATTENDED_OBJECT alert!
    events_t3 = detector.evaluate([], [], [person_far, backpack], timestamp=140.5)
    assert len(events_t3) == 1
    ev = events_t3[0]
    assert ev.rule_type == "UNATTENDED_OBJECT"
    assert ev.severity == "WARNING"
    assert ev.track_id == 2
    assert ev.details["owner_track_id"] == 1
    assert ev.details["owner_separated_duration_sec"] >= 30.0


def test_abandoned_object_dwell_trigger():
    detector = StationaryObjectDetector(
        StationaryObjectConfig(
            stationary_dwell_sec=60.0,
            owner_separation_duration_sec=30.0,
        )
    )

    # Suitcase left alone at t=200.0
    suitcase = MockTrack(10, "suitcase", 0.88, (0.40, 0.60, 0.10, 0.15))
    detector.evaluate([], [], [suitcase], timestamp=200.0)

    # Frame t=250.0: Stationary for 50s (< 60s dwell) -> No abandoned alert
    events_t1 = detector.evaluate([], [], [suitcase], timestamp=250.0)
    assert len(events_t1) == 0

    # Frame t=260.5: Stationary for 60.5s (>= 60s dwell) -> ABANDONED_OBJECT alert!
    events_t2 = detector.evaluate([], [], [suitcase], timestamp=260.5)
    assert len(events_t2) == 1
    ev = events_t2[0]
    assert ev.rule_type == "ABANDONED_OBJECT"
    assert ev.severity == "CRITICAL"
    assert ev.track_id == 10
    assert ev.details["stationary_duration_sec"] >= 60.0


def test_removed_object_confirmation_trigger():
    detector = StationaryObjectDetector(
        StationaryObjectConfig(
            removed_confirmation_sec=5.0,
        )
    )

    # Box has been stationary from t=300.0 to t=320.0
    box = MockTrack(20, "box", 0.80, (0.30, 0.30, 0.10, 0.10))
    detector.evaluate([], [], [box], timestamp=300.0)
    detector.evaluate([], [], [box], timestamp=320.0)

    # Box disappears at t=321.0
    events_t1 = detector.evaluate([], [], [], timestamp=321.0)
    assert len(events_t1) == 0

    # At t=324.0: missing for 3s (< 5s threshold) -> No alert
    events_t2 = detector.evaluate([], [], [], timestamp=324.0)
    assert len(events_t2) == 0

    # At t=326.5: missing for 5.5s (>= 5s threshold) -> REMOVED_OBJECT alert!
    events_t3 = detector.evaluate([], [], [], timestamp=326.5)
    assert len(events_t3) == 1
    ev = events_t3[0]
    assert ev.rule_type == "REMOVED_OBJECT"
    assert ev.severity == "CRITICAL"
    assert ev.track_id == 20
    assert ev.details["action"] == "OBJECT_REMOVED"
    assert ev.details["missing_duration_sec"] >= 5.0


def test_moving_object_resets_stationary_dwell():
    detector = StationaryObjectDetector(
        StationaryObjectConfig(
            stationary_dwell_sec=60.0,
            stationary_displacement_threshold=0.03,
        )
    )

    # Bicycle at (0.2, 0.2)
    bike1 = MockTrack(30, "bicycle", 0.85, (0.20, 0.20, 0.10, 0.10))
    detector.evaluate([], [], [bike1], timestamp=400.0)

    # Bicycle moves to (0.4, 0.4) at t=430.0
    bike2 = MockTrack(30, "bicycle", 0.85, (0.40, 0.40, 0.10, 0.10))
    detector.evaluate([], [], [bike2], timestamp=430.0)

    # Check that stationary timer was reset to 430.0
    cand = detector._candidates.get(30)
    assert cand is not None
    assert cand.first_stationary_time == 430.0

    # At t=470.0 (stationary for 40s since move < 60s) -> No alert
    events = detector.evaluate([], [], [bike2], timestamp=470.0)
    assert len(events) == 0
