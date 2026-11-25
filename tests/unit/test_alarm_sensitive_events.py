"""
Unit Tests for Sensitive Biometric & ANPR Event Handling and Evidence RBAC Auditing.
Phase 12.1 (F-046, Change ID: CHG-20261125-010).

Verifies unconfirmed candidate match labeling, stripping of raw 512-d biometric embeddings,
and role-based evidence access control and cryptographic audit trails.
"""

import uuid
import pytest

from core.events.event_bus import bus
from engines.alarm_engine.alarm_service import alarm_service
from engines.alarm_engine.normalizer import EventNormalizer
from engines.alarm_engine.enums import AlarmCategory, AlarmSeverity, AlarmPriority, AlarmAction


def test_face_candidate_match_normalization_and_disclaimer():
    """
    Verifies that face candidate events are explicitly labeled as unconfirmed
    candidate matches requiring human review, and never declared as confirmed identities.
    """
    raw_payload = {
        "channel_id": "cam_lobby_01",
        "identity_name": "Jane Doe",
        "similarity": 0.88,
        "raw_embedding": [0.1234] * 512,  # Raw 512-d feature vector
        "feature_vector": [0.5678] * 128,
        "snapshot_path": "/storage/snapshots/face_match_001.jpg",
    }

    event = EventNormalizer.normalize("FACE", "CANDIDATE_MATCH", raw_payload)

    # 1. Title disclaimer
    assert "Face Candidate Match" in event.title
    assert "Pending Human Verification" in event.title

    # 2. Description disclaimer
    assert "UNCONFIRMED" in event.description
    assert "human verification" in event.description.lower()

    # 3. Verification status flag in metadata
    assert event.metadata.get("verification_status") == "UNCONFIRMED_CANDIDATE_MATCH"

    # 4. Sensitive biometric stripping: raw 512-d vectors MUST NOT exist in metadata
    assert "raw_embedding" not in event.metadata
    assert "feature_vector" not in event.metadata

    # 5. Non-sensitive references preserved
    assert event.evidence_refs.get("snapshot_path") == "/storage/snapshots/face_match_001.jpg"


def test_anpr_watchlist_candidate_normalization():
    """
    Verifies ANPR watchlist events require human verification and carry candidate disclaimers.
    """
    raw_payload = {
        "channel_id": "cam_gate_north",
        "plate_text": "MH02CB1234",
        "watchlist_category": "Stolen Vehicle",
        "confidence": 0.94,
    }

    event = EventNormalizer.normalize("ANPR", "WATCHLIST_ALERT", raw_payload)

    # Title & description checks
    assert "ANPR Watchlist Candidate" in event.title
    assert "Pending Verification" in event.title
    assert "UNCONFIRMED" in event.description
    assert event.metadata.get("verification_status") == "UNCONFIRMED_CANDIDATE_MATCH"
    assert event.severity == AlarmSeverity.HIGH
    assert event.priority == AlarmPriority.P1_URGENT


def test_evidence_access_rbac_permissions():
    """
    Verifies that only authorized roles (INVESTIGATOR, ADMIN) can access sensitive evidence.
    VIEWER and OPERATOR must receive a PermissionError.
    """
    raw_payload = {
        "channel_id": f"cam_secure_{uuid.uuid4().hex[:6]}",
        "identity_name": "John Doe",
        "similarity": 0.91,
    }
    event = EventNormalizer.normalize("FACE", "CANDIDATE_MATCH", raw_payload)
    alarm_id = alarm_service.process_normalized_event(event)

    # VIEWER: Permission denied
    with pytest.raises(PermissionError) as exc_info:
        alarm_service.audit_evidence_access(alarm_id, operator="guest_user", role="VIEWER", evidence_type="SNAPSHOT")
    assert "ACCESS_EVIDENCE" in str(exc_info.value)

    # OPERATOR: Permission denied (operators cannot access sensitive raw biometric evidence)
    with pytest.raises(PermissionError) as exc_info:
        alarm_service.audit_evidence_access(alarm_id, operator="op_bob", role="OPERATOR", evidence_type="SNAPSHOT")
    assert "ACCESS_EVIDENCE" in str(exc_info.value)

    # INVESTIGATOR: Allowed
    assert alarm_service.audit_evidence_access(alarm_id, operator="investigator_dave", role="INVESTIGATOR", evidence_type="BIOMETRIC_CROP")

    # ADMIN: Allowed
    assert alarm_service.audit_evidence_access(alarm_id, operator="admin_root", role="ADMIN", evidence_type="SNAPSHOT")

    # Check that audit history records both access events and remains cryptographically valid
    history = alarm_service.get_alarm_history(alarm_id)
    evidence_actions = [h for h in history if h["action"] == AlarmAction.EVIDENCE_VIEWED.value]
    assert len(evidence_actions) == 2
    assert evidence_actions[0]["operator"] == "investigator_dave"
    assert evidence_actions[1]["operator"] == "admin_root"

    # Integrity verification must pass
    verification = alarm_service.verify_history_integrity(alarm_id)
    assert verification["valid"] is True
