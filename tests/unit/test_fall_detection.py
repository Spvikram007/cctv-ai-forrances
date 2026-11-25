"""
Unit tests for Fall Detection & Posture Analysis (F-037).
Tests rapid descent velocity, aspect ratio inversion, prone dwell confirmation,
composite confidence, mandatory human review flags, and false-positive rejection.
"""

from dataclasses import dataclass
from typing import Tuple
import pytest

from engines.analytics_engine.behaviour_detectors import (
    FallDetector,
    FallDetectionConfig,
)


@dataclass
class MockTrack:
    track_id: int
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]


def test_fall_detection_rapid_descent_and_prone_confirmation():
    detector = FallDetector(
        FallDetectionConfig(
            rapid_descent_window_sec=1.5,
            min_vertical_descent_delta=0.08,
            prone_confirmation_sec=3.0,
            aspect_ratio_inversion_threshold=1.2,
            confidence_threshold=0.60,
        )
    )

    # 1. Person standing upright at t=100.0 (x=0.5, y=0.2, w=0.10, h=0.35 -> ar=0.28)
    upright_p = MockTrack(1, "person", 0.92, (0.50, 0.20, 0.10, 0.35))
    events_t1 = detector.evaluate([], [], [upright_p], timestamp=100.0)
    assert len(events_t1) == 0

    # 2. Rapid fall to ground at t=101.0 (dt=1.0s <= 1.5s):
    # Centroid moves down from y=0.375 to y=0.60 (delta_y = 0.225 >= 0.08)
    # Bbox flips to prone: w=0.35, h=0.10 -> ar = 3.5 (>= 1.2)
    fallen_p = MockTrack(1, "person", 0.90, (0.40, 0.55, 0.35, 0.10))
    events_t2 = detector.evaluate([], [], [fallen_p], timestamp=101.0)
    # Just fell, prone duration = 0s (< 3.0s) -> No alert yet
    assert len(events_t2) == 0

    cand = detector._candidates.get(1)
    assert cand is not None
    assert cand.descent_detected is True
    assert cand.prone_start_time == 101.0

    # 3. Frame at t=102.5: Prone for 1.5s (< 3.0s threshold) -> No alert yet
    events_t3 = detector.evaluate([], [], [fallen_p], timestamp=102.5)
    assert len(events_t3) == 0

    # 4. Frame at t=104.2: Prone for 3.2s (>= 3.0s threshold) -> FALL_DETECTION alert!
    events_t4 = detector.evaluate([], [], [fallen_p], timestamp=104.2)
    assert len(events_t4) == 1
    ev = events_t4[0]
    assert ev.rule_type == "FALL_DETECTION"
    assert ev.severity == "CRITICAL"
    assert ev.track_id == 1
    assert ev.confidence >= 0.60
    assert ev.details["requires_human_review"] is True
    assert ev.details["prone_duration_sec"] >= 3.0
    assert ev.details["aspect_ratio"] == pytest.approx(3.5)
    assert "human" in ev.details["disclaimer"].lower()


def test_fall_detection_rejects_normal_walking():
    detector = FallDetector()

    # Walking across horizontal plane, maintaining upright posture
    for i in range(10):
        t = 200.0 + (i * 0.5)
        x = 0.10 + (i * 0.05)
        # Upright: w=0.10, h=0.35
        p = MockTrack(5, "person", 0.9, (x, 0.30, 0.10, 0.35))
        events = detector.evaluate([], [], [p], timestamp=t)
        assert len(events) == 0


def test_fall_detection_rejects_gentle_sitting():
    detector = FallDetector(
        FallDetectionConfig(
            rapid_descent_window_sec=1.5,
            min_vertical_descent_delta=0.08,
            aspect_ratio_inversion_threshold=1.2,
        )
    )

    # 1. Standing at t=300.0
    p1 = MockTrack(8, "person", 0.9, (0.50, 0.20, 0.10, 0.35))
    detector.evaluate([], [], [p1], timestamp=300.0)

    # 2. Sits down gradually over 4.0 seconds (at t=304.0)
    # Seated posture: w=0.15, h=0.22 -> ar = 0.68 (< 1.2 prone threshold)
    p2 = MockTrack(8, "person", 0.9, (0.50, 0.32, 0.15, 0.22))
    detector.evaluate([], [], [p2], timestamp=304.0)

    # 3. Remains seated at t=308.0
    events = detector.evaluate([], [], [p2], timestamp=308.0)
    # Never inverted to prone (ar < 1.2) -> No fall alert
    assert len(events) == 0


def test_fall_detection_rejects_transient_bending_or_shoe_tying():
    detector = FallDetector(
        FallDetectionConfig(
            prone_confirmation_sec=3.0,
        )
    )

    # Standing
    p_up = MockTrack(9, "person", 0.9, (0.30, 0.20, 0.10, 0.35))
    detector.evaluate([], [], [p_up], timestamp=400.0)

    # Person crouches/bends down at t=401.0
    p_down = MockTrack(9, "person", 0.9, (0.30, 0.35, 0.20, 0.15))
    detector.evaluate([], [], [p_down], timestamp=401.0)

    # Bends for only 1.0 second, then stands right back up at t=402.5
    detector.evaluate([], [], [p_up], timestamp=402.5)

    # Frame at t=405.0: stood back up, prone dwell never reached 3.0s -> No alert
    events = detector.evaluate([], [], [p_up], timestamp=405.0)
    assert len(events) == 0
