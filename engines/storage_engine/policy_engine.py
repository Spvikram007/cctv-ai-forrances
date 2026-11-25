"""
Storage Policy Engine for Capacity Quotas, Allocation Safeguards, and Retention Rules.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

from typing import Dict, Any, Optional
from database.database_manager import db_manager
from database.models.recordings import StorageVolume
from database.models.storage import StoragePolicy, StoragePool
from core.logging.logger import get_logger

logger = get_logger("storage_policy_engine")


class StoragePolicyEngine:
    """Evaluates write eligibility, safety thresholds, and quota compliance."""

    def __init__(
        self,
        default_warning_pct: float = 85.0,
        default_critical_pct: float = 95.0,
        default_min_free_gb: float = 10.0,
        default_retention_days: int = 30,
    ) -> None:
        self.default_warning_pct = default_warning_pct
        self.default_critical_pct = default_critical_pct
        self.default_min_free_gb = default_min_free_gb
        self.default_retention_days = default_retention_days

    def get_effective_policy_for_volume(self, volume: StorageVolume) -> Dict[str, Any]:
        """Resolves active threshold and retention settings for a given volume."""
        with db_manager.get_session() as session:
            if volume.pool_id:
                policy = session.query(StoragePolicy).filter_by(pool_id=volume.pool_id).first()
                if policy:
                    return {
                        "warning_threshold_pct": policy.warning_threshold_pct,
                        "critical_threshold_pct": policy.critical_threshold_pct,
                        "min_free_gb": policy.min_free_gb,
                        "retention_days": policy.retention_days,
                        "failover_enabled": policy.failover_enabled,
                        "archival_enabled": policy.archival_enabled,
                        "archival_age_days": policy.archival_age_days,
                    }

        return {
            "warning_threshold_pct": getattr(volume, "warning_threshold_pct", self.default_warning_pct),
            "critical_threshold_pct": self.default_critical_pct,
            "min_free_gb": self.default_min_free_gb,
            "retention_days": self.default_retention_days,
            "failover_enabled": True,
            "archival_enabled": False,
            "archival_age_days": 14,
        }

    def is_volume_eligible_for_write(
        self,
        volume: StorageVolume,
        required_mb: float = 50.0,
    ) -> Tuple[bool, str]:
        """
        Determines whether a volume has sufficient capacity and health to accept new writes.
        Returns (eligible: bool, reason: str).
        """
        if not volume.is_active:
            return False, f"Volume [{volume.name}] is marked inactive"

        v_status = str(getattr(volume, "volume_status", "ONLINE")).upper()
        if v_status in ["OFFLINE", "READ_ONLY", "FULL", "DEGRADED"]:
            return False, f"Volume [{volume.name}] status is {v_status}"

        policy = self.get_effective_policy_for_volume(volume)
        total = volume.total_bytes or 0
        used = volume.used_bytes or 0
        free = volume.available_bytes or 0

        if total > 0:
            used_pct = (used / total) * 100.0
            free_gb = free / (1024 ** 3)
            min_free = policy["min_free_gb"]
            crit_pct = policy["critical_threshold_pct"]

            if used_pct >= crit_pct:
                return False, f"Volume [{volume.name}] exceeds critical capacity ({used_pct:.1f}% >= {crit_pct}%)"

            if free_gb < min_free:
                return False, f"Volume [{volume.name}] free space below safety reserve ({free_gb:.1f} GB < {min_free:.1f} GB)"

            required_bytes = int(required_mb * 1024 * 1024)
            if free < required_bytes:
                return False, f"Volume [{volume.name}] cannot accommodate segment size ({free_gb:.2f} GB available)"

        return True, "Eligible"
