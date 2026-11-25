"""
Alarm Engine Enumerations and Constants.
Phase 12 (F-046, Change ID: CHG-20261125-009).
"""

from enum import Enum


class AlarmSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"


class AlarmPriority(str, Enum):
    P1_URGENT = "P1_URGENT"
    P2_HIGH = "P2_HIGH"
    P3_NORMAL = "P3_NORMAL"
    P4_LOW = "P4_LOW"


class AlarmStatus(str, Enum):
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"


class AlarmCategory(str, Enum):
    SECURITY = "SECURITY"
    SAFETY = "SAFETY"
    OPERATIONAL = "OPERATIONAL"
    NETWORK = "NETWORK"
    FORENSIC = "FORENSIC"
    HARDWARE = "HARDWARE"


class SubsystemSource(str, Enum):
    AI = "AI"
    ANALYTICS = "ANALYTICS"
    BEHAVIOUR = "BEHAVIOUR"
    STREAM = "STREAM"
    NETWORK = "NETWORK"
    STORAGE = "STORAGE"
    FORENSICS = "FORENSICS"
    SYSTEM = "SYSTEM"


class AlarmAction(str, Enum):
    CREATED = "CREATED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    ASSIGNED = "ASSIGNED"
    REASSIGNED = "REASSIGNED"
    STATUS_CHANGE = "STATUS_CHANGE"
    ESCALATED = "ESCALATED"
    NOTE_ADDED = "NOTE_ADDED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"
    LINKED = "LINKED"
