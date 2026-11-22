"""
Unit tests for Synchronized Playback Engine, Master Clock, Variable Speeds, and Gap Detection.
"""

import os
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
import numpy as np
import cv2
import pytest

from database.database_manager import db_manager
from database.models.recordings import Recording, RecordingSegment
from engines.recording_engine.storage_manager import storage_manager
from engines.video_engine.playback_controller import (
    SingleCameraPlayer, SynchronizedPlaybackController, PlaybackState
)


@pytest.fixture
def sample_video_fixture():
    """Generates a small valid MP4 test video and DB records with known timestamps."""
    temp_dir = tempfile.mkdtemp(prefix="cctv_playback_test_")
    video_path = os.path.join(temp_dir, "segment_100.mp4")

    # Generate 50 frames @ 25 FPS = 2 seconds
    writer = cv2.VideoWriter(video_path, cv2.VideoWriter_fourcc(*'mp4v'), 25.0, (640, 360))
    for i in range(50):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        frame[:] = (i * 4, 120, 200)
        writer.write(frame)
    writer.release()

    base_time = datetime(2026, 11, 22, 10, 0, 0, tzinfo=timezone.utc)
    end_time = base_time + timedelta(seconds=2)

    vol = storage_manager.initialize_default_volume()
    with db_manager.get_session() as session:
        rec = Recording(
            channel_id="playback_cam_01",
            volume_id=vol.id,
            start_time=base_time,
            end_time=end_time,
            file_path=video_path,
            status="COMPLETED",
            recording_type="CONTINUOUS",
            fps=25.0,
            resolution_width=640,
            resolution_height=360,
        )
        session.add(rec)
        session.flush()

        seg = RecordingSegment(
            recording_id=rec.id,
            segment_index=0,
            file_path=video_path,
            start_time=base_time,
            end_time=end_time,
            duration_sec=2.0,
            file_size_bytes=os.path.getsize(video_path),
        )
        session.add(seg)

    yield {
        "dir": temp_dir,
        "video_path": video_path,
        "base_time": base_time,
        "end_time": end_time,
        "channel_id": "playback_cam_01",
    }
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_single_camera_player_seek_and_gap(sample_video_fixture):
    """Verifies seeking inside video footage and proper handling of recording gaps."""
    player = SingleCameraPlayer("playback_cam_01")
    base_time = sample_video_fixture["base_time"]

    # 1. Seek to timestamp within segment (+1.0s)
    target_dt = base_time + timedelta(seconds=1.0)
    frame = player.seek_to_timestamp(target_dt)
    assert frame is not None
    assert frame.shape == (360, 640, 3)
    assert not player._is_in_gap

    # 2. Seek to timestamp outside segment (recording gap: +10 minutes)
    gap_dt = base_time + timedelta(minutes=10)
    gap_result = player.seek_to_timestamp(gap_dt)
    assert gap_result is None
    assert player._is_in_gap

    # 3. Request display frame during gap - should return standby gap graphic
    display_frame = player.get_display_frame(gap_dt)
    assert display_frame is not None
    assert display_frame.shape == (360, 640, 3)

    player.close()


def test_synchronized_playback_controller_lifecycle(sample_video_fixture):
    """Verifies controller state transitions, playback speeds, and frame stepping."""
    ctrl = SynchronizedPlaybackController()
    ctrl.set_channels(["playback_cam_01", "playback_cam_02"])
    assert len(ctrl.channel_players) == 2

    # Initial state
    assert ctrl.state == PlaybackState.STOPPED

    # Play & Pause
    ctrl.play()
    assert ctrl.state == PlaybackState.PLAYING

    ctrl.pause()
    assert ctrl.state == PlaybackState.PAUSED

    # Variable speeds
    for spd in [0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0]:
        ctrl.set_speed(spd)
        assert ctrl.playback_speed == spd

    # Master clock seek
    base_time = sample_video_fixture["base_time"]
    ctrl.seek_to_timestamp(base_time + timedelta(seconds=0.5))
    assert ctrl.master_clock == base_time + timedelta(seconds=0.5)

    # Frame stepping forward (1 frame @ 25fps = 0.04s)
    ctrl.step_forward(1)
    assert abs((ctrl.master_clock - (base_time + timedelta(seconds=0.54))).total_seconds()) < 0.001

    # Frame stepping backward
    ctrl.step_backward(1)
    assert abs((ctrl.master_clock - (base_time + timedelta(seconds=0.50))).total_seconds()) < 0.001

    # Stop
    ctrl.stop()
    assert ctrl.state == PlaybackState.STOPPED


def test_get_recording_intervals_for_timeline(sample_video_fixture):
    """Verifies timeline interval database queries for multi-camera visualization."""
    base_time = sample_video_fixture["base_time"]
    intervals = SynchronizedPlaybackController.get_recording_intervals(
        channel_id="playback_cam_01",
        start_time=base_time - timedelta(hours=1),
        end_time=base_time + timedelta(hours=1),
    )
    assert len(intervals) >= 1
    assert intervals[0]["duration_sec"] == 2.0
    assert intervals[0]["recording_type"] == "CONTINUOUS"
