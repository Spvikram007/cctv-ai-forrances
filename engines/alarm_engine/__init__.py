"""
Unified Alarm Management Engine Package Export.
Phase 12 (F-046, Change ID: CHG-20261125-009).
"""

from engines.alarm_engine.enums import (
    AlarmSeverity,
    AlarmPriority,
    AlarmStatus,
    AlarmCategory,
    SubsystemSource,
    AlarmAction,
)
from engines.alarm_engine.normalizer import (
    NormalizedAlarmEvent,
    EventNormalizer,
)
from engines.alarm_engine.policy_engine import (
    AlarmPolicyEngine,
    EffectiveAlarmPolicy,
)
from engines.alarm_engine.deduplicator import AlarmDeduplicator
from engines.alarm_engine.correlator import AlarmCorrelator
from engines.alarm_engine.escalator import AlarmEscalationManager
from engines.alarm_engine.notification import AlarmNotificationDispatcher
from engines.alarm_engine.alarm_service import (
    AlarmEngineService,
    alarm_service,
    ROLE_PERMISSIONS,
)
from engines.alarm_engine.adapters import (
    AlarmEventBusAdapter,
    alarm_adapter,
)

__all__ = [
    "AlarmSeverity",
    "AlarmPriority",
    "AlarmStatus",
    "AlarmCategory",
    "SubsystemSource",
    "AlarmAction",
    "NormalizedAlarmEvent",
    "EventNormalizer",
    "AlarmPolicyEngine",
    "EffectiveAlarmPolicy",
    "AlarmDeduplicator",
    "AlarmCorrelator",
    "AlarmEscalationManager",
    "AlarmNotificationDispatcher",
    "AlarmEngineService",
    "alarm_service",
    "ROLE_PERMISSIONS",
    "AlarmEventBusAdapter",
    "alarm_adapter",
]
