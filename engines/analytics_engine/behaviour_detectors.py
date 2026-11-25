"""
Advanced Behaviour Analytics Detectors for Video Surveillance (Phase 8).
Implements:
- F-035: Crowd Density and Occupancy Estimation
- F-036: Stationary, Abandoned and Removed Objects with Owner Association
- F-037: Fall Detection and Posture Analysis (Pose/Keypoint heuristics with fallback)
- F-038: Directional Trajectory and Wrong-Way Movement Detection
- F-039: Advanced Behaviour Rule Engine with AND/OR Conditions and Scheduling
"""

import time
import math
from typing import Dict, List, Tuple, Optional, Set, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import defaultdict, deque

from engines.analytics_engine.geometry import (
    point_in_polygon,
    box_bottom_center,
    box_center,
    euclidean_distance,
    trajectory_heading_angle,
    angular_difference,
    polygon_area,
    box_aspect_ratio,
    cluster_points,
)
from engines.analytics_engine.rule_evaluator import (
    ZoneConfig,
    AnalyticsRuleConfig,
    AnalyticsEventData,
)
from core.logging.logger import get_logger

logger = get_logger("behaviour_detectors")


# =========================================================================
# F-035: CROWD DENSITY AND OCCUPANCY ESTIMATION
# =========================================================================

@dataclass
class CrowdDensityConfig:
    """Configurable parameters for Crowd Density Estimation."""
    warning_density_people_per_m2: float = 3.0
    critical_density_people_per_m2: float = 5.0
    alert_persistence_sec: float = 10.0
    suppression_cooldown_sec: float = 30.0
    default_zone_area_m2: float = 20.0  # Calibrated physical surface area if zone has no metadata
    cluster_distance_norm: float = 0.08  # Max normalized distance between people to form a crowd cluster
    min_people_for_crowd: int = 3
    is_active: bool = True


@dataclass
class CrowdDensityResult:
    """Real-time crowd analysis telemetry."""
    people_count: int
    estimated_area_m2: float
    density_people_per_m2: float
    severity_level: str  # "NORMAL", "WARNING", "CRITICAL"
    clusters_count: int
    clusters: List[Dict[str, Any]]
    is_alert: bool
    evidence_details: Dict[str, Any]


class CrowdDensityDetector:
    """
    Evaluates crowd density and spatial clustering in defined zones or whole scene.
    Enforces a persistence timer (default 10s) before firing alerts to filter transient spikes.
    """

    def __init__(self, config: Optional[CrowdDensityConfig] = None) -> None:
        self.config = config or CrowdDensityConfig()
        # zone_id -> timestamp when density first entered WARNING or CRITICAL
        self._warning_start_time: Dict[str, float] = {}
        self._critical_start_time: Dict[str, float] = {}
        # (zone_id, severity) -> last_alert_time
        self._last_alert_time: Dict[Tuple[str, str], float] = {}

    def evaluate(
        self,
        zones: List[ZoneConfig],
        rules: List[AnalyticsRuleConfig],
        tracked_objects: List[Any],
        timestamp: float,
    ) -> Tuple[List[AnalyticsEventData], Dict[str, CrowdDensityResult]]:
        events: List[AnalyticsEventData] = []
        telemetry: Dict[str, CrowdDensityResult] = {}

        # Filter person tracks
        person_tracks = [
            t for t in tracked_objects
            if getattr(t, "class_name", "").lower() == "person"
            and getattr(t, "confidence", 1.0) >= 0.35
        ]

        active_zones = [z for z in zones if z.is_active and z.zone_type in ("CROWD", "INTRUSION", "LOITERING", "COUNTING")]
        if not active_zones:
            # Default to virtual full-frame zone
            active_zones = [
                ZoneConfig(
                    id="GLOBAL_ZONE",
                    name="Global Scene",
                    zone_type="CROWD",
                    polygon=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
                )
            ]

        for zone in active_zones:
            # Find people inside zone
            people_in_zone = []
            positions = []
            for track in person_tracks:
                pos = box_bottom_center(track.bbox)
                if point_in_polygon(pos, zone.polygon):
                    people_in_zone.append(track)
                    positions.append(pos)

            people_count = len(people_in_zone)

            # Compute calibrated surface area (m²)
            poly_norm_area = polygon_area(zone.polygon)
            # Default scale: normalized 1.0 area corresponds to 100 m² unless overridden
            estimated_area = getattr(zone, "surface_area_m2", None) or max(1.0, poly_norm_area * 100.0)

            # Compute density
            density = people_count / max(1.0, estimated_area)

            # Spatial clustering
            clusters_idx = cluster_points(positions, max_distance=self.config.cluster_distance_norm)
            cluster_telemetry = []
            for c_indices in clusters_idx:
                c_points = [positions[idx] for idx in c_indices]
                c_cx = sum(p[0] for p in c_points) / len(c_points)
                c_cy = sum(p[1] for p in c_points) / len(c_points)
                cluster_telemetry.append({
                    "count": len(c_points),
                    "centroid": [round(c_cx, 4), round(c_cy, 4)],
                })

            # Determine severity
            severity_level = "NORMAL"
            if density >= self.config.critical_density_people_per_m2 and people_count >= self.config.min_people_for_crowd:
                severity_level = "CRITICAL"
            elif density >= self.config.warning_density_people_per_m2 and people_count >= self.config.min_people_for_crowd:
                severity_level = "WARNING"

            # Persistence tracking
            is_alert = False
            triggered_severity = None

            if severity_level == "CRITICAL":
                if zone.id not in self._critical_start_time:
                    self._critical_start_time[zone.id] = timestamp
                duration = timestamp - self._critical_start_time[zone.id]
                if duration >= self.config.alert_persistence_sec:
                    is_alert = True
                    triggered_severity = "CRITICAL"
            else:
                self._critical_start_time.pop(zone.id, None)

            if severity_level in ("WARNING", "CRITICAL") and not is_alert:
                if zone.id not in self._warning_start_time:
                    self._warning_start_time[zone.id] = timestamp
                duration = timestamp - self._warning_start_time[zone.id]
                if duration >= self.config.alert_persistence_sec:
                    is_alert = True
                    triggered_severity = "WARNING"
            elif severity_level == "NORMAL":
                self._warning_start_time.pop(zone.id, None)

            evidence = {
                "zone_id": zone.id,
                "zone_name": zone.name,
                "people_count": people_count,
                "estimated_area_m2": round(estimated_area, 2),
                "density_people_per_m2": round(density, 2),
                "severity_level": severity_level,
                "warning_threshold": self.config.warning_density_people_per_m2,
                "critical_threshold": self.config.critical_density_people_per_m2,
                "persistence_duration_sec": round(
                    timestamp - self._critical_start_time.get(zone.id, self._warning_start_time.get(zone.id, timestamp)), 2
                ),
                "clusters_count": len(clusters_idx),
                "clusters": cluster_telemetry,
            }

            telemetry[zone.id] = CrowdDensityResult(
                people_count=people_count,
                estimated_area_m2=estimated_area,
                density_people_per_m2=density,
                severity_level=severity_level,
                clusters_count=len(clusters_idx),
                clusters=cluster_telemetry,
                is_alert=is_alert,
                evidence_details=evidence,
            )

            # Fire event if alert and cooldown elapsed
            if is_alert and triggered_severity:
                alert_key = (zone.id, triggered_severity)
                last_time = self._last_alert_time.get(alert_key)
                if last_time is None or (timestamp - last_time) >= self.config.suppression_cooldown_sec:
                    self._last_alert_time[alert_key] = timestamp
                    # Find matching rule or generate default
                    matching_rule = next(
                        (r for r in rules if r.is_active and r.rule_type in ("CROWD_DENSITY", "OCCUPANCY") and (not r.zone_id or r.zone_id == zone.id)),
                        None
                    )
                    rule_id = matching_rule.id if matching_rule else None
                    rule_name = matching_rule.name if matching_rule else f"Crowd Alert: {zone.name}"
                    channel_id = matching_rule.channel_id if matching_rule else "CH-01"

                    events.append(
                        AnalyticsEventData(
                            channel_id=channel_id,
                            rule_id=rule_id,
                            rule_name=rule_name,
                            rule_type="CROWD_DENSITY",
                            severity=triggered_severity,
                            track_id=None,
                            class_name="crowd",
                            confidence=min(1.0, density / self.config.critical_density_people_per_m2),
                            details=evidence,
                            timestamp=timestamp,
                        )
                    )

        return events, telemetry

    def reset(self) -> None:
        self._warning_start_time.clear()
        self._critical_start_time.clear()
        self._last_alert_time.clear()


# =========================================================================
# F-036: STATIONARY, ABANDONED & REMOVED OBJECT DETECTOR
# =========================================================================

@dataclass
class StationaryObjectConfig:
    """Configurable parameters for Abandoned and Removed Object Detection."""
    stationary_dwell_sec: float = 60.0  # Time stationary before flagging as abandoned
    owner_separation_distance_m: float = 3.0  # Physical meters
    owner_separation_dist_norm: float = 0.15  # Normalized screen distance equivalent to ~3m
    owner_separation_duration_sec: float = 30.0  # Duration owner is away before flagging unattended
    removed_confirmation_sec: float = 5.0  # Duration missing before confirming removed/theft
    stationary_displacement_threshold: float = 0.025  # Max movement in normalized coordinates to be stationary
    suppression_cooldown_sec: float = 30.0
    target_classes: List[str] = field(default_factory=lambda: [
        "backpack", "handbag", "suitcase", "package", "box", "bicycle", "car", "truck"
    ])
    is_active: bool = True


@dataclass
class StationaryCandidate:
    track_id: int
    class_name: str
    confidence: float
    initial_bbox: Tuple[float, float, float, float]
    initial_pos: Tuple[float, float]
    first_seen: float
    first_stationary_time: float
    last_seen: float
    owner_track_id: Optional[int] = None
    owner_separated_start_time: Optional[float] = None
    unattended_alert_fired: bool = False
    abandoned_alert_fired: bool = False
    removed_start_time: Optional[float] = None
    removed_alert_fired: bool = False


class StationaryObjectDetector:
    """
    Detects stationary objects, associates nearby owners, monitors owner separation distance,
    flags unattended / abandoned items, and detects missing / removed objects.
    """

    def __init__(self, config: Optional[StationaryObjectConfig] = None) -> None:
        self.config = config or StationaryObjectConfig()
        # track_id -> StationaryCandidate
        self._candidates: Dict[int, StationaryCandidate] = {}
        # (track_id, alert_type) -> last_alert_time
        self._last_alert_time: Dict[Tuple[int, str], float] = {}

    def evaluate(
        self,
        zones: List[ZoneConfig],
        rules: List[AnalyticsRuleConfig],
        tracked_objects: List[Any],
        timestamp: float,
    ) -> List[AnalyticsEventData]:
        events: List[AnalyticsEventData] = []
        active_tracks_by_id = {t.track_id: t for t in tracked_objects}
        target_classes_lower = [c.lower() for c in self.config.target_classes]

        # Separate persons from candidate objects
        person_tracks = [
            t for t in tracked_objects
            if getattr(t, "class_name", "").lower() == "person"
        ]

        # 1. Update / Register candidate objects
        for track in tracked_objects:
            t_id = track.track_id
            c_name = getattr(track, "class_name", "").lower()
            if c_name not in target_classes_lower:
                continue

            curr_pos = box_center(track.bbox)

            if t_id not in self._candidates:
                # Associate nearby person as owner if within proximity
                associated_owner = None
                closest_dist = float("inf")
                for p in person_tracks:
                    p_pos = box_bottom_center(p.bbox)
                    d = euclidean_distance(curr_pos, p_pos)
                    if d <= self.config.owner_separation_dist_norm and d < closest_dist:
                        closest_dist = d
                        associated_owner = p.track_id

                self._candidates[t_id] = StationaryCandidate(
                    track_id=t_id,
                    class_name=c_name,
                    confidence=track.confidence,
                    initial_bbox=track.bbox,
                    initial_pos=curr_pos,
                    first_seen=timestamp,
                    first_stationary_time=timestamp,
                    last_seen=timestamp,
                    owner_track_id=associated_owner,
                )
            else:
                cand = self._candidates[t_id]
                cand.last_seen = timestamp
                # Check if still stationary
                dist_moved = euclidean_distance(curr_pos, cand.initial_pos)
                if dist_moved > self.config.stationary_displacement_threshold:
                    # Object has moved; reset stationary timer
                    cand.first_stationary_time = timestamp
                    cand.initial_pos = curr_pos
                    cand.initial_bbox = track.bbox
                    cand.unattended_alert_fired = False
                    cand.abandoned_alert_fired = False

        # 2. Evaluate owner proximity and stationary dwell
        for cand_id, cand in list(self._candidates.items()):
            if cand_id in active_tracks_by_id:
                # Candidate is currently detected
                cand.removed_start_time = None  # Reset removed timer
                stationary_duration = timestamp - cand.first_stationary_time

                # Check owner proximity if owner is known
                owner_distance = None
                if cand.owner_track_id is not None:
                    owner_track = active_tracks_by_id.get(cand.owner_track_id)
                    if owner_track:
                        owner_pos = box_bottom_center(owner_track.bbox)
                        owner_distance = euclidean_distance(cand.initial_pos, owner_pos)

                        if owner_distance > self.config.owner_separation_dist_norm:
                            if cand.owner_separated_start_time is None:
                                cand.owner_separated_start_time = timestamp
                        else:
                            cand.owner_separated_start_time = None
                    else:
                        # Owner has left the camera view
                        if cand.owner_separated_start_time is None:
                            cand.owner_separated_start_time = timestamp

                # Check UNATTENDED condition (owner separated >= 30s)
                if cand.owner_separated_start_time is not None:
                    separated_duration = timestamp - cand.owner_separated_start_time
                    if (
                        separated_duration >= self.config.owner_separation_duration_sec
                        and not cand.unattended_alert_fired
                    ):
                        cand.unattended_alert_fired = True
                        evidence = {
                            "object_track_id": cand.track_id,
                            "class_name": cand.class_name,
                            "stationary_duration_sec": round(stationary_duration, 1),
                            "owner_track_id": cand.owner_track_id,
                            "owner_separated_duration_sec": round(separated_duration, 1),
                            "owner_distance_norm": round(owner_distance or 1.0, 3),
                            "position": list(cand.initial_pos),
                            "action": "OWNER_SEPARATION",
                        }
                        events.append(
                            AnalyticsEventData(
                                channel_id="CH-01",
                                rule_id=None,
                                rule_name=f"Unattended Object: {cand.class_name}",
                                rule_type="UNATTENDED_OBJECT",
                                severity="WARNING",
                                track_id=cand.track_id,
                                class_name=cand.class_name,
                                confidence=cand.confidence,
                                dwell_time_sec=stationary_duration,
                                details=evidence,
                                timestamp=timestamp,
                            )
                        )

                # Check ABANDONED condition (stationary >= 60s)
                if (
                    stationary_duration >= self.config.stationary_dwell_sec
                    and not cand.abandoned_alert_fired
                ):
                    cand.abandoned_alert_fired = True
                    evidence = {
                        "object_track_id": cand.track_id,
                        "class_name": cand.class_name,
                        "stationary_duration_sec": round(stationary_duration, 1),
                        "owner_track_id": cand.owner_track_id,
                        "position": list(cand.initial_pos),
                        "action": "ABANDONED_OBJECT",
                        "dwell_threshold_sec": self.config.stationary_dwell_sec,
                    }
                    events.append(
                        AnalyticsEventData(
                            channel_id="CH-01",
                            rule_id=None,
                            rule_name=f"Abandoned Object: {cand.class_name}",
                            rule_type="ABANDONED_OBJECT",
                            severity="CRITICAL",
                            track_id=cand.track_id,
                            class_name=cand.class_name,
                            confidence=cand.confidence,
                            dwell_time_sec=stationary_duration,
                            details=evidence,
                            timestamp=timestamp,
                        )
                    )

            else:
                # 3. Object was stationary and has now disappeared: check for REMOVED / THEFT
                stationary_prior = cand.last_seen - cand.first_stationary_time
                if stationary_prior >= 10.0 and not cand.removed_alert_fired:
                    if cand.removed_start_time is None:
                        cand.removed_start_time = timestamp
                    removed_duration = timestamp - cand.removed_start_time

                    if removed_duration >= self.config.removed_confirmation_sec:
                        cand.removed_alert_fired = True
                        evidence = {
                            "object_track_id": cand.track_id,
                            "class_name": cand.class_name,
                            "was_stationary_for_sec": round(stationary_prior, 1),
                            "missing_duration_sec": round(removed_duration, 1),
                            "last_known_position": list(cand.initial_pos),
                            "action": "OBJECT_REMOVED",
                        }
                        events.append(
                            AnalyticsEventData(
                                channel_id="CH-01",
                                rule_id=None,
                                rule_name=f"Removed Object: {cand.class_name}",
                                rule_type="REMOVED_OBJECT",
                                severity="CRITICAL",
                                track_id=cand.track_id,
                                class_name=cand.class_name,
                                confidence=cand.confidence,
                                details=evidence,
                                timestamp=timestamp,
                            )
                        )

        # Cleanup very stale candidates (> 120s missing)
        stale_ids = [
            c_id for c_id, c in self._candidates.items()
            if c_id not in active_tracks_by_id and (timestamp - c.last_seen) > 120.0
        ]
        for s_id in stale_ids:
            del self._candidates[s_id]

        return events

    def reset(self) -> None:
        self._candidates.clear()
        self._last_alert_time.clear()


# =========================================================================
# F-037: FALL DETECTION AND POSTURE ANALYSIS
# =========================================================================

@dataclass
class FallDetectionConfig:
    """Configurable parameters for Fall Detection."""
    rapid_descent_window_sec: float = 1.5  # Window to measure downward velocity
    min_vertical_descent_delta: float = 0.08  # Normalized y downward shift
    prone_confirmation_sec: float = 3.0  # Dwell time in prone posture before alert
    aspect_ratio_inversion_threshold: float = 1.2  # w/h >= 1.2 indicates prone / lying down
    confidence_threshold: float = 0.60
    suppression_cooldown_sec: float = 30.0
    requires_human_review: bool = True
    is_active: bool = True


@dataclass
class FallCandidate:
    track_id: int
    history: deque = field(default_factory=lambda: deque(maxlen=60))  # [(timestamp, bbox, y_centroid, aspect_ratio)]
    descent_detected: bool = False
    descent_timestamp: float = 0.0
    pre_fall_y: float = 0.0
    post_fall_y: float = 0.0
    prone_start_time: Optional[float] = None
    alert_fired: bool = False


class FallDetector:
    """
    Detects potential human falls using geometric posture analysis, rapid vertical descent
    velocity, and sustained prone immobility.
    Includes explicit explainable evidence and mandatory human review requirement.
    """

    def __init__(self, config: Optional[FallDetectionConfig] = None) -> None:
        self.config = config or FallDetectionConfig()
        # track_id -> FallCandidate
        self._candidates: Dict[int, FallCandidate] = {}
        # track_id -> last_alert_time
        self._last_alert_time: Dict[int, float] = {}

    def evaluate(
        self,
        zones: List[ZoneConfig],
        rules: List[AnalyticsRuleConfig],
        tracked_objects: List[Any],
        timestamp: float,
    ) -> List[AnalyticsEventData]:
        events: List[AnalyticsEventData] = []
        active_person_ids = set()

        for track in tracked_objects:
            if getattr(track, "class_name", "").lower() != "person":
                continue

            t_id = track.track_id
            active_person_ids.add(t_id)
            bbox = track.bbox
            x, y, w, h = bbox
            y_center = y + (h / 2.0)
            aspect_ratio = box_aspect_ratio(bbox)

            if t_id not in self._candidates:
                self._candidates[t_id] = FallCandidate(track_id=t_id)

            cand = self._candidates[t_id]
            cand.history.append((timestamp, bbox, y_center, aspect_ratio))

            # 1. Evaluate rapid downward descent
            if not cand.descent_detected and len(cand.history) >= 2:
                # Look back within rapid descent window
                oldest_entry = None
                for hist_t, hist_b, hist_y, hist_ar in cand.history:
                    if (timestamp - hist_t) <= self.config.rapid_descent_window_sec:
                        oldest_entry = (hist_t, hist_y, hist_ar)
                        break

                if oldest_entry:
                    pre_t, pre_y, pre_ar = oldest_entry
                    delta_y = y_center - pre_y  # Positive means moving down in image coords
                    dt = max(0.1, timestamp - pre_t)
                    descent_velocity = delta_y / dt

                    # Trigger descent if downward shift is rapid and started from upright posture (ar < 1.0)
                    if (
                        delta_y >= self.config.min_vertical_descent_delta
                        and pre_ar < 1.0
                        and descent_velocity >= (self.config.min_vertical_descent_delta / self.config.rapid_descent_window_sec)
                    ):
                        cand.descent_detected = True
                        cand.descent_timestamp = timestamp
                        cand.pre_fall_y = pre_y
                        cand.post_fall_y = y_center

            # 2. Evaluate prone posture confirmation
            if cand.descent_detected:
                is_prone = aspect_ratio >= self.config.aspect_ratio_inversion_threshold
                if is_prone:
                    if cand.prone_start_time is None:
                        cand.prone_start_time = timestamp

                    prone_duration = timestamp - cand.prone_start_time

                    if (
                        prone_duration >= self.config.prone_confirmation_sec
                        and not cand.alert_fired
                    ):
                        # Calculate explainable confidence score
                        v_shift = max(0.0, cand.post_fall_y - cand.pre_fall_y)
                        norm_shift_score = min(1.0, v_shift / 0.15)
                        aspect_score = min(1.0, (aspect_ratio - 1.0) / 0.8)
                        prone_score = min(1.0, prone_duration / 5.0)
                        fall_confidence = (0.4 * norm_shift_score) + (0.3 * aspect_score) + (0.3 * prone_score)

                        if fall_confidence >= self.config.confidence_threshold:
                            last_alert = self._last_alert_time.get(t_id)
                            if last_alert is None or (timestamp - last_alert) >= self.config.suppression_cooldown_sec:
                                cand.alert_fired = True
                                self._last_alert_time[t_id] = timestamp

                                evidence = {
                                    "track_id": t_id,
                                    "rapid_descent_delta_y": round(v_shift, 4),
                                    "descent_velocity_norm_per_sec": round(v_shift / max(0.1, timestamp - cand.descent_timestamp), 3),
                                    "aspect_ratio": round(aspect_ratio, 2),
                                    "prone_duration_sec": round(prone_duration, 1),
                                    "composite_confidence": round(fall_confidence, 3),
                                    "requires_human_review": self.config.requires_human_review,
                                    "disclaimer": "AI fall suspicion alert; requires human operator confirmation.",
                                    "position": list(box_bottom_center(bbox)),
                                }

                                events.append(
                                    AnalyticsEventData(
                                        channel_id="CH-01",
                                        rule_id=None,
                                        rule_name="Fall Alert: Person Down",
                                        rule_type="FALL_DETECTION",
                                        severity="CRITICAL",
                                        track_id=t_id,
                                        class_name="person",
                                        confidence=fall_confidence,
                                        dwell_time_sec=prone_duration,
                                        details=evidence,
                                        timestamp=timestamp,
                                    )
                                )
                else:
                    # Person stood back up or recovered
                    if (timestamp - cand.descent_timestamp) > 5.0:
                        cand.descent_detected = False
                        cand.prone_start_time = None
                        cand.alert_fired = False

        # Cleanup removed person tracks
        stale_ids = set(self._candidates.keys()) - active_person_ids
        for s_id in stale_ids:
            del self._candidates[s_id]

        return events

    def reset(self) -> None:
        self._candidates.clear()
        self._last_alert_time.clear()


# =========================================================================
# F-038: DIRECTIONAL TRAJECTORY & WRONG-WAY DETECTOR
# =========================================================================

@dataclass
class DirectionalConfig:
    """Configurable parameters for Directional and Wrong-Way Analysis."""
    allowed_angle_deg: float = 0.0  # Permitted direction (0° = East, 90° = South, 180° = West, 270° = North)
    tolerance_deg: float = 30.0  # Permitted angle tolerance (±30°)
    min_trajectory_displacement_norm: float = 0.05  # Normalized displacement (~1.5m) to ignore jitter
    confirmation_duration_sec: float = 2.0  # Duration wrong-way travel must be sustained
    suppression_cooldown_sec: float = 30.0
    target_classes: List[str] = field(default_factory=lambda: [
        "person", "car", "bus", "truck", "motorcycle", "bicycle"
    ])
    is_active: bool = True


@dataclass
class TrajectorySession:
    track_id: int
    class_name: str
    positions: deque = field(default_factory=lambda: deque(maxlen=60))  # [(timestamp, (x, y))]
    wrong_way_start_time: Optional[float] = None
    alert_fired: bool = False


class DirectionalDetector:
    """
    Evaluates trajectory heading angles and detects wrong-way movement in one-way corridors,
    exit lanes, entry doors, and restricted flow paths.
    """

    def __init__(self, config: Optional[DirectionalConfig] = None) -> None:
        self.config = config or DirectionalConfig()
        # track_id -> TrajectorySession
        self._sessions: Dict[int, TrajectorySession] = {}
        # track_id -> last_alert_time
        self._last_alert_time: Dict[int, float] = {}

    def evaluate(
        self,
        zones: List[ZoneConfig],
        rules: List[AnalyticsRuleConfig],
        tracked_objects: List[Any],
        timestamp: float,
    ) -> List[AnalyticsEventData]:
        events: List[AnalyticsEventData] = []
        active_track_ids = set()
        target_classes_lower = [c.lower() for c in self.config.target_classes]

        for track in tracked_objects:
            c_name = getattr(track, "class_name", "").lower()
            if c_name not in target_classes_lower:
                continue

            t_id = track.track_id
            active_track_ids.add(t_id)
            curr_pos = box_bottom_center(track.bbox)

            if t_id not in self._sessions:
                self._sessions[t_id] = TrajectorySession(track_id=t_id, class_name=c_name)

            sess = self._sessions[t_id]
            sess.positions.append((timestamp, curr_pos))

            if len(sess.positions) < 2:
                continue

            # Compute displacement and heading over trajectory
            # Find earliest position within last 3 seconds
            earliest_pos = None
            for p_time, p_coord in sess.positions:
                if (timestamp - p_time) <= 3.0:
                    earliest_pos = p_coord
                    break

            if earliest_pos is None:
                earliest_pos = sess.positions[0][1]

            total_displacement = euclidean_distance(earliest_pos, curr_pos)
            if total_displacement < self.config.min_trajectory_displacement_norm:
                # Stationary or jittering; reset wrong-way duration
                sess.wrong_way_start_time = None
                continue

            heading = trajectory_heading_angle(earliest_pos, curr_pos)
            angular_dev = angular_difference(heading, self.config.allowed_angle_deg)

            # A wrong-way motion is when heading deviates beyond allowed tolerance
            # e.g. If allowed is 0° (East), tolerance ±30°: angles 330°-360° and 0°-30° are valid.
            # Heading opposite or diverging (angular_dev > 180° - tolerance or angular_dev > 90°)
            is_wrong_way = angular_dev > (180.0 - self.config.tolerance_deg) or (angular_dev > 90.0)

            if is_wrong_way:
                if sess.wrong_way_start_time is None:
                    sess.wrong_way_start_time = timestamp

                wrong_way_duration = timestamp - sess.wrong_way_start_time

                if (
                    wrong_way_duration >= self.config.confirmation_duration_sec
                    and not sess.alert_fired
                ):
                    last_alert = self._last_alert_time.get(t_id)
                    if last_alert is None or (timestamp - last_alert) >= self.config.suppression_cooldown_sec:
                        sess.alert_fired = True
                        self._last_alert_time[t_id] = timestamp

                        evidence = {
                            "track_id": t_id,
                            "class_name": c_name,
                            "heading_angle_deg": round(heading, 1),
                            "allowed_angle_deg": round(self.config.allowed_angle_deg, 1),
                            "angular_deviation_deg": round(angular_dev, 1),
                            "trajectory_displacement_norm": round(total_displacement, 4),
                            "wrong_way_duration_sec": round(wrong_way_duration, 1),
                            "current_position": list(curr_pos),
                        }

                        events.append(
                            AnalyticsEventData(
                                channel_id="CH-01",
                                rule_id=None,
                                rule_name=f"Wrong-Way Movement: {c_name}",
                                rule_type="WRONG_WAY",
                                severity="WARNING",
                                track_id=t_id,
                                class_name=c_name,
                                confidence=track.confidence,
                                crossing_direction=f"HEADING_{round(heading)}",
                                details=evidence,
                                timestamp=timestamp,
                            )
                        )
            else:
                sess.wrong_way_start_time = None
                sess.alert_fired = False

        # Cleanup disappeared tracks
        stale_ids = set(self._sessions.keys()) - active_track_ids
        for s_id in stale_ids:
            del self._sessions[s_id]

        return events

    def reset(self) -> None:
        self._sessions.clear()
        self._last_alert_time.clear()


# =========================================================================
# F-039: ADVANCED BEHAVIOUR RULE ENGINE & COMPOSITE LOGIC
# =========================================================================

@dataclass
class BehaviourRuleConfig:
    """Configurable composite behaviour rule."""
    id: str
    name: str
    channel_id: str
    rule_type: str  # CROWD_DENSITY, ABANDONED_OBJECT, FALL_DETECTION, WRONG_WAY, COMPOSITE
    conditions: List[Dict[str, Any]] = field(default_factory=list)  # [{"type": "INTRUSION", "zone_id": "..."}, ...]
    logical_operator: str = "AND"  # "AND" or "OR"
    severity: str = "WARNING"  # INFO, WARNING, CRITICAL
    schedule: Optional[Dict[str, Any]] = None
    trigger_recording: bool = True
    suppression_cooldown_sec: float = 30.0
    is_active: bool = True

    def is_schedule_active(self, timestamp: Optional[float] = None) -> bool:
        if not self.schedule:
            return True
        ts = timestamp or time.time()
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        allowed_days = self.schedule.get("days", list(range(7)))
        if dt.weekday() not in allowed_days:
            return False
        start_str = self.schedule.get("start_time", "00:00")
        end_str = self.schedule.get("end_time", "23:59")
        cur_str = dt.strftime("%H:%M")
        return start_str <= cur_str <= end_str


class BehaviourAnalyticsManager:
    """
    Central coordinator managing CrowdDensity, StationaryObject, Fall, and Directional detectors.
    Supports composite AND/OR rule evaluation per channel.
    """

    def __init__(self, channel_id: str) -> None:
        self.channel_id = channel_id
        self.crowd_detector = CrowdDensityDetector()
        self.stationary_detector = StationaryObjectDetector()
        self.fall_detector = FallDetector()
        self.directional_detector = DirectionalDetector()
        self.rules: Dict[str, BehaviourRuleConfig] = {}
        self._last_rule_alert: Dict[str, float] = {}

    def add_rule(self, rule: BehaviourRuleConfig) -> None:
        self.rules[rule.id] = rule

    def remove_rule(self, rule_id: str) -> None:
        self.rules.pop(rule_id, None)

    def evaluate_frame(
        self,
        zones: List[ZoneConfig],
        tracked_objects: List[Any],
        timestamp: Optional[float] = None,
    ) -> List[AnalyticsEventData]:
        ts = timestamp or time.time()
        all_events: List[AnalyticsEventData] = []

        # 1. Evaluate underlying detectors
        crowd_events, _ = self.crowd_detector.evaluate(zones, [], tracked_objects, ts)
        stat_events = self.stationary_detector.evaluate(zones, [], tracked_objects, ts)
        fall_events = self.fall_detector.evaluate(zones, [], tracked_objects, ts)
        dir_events = self.directional_detector.evaluate(zones, [], tracked_objects, ts)

        all_events.extend(crowd_events)
        all_events.extend(stat_events)
        all_events.extend(fall_events)
        all_events.extend(dir_events)

        # 2. Evaluate composite rules
        for rule in self.rules.values():
            if not rule.is_active or not rule.is_schedule_active(ts):
                continue

            last_alert = self._last_rule_alert.get(rule.id)
            if last_alert is not None and (ts - last_alert) < rule.suppression_cooldown_sec:
                continue

            if rule.rule_type == "COMPOSITE" and rule.conditions:
                # Check condition matches against emitted event types
                cond_matches = []
                for cond in rule.conditions:
                    c_type = cond.get("type")
                    matched = any(ev.rule_type == c_type for ev in all_events)
                    cond_matches.append(matched)

                is_triggered = (
                    all(cond_matches) if rule.logical_operator == "AND" else any(cond_matches)
                )

                if is_triggered:
                    self._last_rule_alert[rule.id] = ts
                    all_events.append(
                        AnalyticsEventData(
                            channel_id=self.channel_id,
                            rule_id=rule.id,
                            rule_name=rule.name,
                            rule_type="COMPOSITE_BEHAVIOUR",
                            severity=rule.severity,
                            track_id=None,
                            class_name="behaviour",
                            confidence=0.90,
                            details={
                                "rule_name": rule.name,
                                "conditions": rule.conditions,
                                "operator": rule.logical_operator,
                            },
                            timestamp=ts,
                        )
                    )

        # Ensure channel_id is properly tagged on all events
        for ev in all_events:
            ev.channel_id = self.channel_id

        return all_events

    def reset(self) -> None:
        self.crowd_detector.reset()
        self.stationary_detector.reset()
        self.fall_detector.reset()
        self.directional_detector.reset()
        self._last_rule_alert.clear()
