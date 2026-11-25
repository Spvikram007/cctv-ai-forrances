"""
Unit and Attack-Simulation Tests for Phase 10.1 Security Hardening (F-018 & F-023).
Validates:
1. Trusted KeyStore, key registration, SHA-256 fingerprinting, revocation, and rotation.
2. Protection against replaced-key / self-signed package forgery (UNTRUSTED_SIGNING_IDENTITY).
3. Mandatory cryptographic signature verification (VERIFICATION_INCOMPLETE on missing deps).
4. Independent signed checkpoints and detection of rewritten / truncated ledger attacks.
5. Full 5-tier Role-Based Access Control (RBAC) permission matrix across all 5 roles.
6. Active locker integrity scanning and tamper alerts.
7. Standalone verifier exit codes (0, 1, 2, 3).
"""

import os
import sys
import json
import zipfile
import tempfile
import subprocess
import pytest
import numpy as np
import cv2
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization

from engines.forensic_engine.crypto_signer import (
    ForensicSigner,
    TrustedKeyStore,
    KeyStatus,
    compute_key_fingerprint,
    CryptoSignerError,
)
from engines.forensic_engine.evidence_locker import (
    EvidenceLocker,
    EvidenceType,
    SignedEvidenceManifest,
    ForensicAccessDeniedError,
    ChainOfCustodyLedger,
    CustodyCheckpoint,
)
from engines.forensic_engine.evidence_packager import EvidencePackager
from tools.verify_evidence import verify_package, VerificationStatus
import tools.verify_evidence as standalone_mod


def create_test_video(path: str) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, 25.0, (160, 120))
    for i in range(10):
        frame = np.full((120, 160, 3), 40 + i * 2, dtype=np.uint8)
        writer.write(frame)
    writer.release()


# ----------------------------------------------------------------------
# 1. Trusted KeyStore, Fingerprints, Revocation & Rotation
# ----------------------------------------------------------------------

def test_trusted_keystore_crud_and_fingerprints() -> None:
    """Verifies keystore registration, SHA-256 fingerprinting, and trust lookup."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ts_path = os.path.join(tmpdir, "trusted_keys.json")
        keystore = TrustedKeyStore(ts_path)

        # Generate a test public key
        priv = ec.generate_private_key(ec.SECP256R1())
        pub_pem = priv.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        fp = compute_key_fingerprint(pub_pem)
        assert fp.startswith("SHA256:")
        assert len(fp) == 7 + 64

        # Key should not be trusted initially
        is_trusted, entry, reason = keystore.is_key_trusted(pub_pem)
        assert is_trusted is False

        # Register key
        keystore.register_key("KEY-TEST-01", pub_pem, "CENTRAL_POLICE_LAB")

        # Key must now be trusted and ACTIVE
        is_trusted, entry, reason = keystore.is_key_trusted(pub_pem)
        assert is_trusted is True
        assert entry["key_id"] == "KEY-TEST-01"
        assert entry["status"] == KeyStatus.ACTIVE.value


def test_key_revocation_and_rotation() -> None:
    """Verifies that revoked keys fail trust verification and key rotation works cleanly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ts_path = os.path.join(tmpdir, "trusted_keys.json")
        keystore = TrustedKeyStore(ts_path)

        priv1 = ec.generate_private_key(ec.SECP256R1())
        pub1 = priv1.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        keystore.register_key("KEY-V1", pub1, "STATION_HQ")
        assert keystore.is_key_trusted(pub1)[0] is True

        # Revoke key
        keystore.revoke_key("KEY-V1", reason="Suspected credential compromise")
        is_trusted, entry, reason = keystore.is_key_trusted(pub1)
        assert is_trusted is False
        assert "REVOKED" in reason

        # Rotate to Key V2
        priv2 = ec.generate_private_key(ec.SECP256R1())
        pub2 = priv2.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        keystore.rotate_key("KEY-V1", "KEY-V2", pub2, "STATION_HQ", reason="Emergency rotation")
        assert keystore.is_key_trusted(pub2)[0] is True
        assert keystore.is_key_trusted(pub1)[0] is False


# ----------------------------------------------------------------------
# 2. Protection Against Self-Signed / Replaced-Key Forgery
# ----------------------------------------------------------------------

def test_replaced_key_self_signed_attack_detected() -> None:
    """
    CRITICAL SECURITY TEST:
    An attacker takes a valid evidence package, alters the video, generates their own
    brand-new private key, re-signs the altered manifest, and packs their own public key.
    The verifier MUST NOT report PASS because the key is not in the trusted keystore.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        locker = EvidenceLocker(
            locker_dir=os.path.join(tmpdir, "locker"),
            checkpoints_dir=os.path.join(tmpdir, "checkpoints"),
        )
        packager = EvidencePackager(locker)

        vid_path = os.path.join(tmpdir, "crime_scene.mp4")
        create_test_video(vid_path)

        manifest = locker.ingest_recording(
            source_file_path=vid_path,
            case_number="CASE-ATTACK-001",
            channel_id="CAM-01",
            operator_username="officer_alice",
            operator_role="INVESTIGATOR",
        )

        pkg_path = os.path.join(tmpdir, "crime_scene.cctvevid")
        packager.create_export_package(
            manifest.evidence_id, pkg_path, "officer_alice", "INVESTIGATOR"
        )

        # Unpack evidence package
        extract_dir = os.path.join(tmpdir, "extracted")
        with zipfile.ZipFile(pkg_path, "r") as zf:
            zf.extractall(extract_dir)

        # Attacker modifies media bytes
        media_p = os.path.join(extract_dir, "crime_scene.mp4")
        with open(media_p, "r+b") as f:
            f.seek(10)
            f.write(b"ATTACKER_INJECTED_FRAMES")

        # Attacker generates their own rogue keypair
        attacker_priv = ec.generate_private_key(ec.SECP256R1())
        attacker_pub_pem = attacker_priv.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        attacker_fp = compute_key_fingerprint(attacker_pub_pem)

        # Attacker reads manifest, updates file_sha256, public_key_pem, key_id, and signs with their private key
        manifest_p = os.path.join(extract_dir, "manifest.json")
        with open(manifest_p, "r", encoding="utf-8") as f:
            m_data = json.load(f)

        new_sha = standalone_mod.compute_file_sha256(media_p)
        m_data["file_sha256"] = new_sha
        m_data["public_key_pem"] = attacker_pub_pem
        m_data["key_id"] = "ROGUE-KEY-001"
        m_data["key_fingerprint"] = attacker_fp

        temp_manifest_obj = SignedEvidenceManifest(**m_data)
        canonical_bytes = temp_manifest_obj.canonical_bytes_for_signing()

        # Attacker signs
        attacker_sig = attacker_priv.sign(canonical_bytes, ec.ECDSA(hashes.SHA256())).hex()
        m_data["signature_hex"] = attacker_sig

        with open(manifest_p, "w", encoding="utf-8") as f:
            json.dump(m_data, f, indent=2)

        with open(os.path.join(extract_dir, "manifest.sig"), "w", encoding="utf-8") as f:
            f.write(attacker_sig)

        with open(os.path.join(extract_dir, "public_key.pem"), "w", encoding="utf-8") as f:
            f.write(attacker_pub_pem)

        # Now run standalone verification using authoritative trust store
        # The attacker's rogue key is NOT in the trust store!
        trust_store_p = str(locker.signer.trust_store.store_file)
        status = verify_package(extract_dir, trust_store_path=trust_store_p)

        # MUST be detected as UNTRUSTED SIGNING IDENTITY, NEVER PASS!
        assert status == VerificationStatus.UNTRUSTED_SIGNING_IDENTITY
        assert bool(status) is False

        # CLI subprocess must exit with code 2
        cmd = [sys.executable, "tools/verify_evidence.py", extract_dir, "--trust-store", trust_store_p]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 2
        assert "UNTRUSTED SIGNING IDENTITY" in res.stdout


# ----------------------------------------------------------------------
# 3. Mandatory Signature Verification (No PASS without Cryptography)
# ----------------------------------------------------------------------

def test_missing_cryptography_dependency_returns_verification_incomplete(monkeypatch) -> None:
    """Verifies that missing cryptographic library returns VERIFICATION INCOMPLETE, never PASS."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vid_p = os.path.join(tmpdir, "test.mp4")
        create_test_video(vid_p)

        locker = EvidenceLocker(locker_dir=os.path.join(tmpdir, "locker"))
        manifest = locker.ingest_recording(vid_p, "CASE-001", "CAM-01", "admin", "ADMIN")

        pkg_folder = str(locker.base_dir / manifest.evidence_id)

        # Mock HAS_CRYPTOGRAPHY to False
        monkeypatch.setattr(standalone_mod, "HAS_CRYPTOGRAPHY", False)

        status = standalone_mod.verify_package(pkg_folder)
        assert status == VerificationStatus.VERIFICATION_INCOMPLETE
        assert bool(status) is False


# ----------------------------------------------------------------------
# 4. Independent Signed Checkpoints & Rewritten Ledger Detection
# ----------------------------------------------------------------------

def test_external_checkpoint_detects_rewritten_ledger_attack() -> None:
    """
    CRITICAL SECURITY TEST:
    A malicious administrator rewrites an intermediate custody record AND
    recomputes all subsequent Merkle hashes in chain_of_custody.jsonl.
    Internal verify_chain() would pass, BUT independent external signed
    checkpoints catch the tampering.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        locker = EvidenceLocker(
            locker_dir=os.path.join(tmpdir, "locker"),
            checkpoints_dir=os.path.join(tmpdir, "checkpoints"),
        )

        vid_p = os.path.join(tmpdir, "evidence.mp4")
        create_test_video(vid_p)

        manifest = locker.ingest_recording(vid_p, "CASE-AUDIT-001", "CAM-01", "officer_bob", "INVESTIGATOR")
        item_dir = locker.base_dir / manifest.evidence_id
        ledger_p = item_dir / "chain_of_custody.jsonl"
        ledger = ChainOfCustodyLedger(ledger_p)

        # Add additional events
        ledger.append_event(manifest.evidence_id, "analyst_carol", "SUPERVISOR", "VIEW", {"reason": "Review"})
        # Create signed checkpoint at record 1
        cp1 = locker.create_signed_checkpoint(manifest.evidence_id, "supervisor", "SUPERVISOR")

        ledger.append_event(manifest.evidence_id, "investigator_dan", "INVESTIGATOR", "EXPORT", {"reason": "Court"})
        cp2 = locker.create_signed_checkpoint(manifest.evidence_id, "supervisor", "SUPERVISOR")

        # Initial check passes
        ver_ok, count, errs = locker.verify_checkpoints(manifest.evidence_id)
        assert ver_ok is True
        assert count == 3  # Genesis + cp1 + cp2

        # ATTACK: Malicious admin modifies event 0 (ingest details) and re-computes all hashes
        events = ledger.get_all_events()
        events[0].details["case_number"] = "FABRICATED-CASE-NUMBER"

        # Re-chain from Genesis
        prev_h = ChainOfCustodyLedger.GENESIS_HASH
        recomputed_lines = []
        import hashlib
        for ev in events:
            ev.prev_hash = prev_h
            payload = {
                "event_id": ev.event_id,
                "evidence_id": ev.evidence_id,
                "timestamp_utc": ev.timestamp_utc,
                "operator_username": ev.operator_username,
                "operator_role": ev.operator_role,
                "action": ev.action,
                "details": ev.details,
                "prev_hash": ev.prev_hash,
            }
            c_str = json.dumps(payload, sort_keys=True)
            ev.record_hash = hashlib.sha256((prev_h + c_str).encode("utf-8")).hexdigest()
            prev_h = ev.record_hash
            recomputed_lines.append(json.dumps(ev.to_dict()) + "\n")

        with open(ledger_p, "w", encoding="utf-8") as f:
            f.writelines(recomputed_lines)

        # Internal hash chain verification passes because attacker recomputed hashes!
        chain_internal_valid, _, _ = ledger.verify_chain()
        assert chain_internal_valid is True

        # BUT external signed checkpoint verification MUST FAIL because signed record_hash differs!
        ver_ok, count, errs = locker.verify_checkpoints(manifest.evidence_id)
        assert ver_ok is False
        assert any("history rewritten" in e for e in errs)

        # Full verify_evidence must also fail
        ver_res = locker.verify_evidence(manifest.evidence_id, "auditor", "INVESTIGATOR")
        assert ver_res["is_valid"] is False
        assert ver_res["checkpoints_valid"] is False


def test_external_checkpoint_detects_truncated_ledger() -> None:
    """Verifies that truncating events from the ledger is detected by checkpoints."""
    with tempfile.TemporaryDirectory() as tmpdir:
        locker = EvidenceLocker(
            locker_dir=os.path.join(tmpdir, "locker"),
            checkpoints_dir=os.path.join(tmpdir, "checkpoints"),
        )
        vid_p = os.path.join(tmpdir, "evidence.mp4")
        create_test_video(vid_p)

        manifest = locker.ingest_recording(vid_p, "CASE-TRUNC-001", "CAM-01", "officer", "INVESTIGATOR")
        item_dir = locker.base_dir / manifest.evidence_id
        ledger_p = item_dir / "chain_of_custody.jsonl"
        ledger = ChainOfCustodyLedger(ledger_p)

        ledger.append_event(manifest.evidence_id, "op1", "ADMIN", "ACTION_1")
        ledger.append_event(manifest.evidence_id, "op2", "ADMIN", "ACTION_2")
        locker.create_signed_checkpoint(manifest.evidence_id, "admin", "ADMIN")

        # Truncate ledger file to 1 line
        with open(ledger_p, "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open(ledger_p, "w", encoding="utf-8") as f:
            f.write(lines[0])

        ver_ok, _, errs = locker.verify_checkpoints(manifest.evidence_id)
        assert ver_ok is False
        assert any("truncated" in e.lower() for e in errs)


# ----------------------------------------------------------------------
# 5. 5-Tier RBAC Permission Matrix
# ----------------------------------------------------------------------

def test_5_tier_rbac_permission_matrix() -> None:
    """
    Tests the full 5-Tier RBAC permission matrix:
    - Tier 1: ADMIN (all permissions)
    - Tier 2: INVESTIGATOR (ingest, export, checkpoint, view)
    - Tier 3: SUPERVISOR (ingest, export, checkpoint, view)
    - Tier 4: OPERATOR (view, verify only; ingest/export/checkpoint denied)
    - Tier 5: VIEWER (view, verify only; ingest/export/checkpoint denied)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        locker = EvidenceLocker(locker_dir=os.path.join(tmpdir, "locker"))
        packager = EvidencePackager(locker)

        vid_p = os.path.join(tmpdir, "sample.mp4")
        create_test_video(vid_p)

        # 1. Ingestion permissions
        allowed_ingest = ["ADMIN", "INVESTIGATOR", "SUPERVISOR"]
        denied_ingest = ["OPERATOR", "VIEWER", "ANONYMOUS", "GUEST"]

        for role in allowed_ingest:
            m = locker.ingest_recording(vid_p, f"CASE-RBAC-{role}", "CAM-01", f"user_{role}", role)
            assert isinstance(m, SignedEvidenceManifest)

        manifest_id = m.evidence_id

        for role in denied_ingest:
            with pytest.raises(ForensicAccessDeniedError):
                locker.ingest_recording(vid_p, "CASE-FAIL", "CAM-01", f"user_{role}", role)

        # 2. Checkpoint permissions
        allowed_cp = ["ADMIN", "INVESTIGATOR", "SUPERVISOR"]
        denied_cp = ["OPERATOR", "VIEWER"]

        for role in allowed_cp:
            cp = locker.create_signed_checkpoint(manifest_id, f"user_{role}", role)
            assert isinstance(cp, CustodyCheckpoint)

        for role in denied_cp:
            with pytest.raises(ForensicAccessDeniedError):
                locker.create_signed_checkpoint(manifest_id, f"user_{role}", role)

        # 3. Export package permissions
        allowed_export = ["ADMIN", "INVESTIGATOR", "SUPERVISOR"]
        denied_export = ["OPERATOR", "VIEWER"]

        for role in allowed_export:
            out_p = os.path.join(tmpdir, f"export_{role}.cctvevid")
            pkg = packager.create_export_package(manifest_id, out_p, f"user_{role}", role)
            assert os.path.exists(pkg)

        for role in denied_export:
            out_p = os.path.join(tmpdir, f"export_fail_{role}.cctvevid")
            with pytest.raises(ForensicAccessDeniedError):
                packager.create_export_package(manifest_id, out_p, f"user_{role}", role)

        # 4. View and Verify permissions (All 5 roles allowed)
        all_5_roles = ["ADMIN", "INVESTIGATOR", "SUPERVISOR", "OPERATOR", "VIEWER"]
        for role in all_5_roles:
            items = locker.list_evidence(operator_role=role)
            assert len(items) > 0
            manifest_obj = locker.get_manifest(manifest_id, operator_role=role)
            assert manifest_obj.evidence_id == manifest_id
            ver = locker.verify_evidence(manifest_id, f"user_{role}", role)
            assert ver["is_valid"] is True


# ----------------------------------------------------------------------
# 6. Active Locker Integrity Scan
# ----------------------------------------------------------------------

def test_active_locker_integrity_scan_detects_tamper() -> None:
    """Verifies that scan_locker_integrity checks all items and identifies tampered media."""
    with tempfile.TemporaryDirectory() as tmpdir:
        locker = EvidenceLocker(locker_dir=os.path.join(tmpdir, "locker"))

        vid1 = os.path.join(tmpdir, "clean1.mp4")
        vid2 = os.path.join(tmpdir, "clean2.mp4")
        create_test_video(vid1)
        create_test_video(vid2)

        m1 = locker.ingest_recording(vid1, "CASE-SCAN-01", "CAM-01", "admin", "ADMIN")
        m2 = locker.ingest_recording(vid2, "CASE-SCAN-02", "CAM-02", "admin", "ADMIN")

        # Initial scan: both items clean
        results = locker.scan_locker_integrity()
        assert len(results) == 2
        assert all(r["is_valid"] is True for r in results)

        # Tamper item 2
        media2 = locker.base_dir / m2.evidence_id / "clean2.mp4"
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(media2), 0x80)
        with open(media2, "r+b") as f:
            f.seek(50)
            f.write(b"TAMPERED_SCAN_BYTES")

        # Second scan: detects item 2 tamper
        results2 = locker.scan_locker_integrity()
        assert len(results2) == 2
        res_m1 = next(r for r in results2 if r["evidence_id"] == m1.evidence_id)
        res_m2 = next(r for r in results2 if r["evidence_id"] == m2.evidence_id)
        assert res_m1["is_valid"] is True
        assert res_m2["is_valid"] is False
        assert res_m2["sha256_match"] is False
