"""
Volume Monitor and Health Checking Engine.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from database.database_manager import db_manager
from database.models.recordings import StorageVolume, StorageEvent
from database.models.storage import StorageHealthHistory
from engines.storage_engine.enums import HealthStatus, VolumeStatus
from engines.storage_engine.adapters.base import StorageMetrics
from engines.storage_engine.adapters.local import LocalStorageAdapter
from engines.storage_engine.adapters.raid import RAIDMonitoringAdapter
from engines.storage_engine.adapters.nas import NASStorageAdapter
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("volume_monitor")


class VolumeMonitor:
    """
    Monitors capacity, free space thresholds, read/write latencies, and availability
    across local, RAID, and NAS storage volumes. Emits alerts to EventBus for F-046.
    """

    def __init__(
        self,
        local_adapter: Optional[LocalStorageAdapter] = None,
        raid_adapter: Optional[RAIDMonitoringAdapter] = None,
        nas_adapter: Optional[NASStorageAdapter] = None,
    ) -> None:
        self.local = local_adapter or LocalStorageAdapter()
        self.raid = raid_adapter or RAIDMonitoringAdapter(local_fallback=self.local)
        self.nas = nas_adapter or NASStorageAdapter(local_fallback=self.local)

    def get_adapter_for_volume(self, volume: StorageVolume):
        """Returns the appropriate adapter based on volume_type."""
        v_type = getattr(volume, "volume_type", "LOCAL") or "LOCAL"
        v_type_str = str(v_type).upper()
        if "RAID" in v_type_str:
            return self.raid
        elif "NAS" in v_type_str or "SMB" in v_type_str or "NFS" in v_type_str:
            return self.nas
        return self.local

    def audit_volume(self, volume_id: str) -> Dict[str, Any]:
        """Samples metrics for a single volume and updates database."""
        with db_manager.get_session() as session:
            vol = session.query(StorageVolume).filter_by(id=volume_id).first()
            if not vol:
                return {"status": "NOT_FOUND", "volume_id": volume_id}

            adapter = self.get_adapter_for_volume(vol)
            metrics = adapter.get_metrics(vol.mount_path)

            # Update volume record
            vol.total_bytes = metrics.total_bytes
            vol.used_bytes = metrics.used_bytes
            vol.available_bytes = metrics.free_bytes
            vol.health_score = 100.0 if metrics.status == HealthStatus.HEALTHY else (70.0 if metrics.status == HealthStatus.WARNING else 20.0)

            if metrics.status == HealthStatus.CRITICAL:
                vol.volume_status = VolumeStatus.DEGRADED.value if metrics.free_gb > 1.0 else VolumeStatus.FULL.value
            elif metrics.status == HealthStatus.WARNING:
                vol.volume_status = VolumeStatus.ONLINE.value
            else:
                vol.volume_status = VolumeStatus.ONLINE.value

            # Record health history
            hist = StorageHealthHistory(
                volume_id=vol.id,
                measured_at=datetime.now(timezone.utc),
                read_latency_ms=metrics.read_latency_ms,
                write_latency_ms=metrics.write_latency_ms,
                throughput_mbps=metrics.throughput_mbps,
                used_pct=metrics.used_percent,
                free_gb=metrics.free_gb,
                status=metrics.status.value,
                error_details=metrics.error_message,
            )
            session.add(hist)

            # Evaluate thresholds and emit events
            self._evaluate_thresholds_and_emit(vol, metrics, session)

            return {
                "volume_id": vol.id,
                "name": vol.name,
                "mount_path": vol.mount_path,
                "used_pct": metrics.used_percent,
                "free_gb": metrics.free_gb,
                "status": metrics.status.value,
                "latency_ms": metrics.write_latency_ms,
                "error": metrics.error_message,
            }

    def audit_all_volumes(self) -> List[Dict[str, Any]]:
        """Audits all registered storage volumes."""
        results = []
        with db_manager.get_session() as session:
            volumes = session.query(StorageVolume).filter(StorageVolume.is_deleted == False).all()
            volume_ids = [str(v.id) for v in volumes]

        for vid in volume_ids:
            try:
                results.append(self.audit_volume(vid))
            except Exception as e:
                logger.error("Error auditing volume %s: %s", vid, e)
                results.append({"volume_id": vid, "status": "ERROR", "error": str(e)})

        return results

    def _evaluate_thresholds_and_emit(self, vol: StorageVolume, metrics: StorageMetrics, session) -> None:
        """Publishes structured EventBus topics on threshold breaches."""
        if metrics.status == HealthStatus.CRITICAL or metrics.used_percent >= vol.warning_threshold_pct + 5.0 or metrics.free_gb < 5.0:
            evt_type = "STORAGE:VOLUME_CRITICAL"
            severity = "CRITICAL"
            topic = "storage.volume_critical"
            msg = f"Critical storage alert: Volume [{vol.name}] at {metrics.used_percent:.1f}% ({metrics.free_gb:.1f} GB free)."
        elif metrics.status == HealthStatus.WARNING or metrics.used_percent >= vol.warning_threshold_pct or metrics.free_gb < 15.0:
            evt_type = "STORAGE:VOLUME_LOW"
            severity = "WARNING"
            topic = "storage.volume_low"
            msg = f"Low storage warning: Volume [{vol.name}] at {metrics.used_percent:.1f}% ({metrics.free_gb:.1f} GB free)."
        else:
            return

        # Record StorageEvent
        event = StorageEvent(
            volume_id=vol.id,
            event_type=evt_type,
            severity=severity,
            message=msg,
        )
        session.add(event)

        # Publish to EventBus
        bus.publish(
            topic,
            {
                "volume_id": str(vol.id),
                "volume_name": vol.name,
                "volume_path": vol.mount_path,
                "used_percent": metrics.used_percent,
                "free_gb": metrics.free_gb,
                "severity": severity,
                "error": metrics.error_message,
            },
            source="volume_monitor",
        )
