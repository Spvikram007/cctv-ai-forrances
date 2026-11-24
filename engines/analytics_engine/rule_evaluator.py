"""
Rule Evaluators and Detectors for Video Analytics.
Implements Intrusion Detection (F-013), Tripwire Line Crossing (F-014),
Loitering Detection (F-015), People & Vehicle Counting (F-016),
and Movement Heatmap Analytics (F-017).
"""

import time
import json
from typing import Dict, List, Tuple, Optional, Set, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import defaultdict

import cv2
import numpy as np

from engines.analytics_engine.geometry import (
    point_in_polygon,
    line_segments_intersect,
    get_crossing_direction,
    box_bottom_center,
    box_center,
)
from core.logging.logger import get_logger

logger = get_logger("rule_evaluator")


@dataclass
class ZoneConfig:
    id: str
    name: str
    zone_type: str = "INTRUSION"  # INTRUSION, LOITERING, EXCLUSION, COUNTING
    polygon: List[Tuple[float, float]] = field(default_factory=list)  # Normalized [(x, y), ...]
    color_hex: str = "#FF0000"
    is_active: bool = True


@dataclass
class TripwireConfig:
    id: str
    name: str
    pt1: Tuple[float, float] = (0.0, 0.0)  # Normalized (x1, y1)
    pt2: Tuple[float, float] = (1.0, 1.0)  # Normalized (x2, y2)
    direction: str = "BIDIRECTIONAL"  # A_TO_B, B_TO_A, BIDIRECTIONAL
    color_hex: str = "#00FF00"
    is_active: bool = True


@dataclass
class AnalyticsRuleConfig:
    id: str
    name: str
    rule_type: str  # INTRUSION, LINE_CROSSING, LOITERING, COUNTING, OCCUPANCY
    channel_id: str
    zone_id: Optional[str] = None
    tripwire_id: Optional[str] = None
    target_classes: List[str] = field(default_factory=lambda: ["person", "car", "bus", "truck", "motorcycle", "bicycle"])
    confidence_threshold: float = 0.50
    min_dwell_time_sec: float = 5.0
    severity: str = "WARNING"  # INFO, WARNING, CRITICAL
    schedule: Optional[Dict[str, Any]] = None  # e.g. {"days": [0,1,2,3,4,5,6], "start_time": "00:00", "end_time": "23:59"}
    trigger_recording: bool = True
    alarm_sound: bool = False
    is_active: bool = True

    def is_schedule_active(self, timestamp: Optional[float] = None) -> bool:
        """Checks if the rule is currently active according to its schedule."""
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


@dataclass
class AnalyticsEventData:
    channel_id: str
    rule_id: Optional[str]
    rule_name: str
    rule_type: str
    severity: str
    track_id: Optional[int]
    class_name: str
    confidence: float
    dwell_time_sec: float = 0.0
    crossing_direction: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)
    snapshot_path: Optional[str] = None


# =========================================================================
# F-013: INTRUSION DETECTOR
# =========================================================================
class IntrusionDetector:
    """
    Evaluates object intrusions into defined polygon zones.
    Detects entry, continuous containment, and exit events.
    """

    def __init__(self, suppression_window_sec: float = 5.0) -> None:
        self.suppression_window = suppression_window_sec
        # track_id -> set of zone_ids where track is currently inside
        self._track_in_zones: Dict[int, Set[str]] = defaultdict(set)
        # (zone_id, track_id) -> last_event_time
        self._last_event_time: Dict[Tuple[str, int], float] = {}

    def evaluate(
        self,
        zones: List[ZoneConfig],
        rules: List[AnalyticsRuleConfig],
        tracked_objects: List[Any],
        timestamp: float,
    ) -> List[AnalyticsEventData]:
        events: List[AnalyticsEventData] = []
        zone_map = {z.id: z for z in zones if z.is_active}
        active_track_ids = set()

        for track in tracked_objects:
            track_id = track.track_id
            active_track_ids.add(track_id)
            class_name = track.class_name.lower()
            confidence = track.confidence
            point = box_bottom_center(track.bbox)

            for rule in rules:
                if not rule.is_active or rule.rule_type != "INTRUSION":
                    continue
                if not rule.is_schedule_active(timestamp):
                    continue
                if class_name not in [c.lower() for c in rule.target_classes]:
                    continue
                if confidence < rule.confidence_threshold:
                    continue
                if not rule.zone_id or rule.zone_id not in zone_map:
                    continue

                zone = zone_map[rule.zone_id]
                is_inside = point_in_polygon(point, zone.polygon)
                was_inside = zone.id in self._track_in_zones[track_id]

                if is_inside and not was_inside:
                    # New Entry Event
                    self._track_in_zones[track_id].add(zone.id)
                    key = (zone.id, track_id)
                    last_time = self._last_event_time.get(key, 0.0)
                    if (timestamp - last_time) >= self.suppression_window:
                        self._last_event_time[key] = timestamp
                        events.append(
                            AnalyticsEventData(
                                channel_id=rule.channel_id,
                                rule_id=rule.id,
                                rule_name=rule.name,
                                rule_type="INTRUSION",
                                severity=rule.severity,
                                track_id=track_id,
                                class_name=class_name,
                                confidence=confidence,
                                details={
                                    "zone_id": zone.id,
                                    "zone_name": zone.name,
                                    "action": "ENTER",
                                    "position": list(point),
                                },
                                timestamp=timestamp,
                            )
                        )
                elif not is_inside and was_inside:
                    # Exit Event
                    self._track_in_zones[track_id].discard(zone.id)
                    events.append(
                        AnalyticsEventData(
                            channel_id=rule.channel_id,
                            rule_id=rule.id,
                            rule_name=rule.name,
                            rule_type="INTRUSION",
                            severity="INFO",
                            track_id=track_id,
                            class_name=class_name,
                            confidence=confidence,
                            details={
                                "zone_id": zone.id,
                                "zone_name": zone.name,
                                "action": "EXIT",
                                "position": list(point),
                            },
                            timestamp=timestamp,
                        )
                    )

        # Cleanup removed tracks
        stale_tracks = set(self._track_in_zones.keys()) - active_track_ids
        for t_id in stale_tracks:
            del self._track_in_zones[t_id]

        return events

    def reset(self) -> None:
        self._track_in_zones.clear()
        self._last_event_time.clear()


# =========================================================================
# F-014: TRIPWIRE & LINE CROSSING
# =========================================================================
class TripwireDetector:
    """
    Evaluates virtual line crossings with directional classification (A-to-B, B-to-A).
    Guarantees zero duplicate counting per crossing event.
    """

    def __init__(self, suppression_cooldown_sec: float = 10.0) -> None:
        self.suppression_cooldown = suppression_cooldown_sec
        # track_id -> previous bottom-center position
        self._prev_positions: Dict[int, Tuple[float, float]] = {}
        # (tripwire_id, track_id) -> last_crossed_time
        self._crossed_cache: Dict[Tuple[str, int], float] = {}
        # Cumulative counters per line: tripwire_id -> {"A_TO_B": count, "B_TO_A": count, "TOTAL": count}
        self.counters: Dict[str, Dict[str, int]] = defaultdict(lambda: {"A_TO_B": 0, "B_TO_A": 0, "TOTAL": 0})

    def evaluate(
        self,
        tripwires: List[TripwireConfig],
        rules: List[AnalyticsRuleConfig],
        tracked_objects: List[Any],
        timestamp: float,
    ) -> List[AnalyticsEventData]:
        events: List[AnalyticsEventData] = []
        tw_map = {tw.id: tw for tw in tripwires if tw.is_active}
        active_track_ids = set()

        for track in tracked_objects:
            track_id = track.track_id
            active_track_ids.add(track_id)
            class_name = track.class_name.lower()
            confidence = track.confidence
            curr_pos = box_bottom_center(track.bbox)
            prev_pos = self._prev_positions.get(track_id)
            self._prev_positions[track_id] = curr_pos

            if prev_pos is None:
                continue  # Need at least two frames of trajectory

            for rule in rules:
                if not rule.is_active or rule.rule_type != "LINE_CROSSING":
                    continue
                if not rule.is_schedule_active(timestamp):
                    continue
                if class_name not in [c.lower() for c in rule.target_classes]:
                    continue
                if confidence < rule.confidence_threshold:
                    continue
                if not rule.tripwire_id or rule.tripwire_id not in tw_map:
                    continue

                tripwire = tw_map[rule.tripwire_id]
                key = (tripwire.id, track_id)
                last_crossed = self._crossed_cache.get(key, 0.0)
                if (timestamp - last_crossed) < self.suppression_cooldown:
                    continue  # Already crossed and within cooldown

                direction = get_crossing_direction(tripwire.pt1, tripwire.pt2, prev_pos, curr_pos)
                if not direction:
                    continue  # Did not cross this segment

                # Check direction filter
                if tripwire.direction != "BIDIRECTIONAL" and tripwire.direction != direction:
                    continue  # Crossed in opposite direction

                # Register crossing
                self._crossed_cache[key] = timestamp
                self.counters[tripwire.id][direction] += 1
                self.counters[tripwire.id]["TOTAL"] += 1

                events.append(
                    AnalyticsEventData(
                        channel_id=rule.channel_id,
                        rule_id=rule.id,
                        rule_name=rule.name,
                        rule_type="LINE_CROSSING",
                        severity=rule.severity,
                        track_id=track_id,
                        class_name=class_name,
                        confidence=confidence,
                        crossing_direction=direction,
                        details={
                            "tripwire_id": tripwire.id,
                            "tripwire_name": tripwire.name,
                            "direction": direction,
                            "line_start": list(tripwire.pt1),
                            "line_end": list(tripwire.pt2),
                            "prev_pos": list(prev_pos),
                            "curr_pos": list(curr_pos),
                            "line_total_count": self.counters[tripwire.id]["TOTAL"],
                        },
                        timestamp=timestamp,
                    )
                )

        # Cleanup positions of tracks that disappeared
        stale_tracks = set(self._prev_positions.keys()) - active_track_ids
        for t_id in stale_tracks:
            del self._prev_positions[t_id]

        return events

    def reset_counters(self, tripwire_id: Optional[str] = None) -> None:
        if tripwire_id:
            self.counters[tripwire_id] = {"A_TO_B": 0, "B_TO_A": 0, "TOTAL": 0}
        else:
            self.counters.clear()
        self._crossed_cache.clear()


# =========================================================================
# F-015: LOITERING DETECTOR
# =========================================================================
@dataclass
class DwellSession:
    first_seen: float
    last_seen: float
    consecutive_frames: int = 1
    alarm_fired: bool = False


class LoiteringDetector:
    """
    Tracks dwell time of objects inside polygon zones.
    Handles temporary occlusion gracefully without resetting dwell clock prematurely.
    """

    def __init__(self, occlusion_grace_period_sec: float = 2.0, min_consecutive_frames: int = 3) -> None:
        self.occlusion_grace_period = occlusion_grace_period_sec
        self.min_consecutive_frames = min_consecutive_frames
        # (zone_id, track_id) -> DwellSession
        self._sessions: Dict[Tuple[str, int], DwellSession] = {}

    def evaluate(
        self,
        zones: List[ZoneConfig],
        rules: List[AnalyticsRuleConfig],
        tracked_objects: List[Any],
        timestamp: float,
    ) -> List[AnalyticsEventData]:
        events: List[AnalyticsEventData] = []
        zone_map = {z.id: z for z in zones if z.is_active}
        active_zone_tracks: Set[Tuple[str, int]] = set()

        for track in tracked_objects:
            track_id = track.track_id
            class_name = track.class_name.lower()
            confidence = track.confidence
            point = box_bottom_center(track.bbox)

            for rule in rules:
                if not rule.is_active or rule.rule_type != "LOITERING":
                    continue
                if not rule.is_schedule_active(timestamp):
                    continue
                if class_name not in [c.lower() for c in rule.target_classes]:
                    continue
                if confidence < rule.confidence_threshold:
                    continue
                if not rule.zone_id or rule.zone_id not in zone_map:
                    continue

                zone = zone_map[rule.zone_id]
                key = (zone.id, track_id)

                if point_in_polygon(point, zone.polygon):
                    active_zone_tracks.add(key)
                    if key not in self._sessions:
                        self._sessions[key] = DwellSession(first_seen=timestamp, last_seen=timestamp)
                    else:
                        sess = self._sessions[key]
                        sess.last_seen = timestamp
                        sess.consecutive_frames += 1

                        dwell_time = timestamp - sess.first_seen
                        if (
                            sess.consecutive_frames >= self.min_consecutive_frames
                            and dwell_time >= rule.min_dwell_time_sec
                            and not sess.alarm_fired
                        ):
                            sess.alarm_fired = True
                            events.append(
                                AnalyticsEventData(
                                    channel_id=rule.channel_id,
                                    rule_id=rule.id,
                                    rule_name=rule.name,
                                    rule_type="LOITERING",
                                    severity=rule.severity,
                                    track_id=track_id,
                                    class_name=class_name,
                                    confidence=confidence,
                                    dwell_time_sec=round(dwell_time, 1),
                                    details={
                                        "zone_id": zone.id,
                                        "zone_name": zone.name,
                                        "dwell_time_sec": round(dwell_time, 1),
                                        "min_dwell_threshold": rule.min_dwell_time_sec,
                                        "position": list(point),
                                    },
                                    timestamp=timestamp,
                                )
                            )

        # Handle occlusion vs exit for missing tracks
        expired_keys = []
        for key, sess in self._sessions.items():
            if key not in active_zone_tracks:
                if (timestamp - sess.last_seen) > self.occlusion_grace_period:
                    expired_keys.append(key)

        for k in expired_keys:
            del self._sessions[k]

        return events

    def reset(self) -> None:
        self._sessions.clear()


# =========================================================================
# F-016: PEOPLE & VEHICLE COUNTING & OCCUPANCY
# =========================================================================
class CountingManager:
    """
    Maintains directional counts, class breakdown (people vs vehicles),
    real-time occupancy, and hourly/daily aggregations.
    """

    VEHICLE_CLASSES = {"car", "bus", "truck", "motorcycle", "bicycle"}

    def __init__(self, channel_id: str) -> None:
        self.channel_id = channel_id
        self.total_entered = 0
        self.total_exited = 0
        self.person_entered = 0
        self.person_exited = 0
        self.vehicle_entered = 0
        self.vehicle_exited = 0
        self._hourly_buckets: Dict[str, Dict[str, int]] = defaultdict(lambda: {"in": 0, "out": 0})
        self._daily_buckets: Dict[str, Dict[str, int]] = defaultdict(lambda: {"in": 0, "out": 0})

    @property
    def current_occupancy(self) -> int:
        return max(0, self.total_entered - self.total_exited)

    def record_count(
        self,
        class_name: str,
        direction: str,  # "ENTER" (A_TO_B) or "EXIT" (B_TO_A)
        track_id: int,
        timestamp: Optional[float] = None,
    ) -> None:
        ts = timestamp or time.time()
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        hour_key = dt.strftime("%Y-%m-%d %H:00")
        day_key = dt.strftime("%Y-%m-%d")

        is_vehicle = class_name.lower() in self.VEHICLE_CLASSES
        is_enter = direction in ("ENTER", "A_TO_B", "IN")

        if is_enter:
            self.total_entered += 1
            if is_vehicle:
                self.vehicle_entered += 1
            else:
                self.person_entered += 1
            self._hourly_buckets[hour_key]["in"] += 1
            self._daily_buckets[day_key]["in"] += 1
        else:
            self.total_exited += 1
            if is_vehicle:
                self.vehicle_exited += 1
            else:
                self.person_exited += 1
            self._hourly_buckets[hour_key]["out"] += 1
            self._daily_buckets[day_key]["out"] += 1

    def calculate_zone_occupancy(
        self,
        zones: List[ZoneConfig],
        tracked_objects: List[Any],
    ) -> Dict[str, Dict[str, int]]:
        """
        Calculates instantaneous occupancy in each active counting zone.
        """
        zone_occupancy: Dict[str, Dict[str, int]] = {}
        for z in zones:
            if not z.is_active:
                continue
            persons = 0
            vehicles = 0
            for track in tracked_objects:
                pt = box_bottom_center(track.bbox)
                if point_in_polygon(pt, z.polygon):
                    if track.class_name.lower() in self.VEHICLE_CLASSES:
                        vehicles += 1
                    else:
                        persons += 1
            zone_occupancy[z.id] = {
                "zone_name": z.name,
                "persons": persons,
                "vehicles": vehicles,
                "total": persons + vehicles,
            }
        return zone_occupancy

    def get_summary(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "total_entered": self.total_entered,
            "total_exited": self.total_exited,
            "current_occupancy": self.current_occupancy,
            "person_entered": self.person_entered,
            "person_exited": self.person_exited,
            "vehicle_entered": self.vehicle_entered,
            "vehicle_exited": self.vehicle_exited,
        }

    def reset_counters(self) -> None:
        self.total_entered = 0
        self.total_exited = 0
        self.person_entered = 0
        self.person_exited = 0
        self.vehicle_entered = 0
        self.vehicle_exited = 0


# =========================================================================
# F-017: HEATMAP & MOVEMENT ANALYTICS
# =========================================================================
class HeatmapGenerator:
    """
    Accumulates track trajectory coordinates into a 2D density grid,
    renders Jet colormaps, generates analytics summaries, and prunes aged points.
    """

    def __init__(
        self,
        channel_id: str,
        grid_width: int = 64,
        grid_height: int = 36,
        retention_hours: float = 24.0,
    ) -> None:
        self.channel_id = channel_id
        self.grid_width = grid_width
        self.grid_height = grid_height
        self.retention_sec = retention_hours * 3600.0
        # List of (x_norm, y_norm, timestamp)
        self._trajectory_points: List[Tuple[float, float, float]] = []

    def add_points(self, tracked_objects: List[Any], timestamp: float) -> None:
        """Collects center ground positions from all active tracks."""
        for track in tracked_objects:
            pt = box_bottom_center(track.bbox)
            self._trajectory_points.append((pt[0], pt[1], timestamp))

    def generate_density_matrix(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> np.ndarray:
        """
        Computes 2D density grid (H, W) normalized to [0.0, 1.0].
        """
        grid = np.zeros((self.grid_height, self.grid_width), dtype=np.float32)
        if not self._trajectory_points:
            return grid

        t_start = start_time or 0.0
        t_end = end_time or time.time()

        for x, y, t in self._trajectory_points:
            if t_start <= t <= t_end:
                gx = int(np.clip(x * self.grid_width, 0, self.grid_width - 1))
                gy = int(np.clip(y * self.grid_height, 0, self.grid_height - 1))
                grid[gy, gx] += 1.0

        max_val = np.max(grid)
        if max_val > 0:
            grid = grid / max_val
        return grid

    def render_heatmap_image(
        self,
        output_width: int = 640,
        output_height: int = 360,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> np.ndarray:
        """
        Generates a colored BGR heatmap image using OpenCV COLORMAP_JET.
        """
        density = self.generate_density_matrix(start_time, end_time)
        density_uint8 = (density * 255).astype(np.uint8)
        # Apply Gaussian blur for smooth thermal contouring
        density_blurred = cv2.GaussianBlur(density_uint8, (5, 5), 0)
        heatmap_small = cv2.applyColorMap(density_blurred, cv2.COLORMAP_JET)
        heatmap_resized = cv2.resize(heatmap_small, (output_width, output_height), interpolation=cv2.INTER_CUBIC)
        return heatmap_resized

    def prune_retention(self, current_time: Optional[float] = None) -> int:
        """Prunes points older than retention window for privacy and memory safety."""
        now = current_time or time.time()
        cutoff = now - self.retention_sec
        before_len = len(self._trajectory_points)
        self._trajectory_points = [p for p in self._trajectory_points if p[2] >= cutoff]
        return before_len - len(self._trajectory_points)

    def reset(self) -> None:
        self._trajectory_points.clear()
