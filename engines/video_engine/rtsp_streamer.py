"""
RTSP Video Stream Worker Engine.
Decoupled background stream receiver supporting FFmpeg/OpenCV, hardware decode hints,
bounded frame queues, auto-reconnection, telemetry, and synthetic surveillance test streams.
"""

import os
import re
import time
import socket
import random
import threading
from urllib.parse import urlparse
from collections import deque
from datetime import datetime, timezone
from typing import Optional, Callable, Dict, Any, Tuple, List
import cv2
import numpy as np

from engines.video_engine.stream_metrics import StreamState, StreamTelemetry, StreamHealthHistory
from core.events.event_bus import bus
from core.logging.logger import get_logger, redact_sensitive_text

logger = get_logger("rtsp_streamer")

# Force OpenCV FFmpeg backend to use TCP transport and set connection timeout
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"


def mask_rtsp_url(url: str) -> str:
    """Masks credentials in RTSP strings."""
    return re.sub(r'(rtsp://[^:]+:)([^@]+)(@)', r'\1******\3', url, flags=re.IGNORECASE)


def validate_rtsp_url(url: str, check_reachability: bool = False, timeout_sec: float = 2.0) -> Tuple[bool, str]:
    """
    Validates RTSP URL formatting and optionally verifies TCP port reachability.
    Supports rtsp://, rtsps://, and simulated test:// schemes.
    """
    if not url or not isinstance(url, str):
        return False, "URL cannot be empty."

    url = url.strip()
    if url.startswith("test://"):
        return True, "Valid synthetic surveillance stream."

    match = re.match(r'^rtsps?://(?:([^:@]+)(?::([^@]+))?@)?([^:/]+)(?::(\d+))?(/.*)?$', url, re.IGNORECASE)
    if not match:
        return False, "Invalid RTSP URL syntax. Expected format: rtsp://[user:pass@]host[:port]/path"

    host = match.group(3)
    port_str = match.group(4)
    port = int(port_str) if port_str else 554

    if not host:
        return False, "Missing host or IP address in RTSP URL."

    if check_reachability:
        try:
            with socket.create_connection((host, port), timeout=timeout_sec):
                return True, "RTSP endpoint is reachable."
        except socket.timeout:
            return False, f"Connection to {host}:{port} timed out after {timeout_sec}s."
        except OSError as e:
            return False, f"Cannot reach {host}:{port}: {e}"

    return True, "Valid RTSP URL syntax."


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
        self._callbacks: List[Callable[[str, np.ndarray, float], None]] = []
        if frame_callback:
            self._callbacks.append(frame_callback)
        self._callbacks_lock = threading.Lock()
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

        # Phase 3: Stream reliability, failover, and backoff configuration
        self.initial_backoff_sec: float = max(0.5, float(reconnect_interval_sec / 2.0))
        self.max_backoff_sec: float = 30.0
        self.backoff_multiplier: float = 2.0
        self.current_backoff: float = self.initial_backoff_sec
        self.last_healthy_connection_time: float = 0.0

        # Frozen frame & stale timestamp detection
        self.frozen_threshold_sec: float = 5.0
        self.stale_threshold_sec: float = 5.0
        self.last_different_frame_time: float = time.time()
        self._last_downsampled_frame: Optional[np.ndarray] = None
        self._consecutive_decode_errors: int = 0

        # Dynamic stream profile switching (MAIN/SUB)
        self._switch_profile_event = threading.Event()
        self._pending_switch_url: Optional[str] = None
        self._pending_switch_profile: Optional[str] = None

        # Rolling health history
        self.history = StreamHealthHistory()

    @property
    def frame_callback(self):
        with self._callbacks_lock:
            return self._callbacks[0] if self._callbacks else None

    @frame_callback.setter
    def frame_callback(self, cb):
        with self._callbacks_lock:
            self._callbacks.clear()
            if cb:
                self._callbacks.append(cb)

    def add_frame_callback(self, callback: Callable[[str, np.ndarray, float], None]) -> None:
        """Registers an additional consumer callback for incoming decoded frames."""
        with self._callbacks_lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def remove_frame_callback(self, callback: Callable[[str, np.ndarray, float], None]) -> None:
        """Removes a registered frame consumer callback."""
        with self._callbacks_lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

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

    def switch_stream_profile(self, profile_type: str, new_url: Optional[str] = None) -> bool:
        """
        Dynamically switches stream profile (e.g. MAIN <-> SUB) without recreating the worker thread
        or losing consumer callbacks.
        """
        old_profile = self.telemetry.current_profile
        self.telemetry.current_profile = profile_type
        if new_url:
            self._pending_switch_url = new_url
            self._pending_switch_profile = profile_type
            self._switch_profile_event.set()
        logger.info("Switching stream profile for [%s]: %s -> %s", self.channel_id, old_profile, profile_type)
        bus.publish("stream.switched", {
            "channel_id": self.channel_id,
            "from_profile": old_profile,
            "to_profile": profile_type,
            "url": mask_rtsp_url(new_url) if new_url else self.masked_url,
        })
        self.history.record_event(self.telemetry.state, self.telemetry.current_fps, f"Switched to {profile_type}")
        return True

    def _check_frozen_frame(self, frame: np.ndarray, timestamp: float) -> bool:
        """
        Evaluates frame difference using rapid downsampling.
        Returns True if frame has been frozen longer than frozen_threshold_sec.
        """
        if frame is None or frame.size == 0:
            return False

        try:
            # Rapid 32x18 downsampling
            small = cv2.resize(frame, (32, 18), interpolation=cv2.INTER_NEAREST)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if len(small.shape) == 3 else small

            if self._last_downsampled_frame is not None:
                diff = float(np.mean(np.abs(gray.astype(np.float32) - self._last_downsampled_frame.astype(np.float32))))
                if diff > 0.5:
                    self.last_different_frame_time = timestamp
                    if self.telemetry.is_frozen:
                        self.telemetry.is_frozen = False
                        self.telemetry.state = StreamState.ONLINE
                        self.history.record_event(StreamState.ONLINE, self.telemetry.current_fps, "Stream unfrozen")
                        bus.publish("stream.recovered", {"channel_id": self.channel_id, "reason": "unfrozen"})
                else:
                    frozen_duration = timestamp - self.last_different_frame_time
                    if frozen_duration >= self.frozen_threshold_sec:
                        if not self.telemetry.is_frozen:
                            self.telemetry.is_frozen = True
                            self.telemetry.state = StreamState.FROZEN
                            self.telemetry.frozen_frames_count += 1
                            self.history.record_event(StreamState.FROZEN, self.telemetry.current_fps, f"Frozen for {frozen_duration:.1f}s")
                            bus.publish("stream.frozen", {"channel_id": self.channel_id, "duration": frozen_duration})
                        return True
            else:
                self.last_different_frame_time = timestamp

            self._last_downsampled_frame = gray
        except Exception as e:
            logger.debug("Frozen frame check error: %s", e)

        return False

    def _open_capture(self) -> bool:
        """Initializes OpenCV video capture for RTSP with hardware hints."""
        if self.is_test_stream:
            self.telemetry.detected_width = 640
            self.telemetry.detected_height = 360
            self.telemetry.state = StreamState.ONLINE
            self.telemetry.start_time = datetime.now(timezone.utc)
            self.history.record_event(StreamState.ONLINE, 25.0, "Connected to simulated stream")
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
                self.telemetry.start_time = datetime.now(timezone.utc)
                self.history.record_event(StreamState.ONLINE, self.telemetry.current_fps, "RTSP connection established")
                logger.info("Connected to RTSP stream [%s] (%dx%d)", self.channel_id, self.telemetry.detected_width, self.telemetry.detected_height)
                return True
        except Exception as e:
            self.telemetry.last_error = str(e)
            logger.warning("Failed opening RTSP stream [%s]: %s", self.channel_id, e)

        self.telemetry.state = StreamState.ERROR
        self.history.record_event(StreamState.ERROR, 0.0, str(self.telemetry.last_error))
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
                self.history.record_event(StreamState.RECONNECTING, 0.0, f"Reconnect attempt {self.telemetry.reconnect_count}")
                bus.publish("stream.disconnected", {"channel_id": self.channel_id, "reconnect_count": self.telemetry.reconnect_count})

                # Calculate exponential backoff delay with random jitter
                backoff_delay = self.current_backoff * (1.0 + random.uniform(-0.1, 0.1))
                self._stop_event.wait(backoff_delay)
                self.current_backoff = min(self.max_backoff_sec, self.current_backoff * self.backoff_multiplier)
                continue

            # Connected successfully
            bus.publish("stream.recovered", {"channel_id": self.channel_id, "reconnect_count": self.telemetry.reconnect_count})
            connection_established_time = time.time()
            last_fps_calc = time.perf_counter()
            frames_in_second = 0

            # Active frame decoding loop
            while not self._stop_event.is_set():
                # Handle pending dynamic stream profile switch
                if self._switch_profile_event.is_set():
                    self._switch_profile_event.clear()
                    if self._pending_switch_url:
                        self.rtsp_url = self._pending_switch_url
                        self.masked_url = mask_rtsp_url(self._pending_switch_url)
                        self.is_test_stream = self.rtsp_url.startswith("test://")
                        self._pending_switch_url = None
                    self._release_capture()
                    break

                frame: Optional[np.ndarray] = None
                timestamp = time.time()

                if self.is_test_stream:
                    time.sleep(0.04)  # ~25 FPS pacing
                    frame = self._generate_synthetic_test_frame()
                else:
                    ret, raw_frame = self._capture.read()
                    if not ret or raw_frame is None or raw_frame.size == 0:
                        self._consecutive_decode_errors += 1
                        self.telemetry.decoder_errors_count += 1
                        logger.warning("Stream read failure / EOF on [%s] (err count=%d)", self.channel_id, self._consecutive_decode_errors)
                        if self._consecutive_decode_errors >= 5:
                            self.telemetry.state = StreamState.RECONNECTING
                            self.telemetry.reconnect_count += 1
                            self.history.record_event(StreamState.RECONNECTING, 0.0, "Decoder errors threshold reached")
                            bus.publish("stream.disconnected", {"channel_id": self.channel_id})
                            self._release_capture()
                            break
                        time.sleep(0.05)
                        continue
                    else:
                        self._consecutive_decode_errors = 0
                        frame = raw_frame

                # Evaluate frozen frame condition
                is_frozen = self._check_frozen_frame(frame, timestamp)
                if is_frozen and not self.is_test_stream:
                    # If frame is frozen on a real stream, cycle capture
                    logger.warning("Frozen frame detected on [%s]. Cycling capture.", self.channel_id)
                    self._release_capture()
                    break

                # Telemetry updates
                self.telemetry.total_frames_received += 1
                self.telemetry.last_frame_timestamp = datetime.now(timezone.utc)
                if self.telemetry.start_time:
                    self.telemetry.uptime_seconds = (datetime.now(timezone.utc) - self.telemetry.start_time).total_seconds()
                frames_in_second += 1

                # Reset backoff if stream has been healthy for > 10 seconds
                if (timestamp - connection_established_time) > 10.0:
                    self.current_backoff = self.initial_backoff_sec

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

                # Packet loss / drop rate estimate
                total_frames = self.telemetry.total_frames_received + self.telemetry.total_frames_dropped
                if total_frames > 0:
                    self.telemetry.packet_loss_pct = (self.telemetry.total_frames_dropped / total_frames) * 100.0

                # Frame callback dispatch to all registered consumers
                with self._callbacks_lock:
                    callbacks_to_call = list(self._callbacks)
                for cb in callbacks_to_call:
                    try:
                        cb(self.channel_id, frame, timestamp)
                    except Exception as e:
                        logger.debug("Error in frame callback for [%s]: %s", self.channel_id, e)

            self._release_capture()
            if not self._stop_event.is_set():
                backoff_delay = self.current_backoff * (1.0 + random.uniform(-0.1, 0.1))
                self._stop_event.wait(backoff_delay)
                self.current_backoff = min(self.max_backoff_sec, self.current_backoff * self.backoff_multiplier)

        # Clean termination
        self._release_capture()
        with self._buffer_lock:
            self._frame_buffer.clear()
        self.telemetry.state = StreamState.STOPPED
        self.history.record_event(StreamState.STOPPED, 0.0, "Worker stopped")
        logger.info("Stream worker thread terminated for [%s]", self.channel_id)
