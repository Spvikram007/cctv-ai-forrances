"""
Phase 12.2 Final Independent Validation Test Suite.
Change ID: CHG-20261125-011 (F-046).

Validates:
1. Database-level partial unique index constraint and atomic multi-worker concurrency.
2. Alarm history tampering, deletion, reordering, and external checkpoint verification against chain reconstruction.
3. Durable notification queues, failure tracking, retries, and permanent failure transitions.
4. Comprehensive 11-category event source matrix verification.
5. Sensitive biometric vector stripping and RBAC evidence access auditing.
6. Retention pruning with evidence lock preservation.
"""

import os
import uuid
import json
import time
import threading
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import text

from database.database_manager import db_manager
from database.models.alarms import Alarm, AlarmHistory, AlarmNotification, AlarmEvent
from engines.alarm_engine.alarm_service import alarm_service
from engines.alarm_engine.normalizer import EventNormalizer, NormalizedAlarmEvent
from engines.alarm_engine.enums import AlarmStatus, AlarmSeverity, AlarmPriority, AlarmCategory, AlarmAction
from engines.alarm_engine.notification import AlarmNotificationDispatcher
from core.events.event_bus import bus


class TestPhase122DatabaseUniquenessAndConcurrency:
    """Validates database-level uniqueness constraints and atomic concurrent upsert."""

    def test_database_partial_unique_index_exists(self):
        """Verifies actual SQLite schema contains uq_alarm_active_dedup partial unique index."""
        db_manager.init_schema()
        with db_manager.get_session() as session:
            conn = session.connection()
            indexes = conn.execute(text("PRAGMA index_list(alarms)")).fetchall()
            index_names = [idx[1] for idx in indexes]
            assert "uq_alarm_active_dedup" in index_names, f"uq_alarm_active_dedup missing from {index_names}"

            # Verify it is unique
            uq_meta = [idx for idx in indexes if idx[1] == "uq_alarm_active_dedup"][0]
            assert uq_meta[2] == 1, "Index uq_alarm_active_dedup is not marked as UNIQUE in SQLite"

    def test_concurrent_multi_worker_identical_event_race(self):
        """
        Simulates 10 concurrent worker threads simultaneously ingesting identical events with the same dedup_key.
        Proves that database constraints prevent split duplicates and occurrence counts remain strictly accurate.
        """
        dedup_key = f"RACE:CAMERA:{uuid.uuid4().hex[:8]}"
        num_workers = 10
        barrier = threading.Barrier(num_workers)
        created_alarm_ids = []
        lock = threading.Lock()

        def _worker_task(worker_idx: int):
            event = NormalizedAlarmEvent(
                event_id=f"race_evt_{worker_idx}_{uuid.uuid4().hex[:6]}",
                source_subsystem="STREAM",
                event_type="STREAM_DISCONNECTED",
                title="Camera Stream Disconnected (Race Test)",
                description="Worker race evaluation",
                category=AlarmCategory.HARDWARE,
                severity=AlarmSeverity.HIGH,
                priority=AlarmPriority.P2_HIGH,
                camera_id="cam_race_test",
                dedup_key=dedup_key,
            )
            # Synchronize thread execution at the gate so all 10 insert simultaneously
            barrier.wait()
            alarm_id = alarm_service.process_normalized_event(event)
            with lock:
                created_alarm_ids.append(alarm_id)

        threads = [threading.Thread(target=_worker_task, args=(i,)) for i in range(num_workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All workers must return the exact same alarm ID
        assert len(created_alarm_ids) == num_workers
        unique_returned_ids = set(created_alarm_ids)
        assert len(unique_returned_ids) == 1, f"Expected 1 unique alarm ID, but got {len(unique_returned_ids)}: {unique_returned_ids}"
        target_alarm_id = created_alarm_ids[0]

        # Verify database state
        with db_manager.get_session() as session:
            active_alarms = (
                session.query(Alarm)
                .filter(
                    Alarm.dedup_key == dedup_key,
                    Alarm.status.in_([AlarmStatus.NEW.value, AlarmStatus.ACKNOWLEDGED.value, AlarmStatus.IN_PROGRESS.value, AlarmStatus.REOPENED.value]),
                    Alarm.is_deleted == False,
                )
                .all()
            )
            # Exactly 1 active row exists in the database
            assert len(active_alarms) == 1
            alarm = active_alarms[0]
            assert str(alarm.id) == target_alarm_id
            # Occurrence count must be exactly 10
            assert alarm.occurrence_count == num_workers

    def test_resolved_alarm_permits_subsequent_reuse_of_dedup_key(self):
        """
        Verifies that once an alarm is closed or resolved, a subsequent event
        with the same dedup_key successfully creates a new active alarm without conflict.
        """
        dedup_key = f"LIFECYCLE:{uuid.uuid4().hex[:8]}"
        ev1 = NormalizedAlarmEvent(
            event_id=f"lifecycle_1_{uuid.uuid4().hex[:6]}",
            source_subsystem="ANALYTICS",
            event_type="LINE_CROSSING",
            title="Line Crossing 1",
            description="Initial event",
            category=AlarmCategory.SECURITY,
            severity=AlarmSeverity.MEDIUM,
            priority=AlarmPriority.P3_NORMAL,
            dedup_key=dedup_key,
        )
        id1 = alarm_service.process_normalized_event(ev1)
        assert id1 != ""

        # Close first alarm
        alarm_service.close_alarm(id1, operator="admin1", role="ADMIN", reason="Incident resolved")

        # Ingest subsequent event with the exact same dedup_key
        ev2 = NormalizedAlarmEvent(
            event_id=f"lifecycle_2_{uuid.uuid4().hex[:6]}",
            source_subsystem="ANALYTICS",
            event_type="LINE_CROSSING",
            title="Line Crossing 2",
            description="Subsequent event after closure",
            category=AlarmCategory.SECURITY,
            severity=AlarmSeverity.MEDIUM,
            priority=AlarmPriority.P3_NORMAL,
            dedup_key=dedup_key,
        )
        id2 = alarm_service.process_normalized_event(ev2)
        assert id2 != ""
        assert id2 != id1, "Subsequent event after closure should create a distinct new alarm"


class TestPhase122AlarmHistoryIntegrityAndCheckpoints:
    """Validates tamper-evidence, record alterations, deletion, reordering, and external checkpoint anchors."""

    @pytest.fixture
    def sample_alarm_with_history(self):
        ev = NormalizedAlarmEvent(
            event_id=f"hist_evt_{uuid.uuid4().hex[:6]}",
            source_subsystem="BEHAVIOUR",
            event_type="FALL_DETECTED",
            title="Fall Detection Audit Test",
            description="Audit trail validation",
            category=AlarmCategory.SAFETY,
            severity=AlarmSeverity.HIGH,
            priority=AlarmPriority.P1_URGENT,
            dedup_key=f"HIST:{uuid.uuid4().hex[:6]}",
        )
        alarm_id = alarm_service.process_normalized_event(ev)
        alarm_service.acknowledge_alarm(alarm_id, operator="operator_a", role="OPERATOR", comments="Investigating fall")
        alarm_service.add_operator_note(alarm_id, operator="operator_a", role="OPERATOR", note="Ambulance dispatched")
        alarm_service.resolve_alarm(alarm_id, operator="operator_a", role="OPERATOR", resolution_notes="Target safe")
        return alarm_id

    def test_tamper_detection_on_record_modification(self, sample_alarm_with_history):
        """Modifying an existing history entry in the database immediately triggers cryptographic digest mismatch."""
        alarm_id = sample_alarm_with_history
        assert alarm_service.verify_history_integrity(alarm_id)["valid"] is True

        # Tamper directly with entry 1 in the database
        with db_manager.get_session() as session:
            entry = session.query(AlarmHistory).filter(AlarmHistory.alarm_id == alarm_id, AlarmHistory.entry_index == 1).first()
            entry.comments = "MALICIOUSLY_ALTERED_COMMENTS"

        result = alarm_service.verify_history_integrity(alarm_id)
        assert result["valid"] is False
        assert result["broken_at_index"] == 1
        assert "Cryptographic digest mismatch" in result["details"]

    def test_tamper_detection_on_intermediate_record_deletion(self, sample_alarm_with_history):
        """Deleting an intermediate history record triggers index discontinuity and linkage break."""
        alarm_id = sample_alarm_with_history

        # Delete intermediate entry 2
        with db_manager.get_session() as session:
            entry = session.query(AlarmHistory).filter(AlarmHistory.alarm_id == alarm_id, AlarmHistory.entry_index == 2).first()
            session.delete(entry)

        result = alarm_service.verify_history_integrity(alarm_id)
        assert result["valid"] is False
        assert result["broken_at_index"] == 2
        assert "Index discontinuity" in result["details"]

    def test_tamper_detection_on_record_reordering(self, sample_alarm_with_history):
        """Swapping entry_index between two records is detected."""
        alarm_id = sample_alarm_with_history

        with db_manager.get_session() as session:
            e1 = session.query(AlarmHistory).filter(AlarmHistory.alarm_id == alarm_id, AlarmHistory.entry_index == 1).first()
            e2 = session.query(AlarmHistory).filter(AlarmHistory.alarm_id == alarm_id, AlarmHistory.entry_index == 2).first()
            e1.entry_index = 99
            e2.entry_index = 1
            e1.entry_index = 2

        result = alarm_service.verify_history_integrity(alarm_id)
        assert result["valid"] is False

    def test_external_checkpoint_detects_tail_truncation(self, tmp_path):
        """
        Proves that an attacker deleting the last history record (tail truncation)
        is immediately detected by external filesystem checkpoints.
        """
        cp_file = str(tmp_path / "test_trunc_checkpoints.jsonl")

        ev = NormalizedAlarmEvent(
            event_id=f"cp_trunc_{uuid.uuid4().hex[:6]}",
            source_subsystem="FORENSICS",
            event_type="INTEGRITY_FAILURE",
            title="Forensic Audit Test (Truncation)",
            description="Checkpoint test",
            category=AlarmCategory.FORENSIC,
            severity=AlarmSeverity.CRITICAL,
            priority=AlarmPriority.P1_URGENT,
            dedup_key=f"CP_TRUNC:{uuid.uuid4().hex[:6]}",
        )
        alarm_id = alarm_service.process_normalized_event(ev)
        alarm_service.acknowledge_alarm(alarm_id, operator="investigator1", role="INVESTIGATOR")
        alarm_service.resolve_alarm(alarm_id, operator="investigator1", role="INVESTIGATOR", resolution_notes="Resolved")

        # Create authoritative external checkpoint
        cp = alarm_service.create_history_checkpoint(alarm_id, custom_path=cp_file)
        assert cp["signature"] is not None
        assert cp["total_entries"] == 3

        # Legitimate verification succeeds
        valid_res = alarm_service.verify_history_integrity(alarm_id, custom_checkpoint_path=cp_file)
        assert valid_res["valid"] is True
        assert valid_res["checkpoint_verified"] is True

        # ATTACK: Attacker deletes the last entry (tail truncation)
        with db_manager.get_session() as session:
            last_entry = session.query(AlarmHistory).filter(AlarmHistory.alarm_id == alarm_id, AlarmHistory.entry_index == 2).first()
            session.delete(last_entry)

        trunc_res = alarm_service.verify_history_integrity(alarm_id, custom_checkpoint_path=cp_file)
        assert trunc_res["valid"] is False
        assert trunc_res["checkpoint_violation"] is True
        assert "truncation violation" in trunc_res["details"]

    def test_external_checkpoint_detects_chain_reconstruction_attack(self, tmp_path):
        """
        Proves that an attacker who completely rewrites the database and fabricates
        a mathematically consistent internal hash chain is caught by external filesystem checkpoints.
        """
        cp_file = str(tmp_path / "test_recon_checkpoints.jsonl")

        ev = NormalizedAlarmEvent(
            event_id=f"cp_recon_{uuid.uuid4().hex[:6]}",
            source_subsystem="FORENSICS",
            event_type="INTEGRITY_FAILURE",
            title="Forensic Audit Test (Reconstruction)",
            description="Checkpoint test",
            category=AlarmCategory.FORENSIC,
            severity=AlarmSeverity.CRITICAL,
            priority=AlarmPriority.P1_URGENT,
            dedup_key=f"CP_RECON:{uuid.uuid4().hex[:6]}",
        )
        alarm_id = alarm_service.process_normalized_event(ev)
        alarm_service.acknowledge_alarm(alarm_id, operator="investigator1", role="INVESTIGATOR")
        alarm_service.resolve_alarm(alarm_id, operator="investigator1", role="INVESTIGATOR", resolution_notes="Resolved")

        # Create authoritative external checkpoint outside the database
        cp = alarm_service.create_history_checkpoint(alarm_id, custom_path=cp_file)
        assert cp["signature"] is not None
        assert cp["total_entries"] == 3

        # Legitimate verification succeeds
        assert alarm_service.verify_history_integrity(alarm_id, custom_checkpoint_path=cp_file)["valid"] is True

        # ATTACK: Attacker fabricates an entirely new history chain with forged timestamps
        # and recomputed SHA-256 hashes. Internally the chain is mathematically valid, but fails against external checkpoint!
        with db_manager.get_session() as session:
            session.query(AlarmHistory).filter(AlarmHistory.alarm_id == alarm_id).delete()
            # Insert 3 fabricated entries
            h0 = alarm_service.compute_history_hash(0, alarm_id, "0" * 64, None, "NEW", "ATTACKER", "CREATED", "2026-01-01 00:00:00.000000", "Forged", "Forged")
            h1 = alarm_service.compute_history_hash(1, alarm_id, h0, "NEW", "ACKNOWLEDGED", "ATTACKER", "ACKNOWLEDGED", "2026-01-01 00:01:00.000000", "Forged", "Forged")
            h2 = alarm_service.compute_history_hash(2, alarm_id, h1, "ACKNOWLEDGED", "RESOLVED", "ATTACKER", "RESOLVED", "2026-01-01 00:02:00.000000", "Forged", "Forged")

            session.add(AlarmHistory(alarm_id=alarm_id, entry_index=0, previous_status=None, new_status="NEW", operator="ATTACKER", action="CREATED", timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc), reason="Forged", comments="Forged", prev_hash="0"*64, entry_hash=h0))
            session.add(AlarmHistory(alarm_id=alarm_id, entry_index=1, previous_status="NEW", new_status="ACKNOWLEDGED", operator="ATTACKER", action="ACKNOWLEDGED", timestamp=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc), reason="Forged", comments="Forged", prev_hash=h0, entry_hash=h1))
            session.add(AlarmHistory(alarm_id=alarm_id, entry_index=2, previous_status="ACKNOWLEDGED", new_status="RESOLVED", operator="ATTACKER", action="RESOLVED", timestamp=datetime(2026, 1, 1, 0, 2, tzinfo=timezone.utc), reason="Forged", comments="Forged", prev_hash=h1, entry_hash=h2))

        # Without external checkpoint, internal verification would pass:
        internal_only = alarm_service.verify_history_integrity(alarm_id, custom_checkpoint_path="/nonexistent/checkpoints.jsonl")
        assert internal_only["valid"] is True, "Internal-only verification cannot detect whole-chain rewrite"

        # WITH authoritative external checkpoint, whole-chain reconstruction is caught!
        cross_res = alarm_service.verify_history_integrity(alarm_id, custom_checkpoint_path=cp_file)
        assert cross_res["valid"] is False
        assert cross_res["checkpoint_violation"] is True
        assert "chain reconstruction/forgery detected" in cross_res["details"]


class TestPhase122NotificationReliabilityAndRetries:
    """Validates durable notification queues, transport error simulation, retries, and failure tracking."""

    def test_durable_retry_on_network_failure_and_recovery(self):
        """Simulates network failure / webhook timeout, durable failure logging, and successful retry."""
        dispatcher = AlarmNotificationDispatcher(suppression_cooldown_sec=0.0)
        alarm_id = f"notif_alarm_{uuid.uuid4().hex[:8]}"

        # Mock webhook handler with simulated transient network failure
        network_available = False

        def mock_webhook_handler(payload):
            if not network_available:
                raise ConnectionError("Network unreachable: Connection timed out after 5000ms")
            return True

        dispatcher.register_channel_handler("WEBHOOK", mock_webhook_handler)

        # 1. Dispatch while network is down
        channels = dispatcher.dispatch(
            alarm_id=alarm_id,
            title="Durable Notification Test",
            severity="CRITICAL",
            category="SECURITY",
            channels=["WEBHOOK"],
        )
        assert "WEBHOOK" not in channels

        # Verify failed notification is durably persisted in database
        with db_manager.get_session() as session:
            notif = session.query(AlarmNotification).filter(AlarmNotification.alarm_id == alarm_id, AlarmNotification.channel == "WEBHOOK").first()
            assert notif is not None
            assert notif.delivery_status == "FAILED"
            assert notif.retry_count == 1
            assert "Connection timed out" in notif.error_message
            assert notif.payload is not None
            notif_id = notif.id

        # 2. Attempt retry while network is STILL down
        retry_res1 = dispatcher.retry_failed_notifications(max_retries=3)
        assert retry_res1["failed"] >= 1
        with db_manager.get_session() as session:
            notif = session.query(AlarmNotification).filter(AlarmNotification.id == notif_id).first()
            assert notif.delivery_status == "FAILED"
            assert notif.retry_count == 2

        # 3. Network recovers!
        network_available = True
        retry_res2 = dispatcher.retry_failed_notifications(max_retries=3)
        assert retry_res2["succeeded"] >= 1
        with db_manager.get_session() as session:
            notif = session.query(AlarmNotification).filter(AlarmNotification.id == notif_id).first()
            assert notif.delivery_status == "DELIVERED"
            assert notif.error_message is None

    def test_permanent_failure_transition_after_max_retries(self):
        """Verifies that notifications exceeding max retries transition to PERMANENTLY_FAILED."""
        dispatcher = AlarmNotificationDispatcher(suppression_cooldown_sec=0.0)
        alarm_id = f"perm_alarm_{uuid.uuid4().hex[:8]}"

        def always_failing_handler(payload):
            raise RuntimeError("HTTP 500 Internal Server Error at upstream endpoint")

        dispatcher.register_channel_handler("FAILING_CHANNEL", always_failing_handler)

        dispatcher.dispatch(alarm_id=alarm_id, title="Test", severity="HIGH", category="OPERATIONAL", channels=["FAILING_CHANNEL"])

        # Exhaust retries
        dispatcher.retry_failed_notifications(max_retries=3)
        dispatcher.retry_failed_notifications(max_retries=3)

        with db_manager.get_session() as session:
            notif = session.query(AlarmNotification).filter(AlarmNotification.alarm_id == alarm_id, AlarmNotification.channel == "FAILING_CHANNEL").first()
            assert notif is not None
            assert notif.delivery_status == "PERMANENTLY_FAILED"
            assert notif.retry_count >= 3


class TestPhase122EventSourceCoverageMatrix:
    """Validates complete normalization, policy evaluation, and deduplication across all 11 user-specified event categories."""

    @pytest.mark.parametrize("subsystem,event_type,expected_cat,expected_sev,extra_data", [
        ("CAMERA", "AUTH_FAILURE", AlarmCategory.SECURITY, AlarmSeverity.HIGH, {"channel_id": "cam_auth_01"}),
        ("STREAM", "STREAM_DISCONNECTED", AlarmCategory.HARDWARE, AlarmSeverity.HIGH, {"channel_id": "cam_stream_01"}),
        ("STREAM", "STREAM_RECOVERED", AlarmCategory.OPERATIONAL, AlarmSeverity.INFORMATIONAL, {"channel_id": "cam_stream_01"}),
        ("STREAM", "STREAM_FROZEN", AlarmCategory.OPERATIONAL, AlarmSeverity.MEDIUM, {"channel_id": "cam_stream_01", "duration": 5.2}),
        ("RECORDING", "FAILED", AlarmCategory.HARDWARE, AlarmSeverity.CRITICAL, {"channel_id": "cam_rec_01", "error": "Disk full"}),
        ("RECORDING", "INTERRUPTED", AlarmCategory.HARDWARE, AlarmSeverity.HIGH, {"channel_id": "cam_rec_01", "reason": "Buffer overflow"}),
        ("STORAGE", "VOLUME_LOW", AlarmCategory.HARDWARE, AlarmSeverity.MEDIUM, {"volume_path": "D:\\Surveillance"}),
        ("STORAGE", "WRITE_FAILURE", AlarmCategory.HARDWARE, AlarmSeverity.CRITICAL, {"volume_path": "D:\\Surveillance", "error": "Read-only I/O"}),
        ("STORAGE", "VOLUME_CRITICAL", AlarmCategory.HARDWARE, AlarmSeverity.CRITICAL, {"volume_path": "D:\\Surveillance"}),
        ("ANALYTICS", "INTRUSION", AlarmCategory.SECURITY, AlarmSeverity.HIGH, {"channel_id": "cam_ai_01", "zone_id": "zone_restricted"}),
        ("ANALYTICS", "LINE_CROSSING", AlarmCategory.SECURITY, AlarmSeverity.MEDIUM, {"channel_id": "cam_ai_01", "direction": "A->B"}),
        ("BEHAVIOUR", "FALL_DETECTED", AlarmCategory.SAFETY, AlarmSeverity.HIGH, {"channel_id": "cam_safety_01"}),
        ("ANPR", "WATCHLIST_ALERT", AlarmCategory.SECURITY, AlarmSeverity.HIGH, {"channel_id": "cam_gate", "plate_text": "KA01AB1234"}),
        ("FACE", "CANDIDATE_MATCH", AlarmCategory.SECURITY, AlarmSeverity.MEDIUM, {"channel_id": "cam_lobby", "identity_name": "John Doe", "similarity": 0.88}),
        ("NETWORK", "SECURITY_ALERT", AlarmCategory.NETWORK, AlarmSeverity.HIGH, {"ip_address": "192.168.1.100", "cve_id": "CVE-2021-36260"}),
        ("FORENSICS", "INTEGRITY_FAILURE", AlarmCategory.FORENSIC, AlarmSeverity.CRITICAL, {"evidence_id": "pkg_evidence_001"}),
    ])
    def test_canonical_event_normalization_and_policy(self, subsystem, event_type, expected_cat, expected_sev, extra_data):
        norm = EventNormalizer.normalize(subsystem, event_type, extra_data)
        assert norm.category == expected_cat
        assert norm.severity == expected_sev
        assert norm.dedup_key is not None
        assert len(norm.dedup_key) > 5

        alarm_id = alarm_service.process_normalized_event(norm)
        assert alarm_id != ""


class TestPhase122SensitiveEventSecurityAndRetention:
    """Validates biometric vector stripping, RBAC evidence access, soft deletion, and retention pruning."""

    def test_biometric_vectors_stripped_from_metadata(self):
        """Verifies raw 512-d float vectors and raw embedding keys are completely stripped from metadata."""
        raw_vector = [0.12345 + i * 0.001 for i in range(512)]
        data = {
            "channel_id": "cam_sec_01",
            "identity_name": "Subject 42",
            "similarity": 0.92,
            "raw_embedding": raw_vector,
            "feature_vector": raw_vector,
            "face_vector": raw_vector,
            "arbitrary_high_dim": [0.5] * 128,
            "safe_metadata": "keep_this",
        }
        norm = EventNormalizer.normalize("FACE", "CANDIDATE_MATCH", data)
        assert "raw_embedding" not in norm.metadata
        assert "feature_vector" not in norm.metadata
        assert "face_vector" not in norm.metadata
        assert "arbitrary_high_dim" not in norm.metadata
        assert norm.metadata.get("safe_metadata") == "keep_this"
        assert norm.metadata.get("verification_status") == "UNCONFIRMED_CANDIDATE_MATCH"

    def test_rbac_evidence_access_and_audit_trail(self):
        """Verifies RBAC enforcement on evidence access and hash-chained audit logging."""
        ev = NormalizedAlarmEvent(
            event_id=f"ev_access_{uuid.uuid4().hex[:6]}",
            source_subsystem="FACE",
            event_type="CANDIDATE_MATCH",
            title="Biometric Evidence Test",
            description="Testing evidence access",
            category=AlarmCategory.SECURITY,
            severity=AlarmSeverity.HIGH,
            priority=AlarmPriority.P2_HIGH,
            dedup_key=f"EVID:{uuid.uuid4().hex[:6]}",
        )
        alarm_id = alarm_service.process_normalized_event(ev)

        # Viewer role must be rejected
        with pytest.raises(PermissionError):
            alarm_service.audit_evidence_access(alarm_id, operator="viewer1", role="VIEWER")

        # Operator role lacks ACCESS_EVIDENCE and must be rejected
        with pytest.raises(PermissionError):
            alarm_service.audit_evidence_access(alarm_id, operator="operator1", role="OPERATOR")

        # Investigator role has ACCESS_EVIDENCE and succeeds
        ok = alarm_service.audit_evidence_access(alarm_id, operator="investigator1", role="INVESTIGATOR", evidence_type="FACE_SNAPSHOT", comments="Case #102")
        assert ok is True

        # Verify audit history
        history = alarm_service.get_alarm_history(alarm_id)
        latest_entry = history[-1]
        assert latest_entry["action"] == AlarmAction.EVIDENCE_VIEWED.value
        assert latest_entry["operator"] == "investigator1"
        assert "FACE_SNAPSHOT" in latest_entry["reason"]

    def test_soft_delete_and_retention_prune_with_evidence_lock(self):
        """Verifies soft-deletion RBAC and retention pruning preserving locked evidence."""
        # 1. Soft delete by non-admin must fail
        ev = NormalizedAlarmEvent(
            event_id=f"del_evt_{uuid.uuid4().hex[:6]}",
            source_subsystem="ANALYTICS",
            event_type="LOITERING",
            title="Deletion Test",
            description="Delete test",
            category=AlarmCategory.SECURITY,
            severity=AlarmSeverity.LOW,
            priority=AlarmPriority.P4_LOW,
            dedup_key=f"DEL:{uuid.uuid4().hex[:6]}",
        )
        alarm_id = alarm_service.process_normalized_event(ev)

        with pytest.raises(PermissionError):
            alarm_service.soft_delete_alarm(alarm_id, operator="operator1", role="OPERATOR")

        # Admin soft-delete succeeds
        assert alarm_service.soft_delete_alarm(alarm_id, operator="admin1", role="ADMIN", reason="Test deletion") is True

        # Verify marked is_deleted
        alarm_rec = alarm_service.get_alarm_by_id(alarm_id)
        assert alarm_rec is None  # Filtered out by get_alarm_by_id

        # 2. Retention prune preserving locked evidence
        with db_manager.get_session() as session:
            old_time = datetime.now(timezone.utc) - timedelta(days=120)
            # Locked alarm
            locked_alarm = Alarm(
                title="Locked Evidence Alarm",
                category="SECURITY",
                source_subsystem="FORENSICS",
                status="CLOSED",
                last_detected_at=old_time,
                evidence_refs=json.dumps({"is_locked": True, "package_id": "pkg_01"}),
            )
            # Unlocked alarm
            unlocked_alarm = Alarm(
                title="Unlocked Expired Alarm",
                category="SECURITY",
                source_subsystem="ANALYTICS",
                status="CLOSED",
                last_detected_at=old_time,
                evidence_refs=json.dumps({"is_locked": False}),
            )
            session.add(locked_alarm)
            session.add(unlocked_alarm)
            session.flush()
            locked_id = str(locked_alarm.id)
            unlocked_id = str(unlocked_alarm.id)

        # Purge
        purged = alarm_service.purge_expired_alarms(retention_days=90, role="ADMIN")
        assert purged >= 1

        with db_manager.get_session() as session:
            check_locked = session.query(Alarm).filter(Alarm.id == locked_id).first()
            check_unlocked = session.query(Alarm).filter(Alarm.id == unlocked_id).first()
            assert check_locked.is_deleted is False, "Locked evidence alarm must NOT be purged"
            assert check_unlocked.is_deleted is True, "Unlocked expired alarm must be soft-deleted"
