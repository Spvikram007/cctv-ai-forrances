"""
Database Models Package Export.
"""

from database.models.base import Base
from database.models.users import Role, Permission, RolePermission, User, UserSession, AuditLog
from database.models.devices import (
    Site,
    Location,
    Device,
    DeviceCredential,
    DeviceChannel,
    StreamProfile,
    DeviceCapability,
    DeviceStatus,
    DeviceDiscoveryRecord,
    StreamHealthLog,
    NVRChannelMapping,
)
from database.models.recordings import StorageVolume, Recording, RecordingSegment, RecordingSchedule
from database.models.ai import AIModel, AIModelVersion, AIJob, Detection, ObjectTrack, AIEvent

__all__ = [
    "Base",
    "Role",
    "Permission",
    "RolePermission",
    "User",
    "UserSession",
    "AuditLog",
    "Site",
    "Location",
    "Device",
    "DeviceCredential",
    "DeviceChannel",
    "StreamProfile",
    "DeviceCapability",
    "DeviceStatus",
    "DeviceDiscoveryRecord",
    "StreamHealthLog",
    "NVRChannelMapping",
    "StorageVolume",
    "Recording",
    "RecordingSegment",
    "RecordingSchedule",
    "AIModel",
    "AIModelVersion",
    "AIJob",
    "Detection",
    "ObjectTrack",
    "AIEvent",
]
