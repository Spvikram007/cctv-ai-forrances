"""
AI Event Processor.
Converts detection and tracking results into actionable events,
triggers recording, generates alarms, manages event deduplication,
and persists events and detection snapshots.
"""

import os
import time
import json
import threading
from typing import Dict, Any, Optional, List, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

import cv2
import numpy as np

from database.database_manager import db_manager
from database.models.ai import Detection, AIEvent, ObjectTrack
from core.events.event_bus import bus
from core.config.settings import settings
from core.logging.logger import get_logger

logger = get_logger("event_processor")


@dataclass
class AIEventRecord:
    """In-memory event record for deduplication and tracking."""
    event_type: str
    channel_id: str
    class_name: str
    confidence: float
    timestamp: float
    track_id: Optional[int] = None
    severity: str = "INFO"
    snapshot_path: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class EventDeduplicator:
    """
    Prevents duplicate event generation for the same detection
    within a configurable suppression window.
    """

    def __init__(self, suppression_window_sec: float = 5.0) -> None:
        self.suppression_window = suppression_window_sec
        self._recent_events: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _make_key(self, channel_id: str, event_type: str, class_name: str, track_id: Optional[int] = None) -> str:
        return f"{channel_id}:{event_type}:{class_name}:{track_id or 'none'}"

    def is_duplicate(self, channel_id: str, event_type: str, class_name: str,
                     track_id: Optional[int] = None) -> bool:
        key = self._make_key(channel_id, event_type, class_name, track_id)
        now = time.time()

        with self._lock:
            last_seen = self._recent_events.get(key)
            if last_seen and (now - last_seen) < self.suppression_window:
                return True
            self._recent_events[key] = now
            return False

    def cleanup(self) -> None:
        """Remove expired entries."""
        now = time.time()
        with self._lock:
            expired = [k for k, t in self._recent_events.items()
                       if (now - t) > self.suppression_window * 2]
            for k in expired:
                del self._recent_events[k]

    def reset(self) -> None:
        with self._lock:
            self._recent_events.clear()


class AIEventProcessor:
    """
    Processes inference results and generates events for:
    - Detection events (new objects entering scene)
    - Tracking events (track started, track lost)
    - Recording triggers (AI event-based recording)
    - Snapshot capture and database persistence
    """

    # Severity classification based on detection class
    SEVERITY_MAP = {
        "person": "WARNING",
        "car": "INFO",
        "truck": "INFO",
        "bus": "INFO",
        "motorcycle": "INFO",
        "bicycle": "INFO",
    }

    def __init__(
        self,
        recording_manager=None,
        dedup_window_sec: float = 5.0,
        min_confidence_for_event: float = 0.6,
        persist_to_database: bool = True,
        snapshots_dir: Optional[str] = None,
    ) -> None:
        self._recording_manager = recording_manager
        self._deduplicator = EventDeduplicator(dedup_window_sec)
        self._min_confidence = min_confidence_for_event
        self._persist_to_db = persist_to_database
        self._snapshots_dir = snapshots_dir or settings.storage.snapshots_dir
        self._lock = threading.Lock()

        # Statistics
        self._total_events_generated = 0
        self._total_events_suppressed = 0
        self._events_by_channel: Dict[str, int] = defaultdict(int)
        self._events_by_class: Dict[str, int] = defaultdict(int)
        self._recent_events: List[AIEventRecord] = []
        self._max_recent = 100

    def set_recording_manager(self, mgr) -> None:
        """Dynamically attach or replace recording manager."""
        self._recording_manager = mgr

    def save_detection_snapshot(
        self,
        channel_id: str,
        frame: np.ndarray,
        bbox_pixels: Optional[Tuple[int, int, int, int]] = None,
        timestamp: Optional[float] = None,
        prefix: str = "ai_snap",
    ) -> Optional[str]:
        """
        Saves a full frame or cropped object snapshot to disk.
        Returns the absolute filepath or None on failure.
        """
        try:
            ts = timestamp or time.time()
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            date_folder = dt.strftime("%Y%m%d")
            folder = Path(self._snapshots_dir) / channel_id / date_folder
            folder.mkdir(parents=True, exist_ok=True)

            filename = f"{prefix}_{channel_id}_{dt.strftime('%H%M%S_%f')[:-3]}.jpg"
            filepath = folder / filename

            img_to_save = frame.copy()
            if bbox_pixels is not None:
                x, y, w, h = bbox_pixels
                cv2.rectangle(img_to_save, (x, y), (x + w, y + h), (0, 255, 0), 2)

            cv2.imwrite(str(filepath), img_to_save)
            return str(filepath.resolve())
        except Exception as e:
            logger.error("Failed to save detection snapshot for [%s]: %s", channel_id, e)
            return None

    def persist_detection(
        self,
        channel_id: str,
        detection,
        timestamp: float,
        track_id: Optional[int] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Persists a single detection record to the database."""
        if not self._persist_to_db:
            return None

        try:
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            with db_manager.get_session() as session:
                rec = Detection(
                    channel_id=channel_id,
                    timestamp=dt,
                    class_name=detection.class_name,
                    confidence=float(detection.confidence),
                    bbox_x=float(detection.bbox_x),
                    bbox_y=float(detection.bbox_y),
                    bbox_w=float(detection.bbox_w),
                    bbox_h=float(detection.bbox_h),
                    track_id=track_id,
                    attributes_json=json.dumps(attributes) if attributes else None,
                )
                session.add(rec)
                session.flush()
                return rec.id
        except Exception as e:
            logger.debug("Database error persisting detection: %s", e)
            return None

    def persist_event(
        self,
        channel_id: str,
        event_type: str,
        severity: str,
        timestamp: float,
        rule_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        snapshot_path: Optional[str] = None,
    ) -> Optional[str]:
        """Persists an AI security event record to the database."""
        if not self._persist_to_db:
            return None

        try:
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            with db_manager.get_session() as session:
                rec = AIEvent(
                    channel_id=channel_id,
                    event_type=event_type,
                    severity=severity,
                    timestamp=dt,
                    rule_name=rule_name or event_type,
                    details_json=json.dumps(details) if details else None,
                    snapshot_path=snapshot_path,
                    is_acknowledged=False,
                )
                session.add(rec)
                session.flush()
                return rec.id
        except Exception as e:
            logger.debug("Database error persisting AI event: %s", e)
            return None

    def process_inference_result(
        self,
        result,
        frame: Optional[np.ndarray] = None,
    ) -> List[AIEventRecord]:
        """
        Processes an InferenceResult and generates appropriate events.
        Optionally accepts source frame for snapshot saving.
        """
        generated_events: List[AIEventRecord] = []

        channel_id = result.channel_id
        timestamp = result.timestamp

        for detection in result.detections:
            if detection.confidence < self._min_confidence:
                continue

            event_type = f"DETECTION_{detection.class_name.upper()}"
            severity = self.SEVERITY_MAP.get(detection.class_name, "INFO")

            # Match with tracking ID
            track_id = None
            for tracked in result.tracked_objects:
                if (tracked.class_name == detection.class_name and
                        abs(tracked.bbox[0] - detection.bbox_x) < 0.05 and
                        abs(tracked.bbox[1] - detection.bbox_y) < 0.05):
                    track_id = tracked.track_id
                    break

            if self._deduplicator.is_duplicate(channel_id, event_type, detection.class_name, track_id):
                self._total_events_suppressed += 1
                continue

            # Capture snapshot for warning/critical events if frame is provided
            snapshot_path = None
            if frame is not None and severity in ("WARNING", "CRITICAL"):
                pixel_bbox = (detection.pixel_x, detection.pixel_y, detection.pixel_w, detection.pixel_h)
                snapshot_path = self.save_detection_snapshot(
                    channel_id=channel_id,
                    frame=frame,
                    bbox_pixels=pixel_bbox,
                    timestamp=timestamp,
                    prefix=f"evt_{detection.class_name}",
                )

            event = AIEventRecord(
                event_type=event_type,
                channel_id=channel_id,
                class_name=detection.class_name,
                confidence=detection.confidence,
                timestamp=timestamp,
                track_id=track_id,
                severity=severity,
                snapshot_path=snapshot_path,
                details={
                    "bbox": [detection.bbox_x, detection.bbox_y, detection.bbox_w, detection.bbox_h],
                    "pixel_bbox": [detection.pixel_x, detection.pixel_y, detection.pixel_w, detection.pixel_h],
                    "latency_ms": result.inference_latency_ms,
                    "device": result.device,
                },
            )
            generated_events.append(event)

            # Persist to database
            self.persist_detection(channel_id, detection, timestamp, track_id)
            self.persist_event(
                channel_id=channel_id,
                event_type=event_type,
                severity=severity,
                timestamp=timestamp,
                details=event.details,
                snapshot_path=snapshot_path,
            )

            # Update statistics
            self._total_events_generated += 1
            self._events_by_channel[channel_id] += 1
            self._events_by_class[detection.class_name] += 1

            with self._lock:
                self._recent_events.append(event)
                if len(self._recent_events) > self._max_recent:
                    self._recent_events = self._recent_events[-self._max_recent:]

            # Publish event to bus
            bus.publish("ai.event", {
                "event_type": event_type,
                "channel_id": channel_id,
                "class_name": detection.class_name,
                "confidence": round(detection.confidence, 3),
                "severity": severity,
                "track_id": track_id,
                "snapshot_path": snapshot_path,
                "timestamp": timestamp,
            }, source="event_processor")

            # Trigger AI event recording if recording manager is available
            rec_mgr = self._recording_manager
            if rec_mgr is None:
                try:
                    from engines.recording_engine.recording_manager import recording_manager
                    rec_mgr = recording_manager
                except ImportError:
                    pass

            if rec_mgr and severity in ("WARNING", "CRITICAL"):
                try:
                    rec_mgr.trigger_event_recording(
                        channel_id=channel_id,
                        event_name=event_type,
                        duration_sec=15.0,
                    )
                except Exception as e:
                    logger.error("Failed to trigger event recording for [%s]: %s", channel_id, e)

        self._deduplicator.cleanup()
        return generated_events

    def get_statistics(self) -> Dict[str, Any]:
        """Returns event processing statistics."""
        return {
            "total_events_generated": self._total_events_generated,
            "total_events_suppressed": self._total_events_suppressed,
            "events_by_channel": dict(self._events_by_channel),
            "events_by_class": dict(self._events_by_class),
            "recent_event_count": len(self._recent_events),
        }

    def get_recent_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns most recent events."""
        with self._lock:
            events = self._recent_events[-limit:]
        return [
            {
                "event_type": e.event_type,
                "channel_id": e.channel_id,
                "class_name": e.class_name,
                "confidence": round(e.confidence, 3),
                "severity": e.severity,
                "track_id": e.track_id,
                "snapshot_path": e.snapshot_path,
                "timestamp": e.timestamp,
            }
            for e in reversed(events)
        ]


# Global event processor singleton
event_processor = AIEventProcessor()
