"""
Unit tests for Event Normalizer (Phase 12 - F-046).
"""

from datetime import datetime, timezone
import pytest

from engines.alarm_engine.normalizer import (
    EventNormalizer,
    NormalizedAlarmEvent,
)
from engines.alarm_engine.enums import (
    AlarmSeverity,
    AlarmPriority,
    AlarmCategory,
)


def test_normalize_analytics_intrusion():
    data = {
        "event_id": "evt_int_101",
        "channel_id": "cam_front",
        "rule_type": "INTRUSION",
        "zone_id": "Zone_North",
        "confidence": 0.88,
        "bbox": [100, 150, 200, 250],
        "snapshot_path": "/snapshots/int_101.jpg",
    }
    event = EventNormalizer.normalize("ANALYTICS", "INTRUSION", data)
    assert isinstance(event, NormalizedAlarmEvent)
    assert event.event_id == "evt_int_101"
    assert event.camera_id == "cam_front"
    assert event.category == AlarmCategory.SECURITY
    assert event.severity == AlarmSeverity.HIGH
    assert event.priority == AlarmPriority.P2_HIGH
    assert event.evidence_refs.get("snapshot_path") == "/snapshots/int_101.jpg"
    assert "ANALYTICS:INTRUSION:cam_front:Zone_North" in event.dedup_key


def test_normalize_behaviour_fall():
    data = {
        "event_id": "evt_fall_01",
        "channel_id": "cam_lobby",
        "rule_type": "FALL_DETECTED",
        "confidence": 0.95,
        "aspect_ratio": 1.45,
    }
    event = EventNormalizer.normalize("BEHAVIOUR", "FALL_DETECTED", data)
    assert event.category == AlarmCategory.SAFETY
    assert event.severity == AlarmSeverity.HIGH
    assert event.priority == AlarmPriority.P1_URGENT
    assert "Fall Detected" in event.title


def test_normalize_anpr_watchlist():
    data = {
        "channel_id": "cam_gate",
        "plate_text": "KA01MJ5678",
        "watchlist_category": "Stolen",
        "confidence": 0.99,
    }
    event = EventNormalizer.normalize("ANPR", "WATCHLIST_ALERT", data)
    assert event.category == AlarmCategory.SECURITY
    assert event.severity == AlarmSeverity.HIGH
    assert event.priority == AlarmPriority.P1_URGENT
    assert "KA01MJ5678" in event.title


def test_normalize_stream_disconnected():
    data = {"channel_id": "cam_parking_02", "reconnect_count": 3}
    event = EventNormalizer.normalize("STREAM", "STREAM_DISCONNECTED", data)
    assert event.category == AlarmCategory.HARDWARE
    assert event.severity == AlarmSeverity.HIGH
    assert "Camera Stream Offline" in event.title


def test_normalize_network_gateway_outage():
    data = {"gateway_ip": "192.168.1.1", "fault_type": "GATEWAY_OFFLINE"}
    event = EventNormalizer.normalize("NETWORK", "GATEWAY_OFFLINE", data)
    assert event.category == AlarmCategory.NETWORK
    assert event.severity == AlarmSeverity.CRITICAL
    assert event.priority == AlarmPriority.P1_URGENT


def test_normalize_forensic_integrity_failure():
    data = {"evidence_id": "evid_2026_01", "details": "SHA-256 hash mismatch"}
    event = EventNormalizer.normalize("FORENSICS", "INTEGRITY_FAILURE", data)
    assert event.category == AlarmCategory.FORENSIC
    assert event.severity == AlarmSeverity.CRITICAL
    assert event.priority == AlarmPriority.P1_URGENT
