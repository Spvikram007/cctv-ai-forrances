"""
Unit Tests for Video Analytics Detectors (F-013, F-014, F-015, F-016, F-017).
Validates Intrusion Detection, Tripwire Crossing, Loitering State Machine,
Directional Counting, Occupancy Calculations, and Heatmap Generation.
"""

import time
from dataclasses import dataclass
from typing import Tuple
import numpy as np
import pytest

from engines.analytics_engine.rule_evaluator import (
    ZoneConfig,
    TripwireConfig,
    AnalyticsRuleConfig,
    IntrusionDetector,
    TripwireDetector,
    LoiteringDetector,
    CountingManager,
    HeatmapGenerator,
)


@dataclass
class MockTrack:
    track_id: int
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]  # (x, y, w, h)


def test_intrusion_entry_and_exit_transitions():
    detector = IntrusionDetector(suppression_window_sec=5.0)
    zone = ZoneConfig(
        id="zone_restricted",
        name="Restricted Courtyard",
        zone_type="INTRUSION",
        polygon=[(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)],
        is_active=True,
    )
    rule = AnalyticsRuleConfig(
        id="rule_intrude_1",
        name="Courtyard Intrusion",
        rule_type="INTRUSION",
        channel_id="CAM_01",
        zone_id="zone_restricted",
        target_classes=["person"],
        confidence_threshold=0.50,
        severity="WARNING",
    )

    t0 = 1000.0
    # Frame 1: Person is outside the zone (bottom center = (0.1, 0.1))
    track_out = MockTrack(track_id=101, class_name="person", confidence=0.85, bbox=(0.08, 0.05, 0.04, 0.05))
    events_1 = detector.evaluate([zone], [rule], [track_out], timestamp=t0)
    assert len(events_1) == 0

    # Frame 2: Person enters the zone (bottom center = (0.5, 0.5))
    track_in = MockTrack(track_id=101, class_name="person", confidence=0.88, bbox=(0.48, 0.40, 0.04, 0.10))
    events_2 = detector.evaluate([zone], [rule], [track_in], timestamp=t0 + 0.2)
    assert len(events_2) == 1
    assert events_2[0].rule_type == "INTRUSION"
    assert events_2[0].details["action"] == "ENTER"
    assert events_2[0].track_id == 101

    # Frame 3: Person continues inside zone -> suppressed (no spamming)
    events_3 = detector.evaluate([zone], [rule], [track_in], timestamp=t0 + 0.4)
    assert len(events_3) == 0

    # Frame 4: Person exits the zone
    events_4 = detector.evaluate([zone], [rule], [track_out], timestamp=t0 + 1.0)
    assert len(events_4) == 1
    assert events_4[0].rule_type == "INTRUSION"
    assert events_4[0].details["action"] == "EXIT"


def test_tripwire_crossing_direction_and_counters():
    detector = TripwireDetector(suppression_cooldown_sec=5.0)
    tw = TripwireConfig(
        id="tw_gate",
        name="Main Gate Line",
        pt1=(0.1, 0.5),
        pt2=(0.9, 0.5),
        direction="BIDIRECTIONAL",
        is_active=True,
    )
    rule = AnalyticsRuleConfig(
        id="rule_tw_1",
        name="Gate Crossing",
        rule_type="LINE_CROSSING",
        channel_id="CAM_01",
        tripwire_id="tw_gate",
        target_classes=["person", "car"],
        confidence_threshold=0.50,
        severity="WARNING",
    )

    t0 = 1000.0
    # Step 1: Track 50 starts on top side (y = 0.3)
    track_pos1 = MockTrack(track_id=50, class_name="car", confidence=0.90, bbox=(0.48, 0.20, 0.04, 0.10))
    events_1 = detector.evaluate([tw], [rule], [track_pos1], timestamp=t0)
    assert len(events_1) == 0  # Initial point recorded

    # Step 2: Track 50 crosses to bottom side (y = 0.7)
    track_pos2 = MockTrack(track_id=50, class_name="car", confidence=0.92, bbox=(0.48, 0.60, 0.04, 0.10))
    events_2 = detector.evaluate([tw], [rule], [track_pos2], timestamp=t0 + 0.2)
    assert len(events_2) == 1
    assert events_2[0].rule_type == "LINE_CROSSING"
    assert events_2[0].crossing_direction in ("A_TO_B", "B_TO_A")
    assert detector.counters["tw_gate"]["TOTAL"] == 1


def test_tripwire_duplicate_crossing_prevention():
    detector = TripwireDetector(suppression_cooldown_sec=10.0)
    tw = TripwireConfig(
        id="tw_door",
        name="Entrance Door",
        pt1=(0.0, 0.5),
        pt2=(1.0, 0.5),
        direction="BIDIRECTIONAL",
        is_active=True,
    )
    rule = AnalyticsRuleConfig(
        id="rule_tw_door",
        name="Door Check",
        rule_type="LINE_CROSSING",
        channel_id="CAM_01",
        tripwire_id="tw_door",
        target_classes=["person"],
        confidence_threshold=0.50,
    )

    t0 = 1000.0
    tr1 = MockTrack(track_id=99, class_name="person", confidence=0.95, bbox=(0.5, 0.3, 0.05, 0.1))
    detector.evaluate([tw], [rule], [tr1], timestamp=t0)

    tr2 = MockTrack(track_id=99, class_name="person", confidence=0.95, bbox=(0.5, 0.6, 0.05, 0.1))
    evs = detector.evaluate([tw], [rule], [tr2], timestamp=t0 + 0.1)
    assert len(evs) == 1
    assert detector.counters["tw_door"]["TOTAL"] == 1

    # Same track moving back across immediately within cooldown
    tr3 = MockTrack(track_id=99, class_name="person", confidence=0.95, bbox=(0.5, 0.3, 0.05, 0.1))
    evs_dup = detector.evaluate([tw], [rule], [tr3], timestamp=t0 + 0.3)
    # MUST be suppressed to prevent bounce/jitter duplicate triggers
    assert len(evs_dup) == 0
    assert detector.counters["tw_door"]["TOTAL"] == 1


def test_loitering_dwell_time_and_alarm():
    detector = LoiteringDetector(occlusion_grace_period_sec=2.0, min_consecutive_frames=2)
    zone = ZoneConfig(
        id="zone_atm",
        name="ATM Lobby",
        zone_type="LOITERING",
        polygon=[(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)],
        is_active=True,
    )
    rule = AnalyticsRuleConfig(
        id="rule_loiter_1",
        name="ATM Loitering Alarm",
        rule_type="LOITERING",
        channel_id="CAM_01",
        zone_id="zone_atm",
        target_classes=["person"],
        confidence_threshold=0.50,
        min_dwell_time_sec=3.0,  # 3 seconds dwell threshold
        severity="WARNING",
    )

    t0 = 5000.0
    track = MockTrack(track_id=77, class_name="person", confidence=0.91, bbox=(0.4, 0.4, 0.1, 0.2))

    # Frame 1: Entry (t = 0.0s) -> no alarm yet
    assert len(detector.evaluate([zone], [rule], [track], timestamp=t0)) == 0

    # Frame 2: (t = 1.0s) -> dwell = 1.0s < 3.0s -> no alarm
    assert len(detector.evaluate([zone], [rule], [track], timestamp=t0 + 1.0)) == 0

    # Frame 3: (t = 2.5s) -> dwell = 2.5s < 3.0s -> no alarm
    assert len(detector.evaluate([zone], [rule], [track], timestamp=t0 + 2.5)) == 0

    # Frame 4: (t = 3.2s) -> dwell = 3.2s >= 3.0s -> ALARM FIRES!
    events = detector.evaluate([zone], [rule], [track], timestamp=t0 + 3.2)
    assert len(events) == 1
    assert events[0].rule_type == "LOITERING"
    assert events[0].dwell_time_sec >= 3.0
    assert events[0].track_id == 77

    # Frame 5: (t = 4.0s) -> continuing loiter -> alarm already fired, do not repeat
    assert len(detector.evaluate([zone], [rule], [track], timestamp=t0 + 4.0)) == 0


def test_loitering_occlusion_tolerance():
    detector = LoiteringDetector(occlusion_grace_period_sec=2.0, min_consecutive_frames=2)
    zone = ZoneConfig(
        id="zone_vault",
        name="Vault Corridor",
        polygon=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
        is_active=True,
    )
    rule = AnalyticsRuleConfig(
        id="rule_vault",
        name="Vault Loiter",
        rule_type="LOITERING",
        channel_id="CAM_01",
        zone_id="zone_vault",
        target_classes=["person"],
        min_dwell_time_sec=4.0,
    )

    t0 = 6000.0
    track = MockTrack(track_id=88, class_name="person", confidence=0.90, bbox=(0.5, 0.5, 0.05, 0.1))

    detector.evaluate([zone], [rule], [track], timestamp=t0)
    detector.evaluate([zone], [rule], [track], timestamp=t0 + 1.0)

    # Temporary occlusion for 1.2 seconds (empty tracked objects)
    detector.evaluate([zone], [rule], [], timestamp=t0 + 2.2)

    # Object re-appears at t0 + 4.5s -> within occlusion grace period of last seen (2.2s)!
    events = detector.evaluate([zone], [rule], [track], timestamp=t0 + 4.5)
    # The dwell session was retained across the brief occlusion!
    assert len(events) == 1
    assert events[0].dwell_time_sec >= 4.0


def test_counting_manager_and_occupancy():
    mgr = CountingManager("CAM_01")

    # 3 persons enter, 1 person exits
    mgr.record_count("person", "ENTER", track_id=1, timestamp=100.0)
    mgr.record_count("person", "ENTER", track_id=2, timestamp=101.0)
    mgr.record_count("person", "ENTER", track_id=3, timestamp=102.0)
    mgr.record_count("person", "EXIT", track_id=1, timestamp=150.0)

    # 2 cars enter, 1 car exits
    mgr.record_count("car", "ENTER", track_id=10, timestamp=110.0)
    mgr.record_count("car", "ENTER", track_id=11, timestamp=115.0)
    mgr.record_count("car", "EXIT", track_id=10, timestamp=160.0)

    summary = mgr.get_summary()
    assert summary["total_entered"] == 5
    assert summary["total_exited"] == 2
    assert summary["current_occupancy"] == 3  # (5 - 2)
    assert summary["person_entered"] == 3
    assert summary["person_exited"] == 1
    assert summary["vehicle_entered"] == 2
    assert summary["vehicle_exited"] == 1

    # Test reset
    mgr.reset_counters()
    assert mgr.current_occupancy == 0
    assert mgr.total_entered == 0


def test_heatmap_generation_and_pruning():
    hm = HeatmapGenerator("CAM_01", grid_width=32, grid_height=18, retention_hours=1.0)
    t0 = 2000.0

    # Add 10 points clustered around (0.5, 0.5)
    for i in range(10):
        tr = MockTrack(track_id=1, class_name="person", confidence=0.9, bbox=(0.48, 0.45, 0.04, 0.05))
        hm.add_points([tr], timestamp=t0 + i)

    # Generate density matrix
    density = hm.generate_density_matrix(t0, t0 + 20)
    assert density.shape == (18, 32)
    assert np.max(density) == pytest.approx(1.0)

    # Render image
    img = hm.render_heatmap_image(output_width=320, output_height=180)
    assert img.shape == (180, 320, 3)

    # Prune points older than 1 hour
    pruned = hm.prune_retention(current_time=t0 + 4000.0)
    assert pruned == 10
    assert len(hm._trajectory_points) == 0
