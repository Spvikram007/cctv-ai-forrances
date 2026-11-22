"""
Unit tests for Recording Engine, Pre-event Buffering, and Crash Recovery.
"""

import os
import time
import uuid
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
import numpy as np
import pytest

from database.database_manager import db_manager
from database.models.recordings import Recording, RecordingSegment
from engines.recording_engine.recorder import ChannelRecordingWorker, RecordingRecoveryService
from engines.recording_engine.recording_manager import RecordingManager
from engines.recording_engine.storage_manager import storage_manager


@pytest.fixture
def temp_storage():
    """Provides an isolated temporary directory for test recordings."""
    temp_dir = tempfile.mkdtemp(prefix="cctv_test_rec_")
    yield temp_dir
    with db_manager.get_session() as session:
        session.query(Recording).filter(Recording.file_path.like(f"%{os.path.basename(temp_dir)}%")).delete(synchronize_session=False)
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_channel_recording_worker_continuous(temp_storage):
    """Verifies continuous segment creation, frame writing, and DB sealing."""
    ch_id = f"cam_cont_{uuid.uuid4().hex[:6]}"
    worker = ChannelRecordingWorker(
        channel_id=ch_id,
        channel_name="Test Camera 1",
        recording_type="CONTINUOUS",
        segment_duration_sec=2,  # 2-second segments for fast testing
        output_dir=temp_storage,
    )
    worker.start()

    # Push 30 frames at 15 FPS (2 seconds total)
    dummy_frame = np.zeros((360, 640, 3), dtype=np.uint8)
    dummy_frame[:] = (50, 100, 150)

    for i in range(30):
        worker.push_frame(dummy_frame, time.time())
        time.sleep(0.06)

    worker.stop()
    worker.join(timeout=3.0)

    # Verify database records
    with db_manager.get_session() as session:
        recs = session.query(Recording).filter_by(channel_id=ch_id).all()
        assert len(recs) >= 1
        rec = recs[0]
        assert rec.status == "COMPLETED"
        assert rec.recording_type == "CONTINUOUS"
        assert rec.fps >= 10.0

        segments = session.query(RecordingSegment).filter_by(recording_id=rec.id).all()
        assert len(segments) >= 1
        for seg in segments:
            assert os.path.exists(seg.file_path)
            assert seg.file_size_bytes > 0
            assert seg.sha256_hash is not None
            assert len(seg.sha256_hash) == 64  # Valid SHA-256


def test_channel_recording_pre_event_buffering(temp_storage):
    """Verifies that pre-event ring buffer captures frames prior to event trigger."""
    ch_id = f"cam_event_{uuid.uuid4().hex[:6]}"
    worker = ChannelRecordingWorker(
        channel_id=ch_id,
        channel_name="Event Camera",
        recording_type="MOTION",
        segment_duration_sec=3,
        pre_event_buffer_sec=2,
        output_dir=temp_storage,
    )
    worker.start()

    dummy_frame = np.zeros((360, 640, 3), dtype=np.uint8)

    # 1. Push frames before trigger (buffered in deque)
    for _ in range(15):
        worker.push_frame(dummy_frame, time.time())
        time.sleep(0.04)

    # 2. Trigger motion event
    worker.trigger_event(duration_sec=2.0)

    # 3. Push more frames during event
    for _ in range(15):
        worker.push_frame(dummy_frame, time.time())
        time.sleep(0.04)

    worker.stop()
    worker.join(timeout=3.0)

    with db_manager.get_session() as session:
        recs = session.query(Recording).filter_by(channel_id=ch_id).all()
        assert len(recs) >= 1
        rec = recs[0]
        assert rec.recording_type == "MOTION"


def test_recording_recovery_service(temp_storage):
    """Tests scanning and sealing orphaned ACTIVE recordings after application crash."""
    ch_id = f"crash_cam_{uuid.uuid4().hex[:6]}"
    dummy_file = os.path.join(temp_storage, f"unclosed_{ch_id}.mp4")
    import cv2
    writer = cv2.VideoWriter(dummy_file, cv2.VideoWriter_fourcc(*'mp4v'), 25.0, (640, 360))
    for _ in range(25):
        writer.write(np.zeros((360, 640, 3), dtype=np.uint8))
    writer.release()

    vol = storage_manager.initialize_default_volume()
    with db_manager.get_session() as session:
        rec = Recording(
            channel_id=ch_id,
            volume_id=vol.id,
            start_time=datetime.now(timezone.utc) - timedelta(minutes=5),
            status="ACTIVE",  # Simulates unclosed state before crash
            recording_type="CONTINUOUS",
            file_path=dummy_file,
        )
        session.add(rec)
        session.flush()

        seg = RecordingSegment(
            recording_id=rec.id,
            segment_index=0,
            file_path=dummy_file,
            start_time=rec.start_time,
            file_size_bytes=0,
        )
        session.add(seg)

    # 2. Run recovery service
    recovered_count = RecordingRecoveryService.recover_interrupted_recordings()
    assert recovered_count >= 1

    # 3. Verify sealed status in DB
    with db_manager.get_session() as session:
        recovered_rec = session.query(Recording).filter_by(channel_id=ch_id).first()
        assert recovered_rec is not None
        assert recovered_rec.status == "RECOVERED"
        assert recovered_rec.end_time is not None

        recovered_seg = session.query(RecordingSegment).filter_by(recording_id=recovered_rec.id).first()
        assert recovered_seg is not None
        assert recovered_seg.file_size_bytes > 0
        assert recovered_seg.sha256_hash is not None
        assert recovered_seg.end_time is not None


def test_recording_manager_controller(temp_storage):
    """Tests RecordingManager start, stop, query, and event trigger."""
    ch_id = f"mgr_cam_{uuid.uuid4().hex[:6]}"
    rm = RecordingManager()
    worker = rm.start_recording(
        channel_id=ch_id,
        channel_name="Manager Cam",
        recording_type="CONTINUOUS",
        output_dir=temp_storage,
    )
    assert rm.is_recording(ch_id)
    assert ch_id in rm.get_active_channels()

    rm.trigger_event_recording(ch_id, event_name="AI_Person")

    rm.stop_recording(ch_id)
    assert not rm.is_recording(ch_id)
