"""
Alarm Policy Engine.
Phase 12 (F-046, Change ID: CHG-20261125-009).

Manages severity, priority, deduplication windows, escalation timeouts,
and notification channels with support for runtime policy overrides.
"""

import json
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from engines.alarm_engine.enums import (
    AlarmSeverity,
    AlarmPriority,
    AlarmCategory,
)
from database.database_manager import db_manager
from database.models.alarms import AlarmPolicy
from core.logging.logger import get_logger

logger = get_logger("alarm_policy_engine")


@dataclass
class EffectiveAlarmPolicy:
    rule_name: str
    event_source: str
    event_type: str
    severity: AlarmSeverity
    priority: AlarmPriority
    enabled: bool = True
    dedup_window_seconds: int = 60
    escalation_timeout_seconds: int = 300
    escalation_target_role: str = "SUPERVISOR"
    notification_channels: list = field(default_factory=lambda: ["DESKTOP", "IN_APP"])
    auto_resolve_timeout_seconds: int = 0


DEFAULT_POLICIES = [
    # Security
    EffectiveAlarmPolicy("Intrusion Detection", "ANALYTICS", "INTRUSION", AlarmSeverity.HIGH, AlarmPriority.P2_HIGH, dedup_window_seconds=60, escalation_timeout_seconds=300),
    EffectiveAlarmPolicy("Tripwire Crossing", "ANALYTICS", "LINE_CROSSING", AlarmSeverity.MEDIUM, AlarmPriority.P3_NORMAL, dedup_window_seconds=30, escalation_timeout_seconds=600),
    EffectiveAlarmPolicy("Loitering Alert", "ANALYTICS", "LOITERING", AlarmSeverity.MEDIUM, AlarmPriority.P3_NORMAL, dedup_window_seconds=120, escalation_timeout_seconds=600),
    EffectiveAlarmPolicy("Unattended Object", "BEHAVIOUR", "ABANDONED_OBJECT", AlarmSeverity.HIGH, AlarmPriority.P2_HIGH, dedup_window_seconds=120, escalation_timeout_seconds=300),
    EffectiveAlarmPolicy("Theft / Object Removed", "BEHAVIOUR", "REMOVED_OBJECT", AlarmSeverity.HIGH, AlarmPriority.P2_HIGH, dedup_window_seconds=60, escalation_timeout_seconds=180),
    EffectiveAlarmPolicy("ANPR Watchlist Match", "ANPR", "WATCHLIST_ALERT", AlarmSeverity.HIGH, AlarmPriority.P1_URGENT, dedup_window_seconds=60, escalation_timeout_seconds=120),
    EffectiveAlarmPolicy("Face Candidate Match", "FACE", "CANDIDATE_MATCH", AlarmSeverity.MEDIUM, AlarmPriority.P2_HIGH, dedup_window_seconds=60, escalation_timeout_seconds=300),
    
    # Safety
    EffectiveAlarmPolicy("Human Fall Detected", "BEHAVIOUR", "FALL_DETECTED", AlarmSeverity.HIGH, AlarmPriority.P1_URGENT, dedup_window_seconds=30, escalation_timeout_seconds=120),
    EffectiveAlarmPolicy("Crowd Density Critical", "BEHAVIOUR", "CROWD_CRITICAL", AlarmSeverity.HIGH, AlarmPriority.P2_HIGH, dedup_window_seconds=60, escalation_timeout_seconds=300),
    EffectiveAlarmPolicy("Crowd Density Warning", "BEHAVIOUR", "CROWD_WARNING", AlarmSeverity.MEDIUM, AlarmPriority.P3_NORMAL, dedup_window_seconds=60, escalation_timeout_seconds=600),
    EffectiveAlarmPolicy("Wrong-Way Movement", "BEHAVIOUR", "WRONG_WAY", AlarmSeverity.MEDIUM, AlarmPriority.P3_NORMAL, dedup_window_seconds=30, escalation_timeout_seconds=600),
    
    # Network & Hardware
    EffectiveAlarmPolicy("Camera Stream Offline", "STREAM", "STREAM_DISCONNECTED", AlarmSeverity.HIGH, AlarmPriority.P2_HIGH, dedup_window_seconds=180, escalation_timeout_seconds=300),
    EffectiveAlarmPolicy("Stream Frozen", "STREAM", "STREAM_FROZEN", AlarmSeverity.MEDIUM, AlarmPriority.P3_NORMAL, dedup_window_seconds=120, escalation_timeout_seconds=600),
    EffectiveAlarmPolicy("Stream Recovered", "STREAM", "STREAM_RECOVERED", AlarmSeverity.INFORMATIONAL, AlarmPriority.P4_LOW, dedup_window_seconds=60, auto_resolve_timeout_seconds=1),
    EffectiveAlarmPolicy("Network Gateway Outage", "NETWORK", "GATEWAY_OFFLINE", AlarmSeverity.CRITICAL, AlarmPriority.P1_URGENT, dedup_window_seconds=300, escalation_timeout_seconds=120),
    EffectiveAlarmPolicy("Network Bandwidth Congestion", "NETWORK", "BANDWIDTH_CONGESTION", AlarmSeverity.MEDIUM, AlarmPriority.P3_NORMAL, dedup_window_seconds=180, escalation_timeout_seconds=600),
    EffectiveAlarmPolicy("Storage Volume Critical", "STORAGE", "VOLUME_CRITICAL", AlarmSeverity.CRITICAL, AlarmPriority.P1_URGENT, dedup_window_seconds=300, escalation_timeout_seconds=120),
    EffectiveAlarmPolicy("Storage Volume Warning", "STORAGE", "VOLUME_LOW", AlarmSeverity.MEDIUM, AlarmPriority.P3_NORMAL, dedup_window_seconds=600, escalation_timeout_seconds=1800),
    
    # Forensics
    EffectiveAlarmPolicy("Forensic Tamper Failure", "FORENSICS", "INTEGRITY_FAILURE", AlarmSeverity.CRITICAL, AlarmPriority.P1_URGENT, dedup_window_seconds=60, escalation_timeout_seconds=120),
]


class AlarmPolicyEngine:
    """Manages policy lookups, database overrides, and default mappings."""

    def __init__(self) -> None:
        self._policy_cache: Dict[str, EffectiveAlarmPolicy] = {}
        self._load_policies()

    def _load_policies(self) -> None:
        """Loads default policies and any custom overrides from database."""
        # 1. Populate defaults
        for pol in DEFAULT_POLICIES:
            key = f"{pol.event_source.upper()}:{pol.event_type.upper()}"
            self._policy_cache[key] = pol

        # 2. Overlay from DB
        try:
            with db_manager.get_session() as session:
                db_policies = session.query(AlarmPolicy).filter(AlarmPolicy.is_deleted == False).all()
                for db_p in db_policies:
                    key = f"{db_p.event_source.upper()}:{db_p.event_type.upper()}"
                    channels = json.loads(db_p.notification_channels) if db_p.notification_channels else ["DESKTOP", "IN_APP"]
                    self._policy_cache[key] = EffectiveAlarmPolicy(
                        rule_name=db_p.rule_name,
                        event_source=db_p.event_source,
                        event_type=db_p.event_type,
                        severity=AlarmSeverity(db_p.severity),
                        priority=AlarmPriority(db_p.priority),
                        enabled=db_p.enabled,
                        dedup_window_seconds=db_p.dedup_window_seconds,
                        escalation_timeout_seconds=db_p.escalation_timeout_seconds,
                        escalation_target_role=db_p.escalation_target_role,
                        notification_channels=channels,
                        auto_resolve_timeout_seconds=db_p.auto_resolve_timeout_seconds,
                    )
        except Exception as e:
            logger.debug("Could not read custom alarm policies from database: %s", e)

    def get_policy(self, source: str, event_type: str) -> EffectiveAlarmPolicy:
        """Returns the effective policy for an event source and type."""
        key = f"{source.upper()}:{event_type.upper()}"
        if key in self._policy_cache:
            return self._policy_cache[key]

        # Check partial source match
        for k, pol in self._policy_cache.items():
            if k.startswith(f"{source.upper()}:"):
                return pol

        # Generic Fallback
        return EffectiveAlarmPolicy(
            rule_name=f"Generic {event_type}",
            event_source=source,
            event_type=event_type,
            severity=AlarmSeverity.MEDIUM,
            priority=AlarmPriority.P3_NORMAL,
            enabled=True,
            dedup_window_seconds=60,
            escalation_timeout_seconds=300,
            escalation_target_role="SUPERVISOR",
        )
