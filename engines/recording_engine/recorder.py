"""
Surveillance Video Recording Engine.
Implements continuous, scheduled, motion, and AI-event-triggered segmented recording,
pre-event and post-event ring buffering, SHA-256 integrity sealing, and crash recovery.
"""

import os
import time
import hashlib
import threading
from collections import deque
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple, List
import cv2
import numpy as np

from database.database_manager import db_manager
from database.models.recordings import Recording, RecordingSegment, RecordingHealthLog
from engines.recording_engine.storage_manager import storage_manager
from core.events.event_bus import bus
from core.config.settings import settings
from core.logging.logger import get_logger

logger = get_logger("recorder")


def calculate_file_sha256(file_path: str) -> str:
    """Computes SHA-256 hash of a file on disk for cryptographic integrity."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


class ChannelRecordingWorker(threading.Thread):
    """
    Independent worker thread dedicated to encoding and segmenting video for a single channel.
    Operates decoupled from live stream rendering to prevent UI stalls.
    """

    def __init__(
        self,
        channel_id: str,
        channel_name: str = "Camera",
        recording_type: str = "CONTINUOUS",  # CONTINUOUS, MOTION, AI_EVENT, MANUAL
        stream_type: str = "MAIN",
        segment_duration_sec: int = 60,
        target_fps: float = 25.0,
        pre_event_buffer_sec: float = 5.0,
        post_event_buffer_sec: float = 10.0,
        output_dir: Optional[str] = None,
    ) -> None:
        super().__init__(name=f"RecorderWorker-{channel_id}", daemon=True)
        self.channel_id = channel_id
        self.channel_name = channel_name
        self.recording_type = recording_type
        self.stream_type = stream_type
        self.segment_duration_sec = segment_duration_sec
        self.target_fps = target_fps
        self.pre_event_buffer_sec = pre_event_buffer_sec
        self.post_event_buffer_sec = post_event_buffer_sec

        self.base_output_dir = output_dir or settings.storage.recordings_dir
        self._stop_event = threading.Event()
        self._frame_queue: deque = deque(maxlen=60)
        self._queue_lock = threading.Lock()

        # Pre-event ring buffer (stores last N seconds of frames in memory)
        max_pre_frames = int(pre_event_buffer_sec * target_fps)
        self._pre_event_buffer: deque = deque(maxlen=max(max_pre_frames, 10))

        # Event trigger state
        self._is_event_active = False
        self._event_end_time: Optional[float] = None

        # Active segment state
        self._current_writer: Optional[cv2.VideoWriter] = None
        self._current_segment_path: Optional[str] = None
        self._segment_start_time: Optional[datetime] = None
        self._segment_start_perf: float = 0.0
        self._current_recording_id: Optional[str] = None
        self._segment_index: int = 0
        self._frames_written_segment: int = 0
        self._volume_id: Optional[str] = None

        self._init_volume()

    def _init_volume(self) -> None:
        vol = storage_manager.initialize_default_volume()
        self._volume_id = vol.id

    def push_frame(self, frame: np.ndarray, timestamp: float) -> None:
        """Called by StreamManager when a new frame is decoded."""
        if self._stop_event.is_set():
            return
        with self._queue_lock:
            self._frame_queue.append((frame.copy(), timestamp))

    def trigger_event(self, duration_sec: Optional[float] = None) -> None:
        """Triggers event-based recording (motion or AI detection)."""
        hold_time = duration_sec or self.post_event_buffer_sec
        self._event_end_time = time.time() + hold_time
        self._is_event_active = True
        logger.info("Event triggered for channel [%s] (hold: %.1fs)", self.channel_id, hold_time)

    def stop(self) -> None:
        """Signals the recording worker to finalize and close active segment."""
        self._stop_event.set()
        logger.info("Stopping recording worker for channel [%s]", self.channel_id)

    def _get_segment_filepath(self, start_dt: datetime) -> str:
        """Generates structured file path: recordings/{channel_id}/{YYYYMMDD}/rec_{channel}_{YYYYMMDD_HHMMSS}.mp4"""
        date_folder = start_dt.strftime("%Y%m%d")
        folder = Path(self.base_output_dir) / self.channel_id / date_folder
        folder.mkdir(parents=True, exist_ok=True)

        time_str = start_dt.strftime("%Y%m%d_%H%M%S")
        filename = f"rec_{self.channel_id}_{time_str}_{self._segment_index:03d}.mp4"
        return str((folder / filename).resolve())

    def _start_new_segment(self, first_frame: np.ndarray, timestamp: float) -> None:
        """Opens a new MP4 container segment and logs the database record."""
        self._close_current_segment()

        h, w, _ = first_frame.shape
        self._segment_start_time = datetime.now(timezone.utc)
        self._segment_start_perf = time.perf_counter()
        self._current_segment_path = self._get_segment_filepath(self._segment_start_time)
        self._frames_written_segment = 0
        self._segment_index += 1

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._current_writer = cv2.VideoWriter(
            self._current_segment_path,
            fourcc,
            self.target_fps,
            (w, h),
            isColor=True,
        )

        # Commit initial database record in ACTIVE state
        with db_manager.get_session() as session:
            rec = Recording(
                channel_id=self.channel_id,
                volume_id=self._volume_id,
                file_path=self._current_segment_path,
                recording_type=self.recording_type,
                stream_type=self.stream_type,
                start_time=self._segment_start_time,
                codec="H264/MP4V",
                resolution_width=w,
                resolution_height=h,
                fps=self.target_fps,
                status="ACTIVE",
            )
            session.add(rec)
            session.flush()
            self._current_recording_id = rec.id

        logger.info("Started new recording segment for [%s]: %s", self.channel_id, self._current_segment_path)

    def _close_current_segment(self) -> None:
        """Finalizes active segment, computes cryptographic hash, and seals database record."""
        if self._current_writer is not None:
            self._current_writer.release()
            self._current_writer = None

            if self._current_segment_path and os.path.exists(self._current_segment_path):
                file_size = os.path.getsize(self._current_segment_path)
                sha256 = calculate_file_sha256(self._current_segment_path) if file_size > 0 else None
                end_time = datetime.now(timezone.utc)
                duration = int((time.perf_counter() - self._segment_start_perf))

                # Update database record to COMPLETED state
                with db_manager.get_session() as session:
                    rec = session.query(Recording).filter_by(id=self._current_recording_id).first()
                    if rec:
                        rec.end_time = end_time
                        rec.duration_sec = duration
                        rec.file_size_bytes = file_size
                        rec.sha256_hash = sha256
                        rec.status = "COMPLETED"

                    # Add segment entry
                    seg = RecordingSegment(
                        recording_id=self._current_recording_id,
                        segment_index=self._segment_index,
                        file_path=self._current_segment_path,
                        start_time=self._segment_start_time,
                        end_time=end_time,
                        duration_sec=duration,
                        file_size_bytes=file_size,
                        sha256_hash=sha256,
                    )
                    session.add(seg)

                bus.publish("recording.segment_completed", {
                    "channel_id": self.channel_id,
                    "file_path": self._current_segment_path,
                    "duration_sec": duration,
                    "sha256": sha256,
                })
                logger.info("Sealed recording segment for [%s] (Duration: %ds, Size: %.2fMB, Hash: %s...)",
                            self.channel_id, duration, file_size / (1024 * 1024), sha256[:12] if sha256 else "None")

        self._current_segment_path = None
        self._current_recording_id = None

    def run(self) -> None:
        logger.info("Channel recording worker started for [%s] (Mode: %s, Segment: %ds)",
                    self.channel_id, self.recording_type, self.segment_duration_sec)

        while not self._stop_event.is_set():
            frame_tuple = None
            with self._queue_lock:
                if self._frame_queue:
                    frame_tuple = self._frame_queue.popleft()

            if frame_tuple is None:
                time.sleep(0.01)
                continue

            frame, ts = frame_tuple

            # Check event hold expiration
            if self._is_event_active and self._event_end_time and time.time() > self._event_end_time:
                self._is_event_active = False

            # Decide whether this frame should be written
            should_record = False
            if self.recording_type in ["CONTINUOUS", "MANUAL"]:
                should_record = True
            elif self.recording_type in ["MOTION", "AI_EVENT"] and self._is_event_active:
                should_record = True

            if should_record:
                # Start new segment if not started or duration exceeded
                now_perf = time.perf_counter()
                if (
                    self._current_writer is None
                    or (now_perf - self._segment_start_perf) >= self.segment_duration_sec
                ):
                    # Write pre-event buffer if starting an event-based segment
                    pre_frames = list(self._pre_event_buffer) if self.recording_type in ["MOTION", "AI_EVENT"] else []
                    self._start_new_segment(frame, ts)
                    for pf, _ in pre_frames:
                        self._current_writer.write(pf)
                        self._frames_written_segment += 1

                self._current_writer.write(frame)
                self._frames_written_segment += 1
            else:
                # If was recording but event ended, close segment
                if self._current_writer is not None:
                    self._close_current_segment()
                # Maintain pre-event ring buffer in memory
                self._pre_event_buffer.append((frame, ts))

        # Finalize upon stop
        self._close_current_segment()
        logger.info("Channel recording worker terminated for [%s]", self.channel_id)


class RecordingRecoveryService:
    """
    Runs at startup to detect unclosed recording segments from application crashes
    or sudden power loss, computes actual file duration and SHA-256 hash, and marks RECOVERED.
    """

    @classmethod
    def recover_interrupted_recordings(cls) -> int:
        recovered_count = 0
        with db_manager.get_session() as session:
            active_recs = session.query(Recording).filter_by(status="ACTIVE").all()
            for rec in active_recs:
                if not os.path.exists(rec.file_path):
                    rec.status = "CORRUPTED"
                    logger.warning("Unclosed recording file missing on disk: %s. Marked CORRUPTED.", rec.file_path)
                    continue

                try:
                    f_size = os.path.getsize(rec.file_path)
                    if f_size == 0:
                        rec.status = "CORRUPTED"
                        continue

                    # Probe actual frame count and duration using OpenCV
                    cap = cv2.VideoCapture(rec.file_path)
                    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
                    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                    cap.release()

                    duration = int(frame_count / fps) if fps > 0 else 0
                    sha256 = calculate_file_sha256(rec.file_path)

                    rec.file_size_bytes = f_size
                    rec.duration_sec = duration
                    rec.end_time = rec.start_time + timedelta(seconds=duration)
                    rec.sha256_hash = sha256
                    rec.status = "RECOVERED"

                    for seg in rec.segments:
                        if os.path.exists(seg.file_path):
                            seg.file_size_bytes = os.path.getsize(seg.file_path)
                            seg.sha256_hash = calculate_file_sha256(seg.file_path)
                            seg.duration_sec = duration
                            seg.end_time = rec.end_time

                    recovered_count += 1
                    logger.info("Successfully recovered interrupted recording [%s] (%ds, %s)", rec.file_path, duration, sha256[:12])
                except Exception as e:
                    rec.status = "CORRUPTED"
                    logger.error("Error recovering recording %s: %s", rec.file_path, e)

        return recovered_count
