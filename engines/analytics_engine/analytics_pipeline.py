"""
Camera Analytics Pipeline and Central Analytics Manager.
Coordinates per-camera rules, geometry detection, event generation,
snapshot capture, AI recording triggers, database persistence, and EventBus distribution.
"""

import os
import time
import json
import threading
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

import cv2
import numpy as np

from database.database_manager import db_manager
from database.models.analytics import (
    AnalyticsZone,
    TripwireLine,
    AnalyticsRule,
    AnalyticsEvent,
    ObjectCount,
    OccupancyRecord,
    HeatmapData,
)
from database.models.users import AuditLog
from core.events.event_bus import bus
from core.config.settings import settings
from core.logging.logger import get_logger
from engines.analytics_engine.rule_evaluator import (
    ZoneConfig,
    TripwireConfig,
    AnalyticsRuleConfig,
    AnalyticsEventData,
    IntrusionDetector,
    TripwireDetector,
    LoiteringDetector,
    CountingManager,
    HeatmapGenerator,
)

logger = get_logger("analytics_pipeline")


class CameraAnalyticsPipeline:
    """
    Per-channel video analytics processor.
    Evaluates intrusion, line-crossing, loitering, counting, and heatmaps
    for a single camera stream.
    """

    def __init__(
        self,
        channel_id: str,
        recording_manager=None,
        persist_to_db: bool = True,
        snapshots_dir: Optional[str] = None,
    ) -> None:
        self.channel_id = channel_id
        self.recording_manager = recording_manager
        self.persist_to_db = persist_to_db
        self.snapshots_dir = snapshots_dir or settings.storage.snapshots_dir
        self._lock = threading.Lock()

        # Configurations
        self.zones: Dict[str, ZoneConfig] = {}
        self.tripwires: Dict[str, TripwireConfig] = {}
        self.rules: Dict[str, AnalyticsRuleConfig] = {}

        # Detectors
        self.intrusion_detector = IntrusionDetector()
        self.tripwire_detector = TripwireDetector()
        self.loitering_detector = LoiteringDetector()
        self.counting_manager = CountingManager(channel_id)
        self.heatmap_generator = HeatmapGenerator(channel_id)

        # Telemetry
        self.total_events_generated = 0
        self.events_by_type: Dict[str, int] = defaultdict(int)

    def add_zone(self, zone: ZoneConfig) -> None:
        with self._lock:
            self.zones[zone.id] = zone

    def remove_zone(self, zone_id: str) -> None:
        with self._lock:
            self.zones.pop(zone_id, None)

    def add_tripwire(self, tripwire: TripwireConfig) -> None:
        with self._lock:
            self.tripwires[tripwire.id] = tripwire

    def remove_tripwire(self, tripwire_id: str) -> None:
        with self._lock:
            self.tripwires.pop(tripwire_id, None)

    def add_rule(self, rule: AnalyticsRuleConfig) -> None:
        with self._lock:
            self.rules[rule.id] = rule

    def remove_rule(self, rule_id: str) -> None:
        with self._lock:
            self.rules.pop(rule_id, None)

    def save_snapshot(
        self,
        frame: np.ndarray,
        event_type: str,
        timestamp: float,
    ) -> Optional[str]:
        """Saves an event snapshot to the configured snapshots directory."""
        try:
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            folder = Path(self.snapshots_dir) / self.channel_id / dt.strftime("%Y%m%d")
            folder.mkdir(parents=True, exist_ok=True)
            filename = f"analytics_{event_type.lower()}_{self.channel_id}_{dt.strftime('%H%M%S_%f')[:-3]}.jpg"
            filepath = folder / filename

            # Save annotated snapshot copy
            cv2.imwrite(str(filepath), frame)
            return str(filepath.resolve())
        except Exception as e:
            logger.error("Failed to save analytics snapshot for [%s]: %s", self.channel_id, e)
            return None

    def process(
        self,
        tracked_objects: List[Any],
        frame: Optional[np.ndarray] = None,
        timestamp: Optional[float] = None,
    ) -> List[AnalyticsEventData]:
        """
        Main analytics processing tick for incoming tracking results.
        Thread-safe and decoupled from streaming/recording loops.
        """
        ts = timestamp or time.time()
        generated_events: List[AnalyticsEventData] = []

        with self._lock:
            active_zones = list(self.zones.values())
            active_tripwires = list(self.tripwires.values())
            active_rules = list(self.rules.values())

        # 1. Update Heatmap
        self.heatmap_generator.add_points(tracked_objects, ts)

        # 2. Evaluate Intrusion Rules (F-013)
        intrusion_events = self.intrusion_detector.evaluate(
            active_zones, active_rules, tracked_objects, ts
        )
        generated_events.extend(intrusion_events)

        # 3. Evaluate Line Crossing Rules (F-014 & F-016)
        crossing_events = self.tripwire_detector.evaluate(
            active_tripwires, active_rules, tracked_objects, ts
        )
        for ev in crossing_events:
            # Update counting stats
            if ev.crossing_direction:
                self.counting_manager.record_count(
                    class_name=ev.class_name,
                    direction=ev.crossing_direction,
                    track_id=ev.track_id or 0,
                    timestamp=ts,
                )
        generated_events.extend(crossing_events)

        # 4. Evaluate Loitering Rules (F-015)
        loitering_events = self.loitering_detector.evaluate(
            active_zones, active_rules, tracked_objects, ts
        )
        generated_events.extend(loitering_events)

        # 5. Process Generated Events: Snapshots, Triggers, DB Persistence, EventBus
        for event in generated_events:
            self.total_events_generated += 1
            self.events_by_type[event.rule_type] += 1

            # Snapshot capture
            if frame is not None and frame.size > 0:
                event.snapshot_path = self.save_snapshot(frame, event.rule_type, ts)

            # Trigger Recording (Fault-isolated)
            rule = self.rules.get(event.rule_id or "")
            if rule and rule.trigger_recording and self.recording_manager:
                try:
                    self.recording_manager.trigger_event_recording(
                        channel_id=self.channel_id,
                        event_type=f"ANALYTICS_{event.rule_type}",
                        pre_event_sec=5,
                        post_event_sec=15,
                    )
                except Exception as rec_err:
                    logger.debug("Failed to trigger event recording for [%s]: %s", self.channel_id, rec_err)

            # Publish Event to EventBus
            event_payload = {
                "channel_id": self.channel_id,
                "rule_id": event.rule_id,
                "rule_name": event.rule_name,
                "rule_type": event.rule_type,
                "severity": event.severity,
                "track_id": event.track_id,
                "class_name": event.class_name,
                "confidence": round(event.confidence, 3),
                "dwell_time_sec": event.dwell_time_sec,
                "crossing_direction": event.crossing_direction,
                "snapshot_path": event.snapshot_path,
                "details": event.details,
                "timestamp": event.timestamp,
            }
            bus.publish("analytics.event", event_payload, source=f"pipeline:{self.channel_id}")

            # Persist to Database
            if self.persist_to_db:
                self._persist_event_to_db(event)

        return generated_events

    def _persist_event_to_db(self, event: AnalyticsEventData) -> None:
        """Persists single analytics event record to database."""
        try:
            dt = datetime.fromtimestamp(event.timestamp, tz=timezone.utc)
            with db_manager.get_session() as session:
                rec = AnalyticsEvent(
                    channel_id=self.channel_id,
                    rule_id=event.rule_id,
                    rule_name=event.rule_name,
                    rule_type=event.rule_type,
                    severity=event.severity,
                    track_id=event.track_id,
                    class_name=event.class_name,
                    confidence=event.confidence,
                    dwell_time_sec=event.dwell_time_sec,
                    crossing_direction=event.crossing_direction,
                    details_json=json.dumps(event.details) if event.details else None,
                    snapshot_path=event.snapshot_path,
                    timestamp=dt,
                )
                session.add(rec)
                session.commit()
        except Exception as e:
            logger.error("Failed to persist analytics event to DB: %s", e)

    def persist_occupancy_record(
        self,
        zone_id: Optional[str] = None,
        zone_name: Optional[str] = None,
        max_capacity: Optional[int] = None,
        tracked_objects: Optional[List[Any]] = None,
    ) -> Optional[int]:
        """Snapshots current occupancy into database."""
        if not self.persist_to_db:
            return None

        try:
            now_dt = datetime.now(timezone.utc)
            summary = self.counting_manager.get_summary()
            current_occ = summary["current_occupancy"]
            p_count = summary["person_entered"] - summary["person_exited"]
            v_count = summary["vehicle_entered"] - summary["vehicle_exited"]
            is_over = max_capacity is not None and current_occ > max_capacity

            with db_manager.get_session() as session:
                rec = OccupancyRecord(
                    channel_id=self.channel_id,
                    zone_id=zone_id,
                    zone_name=zone_name,
                    current_occupancy=max(0, current_occ),
                    person_count=max(0, p_count),
                    vehicle_count=max(0, v_count),
                    max_capacity=max_capacity,
                    is_over_capacity=is_over,
                    timestamp=now_dt,
                )
                session.add(rec)
                session.commit()
            return current_occ
        except Exception as e:
            logger.error("Failed to persist occupancy record: %s", e)
            return None

    def persist_heatmap_data(
        self,
        time_window_start: datetime,
        time_window_end: datetime,
    ) -> Optional[str]:
        """Serializes current heatmap density matrix to DB."""
        if not self.persist_to_db:
            return None

        try:
            t_start = time_window_start.timestamp()
            t_end = time_window_end.timestamp()
            density = self.heatmap_generator.generate_density_matrix(t_start, t_end)
            matrix_list = density.tolist()

            with db_manager.get_session() as session:
                rec = HeatmapData(
                    channel_id=self.channel_id,
                    time_window_start=time_window_start,
                    time_window_end=time_window_end,
                    grid_width=self.heatmap_generator.grid_width,
                    grid_height=self.heatmap_generator.grid_height,
                    density_matrix_json=json.dumps(matrix_list),
                    total_points=len(self.heatmap_generator._trajectory_points),
                )
                session.add(rec)
                session.commit()
                return rec.id
        except Exception as e:
            logger.error("Failed to persist heatmap data: %s", e)
            return None


class AnalyticsManager:
    """
    Central Manager for all video analytics pipelines across 1 to 64 camera streams.
    Provides database synchronization, rule auditing, and pipeline lifecycle control.
    """

    _instance: Optional["AnalyticsManager"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, recording_manager=None) -> None:
        if getattr(self, "_initialized", False):
            return
        self.recording_manager = recording_manager
        self._pipelines: Dict[str, CameraAnalyticsPipeline] = {}
        self._pipeline_lock = threading.Lock()
        self._initialized = True

    def set_recording_manager(self, mgr) -> None:
        self.recording_manager = mgr
        with self._pipeline_lock:
            for p in self._pipelines.values():
                p.recording_manager = mgr

    def get_pipeline(self, channel_id: str) -> CameraAnalyticsPipeline:
        with self._pipeline_lock:
            if channel_id not in self._pipelines:
                self._pipelines[channel_id] = CameraAnalyticsPipeline(
                    channel_id=channel_id,
                    recording_manager=self.recording_manager,
                )
            return self._pipelines[channel_id]

    def remove_pipeline(self, channel_id: str) -> None:
        with self._pipeline_lock:
            self._pipelines.pop(channel_id, None)

    def load_from_db(self) -> None:
        """Loads all active zones, tripwires, and rules from database."""
        try:
            with db_manager.get_session() as session:
                # 1. Load Zones
                zones = session.query(AnalyticsZone).filter_by(is_deleted=False).all()
                for z in zones:
                    pipeline = self.get_pipeline(z.channel_id)
                    polygon = json.loads(z.polygon_json)
                    pipeline.add_zone(
                        ZoneConfig(
                            id=z.id,
                            name=z.name,
                            zone_type=z.zone_type,
                            polygon=[(float(p[0]), float(p[1])) for p in polygon],
                            color_hex=z.color_hex,
                            is_active=z.is_active,
                        )
                    )

                # 2. Load Tripwires
                tripwires = session.query(TripwireLine).filter_by(is_deleted=False).all()
                for tw in tripwires:
                    pipeline = self.get_pipeline(tw.channel_id)
                    coords = json.loads(tw.line_coords_json)
                    pipeline.add_tripwire(
                        TripwireConfig(
                            id=tw.id,
                            name=tw.name,
                            pt1=(float(coords["pt1"][0]), float(coords["pt1"][1])),
                            pt2=(float(coords["pt2"][0]), float(coords["pt2"][1])),
                            direction=tw.direction,
                            color_hex=tw.color_hex,
                            is_active=tw.is_active,
                        )
                    )

                # 3. Load Rules
                rules = session.query(AnalyticsRule).filter_by(is_deleted=False).all()
                for r in rules:
                    pipeline = self.get_pipeline(r.channel_id)
                    pipeline.add_rule(
                        AnalyticsRuleConfig(
                            id=r.id,
                            name=r.name,
                            rule_type=r.rule_type,
                            channel_id=r.channel_id,
                            zone_id=r.zone_id,
                            tripwire_id=r.tripwire_id,
                            target_classes=json.loads(r.target_classes_json) if r.target_classes_json else ["person"],
                            confidence_threshold=r.confidence_threshold,
                            min_dwell_time_sec=r.min_dwell_time_sec,
                            severity=r.severity,
                            schedule=json.loads(r.schedule_json) if r.schedule_json else None,
                            trigger_recording=r.trigger_recording,
                            alarm_sound=r.alarm_sound,
                            is_active=r.is_active,
                        )
                    )
            logger.info("Successfully synchronized analytics configuration from database.")
        except Exception as e:
            logger.error("Failed to load analytics configuration from database: %s", e)

    def audit_change(self, user_id: Optional[str], action: str, entity_type: str, entity_id: str, details: str) -> None:
        """Records audit log entry for rule configuration changes."""
        try:
            with db_manager.get_session() as session:
                log_entry = AuditLog(
                    user_id=None,  # Decoupled for offline system administration
                    action=action,
                    resource_type=entity_type,
                    resource_id=entity_id,
                    details_json=json.dumps({"details": details, "operator": user_id or "system"}),
                )
                session.add(log_entry)
                session.commit()
        except Exception as e:
            logger.error("Audit log error: %s", e)


analytics_manager = AnalyticsManager()
