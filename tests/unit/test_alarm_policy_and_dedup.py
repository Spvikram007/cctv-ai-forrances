"""
Unit tests for Alarm Policy Engine and Deduplicator (Phase 12 - F-046).
"""

import time
import pytest

from engines.alarm_engine.policy_engine import AlarmPolicyEngine
from engines.alarm_engine.deduplicator import AlarmDeduplicator
from engines.alarm_engine.enums import AlarmSeverity, AlarmPriority


def test_alarm_policy_engine_lookups():
    engine = AlarmPolicyEngine()
    
    # 1. Exact match
    p_int = engine.get_policy("ANALYTICS", "INTRUSION")
    assert p_int.severity == AlarmSeverity.HIGH
    assert p_int.priority == AlarmPriority.P2_HIGH
    assert p_int.dedup_window_seconds == 60

    # 2. Critical forensic policy
    p_for = engine.get_policy("FORENSICS", "INTEGRITY_FAILURE")
    assert p_for.severity == AlarmSeverity.CRITICAL
    assert p_for.priority == AlarmPriority.P1_URGENT

    # 3. Fallback policy
    p_unknown = engine.get_policy("UNKNOWN_SUBSYSTEM", "CUSTOM_EVENT")
    assert p_unknown.severity == AlarmSeverity.MEDIUM
    assert p_unknown.priority == AlarmPriority.P3_NORMAL


def test_alarm_deduplicator_sliding_window():
    dedup = AlarmDeduplicator(default_window_seconds=2)
    key = "STREAM:DISCONNECTED:cam_01"

    # First event: Not duplicate
    is_dup, ex_id, cnt = dedup.check_and_update(key, window_seconds=2)
    assert is_dup is False
    assert ex_id is None
    assert cnt == 1

    # Register active alarm
    dedup.register_alarm(key, "alarm_uuid_100", status="NEW")

    # Immediate second event: IS duplicate
    is_dup, ex_id, cnt = dedup.check_and_update(key, window_seconds=2)
    assert is_dup is True
    assert ex_id == "alarm_uuid_100"
    assert cnt == 2

    # Third rapid event: count becomes 3
    is_dup, ex_id, cnt = dedup.check_and_update(key, window_seconds=2)
    assert is_dup is True
    assert cnt == 3

    # When alarm is marked RESOLVED, cache is evicted
    dedup.update_status("alarm_uuid_100", "RESOLVED")
    is_dup, ex_id, cnt = dedup.check_and_update(key, window_seconds=2)
    assert is_dup is False
    assert cnt == 1
