"""
Unit Tests for Multi-Tier Archival and Evidentiary Protection.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

import os
import pytest
from datetime import datetime, timezone, timedelta
from database.database_manager import db_manager
from database.models.recordings import Recording, StorageVolume
from database.models.storage import StorageArchivalJob, StorageArchivalCopy
from engines.storage_engine.archival_manager import StorageArchivalManager
from engines.storage_engine.storage_service import enterprise_storage_service
from engines.storage_engine.enums import ArchivalTier


class TestStorageArchivalAndRetention:
    """Validates multi-tier archival, copy verification, and forensic evidence locks."""

    @pytest.fixture
    def archival_fixture(self, tmp_path):
        hot_dir = str(tmp_path / "hot_tier")
        cold_dir = str(tmp_path / "cold_tier")
        os.makedirs(hot_dir, exist_ok=True)
        os.makedirs(cold_dir, exist_ok=True)

        with db_manager.get_session() as session:
            v_hot = StorageVolume(
                name="Hot NVMe Tier",
                mount_path=hot_dir,
                total_bytes=100 * 1024 * 1024 * 1024,
                available_bytes=50 * 1024 * 1024 * 1024,
                is_active=True,
                volume_type="LOCAL",
            )
            v_cold = StorageVolume(
                name="Cold NAS Archive",
                mount_path=cold_dir,
                total_bytes=500 * 1024 * 1024 * 1024,
                available_bytes=400 * 1024 * 1024 * 1024,
                is_active=True,
                volume_type="NAS_SMB",
            )
            session.add(v_hot)
            session.add(v_cold)
            session.flush()
            hot_id = str(v_hot.id)
            cold_id = str(v_cold.id)

        mgr = StorageArchivalManager()
        return mgr, hot_id, cold_id, hot_dir, cold_dir

    def test_archival_migration_and_hash_verification(self, archival_fixture):
        mgr, hot_id, cold_id, hot_dir, cold_dir = archival_fixture

        # Create an old unlocked recording file in hot tier
        rec_file = os.path.join(hot_dir, "cam_old_01", "rec_001.mp4")
        os.makedirs(os.path.dirname(rec_file), exist_ok=True)
        with open(rec_file, "wb") as f:
            f.write(b"SAMPLE_HIGH_DEF_VIDEO_FRAME_DATA" * 50)

        old_dt = datetime.now(timezone.utc) - timedelta(days=20)
        with db_manager.get_session() as session:
            rec = Recording(
                channel_id="cam_old_01",
                volume_id=hot_id,
                file_path=rec_file,
                start_time=old_dt,
                end_time=old_dt + timedelta(minutes=10),
                status="COMPLETED",
                is_locked=False,
            )
            session.add(rec)
            session.flush()
            rec_id = str(rec.id)

        # Execute archival job
        res = mgr.create_archival_job(
            source_volume_id=hot_id,
            target_volume_id=cold_id,
            target_tier=ArchivalTier.COLD,
            min_age_days=14,
        )

        assert res["status"] == "COMPLETED"
        assert res["files_transferred"] == 1
        assert res["verification_failed_count"] == 0

        # Verify archive copy exists in cold tier
        with db_manager.get_session() as session:
            copy_rec = (
                session.query(StorageArchivalCopy)
                .filter_by(recording_id=rec_id)
                .first()
            )
            assert copy_rec is not None
            assert os.path.exists(copy_rec.archive_path)
            assert copy_rec.tier == "COLD"
            assert copy_rec.status == "VERIFIED"

    def test_evidentiary_lock_prevents_source_deletion(self, archival_fixture):
        """
        CRITICAL FORENSIC REQUIREMENT:
        Recordings flagged as locked evidence (is_locked=True) MUST NEVER have their source deleted.
        """
        mgr, hot_id, cold_id, hot_dir, cold_dir = archival_fixture

        # Create an old LOCKED evidence recording
        rec_file = os.path.join(hot_dir, "cam_evidence_01", "rec_evidence.mp4")
        os.makedirs(os.path.dirname(rec_file), exist_ok=True)
        with open(rec_file, "wb") as f:
            f.write(b"CRITICAL_MURDER_INVESTIGATION_FORENSIC_FOOTAGE" * 20)

        old_dt = datetime.now(timezone.utc) - timedelta(days=40)
        with db_manager.get_session() as session:
            rec = Recording(
                channel_id="cam_evidence_01",
                volume_id=hot_id,
                file_path=rec_file,
                start_time=old_dt,
                end_time=old_dt + timedelta(minutes=10),
                status="COMPLETED",
                is_locked=True,  # FORENSIC EVIDENCE LOCK
            )
            session.add(rec)

        # Run archival
        res = mgr.create_archival_job(hot_id, cold_id, target_tier=ArchivalTier.COLD, min_age_days=14)
        assert res["files_transferred"] >= 1

        # Source file MUST STILL EXIST because it is locked!
        assert os.path.exists(rec_file) is True, "Source file for locked forensic evidence was erroneously deleted!"

        # Run retention pruning: locked file MUST STILL BE PRESERVED!
        freed = enterprise_storage_service.prune_expired_recordings(retention_days=30, volume_id=hot_id)
        assert os.path.exists(rec_file) is True, "Locked evidence was deleted during retention pruning!"

    def test_restore_archival_copy(self, archival_fixture):
        mgr, hot_id, cold_id, hot_dir, cold_dir = archival_fixture

        # Setup an archive copy
        archived_file = os.path.join(cold_dir, "archived_rec.mp4")
        with open(archived_file, "wb") as f:
            f.write(b"RESTORE_TEST_DATA" * 50)

        import hashlib
        h = hashlib.sha256(b"RESTORE_TEST_DATA" * 50).hexdigest()

        with db_manager.get_session() as session:
            rec = Recording(
                channel_id="cam_restore",
                volume_id=cold_id,
                file_path=archived_file,
                start_time=datetime.now(timezone.utc),
                status="COMPLETED",
            )
            session.add(rec)
            session.flush()
            rec_id = str(rec.id)

            copy_rec = StorageArchivalCopy(
                recording_id=rec_id,
                target_volume_id=cold_id,
                archive_path=archived_file,
                tier="COLD",
                sha256_hash=h,
                status="VERIFIED",
            )
            session.add(copy_rec)

        ok, msg = mgr.restore_archival_copy(rec_id, destination_volume_id=hot_id)
        assert ok is True
        assert "restored" in msg.lower()
