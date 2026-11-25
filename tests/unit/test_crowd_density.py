"""
Unit tests for Crowd Density & Occupancy Estimation (F-035).
Tests density thresholds, persistence timer, spatial clustering, and suppression cooldown.
"""

from dataclasses import dataclass
from typing import Tuple, List
import pytest

from engines.analytics_engine.behaviour_detectors import (
    CrowdDensityDetector,
    CrowdDensityConfig,
)
from engines.analytics_engine.rule_evaluator import ZoneConfig


@dataclass
class MockTrack:
    track_id: int
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]


def _create_people_tracks(count: int, x_range=(0.2, 0.4), y_range=(0.2, 0.4)) -> List[MockTrack]:
    tracks = []
    dx = (x_range[1] - x_range[0]) / max(1, count)
    for i in range(count):
        x = x_range[0] + (i * dx)
        y = y_range[0] + ((i % 5) * 0.03)
        tracks.append(
            MockTrack(
                track_id=i + 1,
                class_name="person",
                confidence=0.85,
                bbox=(x, y, 0.05, 0.15),
            )
        )
    return tracks


def test_crowd_density_normal_level():
    detector = CrowdDensityDetector(
        CrowdDensityConfig(
            warning_density_people_per_m2=3.0,
            critical_density_people_per_m2=5.0,
            alert_persistence_sec=10.0,
        )
    )
    # Zone: 10 m² area
    zone = ZoneConfig(
        id="ZONE_01",
        name="Plaza Zone",
        zone_type="CROWD",
        polygon=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
    )
    setattr(zone, "surface_area_m2", 10.0)

    # 5 people in 10 m² = 0.5 people/m² (below 3.0 warning)
    tracks = _create_people_tracks(5)
    events, telemetry = detector.evaluate([zone], [], tracks, timestamp=100.0)

    assert len(events) == 0
    assert "ZONE_01" in telemetry
    result = telemetry["ZONE_01"]
    assert result.people_count == 5
    assert result.density_people_per_m2 == pytest.approx(0.5)
    assert result.severity_level == "NORMAL"
    assert result.is_alert is False


def test_crowd_density_warning_level_and_persistence():
    detector = CrowdDensityDetector(
        CrowdDensityConfig(
            warning_density_people_per_m2=3.0,
            critical_density_people_per_m2=5.0,
            alert_persistence_sec=10.0,
            suppression_cooldown_sec=30.0,
        )
    )
    zone = ZoneConfig(
        id="ZONE_01",
        name="Concourse",
        zone_type="CROWD",
        polygon=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
    )
    setattr(zone, "surface_area_m2", 10.0)

    # 35 people in 10 m² = 3.5 people/m² (WARNING level)
    tracks = _create_people_tracks(35)

    # Tick 1: t=100.0 -> Density exceeds warning, but duration = 0s (< 10s) -> No event
    events_t1, _ = detector.evaluate([zone], [], tracks, timestamp=100.0)
    assert len(events_t1) == 0

    # Tick 2: t=105.0 -> Duration = 5s (< 10s) -> No event
    events_t2, _ = detector.evaluate([zone], [], tracks, timestamp=105.0)
    assert len(events_t2) == 0

    # Tick 3: t=110.5 -> Duration = 10.5s (>= 10s persistence) -> Alert fired!
    events_t3, telemetry = detector.evaluate([zone], [], tracks, timestamp=110.5)
    assert len(events_t3) == 1
    ev = events_t3[0]
    assert ev.rule_type == "CROWD_DENSITY"
    assert ev.severity == "WARNING"
    assert ev.details["people_count"] == 35
    assert ev.details["density_people_per_m2"] == pytest.approx(3.5)

    # Tick 4: t=115.0 -> Suppressed within 30s cooldown
    events_t4, _ = detector.evaluate([zone], [], tracks, timestamp=115.0)
    assert len(events_t4) == 0


def test_crowd_density_critical_level():
    detector = CrowdDensityDetector(
        CrowdDensityConfig(
            warning_density_people_per_m2=3.0,
            critical_density_people_per_m2=5.0,
            alert_persistence_sec=5.0,
        )
    )
    zone = ZoneConfig(
        id="ZONE_02",
        name="Turnstile Gate",
        zone_type="CROWD",
        polygon=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
    )
    setattr(zone, "surface_area_m2", 10.0)

    # 55 people in 10 m² = 5.5 people/m² (CRITICAL level)
    tracks = _create_people_tracks(55)

    # Initial frame
    detector.evaluate([zone], [], tracks, timestamp=200.0)

    # After persistence duration
    events, telemetry = detector.evaluate([zone], [], tracks, timestamp=206.0)
    assert len(events) == 1
    assert events[0].severity == "CRITICAL"
    assert telemetry["ZONE_02"].severity_level == "CRITICAL"
    assert telemetry["ZONE_02"].density_people_per_m2 == pytest.approx(5.5)


def test_crowd_density_spatial_clustering():
    detector = CrowdDensityDetector(CrowdDensityConfig(cluster_distance_norm=0.10))
    zone = ZoneConfig(
        id="ZONE_GLOBAL",
        name="Full Hall",
        zone_type="CROWD",
        polygon=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
    )
    setattr(zone, "surface_area_m2", 20.0)

    # Cluster 1 (Left): 4 people near x=0.1
    # Cluster 2 (Right): 3 people near x=0.8
    tracks = []
    for i in range(4):
        tracks.append(MockTrack(i + 1, "person", 0.9, (0.10 + i * 0.02, 0.20, 0.05, 0.15)))
    for i in range(3):
        tracks.append(MockTrack(i + 10, "person", 0.9, (0.80 + i * 0.02, 0.80, 0.05, 0.15)))

    _, telemetry = detector.evaluate([zone], [], tracks, timestamp=300.0)
    result = telemetry["ZONE_GLOBAL"]
    assert result.people_count == 7
    assert result.clusters_count == 2
    assert len(result.clusters) == 2
