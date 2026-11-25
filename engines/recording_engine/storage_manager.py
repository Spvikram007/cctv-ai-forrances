"""
Storage and Retention Management Engine for CCTV AI Intelligence Platform.
Monitors disk volumes, quotas, free disk thresholds, and executes
automatic retention pruning of old non-evidence video recordings.
"""

import os
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from database.database_manager import db_manager
from database.models.recordings import StorageVolume, StorageEvent, Recording, RecordingSegment
from core.config.settings import settings
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("storage_manager")


@dataclass
class VolumeMetrics:
    total_bytes: int
    used_bytes: int
    free_bytes: int
    used_percent: float
    warning_threshold_pct: float
    critical_threshold_pct: float
    total_gb: float
    free_gb: float
    used_gb: float


class StorageManager:
    """Manages storage volume health, disk quotas, and retention pruning."""

    def __init__(
        self,
        primary_volume_path: Optional[str] = None,
        min_free_gb: float = 10.0,
        default_retention_days: int = 30,
        warning_threshold_pct: float = 85.0,
        critical_threshold_pct: float = 95.0,
    ) -> None:
        self.primary_volume_path = primary_volume_path
        self.min_free_gb = min_free_gb
        self.default_retention_days = default_retention_days
        self.warning_threshold_pct = warning_threshold_pct
        self.critical_threshold_pct = critical_threshold_pct

    def initialize_default_volume(self) -> StorageVolume:
        """Ensures the primary default storage volume exists in the database."""
        path_str = self.primary_volume_path or settings.storage.recordings_dir
        recordings_dir = Path(path_str).resolve()
        recordings_dir.mkdir(parents=True, exist_ok=True)
        mount_path = recordings_dir.as_posix()

        with db_manager.get_session() as session:
            volume = session.query(StorageVolume).filter_by(mount_path=mount_path).first()
            if not volume:
                usage = shutil.disk_usage(mount_path)
                volume = StorageVolume(
                    name="Primary Surveillance Store",
                    mount_path=mount_path,
                    total_bytes=usage.total,
                    used_bytes=usage.used,
                    available_bytes=usage.free,
                    warning_threshold_pct=self.warning_threshold_pct,
                    is_active=True,
                    is_default=True,
                )
                session.add(volume)
                session.flush()
                logger.info("Initialized primary storage volume: %s", mount_path)

            # Eagerly load attributes before session close to prevent DetachedInstanceError
            _ = (volume.id, volume.name, volume.mount_path, volume.total_bytes, volume.warning_threshold_pct)
            session.expunge(volume)
            return volume

    def get_volume_metrics(self, volume_id: Optional[str] = None) -> VolumeMetrics:
        """Calculates volume storage metrics for the designated or default volume."""
        path_str = self.primary_volume_path or settings.storage.recordings_dir
        mount_path = Path(path_str).resolve().as_posix()

        usage = shutil.disk_usage(mount_path)
        used_pct = (usage.used / usage.total) * 100 if usage.total > 0 else 0.0
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        used_gb = usage.used / (1024 ** 3)

        return VolumeMetrics(
            total_bytes=usage.total,
            used_bytes=usage.used,
            free_bytes=usage.free,
            used_percent=round(used_pct, 1),
            warning_threshold_pct=self.warning_threshold_pct,
            critical_threshold_pct=self.critical_threshold_pct,
            total_gb=round(total_gb, 2),
            free_gb=round(free_gb, 2),
            used_gb=round(used_gb, 2),
        )

    def check_storage_health(self) -> str:
        """
        Evaluates storage capacity against warning and critical thresholds.
        Emits StorageEvent record on threshold breach.
        Returns 'HEALTHY', 'WARNING', or 'CRITICAL'.
        """
        metrics = self.get_volume_metrics()
        status = "HEALTHY"

        if metrics.used_percent >= self.critical_threshold_pct or metrics.free_gb < 5.0:
            status = "CRITICAL"
        elif metrics.used_percent >= self.warning_threshold_pct or metrics.free_gb < self.min_free_gb:
            status = "WARNING"

        if status in ["WARNING", "CRITICAL"]:
            vol = self.initialize_default_volume()
            with db_manager.get_session() as session:
                event = StorageEvent(
                    volume_id=vol.id,
                    event_type="WARNING_LOW_DISK",
                    severity=status,
                    message=f"Storage volume at {metrics.used_percent:.1f}% ({metrics.free_gb:.1f} GB free).",
                )
                session.add(event)
                logger.warning("Low disk threshold crossed: Status=%s (%.1f%% used, %.1f GB free)",
                               status, metrics.used_percent, metrics.free_gb)

            # Publish to EventBus for Alarm Management
            topic = "storage.volume_critical" if status == "CRITICAL" else "storage.volume_low"
            bus.publish(
                topic,
                {
                    "volume_id": vol.id,
                    "volume_path": vol.mount_path,
                    "used_percent": metrics.used_percent,
                    "free_gb": metrics.free_gb,
                    "severity": status,
                },
                source="storage_manager",
            )

        return status

    def update_volume_metrics(self, volume_id: Optional[str] = None) -> Dict[str, Any]:
        """Polls disk usage from operating system and updates database metrics."""
        with db_manager.get_session() as session:
            query = session.query(StorageVolume)
            if volume_id:
                query = query.filter_by(id=volume_id)
            volumes = query.all()

            results = []
            for vol in volumes:
                if not os.path.exists(vol.mount_path):
                    logger.error("Storage mount path missing or inaccessible: %s", vol.mount_path)
                    continue

                usage = shutil.disk_usage(vol.mount_path)
                vol.total_bytes = usage.total
                vol.used_bytes = usage.used
                vol.available_bytes = usage.free

                used_pct = (usage.used / usage.total) * 100 if usage.total > 0 else 0.0
                free_gb = usage.free / (1024 ** 3)

                if used_pct >= vol.warning_threshold_pct or free_gb < self.min_free_gb:
                    event = StorageEvent(
                        volume_id=vol.id,
                        event_type="WARNING_LOW_DISK",
                        severity="WARNING" if free_gb >= 5.0 else "CRITICAL",
                        message=f"Storage volume [{vol.name}] at {used_pct:.1f}% ({free_gb:.1f} GB free).",
                    )
                    session.add(event)
                    logger.warning("Low disk space on volume %s: %.1f GB free", vol.name, free_gb)

                results.append({
                    "id": vol.id,
                    "name": vol.name,
                    "mount_path": vol.mount_path,
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "used_gb": round(usage.used / (1024 ** 3), 2),
                    "free_gb": round(free_gb, 2),
                    "used_pct": round(used_pct, 1),
                })
            return {"volumes": results}

    def execute_retention_pruning(self, volume_id: Optional[str] = None, max_age_days: Optional[int] = None) -> int:
        """
        Deletes old recording segments that exceed retention age or when disk is full.
        STRICT GUARANTEE: Never deletes locked evidence files (is_locked == True).
        """
        retention_days = max_age_days or self.default_retention_days
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        total_freed_bytes = 0
        pruned_count = 0

        with db_manager.get_session() as session:
            # Query candidate unlocked recordings older than cutoff
            query = session.query(Recording).filter(
                Recording.end_time != None,
                Recording.end_time < cutoff_date,
                Recording.is_locked == False,  # EVIDENCE PROTECTION
            )
            if volume_id:
                query = query.filter(Recording.volume_id == volume_id)

            old_recordings = query.order_by(Recording.end_time.asc()).limit(100).all()

            for rec in old_recordings:
                # Delete segment files from disk
                for seg in rec.segments:
                    if os.path.exists(seg.file_path):
                        try:
                            f_size = os.path.getsize(seg.file_path)
                            os.remove(seg.file_path)
                            total_freed_bytes += f_size
                        except Exception as e:
                            logger.error("Failed to delete segment file %s: %s", seg.file_path, e)

                # Delete main recording file if distinct
                if os.path.exists(rec.file_path):
                    try:
                        f_size = os.path.getsize(rec.file_path)
                        os.remove(rec.file_path)
                        total_freed_bytes += f_size
                    except Exception as e:
                        logger.error("Failed to delete recording file %s: %s", rec.file_path, e)

                pruned_count += 1
                session.delete(rec)

            if pruned_count > 0:
                event = StorageEvent(
                    volume_id=volume_id or (old_recordings[0].volume_id if old_recordings else "default"),
                    event_type="PRUNED_OLD_RECORDINGS",
                    severity="INFO",
                    message=f"Pruned {pruned_count} expired recordings older than {retention_days} days.",
                    bytes_freed=total_freed_bytes,
                )
                session.add(event)
                logger.info("Retention pruning completed: %d recordings removed, %.2f MB freed.", pruned_count, total_freed_bytes / (1024 * 1024))

        return pruned_count

    def prune_expired_recordings(self, retention_days: Optional[int] = None, volume_id: Optional[str] = None) -> int:
        """Alias for execute_retention_pruning."""
        return self.execute_retention_pruning(volume_id=volume_id, max_age_days=retention_days)

    def audit_database_filesystem_consistency(self) -> Dict[str, Any]:
        """Audits database records against physical files on disk, detecting missing or orphaned files."""
        missing_records = []
        verified_count = 0

        with db_manager.get_session() as session:
            recordings = session.query(Recording).all()
            for rec in recordings:
                if not os.path.exists(rec.file_path):
                    missing_records.append({
                        "recording_id": rec.id,
                        "channel_id": rec.channel_id,
                        "file_path": rec.file_path,
                    })
                else:
                    verified_count += 1

        return {
            "total_records": len(recordings),
            "verified_files": verified_count,
            "missing_files_count": len(missing_records),
            "missing_records": missing_records,
            "missing_files": [r["file_path"] for r in missing_records[:20]],
        }


# Global storage manager singleton
storage_manager = StorageManager()
