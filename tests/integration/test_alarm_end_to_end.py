"""
End-to-End Integration Tests for Unified Alarm Management Engine (Phase 12 - F-046).

Tests live EventBus publishing from subsystems (Analytics, ANPR, Stream, Network,
Storage, Forensics), normalization, deduplication bursts, multi-threaded concurrency,
and full lifecycle resolution.
"""

import time
import threading
from datetime import datetime, timezone
import pytest

from core.events.event_bus import bus
from engines.alarm_engine.alarm_service import alarm_service
from engines.alarm_engine.adapters import alarm_adapter
from engines.alarm_engine.enums import (
    AlarmSeverity,
    AlarmPriority,
    AlarmStatus,
    AlarmCategory,
)
from database.database_manager import db_manager
from database.models.alarms import Alarm, AlarmEvent, AlarmHistory


@pytest.fixture(autouse=True, scope="module")
def setup_alarm_adapters():
    """Ensures alarm EventBus adapters are active throughout the integration suite."""
    alarm_adapter.start()
    yield
    # Keep active or clean up if needed


def test_e2e_analytics_event_to_alarm_lifecycle():
    """
    Traces a real Analytics event published on EventBus:
    EventBus -> AlarmEventBusAdapter -> Ingestion Queue -> Normalization ->
    Deduplication -> DB Persistence -> Notification -> Acknowledgment -> Resolution.
    """
    channel_id = "cam_perimeter_south"
    event_payload = {
        "channel_id": channel_id,
        "rule_type": "INTRUSION",
        "zone_id": "Zone_Restricted",
        "confidence": 0.92,
        "bbox": [50, 60, 200, 350],
        "snapshot_path": "/storage/snapshots/intrusion_e2e.jpg",
        "timestamp": time.time(),
    }

    # 1. Publish directly onto the platform EventBus as analytics_pipeline does
    bus.publish("analytics.event", event_payload, source=f"pipeline:{channel_id}")

    # Give ingestion worker brief time to process queue
    time.sleep(0.3)

    # 2. Query database for created alarm
    with db_manager.get_session() as session:
        alarm = (
            session.query(Alarm)
            .filter(Alarm.camera_id == channel_id, Alarm.is_deleted == False)
            .order_by(Alarm.first_detected_at.desc())
            .first()
        )
        assert alarm is not None
        alarm_id = alarm.id
        assert alarm.category == AlarmCategory.SECURITY.value
        assert alarm.severity == AlarmSeverity.HIGH.value
        assert alarm.status == AlarmStatus.NEW.value
        assert "Zone_Restricted" in alarm.description

    # 3. Acknowledge the alarm
    ok_ack = alarm_service.acknowledge_alarm(alarm_id, operator="Sergeant_Vance", role="OPERATOR")
    assert ok_ack is True

    # 4. Resolve the alarm
    ok_res = alarm_service.resolve_alarm(alarm_id, operator="Sergeant_Vance", role="OPERATOR", reason="Authorized maintenance staff")
    assert ok_res is True

    # 5. Verify resolved state and history audit trail
    history = alarm_service.get_alarm_history(alarm_id)
    actions = [h["action"] for h in history]
    assert "CREATED" in actions
    assert "ACKNOWLEDGED" in actions
    assert "RESOLVED" in actions


def test_e2e_stream_disconnect_and_deduplication_burst():
    """
    Publishes a burst of 20 stream disconnect events.
    Verifies that the deduplicator merges them into a single active alarm
    with occurrence_count = 20 rather than generating 20 separate alarms.
    """
    cam_id = "cam_traffic_junction"

    # Fire 20 rapid disconnect events
    for _ in range(20):
        bus.publish("stream.disconnected", {"channel_id": cam_id, "reconnect_count": 5}, source="rtsp_streamer")

    time.sleep(0.4)

    with db_manager.get_session() as session:
        active_alarms = (
            session.query(Alarm)
            .filter(Alarm.camera_id == cam_id, Alarm.status == AlarmStatus.NEW.value, Alarm.is_deleted == False)
            .all()
        )
        # Must be exactly 1 consolidated alarm
        assert len(active_alarms) == 1
        alarm = active_alarms[0]
        assert alarm.occurrence_count == 20
        assert "Camera Stream Offline" in alarm.title


def test_e2e_concurrent_multi_threaded_ingestion():
    """
    Spawns 8 concurrent threads publishing events simultaneously.
    Verifies thread-safe ingestion without race conditions or database deadlocks.
    """
    num_threads = 8
    events_per_thread = 10
    total_expected = num_threads * events_per_thread

    def worker_task(thread_idx: int):
        for i in range(events_per_thread):
            cam = f"cam_concurrent_{thread_idx}_{i}"
            bus.publish(
                "anpr.watchlist_alert",
                {
                    "channel_id": cam,
                    "plate_text": f"DL{thread_idx}AB{i:04d}",
                    "watchlist_category": "Wanted",
                    "confidence": 0.95,
                },
                source="anpr_pipeline",
            )

    threads = [threading.Thread(target=worker_task, args=(t,)) for t in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Allow worker thread to drain queue
    time.sleep(0.8)

    # Verify alarms are created and searchable
    alarms, count = alarm_service.get_alarms(search="DL", limit=total_expected + 50)
    assert count >= total_expected


def test_e2e_forensic_integrity_failure_critical_alarm():
    """
    Publishes a forensic evidence tamper failure.
    Verifies CRITICAL severity and P1_URGENT priority assignment.
    """
    bus.publish(
        "forensic.integrity_failure",
        {
            "evidence_id": "EV-2026-BANK-VAULT-01",
            "details": "Digital signature verification failed. Public key mismatch.",
        },
        source="evidence_locker",
    )

    time.sleep(0.3)

    alarms, _ = alarm_service.get_alarms(severity=AlarmSeverity.CRITICAL.value, limit=10)
    vault_alarms = [a for a in alarms if "EV-2026-BANK-VAULT-01" in (a.get("description") or "")]
    assert len(vault_alarms) >= 1
    assert vault_alarms[0]["severity"] == "CRITICAL"
    assert vault_alarms[0]["priority"] == "P1_URGENT"

