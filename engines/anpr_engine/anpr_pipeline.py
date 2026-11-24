"""
Automatic Number Plate Recognition (ANPR) Processing Pipeline.
Integrates plate localization, OCR recognition, snapshot archival, watchlist verification,
recording triggers, and database persistence.
"""

import os
import time
import json
import threading
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from database.database_manager import db_manager
from database.models.biometrics import (
    ANPRDetection,
    ANPRPlateRecord,
    VehicleEvent,
)
from core.events.event_bus import bus
from core.config.settings import settings
from core.logging.logger import get_logger
from engines.anpr_engine.plate_detector import PlateDetector, PlateCandidate
from engines.anpr_engine.ocr_recognizer import PlateOCRRecognizer, OCRResult

logger = get_logger("anpr_pipeline")


@dataclass
class ANPRResult:
    channel_id: str
    track_id: Optional[int]
    vehicle_class: str
    plate_text: str
    confidence: float
    is_watchlist: bool
    watchlist_category: Optional[str]
    requires_manual_review: bool
    plate_crop_path: Optional[str] = None
    vehicle_snapshot_path: Optional[str] = None
    timestamp: float = 0.0


class ANPRPipeline:
    """
    Dedicated per-channel / global ANPR processing engine.
    Associates plates with persistent vehicle tracks to eliminate duplicate recognitions.
    """

    _instance: Optional["ANPRPipeline"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(
        self,
        recording_manager=None,
        persist_to_db: bool = True,
        snapshots_dir: Optional[str] = None,
    ) -> None:
        if getattr(self, "_initialized", False):
            return

        self.recording_manager = recording_manager
        self.persist_to_db = persist_to_db
        self.snapshots_dir = snapshots_dir or settings.storage.snapshots_dir
        self.detector = PlateDetector()
        self.recognizer = PlateOCRRecognizer()

        # track_id -> (plate_text, confidence, timestamp)
        self._track_plates: Dict[int, Tuple[str, float, float]] = {}
        self._track_lock = threading.Lock()
        self._initialized = True

    def set_recording_manager(self, mgr) -> None:
        self.recording_manager = mgr

    def process_vehicle(
        self,
        channel_id: str,
        vehicle_bgr: np.ndarray,
        track_id: Optional[int] = None,
        vehicle_class: str = "car",
        full_frame: Optional[np.ndarray] = None,
        timestamp: Optional[float] = None,
        expected_format: str = "GENERIC",
    ) -> Optional[ANPRResult]:
        """
        Executes plate detection and OCR on a detected vehicle crop.
        Guarantees zero redundant OCR operations for already-recognized persistent tracks.
        """
        if vehicle_bgr is None or vehicle_bgr.size == 0:
            return None

        now = timestamp or time.time()

        # 1. Check if persistent vehicle track was already recognized with confidence
        if track_id is not None:
            with self._track_lock:
                existing = self._track_plates.get(track_id)
                if existing and (now - existing[2]) < 10.0 and existing[1] >= 0.50:
                    # Already recognized for this active track
                    return None

        # 2. Localize Plates
        candidates = self.detector.detect_plates(vehicle_bgr)
        if not candidates:
            return None

        best_cand = candidates[0]

        # 3. OCR Recognition
        ocr_res = self.recognizer.recognize_plate(best_cand.enhanced_plate, expected_format)
        if not ocr_res.plate_text or ocr_res.plate_text == "UNREADABLE":
            return None

        # Record recognized plate for this track
        if track_id is not None:
            with self._track_lock:
                self._track_plates[track_id] = (ocr_res.plate_text, ocr_res.confidence, now)

        # 4. Save Snapshots
        crop_path, snap_path = self._save_snapshots(
            channel_id=channel_id,
            plate_crop=best_cand.cropped_plate,
            full_frame=full_frame or vehicle_bgr,
            plate_text=ocr_res.plate_text,
            timestamp=now,
        )

        # 5. Check Watchlist & Database Catalog
        is_watchlist = False
        watchlist_cat = None

        if self.persist_to_db:
            is_watchlist, watchlist_cat = self._sync_database(
                channel_id=channel_id,
                plate_text=ocr_res.plate_text,
                confidence=ocr_res.confidence,
                char_confs=ocr_res.character_confidences,
                plate_format=ocr_res.plate_format,
                requires_review=ocr_res.requires_manual_review,
                vehicle_class=vehicle_class,
                track_id=track_id,
                crop_path=crop_path,
                snap_path=snap_path,
                timestamp=now,
            )

        # 6. Event Dispatch & Alarms
        event_type = "WATCHLIST_ALERT" if is_watchlist else "PLATE_DETECTED"
        severity = "CRITICAL" if is_watchlist else "INFO"

        event_payload = {
            "channel_id": channel_id,
            "track_id": track_id,
            "vehicle_class": vehicle_class,
            "plate_text": ocr_res.plate_text,
            "confidence": ocr_res.confidence,
            "is_watchlist": is_watchlist,
            "watchlist_category": watchlist_cat,
            "requires_manual_review": ocr_res.requires_manual_review,
            "crop_path": crop_path,
            "snapshot_path": snap_path,
            "timestamp": now,
        }

        bus.publish("anpr.plate_detected", event_payload, source=f"anpr:{channel_id}")

        if is_watchlist:
            bus.publish("anpr.watchlist_alert", event_payload, source=f"anpr:{channel_id}")
            if self.recording_manager:
                try:
                    self.recording_manager.trigger_event_recording(
                        channel_id=channel_id,
                        event_type="ANPR_WATCHLIST",
                        pre_event_sec=5,
                        post_event_sec=20,
                    )
                except Exception as e:
                    logger.debug("Failed to trigger ANPR recording: %s", e)

        return ANPRResult(
            channel_id=channel_id,
            track_id=track_id,
            vehicle_class=vehicle_class,
            plate_text=ocr_res.plate_text,
            confidence=ocr_res.confidence,
            is_watchlist=is_watchlist,
            watchlist_category=watchlist_cat,
            requires_manual_review=ocr_res.requires_manual_review,
            plate_crop_path=crop_path,
            vehicle_snapshot_path=snap_path,
            timestamp=now,
        )

    def _save_snapshots(
        self,
        channel_id: str,
        plate_crop: np.ndarray,
        full_frame: np.ndarray,
        plate_text: str,
        timestamp: float,
    ) -> Tuple[Optional[str], Optional[str]]:
        try:
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            folder = Path(self.snapshots_dir) / channel_id / "anpr" / dt.strftime("%Y%m%d")
            folder.mkdir(parents=True, exist_ok=True)

            clean_text = "".join(c for c in plate_text if c.isalnum())
            ts_str = dt.strftime("%H%M%S_%f")[:-3]

            crop_name = f"plate_{clean_text}_{ts_str}.jpg"
            crop_path = folder / crop_name
            cv2.imwrite(str(crop_path), plate_crop)

            snap_name = f"vehicle_{clean_text}_{ts_str}.jpg"
            snap_path = folder / snap_name
            cv2.imwrite(str(snap_path), full_frame)

            return str(crop_path.resolve()), str(snap_path.resolve())
        except Exception as e:
            logger.error("Failed to save ANPR snapshots: %s", e)
            return None, None

    def _sync_database(
        self,
        channel_id: str,
        plate_text: str,
        confidence: float,
        char_confs: List[float],
        plate_format: str,
        requires_review: bool,
        vehicle_class: str,
        track_id: Optional[int],
        crop_path: Optional[str],
        snap_path: Optional[str],
        timestamp: float,
    ) -> Tuple[bool, Optional[str]]:
        """Persists detection record and updates plate sightings catalog."""
        is_watchlist = False
        watchlist_cat = None

        try:
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            with db_manager.get_session() as session:
                # 1. Add Detection Record
                det = ANPRDetection(
                    channel_id=channel_id,
                    track_id=track_id,
                    vehicle_class=vehicle_class,
                    plate_text=plate_text,
                    confidence=confidence,
                    character_confidences_json=json.dumps(char_confs),
                    plate_format=plate_format,
                    requires_manual_review=requires_review,
                    plate_crop_path=crop_path,
                    vehicle_snapshot_path=snap_path,
                    timestamp=dt,
                )
                session.add(det)

                # 2. Check / Update Plate Record
                rec = session.query(ANPRPlateRecord).filter_by(plate_text_normalized=plate_text).first()
                if rec is None:
                    rec = ANPRPlateRecord(
                        plate_text_normalized=plate_text,
                        vehicle_class=vehicle_class,
                        first_seen=dt,
                        last_seen=dt,
                        total_sightings=1,
                        is_watchlist=False,
                    )
                    session.add(rec)
                else:
                    rec.last_seen = dt
                    rec.total_sightings += 1
                    is_watchlist = rec.is_watchlist
                    watchlist_cat = rec.watchlist_category

                # 3. Add Vehicle Event
                v_ev = VehicleEvent(
                    channel_id=channel_id,
                    plate_text=plate_text,
                    event_type="WATCHLIST_ALERT" if is_watchlist else "PLATE_DETECTED",
                    severity="CRITICAL" if is_watchlist else "INFO",
                    confidence=confidence,
                    track_id=track_id,
                    timestamp=dt,
                )
                session.add(v_ev)
                session.commit()

        except Exception as e:
            logger.error("Database sync error in ANPR: %s", e)

        return is_watchlist, watchlist_cat


anpr_pipeline = ANPRPipeline()
