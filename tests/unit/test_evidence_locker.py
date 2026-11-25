"""
Unit Tests for Evidence Locker & Role-Based Access Control (Phase 10 - F-023).
"""

import os
import json
import tempfile
import pytest
import numpy as np
import cv2

from engines.forensic_engine.evidence_locker import (
    EvidenceLocker,
    EvidenceType,
    SignedEvidenceManifest,
    ForensicAccessDeniedError,
)


@pytest.fixture
def locker() -> EvidenceLocker:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield EvidenceLocker(locker_dir=tmpdir)


def create_sample_video(path: str) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, 25.0, (160, 120))
    for i in range(15):
        frame = np.full((120, 160, 3), 40 + i * 2, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_ingest_original_recording(locker: EvidenceLocker) -> None:
    """Verifies ingestion of raw camera recording as ORIGINAL_CAPTURE."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "raw_capture.mp4")
        create_sample_video(src)

        manifest = locker.ingest_recording(
            source_file_path=src,
            case_number="CASE-2026-001",
            channel_id="CAM-01",
            operator_username="investigator_smith",
            operator_role="INVESTIGATOR",
        )

        assert isinstance(manifest, SignedEvidenceManifest)
        assert manifest.evidence_type == EvidenceType.ORIGINAL_CAPTURE.value
        assert len(manifest.file_sha256) == 64
        assert manifest.is_sealed is True
        assert len(manifest.signature_hex) > 60

        # Verify locker files created
        item_dir = locker.base_dir / manifest.evidence_id
        assert (item_dir / "manifest.json").exists()
        assert (item_dir / "manifest.sig").exists()
        assert (item_dir / "chain_of_custody.jsonl").exists()
        assert (item_dir / "raw_capture.mp4").exists()


def test_ingest_derived_enhancement_recording(locker: EvidenceLocker) -> None:
    """Verifies ingestion of Phase 9 enhanced clip as DERIVED_ENHANCEMENT."""
    with tempfile.TemporaryDirectory() as tmpdir:
        enh_path = os.path.join(tmpdir, "enhanced_clip.mp4")
        create_sample_video(enh_path)

        # Mock Phase 9 sidecar manifest
        sidecar_path = f"{enh_path}.manifest.json"
        sidecar_data = {
            "source_path": "storage/recordings/CAM-01/orig.mp4",
            "source_sha256": "112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00",
            "config_applied": {"low_light_enabled": True, "super_resolution_scale": 2},
            "engine_version": "0.9.0-alpha",
        }
        with open(sidecar_path, "w", encoding="utf-8") as f:
            json.dump(sidecar_data, f)

        manifest = locker.ingest_recording(
            source_file_path=enh_path,
            case_number="CASE-2026-002",
            channel_id="CAM-02",
            operator_username="investigator_smith",
            operator_role="INVESTIGATOR",
        )

        assert manifest.evidence_type == EvidenceType.DERIVED_ENHANCEMENT.value
        assert manifest.source_sha256 == sidecar_data["source_sha256"]
        assert manifest.enhancement_metadata["super_resolution_scale"] == 2
        assert "DERIVED_ENHANCEMENT" in manifest.legal_disclaimer


def test_rbac_access_control(locker: EvidenceLocker) -> None:
    """Verifies unauthorized roles cannot ingest evidence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "sample.mp4")
        create_sample_video(src)

        # VIEWER is not allowed to ingest
        with pytest.raises(ForensicAccessDeniedError):
            locker.ingest_recording(
                source_file_path=src,
                case_number="CASE-003",
                channel_id="CAM-01",
                operator_username="unauthorized_viewer",
                operator_role="VIEWER",
            )


def test_verify_evidence_integrity_and_tamper_detection(locker: EvidenceLocker) -> None:
    """Verifies evidence verification detects altered media in locker."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "clean.mp4")
        create_sample_video(src)

        manifest = locker.ingest_recording(
            source_file_path=src,
            case_number="CASE-004",
            channel_id="CAM-01",
            operator_username="investigator_smith",
            operator_role="INVESTIGATOR",
        )

        # 1. Verification of untouched evidence passes
        ver_res = locker.verify_evidence(manifest.evidence_id, "investigator_smith", "INVESTIGATOR")
        assert ver_res["is_valid"] is True
        assert ver_res["sha256_match"] is True
        assert ver_res["signature_valid"] is True

        # 2. Tamper media file
        media_file = locker.base_dir / manifest.evidence_id / "clean.mp4"
        # Temporarily clear read-only to simulate malicious tampering
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(media_file), 0x80)  # NORMAL
        else:
            os.chmod(str(media_file), 0o666)

        with open(media_file, "r+b") as f:
            f.seek(100)
            f.write(b"MALICIOUS_MODIFICATION_BYTES")

        # 3. Verification of tampered evidence FAILS
        ver_res2 = locker.verify_evidence(manifest.evidence_id, "investigator_smith", "INVESTIGATOR")
        assert ver_res2["is_valid"] is False
        assert ver_res2["sha256_match"] is False
