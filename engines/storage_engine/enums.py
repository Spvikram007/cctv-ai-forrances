"""
Storage Engine Enums & Constants.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

from enum import Enum


class StorageType(str, Enum):
    LOCAL = "LOCAL"
    RAID = "RAID"
    NAS_SMB = "NAS_SMB"
    NAS_NFS = "NAS_NFS"


class VolumeStatus(str, Enum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    READ_ONLY = "READ_ONLY"
    FULL = "FULL"


class RAIDLevel(str, Enum):
    RAID0 = "RAID0"
    RAID1 = "RAID1"
    RAID5 = "RAID5"
    RAID6 = "RAID6"
    RAID10 = "RAID10"
    JBOD = "JBOD"
    UNKNOWN = "UNKNOWN"


class RAIDStatus(str, Enum):
    OPTIMAL = "OPTIMAL"
    DEGRADED = "DEGRADED"
    REBUILDING = "REBUILDING"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class PoolTier(str, Enum):
    HOT = "HOT"
    WARM = "WARM"
    COLD = "COLD"
    ARCHIVE = "ARCHIVE"


class ArchivalTier(str, Enum):
    WARM = "WARM"
    COLD = "COLD"


class FailoverStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RECOVERED = "RECOVERED"
    FAILED_BACK = "FAILED_BACK"


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class NASProtocol(str, Enum):
    SMB = "SMB"
    NFS = "NFS"


class AllocationPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class TelemetrySource(str, Enum):
    DIRECT_WMI = "DIRECT_WMI"
    VENDOR_API = "VENDOR_API"
    SIMULATED = "SIMULATED"
    UNSUPPORTED = "UNSUPPORTED"


class ArchivalJobStatus(str, Enum):
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
