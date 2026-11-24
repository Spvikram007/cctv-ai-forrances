"""
ANPR Investigation and Search Engine.
Provides full/partial plate searches, multi-parameter filtering, vehicle event history,
and exportable intelligence reports.
"""

import csv
import json
import io
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone

from sqlalchemy import or_, and_
from database.database_manager import db_manager
from database.models.biometrics import ANPRDetection, ANPRPlateRecord, VehicleEvent
from core.logging.logger import get_logger

logger = get_logger("anpr_search")


class ANPRSearchEngine:
    """
    Parametric search engine for license plate sightings and vehicle event history.
    """

    @staticmethod
    def search(
        plate_query: Optional[str] = None,
        channel_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        vehicle_class: Optional[str] = None,
        min_confidence: float = 0.0,
        watchlist_only: bool = False,
        review_only: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Executes multi-criteria query across ANPR detections.
        Supports full or wildcard plate searches.
        """
        results: List[Dict[str, Any]] = []

        try:
            with db_manager.get_session() as session:
                query = session.query(ANPRDetection)

                if plate_query:
                    clean_q = plate_query.strip().upper().replace("*", "%")
                    if "%" not in clean_q:
                        clean_q = f"%{clean_q}%"
                    query = query.filter(ANPRDetection.plate_text.like(clean_q))

                if channel_id and channel_id != "ALL":
                    query = query.filter(ANPRDetection.channel_id == channel_id)

                if start_time:
                    query = query.filter(ANPRDetection.timestamp >= start_time)

                if end_time:
                    query = query.filter(ANPRDetection.timestamp <= end_time)

                if vehicle_class and vehicle_class != "ALL":
                    query = query.filter(ANPRDetection.vehicle_class == vehicle_class)

                if min_confidence > 0.0:
                    query = query.filter(ANPRDetection.confidence >= min_confidence)

                if review_only:
                    query = query.filter(ANPRDetection.requires_manual_review == True)

                # Order newest first
                records = query.order_by(ANPRDetection.timestamp.desc()).limit(limit).all()

                for r in records:
                    results.append({
                        "id": r.id,
                        "channel_id": r.channel_id,
                        "track_id": r.track_id,
                        "vehicle_class": r.vehicle_class,
                        "plate_text": r.plate_text,
                        "confidence": r.confidence,
                        "plate_format": r.plate_format,
                        "requires_manual_review": r.requires_manual_review,
                        "plate_crop_path": r.plate_crop_path,
                        "vehicle_snapshot_path": r.vehicle_snapshot_path,
                        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    })

        except Exception as e:
            logger.error("ANPR search query failed: %s", e)

        return results

    @staticmethod
    def export_to_csv(results: List[Dict[str, Any]]) -> str:
        """Serializes search results to CSV format."""
        output = io.StringIO()
        fieldnames = [
            "id", "channel_id", "timestamp", "vehicle_class",
            "plate_text", "confidence", "plate_format", "requires_manual_review"
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in results:
            writer.writerow(row)
        return output.getvalue()
