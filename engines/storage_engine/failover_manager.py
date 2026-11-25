"""
Storage Failover and Controlled Recovery Manager.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

import time
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional, List

from database.database_manager import db_manager
from database.models.recordings import StorageVolume
from database.models.storage import StorageFailoverEvent, StorageAllocation
from engines.storage_engine.enums import FailoverStatus, VolumeStatus
from engines.storage_engine.allocation_manager import StorageAllocationManager
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("storage_failover")


class StorageFailoverManager:
    """
    Detects storage volume unavailability or write failures, redirects recordings
    to eligible failover targets, records failover events with gap calculations,
    and coordinates controlled failback upon primary recovery.
    """

    def __init__(self, allocation_manager: Optional[StorageAllocationManager] = None) -> None:
        self.allocation_manager = allocation_manager or StorageAllocationManager()
        self._active_failovers: Dict[str, Dict[str, Any]] = {}  # channel_id -> failover_info

    def handle_storage_failure(
        self,
        channel_id: str,
        failed_volume_id: str,
        reason: str = "Disk write failure / path unreachable",
        gap_seconds: float = 0.0,
    ) -> Tuple[Optional[StorageVolume], str]:
        """
        Triggered when a recording write operation fails on a primary volume.
        Selects an alternate destination, logs the failover event, and publishes alarms.
        """
        now = datetime.now(timezone.utc)
        logger.error("Handling storage failure for channel [%s] on volume [%s]: %s",
                     channel_id, failed_volume_id, reason)

        with db_manager.get_session() as session:
            # Mark primary volume degraded or offline
            failed_vol = session.query(StorageVolume).filter_by(id=failed_volume_id).first()
            if failed_vol:
                failed_vol.volume_status = VolumeStatus.DEGRADED.value
                failed_vol.health_score = max(0.0, failed_vol.health_score - 50.0)

            # Query candidate failover volume
            alloc = session.query(StorageAllocation).filter_by(channel_id=channel_id).first()
            failover_vol = None
            if alloc and alloc.failover_volume_id and alloc.failover_volume_id != failed_volume_id:
                failover_vol = session.query(StorageVolume).filter_by(id=alloc.failover_volume_id, is_active=True).first()

            # If no designated failover volume, find any active volume marked as failover target
            if not failover_vol:
                failover_vol = (
                    session.query(StorageVolume)
                    .filter(
                        StorageVolume.id != failed_volume_id,
                        StorageVolume.is_active == True,
                        StorageVolume.is_failover_target == True,
                    )
                    .first()
                )

            # Fallback to any active volume with sufficient space
            if not failover_vol:
                failover_vol = (
                    session.query(StorageVolume)
                    .filter(
                        StorageVolume.id != failed_volume_id,
                        StorageVolume.is_active == True,
                    )
                    .order_by(StorageVolume.available_bytes.desc())
                    .first()
                )

            if not failover_vol:
                err_msg = f"CRITICAL: No eligible failover storage volume available for channel [{channel_id}]!"
                logger.critical(err_msg)
                bus.publish("storage.write_failure", {
                    "channel_id": channel_id,
                    "failed_volume_id": failed_volume_id,
                    "error": err_msg,
                }, source="failover_manager")
                return None, err_msg

            # Log StorageFailoverEvent in database
            failover_event = StorageFailoverEvent(
                channel_id=channel_id,
                primary_volume_id=failed_volume_id,
                failover_volume_id=str(failover_vol.id),
                triggered_at=now,
                reason=reason,
                status=FailoverStatus.ACTIVE.value,
                gap_seconds=gap_seconds,
                segments_redirected=1,
            )
            session.add(failover_event)
            session.flush()
            event_id = str(failover_event.id)

            session.expunge(failover_vol)

        # Track in memory
        self._active_failovers[channel_id] = {
            "event_id": event_id,
            "primary_volume_id": failed_volume_id,
            "failover_volume_id": str(failover_vol.id),
            "triggered_at": now,
            "gap_seconds": gap_seconds,
        }

        # Publish EventBus alert for Alarm Engine
        bus.publish("storage.failover_active", {
            "event_id": event_id,
            "channel_id": channel_id,
            "failed_volume_id": failed_volume_id,
            "failover_volume_id": str(failover_vol.id),
            "failover_volume_name": failover_vol.name,
            "gap_seconds": gap_seconds,
            "reason": reason,
        }, source="failover_manager")

        if gap_seconds > 0.0:
            bus.publish("storage.recording_gap", {
                "channel_id": channel_id,
                "gap_seconds": gap_seconds,
                "reason": f"Storage failover transition gap ({gap_seconds:.2f}s)",
            }, source="failover_manager")

        logger.warning("Failover activated for [%s]: Redirected to volume [%s] (gap: %.2fs)",
                       channel_id, failover_vol.name, gap_seconds)
        return failover_vol, "Failover activated"

    def execute_controlled_failback(
        self,
        channel_id: str,
        operator: Optional[str] = "SYSTEM",
    ) -> Tuple[bool, str]:
        """
        Verifies primary storage health and performs controlled failback to primary volume.
        """
        now = datetime.now(timezone.utc)
        failover_info = self._active_failovers.get(channel_id)

        with db_manager.get_session() as session:
            # Query active failover event
            event = None
            if failover_info:
                event = session.query(StorageFailoverEvent).filter_by(id=failover_info["event_id"]).first()
            if not event:
                event = (
                    session.query(StorageFailoverEvent)
                    .filter_by(channel_id=channel_id, status=FailoverStatus.ACTIVE.value)
                    .order_by(StorageFailoverEvent.triggered_at.desc())
                    .first()
                )

            if not event:
                return False, f"No active failover record found for channel [{channel_id}]."

            primary_vol = session.query(StorageVolume).filter_by(id=event.primary_volume_id).first()
            if not primary_vol:
                return False, f"Primary volume [{event.primary_volume_id}] does not exist."

            # Verify primary volume is actually recovered and healthy
            ok, reason = self.allocation_manager.policy_engine.is_volume_eligible_for_write(primary_vol)
            if not ok:
                return False, f"Cannot failback: Primary volume is still ineligible ({reason})."

            # Execute failback
            event.status = FailoverStatus.FAILED_BACK.value
            event.resolved_at = now
            event.failback_at = now

            primary_vol.volume_status = VolumeStatus.ONLINE.value
            primary_vol.health_score = 100.0
            primary_id = str(primary_vol.id)
            primary_name = str(primary_vol.name)

        self._active_failovers.pop(channel_id, None)

        bus.publish("storage.failback_completed", {
            "channel_id": channel_id,
            "primary_volume_id": primary_id,
            "operator": operator,
        }, source="failover_manager")

        logger.info("Controlled failback completed for [%s] to primary volume [%s]", channel_id, primary_name)
        return True, f"Failback to primary volume [{primary_name}] completed successfully."

    execute_failback = execute_controlled_failback
