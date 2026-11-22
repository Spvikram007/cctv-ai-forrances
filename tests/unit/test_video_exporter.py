"""
Unit tests for Video Export Engine, SHA-256 Cryptographic Hashing, and Evidence Preservation.
"""

import os
import json
import shutil
import tempfile
import threading
from datetime import datetime, timezone, timedelta
import numpy as np
import cv2
import pytest

from database.database_manager import db_manager
from database.models.recordings import Recording, RecordingSegment, ExportJob
from engines.recording_engine.storage_manager import storage_manager
from engines.video_engine.video_exporter import VideoExporter


@pytest.fixture
def export_test_data():
    """Generates two consecutive video segments for export testing."""
    temp_dir = tempfile.mkdtemp(prefix="cctv_export_test_")
    seg1_path = os.path.join(temp_dir, "seg1.mp4")
    seg2_path = os.path.join(temp_dir, "seg2.mp4")

    # Write seg1: 25 frames (1.0 sec)
    w1 = cv2.VideoWriter(seg1_path, cv2.VideoWriter_fourcc(*'mp4v'), 25.0, (640, 360))
    for _ in range(25):
        w1.write(np.zeros((360, 640, 3), dtype=np.uint8))
    w1.release()

    # Write seg2: 25 frames (1.0 sec)
    w2 = cv2.VideoWriter(seg2_path, cv2.VideoWriter_fourcc(*'mp4v'), 25.0, (640, 360))
    for _ in range(25):
        w2.write(np.zeros((360, 640, 3), dtype=np.uint8))
    w2.release()

    t0 = datetime(2026, 11, 22, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=1)
    t2 = t1 + timedelta(seconds=1)
    ch_id = f"exp_cam_{temp_dir[-6:]}"

    vol = storage_manager.initialize_default_volume()
    with db_manager.get_session() as session:
        rec = Recording(
            channel_id=ch_id,
            volume_id=vol.id,
            start_time=t0,
            end_time=t2,
            file_path=seg1_path,
            status="COMPLETED",
            is_locked=False,
        )
        session.add(rec)
        session.flush()

        s1 = RecordingSegment(
            recording_id=rec.id,
            segment_index=0,
            file_path=seg1_path,
            start_time=t0,
            end_time=t1,
            duration_sec=1.0,
            file_size_bytes=os.path.getsize(seg1_path),
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )
        s2 = RecordingSegment(
            recording_id=rec.id,
            segment_index=1,
            file_path=seg2_path,
            start_time=t1,
            end_time=t2,
            duration_sec=1.0,
            file_size_bytes=os.path.getsize(seg2_path),
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )
        session.add(s1)
        session.add(s2)

    yield {
        "dir": temp_dir,
        "t0": t0,
        "t1": t1,
        "t2": t2,
        "channel_id": ch_id,
    }
    with db_manager.get_session() as session:
        session.query(Recording).filter_by(channel_id=ch_id).delete(synchronize_session=False)
        session.query(ExportJob).filter_by(channel_id=ch_id).delete(synchronize_session=False)
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_video_export_success_with_hash_and_manifest(export_test_data):
    """Verifies seamless multi-segment export, SHA-256 computation, and metadata manifest."""
    exporter = VideoExporter()
    out_file = os.path.join(export_test_data["dir"], "final_export.mp4")

    progress_reports = []
    job = exporter.export_clip(
        channel_id=export_test_data["channel_id"],
        start_time=export_test_data["t0"],
        end_time=export_test_data["t2"],
        output_path=out_file,
        is_evidence=True,
        notes="Suspect vehicle departure",
        progress_callback=lambda p: progress_reports.append(p),
    )

    # 1. Output video verification
    assert os.path.exists(out_file)
    assert os.path.getsize(out_file) > 0
    assert len(progress_reports) >= 1
    assert progress_reports[-1] == 100.0

    # 2. SHA-256 Hash verification
    assert job.sha256_hash is not None
    assert len(job.sha256_hash) == 64
    actual_hash = VideoExporter._calculate_sha256(out_file)
    assert job.sha256_hash == actual_hash

    # 3. Sidecar JSON Manifest verification
    manifest_path = f"{os.path.splitext(out_file)[0]}_manifest.json"
    assert os.path.exists(manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["channel_id"] == export_test_data["channel_id"]
    assert manifest["sha256_hash"] == actual_hash
    assert manifest["is_evidence"] is True
    assert len(manifest["source_segments"]) == 2

    # 4. Evidence lock verification: parent recording must now be locked!
    with db_manager.get_session() as session:
        rec = session.query(Recording).filter_by(channel_id=export_test_data["channel_id"]).first()
        assert rec.is_locked is True, "Parent recording must be locked when exported as evidence"


def test_video_export_validation_errors(export_test_data):
    """Verifies input validation: invalid time bounds or non-existent footage."""
    exporter = VideoExporter()
    out_file = os.path.join(export_test_data["dir"], "invalid.mp4")

    # 1. End before start
    with pytest.raises(ValueError):
        exporter.export_clip(
            channel_id=export_test_data["channel_id"],
            start_time=export_test_data["t2"],
            end_time=export_test_data["t0"],
            output_path=out_file,
        )

    # 2. No recordings in range
    with pytest.raises(RuntimeError):
        exporter.export_clip(
            channel_id="export_cam_01",
            start_time=export_test_data["t0"] - timedelta(days=10),
            end_time=export_test_data["t0"] - timedelta(days=9),
            output_path=out_file,
        )


def test_video_export_cancellation(export_test_data):
    """Verifies that cancel event aborts export and updates job status to CANCELLED."""
    exporter = VideoExporter()
    out_file = os.path.join(export_test_data["dir"], "cancelled.mp4")

    cancel_evt = threading.Event()
    cancel_evt.set()  # Cancel immediately

    job = exporter.export_clip(
        channel_id=export_test_data["channel_id"],
        start_time=export_test_data["t0"],
        end_time=export_test_data["t2"],
        output_path=out_file,
        cancel_event=cancel_evt,
    )

    with db_manager.get_session() as session:
        db_job = session.query(ExportJob).filter_by(id=job.id).first()
        assert db_job.status == "CANCELLED"
