"""
Storage Adapter Base Interface and Metrics Data Structures.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass
from engines.storage_engine.enums import StorageType, HealthStatus


@dataclass
class StorageMetrics:
    total_bytes: int
    used_bytes: int
    free_bytes: int
    used_percent: float
    total_gb: float
    used_gb: float
    free_gb: float
    read_latency_ms: float = 0.0
    write_latency_ms: float = 0.0
    throughput_mbps: float = 0.0
    status: HealthStatus = HealthStatus.HEALTHY
    filesystem: str = "NTFS"
    is_read_only: bool = False
    error_message: Optional[str] = None


class StorageAdapter(ABC):
    """Abstract base class for storage devices, local volumes, RAID arrays, and NAS mounts."""

    @property
    @abstractmethod
    def adapter_type(self) -> StorageType:
        """Returns the storage type handled by this adapter."""
        pass

    @abstractmethod
    def get_metrics(self, volume_path: str) -> StorageMetrics:
        """Samples capacity, utilization, and read/write latency metrics."""
        pass

    @abstractmethod
    def test_read_write(self, volume_path: str) -> Tuple[bool, float, Optional[str]]:
        """
        Executes an atomic read/write probe on the storage target.
        Returns (success: bool, latency_ms: float, error: Optional[str]).
        """
        pass

    @abstractmethod
    def check_availability(self, volume_path: str) -> bool:
        """Quickly checks whether the storage path is mounted and reachable."""
        pass

    @abstractmethod
    def resolve_path(self, volume_path: str, relative_path: str) -> str:
        """Resolves a canonical filesystem path, preventing path traversal attacks."""
        pass

    @abstractmethod
    def ensure_directory(self, directory_path: str) -> bool:
        """Ensures the specified directory structure exists on the target storage."""
        pass

    @abstractmethod
    def get_capabilities(self, volume_path: str) -> Dict[str, Any]:
        """Queries underlying filesystem and hardware capabilities."""
        pass
