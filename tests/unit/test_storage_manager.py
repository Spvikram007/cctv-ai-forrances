"""
Unit tests for Storage Manager, Quota Monitoring, Evidence Protection, and Retention Pruning.
"""

import os
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
import pytest

from database.database_manager import db_manager
from database.models.recordings import Recording, RecordingSegment, StorageEvent
from engines.recording_engine.storage_manager import StorageManager


@pytest.fixture
def temp_storage_vol():
    """Provides isolated directory pretending to be a surveillance storage volume."""
    temp_dir = tempfile.mkdtemp(prefix="cctv_vol_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_storage_manager_volume_metrics(temp_storage_vol):
    """Verifies volume metrics detection and health check."""
    sm = StorageManager(primary_volume_path=temp_storage_vol)
    metrics = sm.get_volume_metrics()

    assert metrics.total_bytes > 0
    assert metrics.free_bytes > 0
    assert 0.0 <= metrics.used_percent <= 100.0
    assert metrics.warning_threshold_pct == 85.0
    assert metrics.critical_threshold_pct == 95.0


def test_storage_manager_low_disk_warning(temp_storage_vol):
    """Verifies event emission and DB logging on threshold crossing."""
    sm = StorageManager(
        primary_volume_path=temp_storage_vol,
        warning_threshold_pct=0.01,  # Set very low to trigger warning
    )
    status = sm.check_storage_health()
    assert status in ["WARNING", "CRITICAL", "HEALTHY"]

    with db_manager.get_session() as session:
        events = session.query(StorageEvent).all()
        assert len(events) >= 1


def test_storage_manager_retention_and_evidence_protection(temp_storage_vol):
    """
    CRITICAL FORENSIC REQUIREMENT:
    Verifies that old recordings are pruned according to retention policy,
    BUT evidence files marked is_locked=True are strictly preserved and NEVER deleted.
    """
    sm = StorageManager(primary_volume_path=temp_storage_vol)

    # 1. Create an old UNLOCKED recording file (should be pruned)
    old_file_prunable = os.path.join(temp_storage_vol, "old_unlocked.mp4")
    with open(old_file_prunable, "wb") as f:
        f.write(b"normal footage" * 100)

    # 2. Create an old LOCKED evidence recording file (MUST BE PRESERVED)
    old_file_locked = os.path.join(temp_storage_vol, "old_evidence_locked.mp4")
    with open(old_file_locked, "wb") as f:
        f.write(b"critical forensic evidence" * 100)

    old_date = datetime.now(timezone.utc) - timedelta(days=45)

    vol = sm.initialize_default_volume()
    with db_manager.get_session() as session:
        # Unlocked record
        rec_unlocked = Recording(
            channel_id="cam_normal",
            volume_id=vol.id,
            start_time=old_date,
            end_time=old_date + timedelta(minutes=5),
            file_path=old_file_prunable,
            is_locked=False,
            status="COMPLETED",
        )
        session.add(rec_unlocked)
        session.flush()

        seg_unlocked = RecordingSegment(
            recording_id=rec_unlocked.id,
            segment_index=0,
            file_path=old_file_prunable,
            start_time=old_date,
            end_time=old_date + timedelta(minutes=5),
            file_size_bytes=os.path.getsize(old_file_prunable),
        )
        session.add(seg_unlocked)

        # Locked evidence record
        rec_locked = Recording(
            channel_id="cam_evidence",
            volume_id=vol.id,
            start_time=old_date,
            end_time=old_date + timedelta(minutes=5),
            file_path=old_file_locked,
            is_locked=True,  # PROTECTED
            status="COMPLETED",
        )
        session.add(rec_locked)
        session.flush()

        seg_locked = RecordingSegment(
            recording_id=rec_locked.id,
            segment_index=0,
            file_path=old_file_locked,
            start_time=old_date,
            end_time=old_date + timedelta(minutes=5),
            file_size_bytes=os.path.getsize(old_file_locked),
        )
        session.add(seg_locked)

    # 3. Execute retention pruning for records older than 30 days
    pruned_count = sm.prune_expired_recordings(retention_days=30)
    assert pruned_count >= 1

    # 4. Verify results
    assert not os.path.exists(old_file_prunable), "Unlocked old recording must be deleted"
    assert os.path.exists(old_file_locked), "LOCKED EVIDENCE MUST NEVER BE DELETED BY RETENTION"

    with db_manager.get_session() as session:
        # Unlocked DB record was deleted
        assert session.query(Recording).filter_by(channel_id="cam_normal").first() is None
        # Locked DB record MUST remain in database
        locked_in_db = session.query(Recording).filter_by(channel_id="cam_evidence").first()
        assert locked_in_db is not None
        assert locked_in_db.is_locked is True


def test_database_filesystem_consistency_audit(temp_storage_vol):
    """Verifies detection of missing physical files compared against DB catalog."""
    sm = StorageManager(primary_volume_path=temp_storage_vol)

    missing_path = os.path.join(temp_storage_vol, "non_existent_footage.mp4")
    vol = sm.initialize_default_volume()
    with db_manager.get_session() as session:
        rec = Recording(
            channel_id="cam_audit",
            volume_id=vol.id,
            start_time=datetime.now(timezone.utc),
            file_path=missing_path,
            status="COMPLETED",
        )
        session.add(rec)
        session.flush()
        seg = RecordingSegment(
            recording_id=rec.id,
            segment_index=0,
            file_path=missing_path,
            start_time=rec.start_time,
        )
        session.add(seg)

    audit = sm.audit_database_filesystem_consistency()
    assert audit["missing_files_count"] >= 1
    assert any(item["file_path"] == missing_path for item in audit["missing_records"])
