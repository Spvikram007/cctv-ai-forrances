"""
Unit Tests for Storage Failover Manager and Integrity Manifest Verification.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

import os
import pytest
from datetime import datetime, timezone, timedelta
from database.database_manager import db_manager
from database.models.recordings import StorageVolume
from database.models.storage import StorageFailoverEvent, StorageRecordingManifest
from engines.storage_engine.failover_manager import StorageFailoverManager
from engines.storage_engine.integrity_manager import StorageIntegrityManager
from engines.storage_engine.enums import FailoverStatus, VolumeStatus


class TestStorageFailoverManager:
    """Validates failover target selection, gap calculation, and controlled failback."""

    @pytest.fixture
    def failover_setup(self, tmp_path):
        p_dir = str(tmp_path / "primary_store")
        f_dir = str(tmp_path / "failover_store")
        os.makedirs(p_dir, exist_ok=True)
        os.makedirs(f_dir, exist_ok=True)

        with db_manager.get_session() as session:
            v1 = StorageVolume(
                name="Primary Storage",
                mount_path=p_dir,
                total_bytes=100 * 1024 * 1024 * 1024,
                used_bytes=10 * 1024 * 1024 * 1024,
                available_bytes=80 * 1024 * 1024 * 1024,
                is_active=True,
                volume_status="ONLINE",
            )
            v2 = StorageVolume(
                name="Backup Failover Storage",
                mount_path=f_dir,
                total_bytes=100 * 1024 * 1024 * 1024,
                used_bytes=10 * 1024 * 1024 * 1024,
                available_bytes=80 * 1024 * 1024 * 1024,
                is_active=True,
                is_failover_target=True,
                volume_status="ONLINE",
            )
            session.add(v1)
            session.add(v2)
            session.flush()
            v1_id = str(v1.id)
            v2_id = str(v2.id)

        fm = StorageFailoverManager()
        fm.allocation_manager.allocate_channel(channel_id="cam_entry_01", primary_volume_id=v1_id, failover_volume_id=v2_id)
        fm.allocation_manager.allocate_channel(channel_id="cam_entry_02", primary_volume_id=v1_id, failover_volume_id=v2_id)
        return fm, v1_id, v2_id

    def test_failover_activation_and_gap_logging(self, failover_setup):
        fm, v1_id, v2_id = failover_setup
        target_vol, msg = fm.handle_storage_failure(
            channel_id="cam_entry_01",
            failed_volume_id=v1_id,
            reason="Disk write timeout",
            gap_seconds=1.85,
        )

        assert target_vol is not None
        assert str(target_vol.id) == v2_id
        assert msg == "Failover activated"

        # Verify failover event in database
        with db_manager.get_session() as session:
            evt = session.query(StorageFailoverEvent).filter_by(channel_id="cam_entry_01").order_by(StorageFailoverEvent.triggered_at.desc()).first()
            assert evt is not None
            assert evt.primary_volume_id == v1_id
            assert evt.failover_volume_id == v2_id
            assert evt.gap_seconds == 1.85
            assert evt.status == FailoverStatus.ACTIVE.value

    def test_controlled_failback(self, failover_setup):
        fm, v1_id, v2_id = failover_setup
        fm.handle_storage_failure("cam_entry_02", v1_id, reason="Simulated drop", gap_seconds=0.5)

        # Restore primary volume status in database
        with db_manager.get_session() as session:
            v1 = session.query(StorageVolume).filter_by(id=v1_id).first()
            v1.volume_status = VolumeStatus.ONLINE.value
            v1.is_active = True

        ok, msg = fm.execute_failback("cam_entry_02", operator="Admin")
        assert ok is True
        assert "completed successfully" in msg

        with db_manager.get_session() as session:
            evt = session.query(StorageFailoverEvent).filter_by(channel_id="cam_entry_02").order_by(StorageFailoverEvent.triggered_at.desc()).first()
            assert evt.status == FailoverStatus.FAILED_BACK.value
            assert evt.resolved_at is not None
            assert evt.failback_at is not None


class TestStorageIntegrityManager:
    """Validates segment manifest creation, SHA-256 verification, and gap detection."""

    @pytest.fixture
    def integrity_manager(self):
        return StorageIntegrityManager()

    def test_manifest_creation_and_cryptographic_verification(self, integrity_manager, tmp_path):
        seg_file = str(tmp_path / "segment_001.mp4")
        with open(seg_file, "wb") as f:
            f.write(b"SAMPLE_VIDEO_STREAM_DATA_FRAME_BYTES" * 50)

        t_start = datetime.now(timezone.utc) - timedelta(seconds=60)
        t_end = datetime.now(timezone.utc)

        manifest = integrity_manager.create_segment_manifest(
            channel_id="cam_test_01",
            destination_volume_id="vol_01",
            file_path=seg_file,
            start_time=t_start,
            end_time=t_end,
            duration_sec=60,
        )

        assert manifest.sha256_hash is not None
        assert manifest.verification_status == "VERIFIED"

        # Verification passes on untouched file
        res = integrity_manager.verify_segment_manifest(manifest.id)
        assert res["valid"] is True

        # Tamper with file directly on disk
        with open(seg_file, "ab") as f:
            f.write(b"MALICIOUS_TAMPERED_BYTES")

        # Verification must catch digest mismatch!
        tamper_res = integrity_manager.verify_segment_manifest(manifest.id)
        assert tamper_res["valid"] is False
        assert "digest mismatch" in tamper_res["details"]

    def test_detect_recording_gaps(self, integrity_manager, tmp_path):
        t0 = datetime(2026, 11, 25, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 11, 25, 10, 1, 0, tzinfo=timezone.utc)
        # Introduce a 10-second gap
        t2 = datetime(2026, 11, 25, 10, 1, 10, tzinfo=timezone.utc)
        t3 = datetime(2026, 11, 25, 10, 2, 10, tzinfo=timezone.utc)

        f1 = str(tmp_path / "seg1.mp4")
        f2 = str(tmp_path / "seg2.mp4")
        with open(f1, "wb") as f: f.write(b"seg1")
        with open(f2, "wb") as f: f.write(b"seg2")

        integrity_manager.create_segment_manifest("cam_gap_test", "vol_01", f1, start_time=t0, end_time=t1, duration_sec=60)
        integrity_manager.create_segment_manifest("cam_gap_test", "vol_01", f2, start_time=t2, end_time=t3, duration_sec=60)

        gaps = integrity_manager.detect_recording_gaps("cam_gap_test", start_time=t0, end_time=t3)
        assert len(gaps) == 1
        assert gaps[0]["gap_seconds"] == 10.0
