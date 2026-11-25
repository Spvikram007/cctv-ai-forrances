"""
Enterprise Storage Service Facade.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

import os
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

from database.database_manager import db_manager
from database.models.recordings import StorageVolume, StorageEvent, Recording, RecordingSegment
from database.models.storage import (
    StoragePool,
    StorageDevice,
    StoragePolicy,
    StorageAllocation,
    StorageHealthHistory,
    StorageFailoverEvent,
    StorageRecordingManifest,
    StorageArchivalJob,
    StorageArchivalCopy,
    NASConnection,
)
from engines.storage_engine.enums import (
    StorageType,
    VolumeStatus,
    RAIDLevel,
    RAIDStatus,
    PoolTier,
    ArchivalTier,
    FailoverStatus,
    HealthStatus,
)
from engines.storage_engine.adapters.local import LocalStorageAdapter
from engines.storage_engine.adapters.raid import RAIDMonitoringAdapter, RAIDArrayInfo
from engines.storage_engine.adapters.nas import NASStorageAdapter
from engines.storage_engine.volume_monitor import VolumeMonitor
from engines.storage_engine.policy_engine import StoragePolicyEngine
from engines.storage_engine.allocation_manager import StorageAllocationManager
from engines.storage_engine.failover_manager import StorageFailoverManager
from engines.storage_engine.archival_manager import StorageArchivalManager
from engines.storage_engine.integrity_manager import StorageIntegrityManager
from engines.storage_engine.scheduler import StorageScheduler
from core.config.settings import settings
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("enterprise_storage_service")


class EnterpriseStorageService:
    """
    Central enterprise storage subsystem facade.
    Orchestrates hardware-independent adapters (Local, RAID, NAS), dynamic camera allocations,
    automated failover and gap detection, multi-tier archival, and forensic evidence locks.
    """

    def __init__(self) -> None:
        self.local_adapter = LocalStorageAdapter()
        self.raid_adapter = RAIDMonitoringAdapter(local_fallback=self.local_adapter)
        self.nas_adapter = NASStorageAdapter(local_fallback=self.local_adapter)

        self.policy_engine = StoragePolicyEngine()
        self.volume_monitor = VolumeMonitor(
            local_adapter=self.local_adapter,
            raid_adapter=self.raid_adapter,
            nas_adapter=self.nas_adapter,
        )
        self.allocation_manager = StorageAllocationManager(policy_engine=self.policy_engine)
        self.failover_manager = StorageFailoverManager(allocation_manager=self.allocation_manager)
        self.archival_manager = StorageArchivalManager()
        self.integrity_manager = StorageIntegrityManager()

        self._scheduler: Optional[StorageScheduler] = None
        self._is_initialized = False

    def initialize(self) -> None:
        """Initializes default primary volume, default pool, and seeds initial storage metadata."""
        if self._is_initialized:
            return

        db_manager.init_schema()

        # Ensure default volume exists in database
        path_str = settings.storage.recordings_dir
        recordings_dir = Path(path_str).resolve()
        recordings_dir.mkdir(parents=True, exist_ok=True)
        mount_path = recordings_dir.as_posix()

        with db_manager.get_session() as session:
            vol = session.query(StorageVolume).filter_by(mount_path=mount_path).first()
            if not vol:
                usage = shutil.disk_usage(mount_path)
                vol = StorageVolume(
                    name="Primary Surveillance Store",
                    mount_path=mount_path,
                    total_bytes=usage.total,
                    used_bytes=usage.used,
                    available_bytes=usage.free,
                    warning_threshold_pct=85.0,
                    is_active=True,
                    is_default=True,
                    volume_type="LOCAL",
                    filesystem="NTFS",
                    volume_status="ONLINE",
                    health_score=100.0,
                )
                session.add(vol)
                session.flush()
                logger.info("Initialized default primary storage volume: %s", mount_path)

        # Ensure default pool exists
        self.allocation_manager.get_or_create_default_pool(tier=PoolTier.HOT)
        self._is_initialized = True
        logger.info("Enterprise Storage Service initialized successfully.")

    def start_scheduler(self) -> None:
        """Starts background maintenance worker thread."""
        if self._scheduler is None or not self._scheduler.is_alive():
            self._scheduler = StorageScheduler(
                health_check_interval_sec=120.0,
                retention_interval_sec=3600.0,
                health_callback=self.volume_monitor.audit_all_volumes,
                retention_callback=self.prune_expired_recordings,
            )
            self._scheduler.start()

    def stop_scheduler(self) -> None:
        """Stops background maintenance worker thread."""
        if self._scheduler and self._scheduler.is_alive():
            self._scheduler.stop()
            self._scheduler.join(timeout=3.0)
            self._scheduler = None

    # -------------------------------------------------------------------------
    # Recording Engine Integration Endpoints
    # -------------------------------------------------------------------------
    def get_recording_destination(
        self,
        channel_id: str,
        required_mb: float = 50.0,
    ) -> Tuple[StorageVolume, str, bool]:
        """Resolves target volume and directory path for an active camera stream."""
        return self.allocation_manager.resolve_destination_for_channel(channel_id, required_mb)

    def notify_write_failure(
        self,
        channel_id: str,
        failed_volume_id: str,
        reason: str = "Disk write failure",
        gap_seconds: float = 0.0,
    ) -> Tuple[Optional[StorageVolume], str]:
        """Invoked when a recording worker catches a storage write error."""
        return self.failover_manager.handle_storage_failure(
            channel_id=channel_id,
            failed_volume_id=failed_volume_id,
            reason=reason,
            gap_seconds=gap_seconds,
        )

    def execute_failback(self, channel_id: str, operator: str = "SYSTEM") -> Tuple[bool, str]:
        """Restores a camera recording back to primary volume after recovery."""
        return self.failover_manager.execute_controlled_failback(channel_id, operator)

    def seal_segment(
        self,
        channel_id: str,
        volume_id: str,
        file_path: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        sha256_hash: Optional[str] = None,
        file_size_bytes: int = 0,
        duration_sec: int = 0,
        is_failover: bool = False,
        recording_id: Optional[str] = None,
        segment_id: Optional[str] = None,
    ) -> StorageRecordingManifest:
        """Creates cryptographic manifest for a completed recording segment."""
        return self.integrity_manager.create_segment_manifest(
            channel_id=channel_id,
            destination_volume_id=volume_id,
            file_path=file_path,
            start_time=start_time,
            end_time=end_time,
            recording_id=recording_id,
            segment_id=segment_id,
            sha256_hash=sha256_hash,
            file_size_bytes=file_size_bytes,
            duration_sec=duration_sec,
            is_failover=is_failover,
        )

    # -------------------------------------------------------------------------
    # Archival & Retention
    # -------------------------------------------------------------------------
    def execute_archival_job(
        self,
        source_volume_id: str,
        target_volume_id: str,
        target_tier: ArchivalTier = ArchivalTier.COLD,
        min_age_days: int = 14,
    ) -> Dict[str, Any]:
        """Executes multi-tier migration preserving locked evidence."""
        return self.archival_manager.create_archival_job(
            source_volume_id=source_volume_id,
            target_volume_id=target_volume_id,
            target_tier=target_tier,
            min_age_days=min_age_days,
        )

    def restore_archival(
        self,
        recording_id: str,
        destination_volume_id: str,
        operator: str = "INVESTIGATOR",
    ) -> Tuple[bool, str]:
        """Restores an archived copy to hot storage."""
        return self.archival_manager.restore_archival_copy(
            recording_id=recording_id,
            destination_volume_id=destination_volume_id,
            operator=operator,
        )

    def prune_expired_recordings(
        self,
        retention_days: Optional[int] = None,
        volume_id: Optional[str] = None,
    ) -> int:
        """
        Deletes unlocked recordings exceeding retention age.
        STRICT FORENSIC RULE: Preserves all files where is_locked == True.
        """
        ret_days = retention_days or 30
        cutoff = datetime.now(timezone.utc) - timedelta(days=ret_days)
        pruned_count = 0
        total_freed_bytes = 0

        with db_manager.get_session() as session:
            query = session.query(Recording).filter(
                Recording.end_time != None,
                Recording.end_time < cutoff,
                Recording.is_locked == False,  # EVIDENCE PROTECTION
            )
            if volume_id:
                query = query.filter(Recording.volume_id == volume_id)

            old_recs = query.order_by(Recording.end_time.asc()).limit(100).all()
            for rec in old_recs:
                for seg in rec.segments:
                    if os.path.exists(seg.file_path):
                        try:
                            sz = os.path.getsize(seg.file_path)
                            os.remove(seg.file_path)
                            total_freed_bytes += sz
                        except Exception as e:
                            logger.error("Failed to delete segment %s: %s", seg.file_path, e)

                if os.path.exists(rec.file_path):
                    try:
                        sz = os.path.getsize(rec.file_path)
                        os.remove(rec.file_path)
                        total_freed_bytes += sz
                    except Exception as e:
                        logger.error("Failed to delete recording %s: %s", rec.file_path, e)

                pruned_count += 1
                session.delete(rec)

            if pruned_count > 0:
                event = StorageEvent(
                    volume_id=volume_id or (old_recs[0].volume_id if old_recs else "default"),
                    event_type="PRUNED_OLD_RECORDINGS",
                    severity="INFO",
                    message=f"Retention pruning removed {pruned_count} expired recordings older than {ret_days} days.",
                    bytes_freed=total_freed_bytes,
                )
                session.add(event)
                logger.info("Retention pruning: %d recordings deleted (%.2f MB freed)",
                            pruned_count, total_freed_bytes / (1024 * 1024))

        return pruned_count

    # -------------------------------------------------------------------------
    # Capacity Forecasting
    # -------------------------------------------------------------------------
    def forecast_capacity(self, volume_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Extrapolates capacity exhaustion based on current daily consumption trends.
        """
        with db_manager.get_session() as session:
            query = session.query(StorageVolume).filter(StorageVolume.is_active == True)
            if volume_id:
                query = query.filter_by(id=volume_id)
            vols = query.all()

            forecasts = []
            for vol in vols:
                total_gb = vol.total_bytes / (1024 ** 3) if vol.total_bytes else 100.0
                used_gb = vol.used_bytes / (1024 ** 3) if vol.used_bytes else 10.0
                free_gb = vol.available_bytes / (1024 ** 3) if vol.available_bytes else (total_gb - used_gb)

                # Estimate daily consumption based on active channels or default 15 GB/day
                channel_count = session.query(StorageAllocation).filter_by(primary_volume_id=vol.id).count()
                daily_burn_gb = max(5.0, channel_count * 12.0)  # ~12 GB per camera per day @ 1080p 4Mbps

                days_to_warning = max(0.0, round((free_gb - (total_gb * 0.15)) / daily_burn_gb, 1))
                days_to_full = max(0.0, round(free_gb / daily_burn_gb, 1))

                forecasts.append({
                    "volume_id": vol.id,
                    "volume_name": vol.name,
                    "total_gb": round(total_gb, 1),
                    "free_gb": round(free_gb, 1),
                    "estimated_daily_burn_gb": round(daily_burn_gb, 1),
                    "days_until_warning_threshold": days_to_warning,
                    "days_until_exhaustion": days_to_full,
                })

            return {"forecasts": forecasts}


# Global enterprise storage service singleton
enterprise_storage_service = EnterpriseStorageService()
