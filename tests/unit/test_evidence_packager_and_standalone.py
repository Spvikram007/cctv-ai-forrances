"""
Unit Tests for Evidence Packaging & Standalone Verification Utility (Phase 10 & 10.1 - F-023).
"""

import os
import sys
import subprocess
import tempfile
import zipfile
import pytest
import numpy as np
import cv2

from engines.forensic_engine.evidence_locker import EvidenceLocker
from engines.forensic_engine.evidence_packager import EvidencePackager
from tools.verify_evidence import verify_package, VerificationStatus


@pytest.fixture
def packager_fixture():
    with tempfile.TemporaryDirectory() as tmpdir:
        locker = EvidenceLocker(locker_dir=os.path.join(tmpdir, "locker"))
        packager = EvidencePackager(locker)
        yield locker, packager, tmpdir


def create_test_video(path: str) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, 25.0, (160, 120))
    for i in range(10):
        frame = np.full((120, 160, 3), 50 + i * 3, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_create_and_verify_standalone_package(packager_fixture) -> None:
    """Verifies creation of .cctvevid package and execution of standalone verification."""
    locker, packager, tmpdir = packager_fixture
    vid_path = os.path.join(tmpdir, "test_raw.mp4")
    create_test_video(vid_path)

    manifest = locker.ingest_recording(
        source_file_path=vid_path,
        case_number="CASE-PKG-001",
        channel_id="CAM-01",
        operator_username="investigator_smith",
        operator_role="INVESTIGATOR",
    )

    pkg_path = os.path.join(tmpdir, "evidence_export.cctvevid")
    created_pkg = packager.create_export_package(
        evidence_id=manifest.evidence_id,
        export_destination_path=pkg_path,
        operator_username="investigator_smith",
        operator_role="INVESTIGATOR",
    )

    assert os.path.exists(created_pkg)

    # 1. Inspect package contents
    with zipfile.ZipFile(created_pkg, "r") as zf:
        namelist = zf.namelist()
        assert "manifest.json" in namelist
        assert "manifest.sig" in namelist
        assert "public_key.pem" in namelist
        assert "chain_of_custody.jsonl" in namelist
        assert "checkpoints.json" in namelist
        assert "verify_evidence.py" in namelist
        assert "README_FORENSIC_VERIFICATION.txt" in namelist
        assert "test_raw.mp4" in namelist

    # 2. Run standalone in-process verification with trust store
    trust_store_p = str(locker.signer.trust_store.store_file)
    status = verify_package(created_pkg, trust_store_path=trust_store_p)
    assert status == VerificationStatus.VERIFIED
    assert bool(status) is True

    # 3. Test execution via external python subprocess CLI (as court/defense would execute)
    cmd = [sys.executable, "tools/verify_evidence.py", created_pkg, "--trust-store", trust_store_p]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0
    assert "FINAL VERDICT: EVIDENCE IS CRYPTOGRAPHICALLY VALID" in result.stdout


def test_tampered_package_detected_by_standalone_verifier(packager_fixture) -> None:
    """Verifies that an altered package is rejected with non-zero exit code."""
    locker, packager, tmpdir = packager_fixture
    vid_path = os.path.join(tmpdir, "tamper_test.mp4")
    create_test_video(vid_path)

    manifest = locker.ingest_recording(
        source_file_path=vid_path,
        case_number="CASE-PKG-002",
        channel_id="CAM-01",
        operator_username="investigator_smith",
        operator_role="INVESTIGATOR",
    )

    pkg_path = os.path.join(tmpdir, "tamper_export.cctvevid")
    packager.create_export_package(
        evidence_id=manifest.evidence_id,
        export_destination_path=pkg_path,
        operator_username="investigator_smith",
        operator_role="INVESTIGATOR",
    )

    # Extract, tamper media, and repackage
    extract_dir = os.path.join(tmpdir, "extracted")
    with zipfile.ZipFile(pkg_path, "r") as zf:
        zf.extractall(extract_dir)

    # Modify media file bytes
    media_file = os.path.join(extract_dir, "tamper_test.mp4")
    with open(media_file, "r+b") as f:
        f.seek(50)
        f.write(b"CORRUPTED_BYTES_INJECTION")

    # Re-verify extracted folder directly
    trust_store_p = str(locker.signer.trust_store.store_file)
    status = verify_package(extract_dir, trust_store_path=trust_store_p)
    assert status == VerificationStatus.FAILED
    assert bool(status) is False

    # Subprocess CLI verification must fail with exit code 1
    cmd = [sys.executable, "tools/verify_evidence.py", extract_dir, "--trust-store", trust_store_p]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 1
    assert "FINAL VERDICT: EVIDENCE VERIFICATION FAILED" in result.stdout
