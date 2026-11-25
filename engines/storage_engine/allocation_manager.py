"""
Storage Allocation Manager for Camera-to-Pool/Volume Resolution and Quota Management.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional, List

from database.database_manager import db_manager
from database.models.recordings import StorageVolume
from database.models.storage import StoragePool, StorageAllocation, StoragePolicy
from engines.storage_engine.enums import PoolTier, VolumeStatus
from engines.storage_engine.policy_engine import StoragePolicyEngine
from core.config.settings import settings
from core.logging.logger import get_logger

logger = get_logger("allocation_manager")


class StorageAllocationManager:
    """Resolves and allocates physical storage volumes and folder paths for surveillance cameras."""

    def __init__(self, policy_engine: Optional[StoragePolicyEngine] = None) -> None:
        self.policy_engine = policy_engine or StoragePolicyEngine()

    def get_or_create_default_pool(self, tier: PoolTier = PoolTier.HOT) -> StoragePool:
        """Guarantees default primary storage pool exists in the database."""
        with db_manager.get_session() as session:
            pool = session.query(StoragePool).filter_by(name="Primary Surveillance Pool").first()
            if not pool:
                pool = StoragePool(
                    name="Primary Surveillance Pool",
                    pool_tier=tier.value,
                    description="Default hot tier storage pool for active camera recordings.",
                    min_free_space_gb=15.0,
                    is_active=True,
                )
                session.add(pool)
                session.flush()

                # Add default policy
                pol = StoragePolicy(
                    name="Default Hot Pool Policy",
                    pool_id=pool.id,
                    warning_threshold_pct=85.0,
                    critical_threshold_pct=95.0,
                    min_free_gb=10.0,
                    retention_days=30,
                    failover_enabled=True,
                    archival_enabled=False,
                )
                session.add(pol)
                logger.info("Initialized default storage pool and policy: %s", pool.name)

            _ = (pool.id, pool.name, pool.pool_tier)
            session.expunge(pool)
            return pool

    def allocate_channel(
        self,
        channel_id: str,
        primary_volume_id: str,
        failover_volume_id: Optional[str] = None,
        pool_id: Optional[str] = None,
        quota_bytes: int = 0,
        priority: str = "NORMAL",
    ) -> StorageAllocation:
        """Assigns camera channel to primary and optional failover storage volumes."""
        with db_manager.get_session() as session:
            alloc = session.query(StorageAllocation).filter_by(channel_id=channel_id).first()
            if not alloc:
                eff_pool_id = pool_id
                if not eff_pool_id:
                    def_pool = self.get_or_create_default_pool()
                    eff_pool_id = def_pool.id

                alloc = StorageAllocation(
                    channel_id=channel_id,
                    pool_id=eff_pool_id,
                    primary_volume_id=primary_volume_id,
                    failover_volume_id=failover_volume_id,
                    quota_bytes=quota_bytes,
                    priority=priority,
                )
                session.add(alloc)
            else:
                alloc.primary_volume_id = primary_volume_id
                alloc.failover_volume_id = failover_volume_id
                if pool_id:
                    alloc.pool_id = pool_id
                alloc.quota_bytes = quota_bytes
                alloc.priority = priority

            session.flush()
            _ = (alloc.id, alloc.channel_id, alloc.primary_volume_id, alloc.failover_volume_id)
            session.expunge(alloc)
            logger.info("Allocated channel [%s] to primary volume [%s] (failover: %s)",
                        channel_id, primary_volume_id, failover_volume_id)
            return alloc

    def resolve_destination_for_channel(
        self,
        channel_id: str,
        required_mb: float = 50.0,
    ) -> Tuple[StorageVolume, str, bool]:
        """
        Resolves the active target StorageVolume and directory path for a channel.
        Returns:
            (volume: StorageVolume, directory_path: str, is_failover: bool)
        """
        now = datetime.now(timezone.utc)
        date_folder = now.strftime("%Y%m%d")

        with db_manager.get_session() as session:
            # 1. Check if channel is currently in active failover
            from database.models.storage import StorageFailoverEvent
            from engines.storage_engine.enums import FailoverStatus
            active_failover = (
                session.query(StorageFailoverEvent)
                .filter_by(channel_id=channel_id, status=FailoverStatus.ACTIVE.value)
                .order_by(StorageFailoverEvent.triggered_at.desc())
                .first()
            )
            if active_failover and active_failover.failover_volume_id:
                failover_vol = session.query(StorageVolume).filter_by(id=active_failover.failover_volume_id, is_active=True).first()
                if failover_vol:
                    ok, _ = self.policy_engine.is_volume_eligible_for_write(failover_vol, required_mb)
                    if ok and os.path.exists(failover_vol.mount_path):
                        session.expunge(failover_vol)
                        dir_path = str(Path(failover_vol.mount_path) / channel_id / date_folder)
                        return failover_vol, dir_path, True

            alloc = session.query(StorageAllocation).filter_by(channel_id=channel_id).first()
            if alloc:
                # Check primary volume
                primary_vol = session.query(StorageVolume).filter_by(id=alloc.primary_volume_id).first()
                if primary_vol:
                    ok, _ = self.policy_engine.is_volume_eligible_for_write(primary_vol, required_mb)
                    if ok and os.path.exists(primary_vol.mount_path):
                        session.expunge(primary_vol)
                        dir_path = str(Path(primary_vol.mount_path) / channel_id / date_folder)
                        return primary_vol, dir_path, False

                # If primary is not eligible, check failover volume
                if alloc.failover_volume_id:
                    failover_vol = session.query(StorageVolume).filter_by(id=alloc.failover_volume_id).first()
                    if failover_vol:
                        ok, _ = self.policy_engine.is_volume_eligible_for_write(failover_vol, required_mb)
                        if ok and os.path.exists(failover_vol.mount_path):
                            session.expunge(failover_vol)
                            dir_path = str(Path(failover_vol.mount_path) / channel_id / date_folder)
                            logger.warning("Primary storage ineligible for channel [%s] -> redirected to failover volume [%s]",
                                           channel_id, failover_vol.name)
                            return failover_vol, dir_path, True

            # Fallback to default volume
            def_vol = session.query(StorageVolume).filter_by(is_default=True, is_active=True).first()
            if not def_vol:
                def_vol = session.query(StorageVolume).filter_by(is_active=True).first()

            if def_vol:
                session.expunge(def_vol)
                dir_path = str(Path(def_vol.mount_path) / channel_id / date_folder)
                return def_vol, dir_path, False

        # If no volume exists in DB, use default configured recordings dir
        fallback_dir = Path(settings.storage.recordings_dir) / channel_id / date_folder
        fallback_dir.mkdir(parents=True, exist_ok=True)
        synthetic_vol = StorageVolume(
            name="Emergency Local Storage",
            mount_path=str(Path(settings.storage.recordings_dir).resolve()),
            total_bytes=100 * 1024 * 1024 * 1024,
            available_bytes=50 * 1024 * 1024 * 1024,
            is_active=True,
        )
        return synthetic_vol, str(fallback_dir), False
