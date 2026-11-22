"""
RTSP Video Stream Worker Engine.
Decoupled background stream receiver supporting FFmpeg/OpenCV, hardware decode hints,
bounded frame queues, auto-reconnection, telemetry, and synthetic surveillance test streams.
"""

import os
import re
import time
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Optional, Callable, Dict, Any, Tuple
import cv2
import numpy as np

from engines.video_engine.stream_metrics import StreamState, StreamTelemetry
from core.logging.logger import get_logger, redact_sensitive_text

logger = get_logger("rtsp_streamer")

# Force OpenCV FFmpeg backend to use TCP transport and set connection timeout
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"


def mask_rtsp_url(url: str) -> str:
    """Masks credentials in RTSP strings."""
    return re.sub(r'(rtsp://[^:]+:)([^@]+)(@)', r'\1******\3', url, flags=re.IGNORECASE)


class RTSPStreamWorker(threading.Thread):
    """
    Independent worker thread dedicated to ingesting, decoding,
    and buffering video frames from a single camera RTSP stream.
    """

    def __init__(
        self,
        channel_id: str,
        rtsp_url: str,
        channel_name: str = "Camera",
        max_buffer_size: int = 30,
        reconnect_interval_sec: float = 3.0,
        frame_callback: Optional[Callable[[str, np.ndarray, float], None]] = None,
        is_test_stream: bool = False,
    ) -> None:
        super().__init__(name=f"StreamWorker-{channel_id}", daemon=True)
        self.channel_id = channel_id
        self.channel_name = channel_name
        self.rtsp_url = rtsp_url
        self.masked_url = mask_rtsp_url(rtsp_url)
        self.max_buffer_size = max_buffer_size
        self.reconnect_interval_sec = reconnect_interval_sec
        self.frame_callback = frame_callback
        self.is_test_stream = is_test_stream or rtsp_url.startswith("test://")

        # Bounded frame buffer: automatically drops oldest frame when full
        self._frame_buffer: deque = deque(maxlen=max_buffer_size)
        self._buffer_lock = threading.Lock()

        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._capture: Optional[cv2.VideoCapture] = None

        self.telemetry = StreamTelemetry(
            channel_id=channel_id,
            state=StreamState.OFFLINE,
            queue_capacity=max_buffer_size,
        )

        # FPS calculation state
        self._fps_timestamps: deque = deque(maxlen=30)
        self._test_frame_counter = 0

    def stop(self) -> None:
        """Signals worker to stop and releases hardware resources."""
        self._stop_event.set()
        logger.info("Stopping stream worker [%s] (%s)", self.channel_id, self.masked_url)

    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def get_latest_frame(self) -> Optional[Tuple[np.ndarray, float]]:
        """Retrieves the newest frame without blocking."""
        with self._buffer_lock:
            if self._frame_buffer:
                return self._frame_buffer[-1]
        return None

    def _generate_synthetic_test_frame(self) -> np.ndarray:
        """Generates realistic surveillance test video frame for testing and offline simulation."""
        self._test_frame_counter += 1
        width, height = 640, 360
        frame = np.zeros((height, width, 3), dtype=np.uint8)

        # Dark surveillance background gradient
        frame[:] = (20, 24, 30)

        # Grid lines
        for y in range(0, height, 40):
            cv2.line(frame, (0, y), (width, y), (35, 42, 52), 1)
        for x in range(0, width, 40):
            cv2.line(frame, (x, 0), (x, height), (35, 42, 52), 1)

        # Animated simulated moving object (target)
        t = self._test_frame_counter * 0.05
        obj_x = int((np.sin(t) * 0.4 + 0.5) * (width - 100)) + 50
        obj_y = int((np.cos(t * 0.8) * 0.3 + 0.5) * (height - 80)) + 40
        cv2.rectangle(frame, (obj_x, obj_y), (obj_x + 60, obj_y + 70), (0, 180, 216), 2)
        cv2.putText(frame, "SIMULATED TARGET", (obj_x, obj_y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 180, 216), 1)

        # Timestamp and OSD overlay
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-4] + " UTC"
        cv2.putText(frame, f"{self.channel_name.upper()} | {now_str}", (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        cv2.putText(frame, f"CHANNEL: {self.channel_id} | RESOLUTION: {width}x{height}", (15, height - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (148, 163, 184), 1)

        # Status indicator
        cv2.circle(frame, (width - 25, 25), 6, (0, 220, 50), -1)

        return frame

    def _open_capture(self) -> bool:
        """Initializes OpenCV video capture for RTSP."""
        if self.is_test_stream:
            self.telemetry.detected_width = 640
            self.telemetry.detected_height = 360
            self.telemetry.state = StreamState.ONLINE
            return True

        self.telemetry.state = StreamState.CONNECTING
        logger.info("Connecting to RTSP stream [%s]: %s", self.channel_id, self.masked_url)

        try:
            self._capture = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            if self._capture.isOpened():
                w = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                self.telemetry.detected_width = w if w > 0 else 1920
                self.telemetry.detected_height = h if h > 0 else 1080
                self.telemetry.state = StreamState.ONLINE
                self.telemetry.last_error = None
                logger.info("Connected to RTSP stream [%s] (%dx%d)", self.channel_id, self.telemetry.detected_width, self.telemetry.detected_height)
                return True
        except Exception as e:
            self.telemetry.last_error = str(e)
            logger.warning("Failed opening RTSP stream [%s]: %s", self.channel_id, e)

        self.telemetry.state = StreamState.ERROR
        return False

    def _release_capture(self) -> None:
        if self._capture:
            try:
                self._capture.release()
            except Exception as e:
                logger.debug("Error releasing VideoCapture [%s]: %s", self.channel_id, e)
            self._capture = None

    def run(self) -> None:
        logger.info("Stream worker thread started for [%s]", self.channel_id)

        while not self._stop_event.is_set():
            if not self._open_capture():
                self.telemetry.state = StreamState.RECONNECTING
                self.telemetry.reconnect_count += 1
                self._stop_event.wait(self.reconnect_interval_sec)
                continue

            last_fps_calc = time.perf_counter()
            frames_in_second = 0

            # Active frame decoding loop
            while not self._stop_event.is_set():
                frame: Optional[np.ndarray] = None
                timestamp = time.time()

                if self.is_test_stream:
                    time.sleep(0.04)  # ~25 FPS pacing
                    frame = self._generate_synthetic_test_frame()
                else:
                    ret, raw_frame = self._capture.read()
                    if not ret or raw_frame is None:
                        logger.warning("Stream read failure / EOF on [%s]. Triggering reconnect.", self.channel_id)
                        self.telemetry.state = StreamState.RECONNECTING
                        self.telemetry.reconnect_count += 1
                        self._release_capture()
                        break
                    frame = raw_frame

                # Telemetry updates
                self.telemetry.total_frames_received += 1
                self.telemetry.last_frame_timestamp = datetime.now(timezone.utc)
                frames_in_second += 1

                # Calculate smoothed FPS
                now_perf = time.perf_counter()
                elapsed = now_perf - last_fps_calc
                if elapsed >= 1.0:
                    self.telemetry.current_fps = round(frames_in_second / elapsed, 1)
                    frames_in_second = 0
                    last_fps_calc = now_perf

                # Buffer frame
                with self._buffer_lock:
                    if len(self._frame_buffer) >= self.max_buffer_size:
                        self.telemetry.total_frames_dropped += 1
                    self._frame_buffer.append((frame, timestamp))
                    self.telemetry.queue_occupancy = len(self._frame_buffer)

                # Frame callback dispatch
                if self.frame_callback:
                    try:
                        self.frame_callback(self.channel_id, frame, timestamp)
                    except Exception as e:
                        logger.debug("Error in frame callback for [%s]: %s", self.channel_id, e)

            self._release_capture()
            if not self._stop_event.is_set():
                self._stop_event.wait(self.reconnect_interval_sec)

        # Clean termination
        self._release_capture()
        with self._buffer_lock:
            self._frame_buffer.clear()
        self.telemetry.state = StreamState.STOPPED
        logger.info("Stream worker thread terminated for [%s]", self.channel_id)
