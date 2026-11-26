"""
Centralized Shared Frame Distribution Hub (Milestone W4.2).
Provides fan-out of decoded video frames from a single upstream RTSPStreamWorker
to multiple concurrent web client subscribers (WebRTC, MJPEG, AI Inference, Desktop).

Core Architectural Guarantees:
1. Zero Duplicate RTSP Sessions: Exactly one upstream connection per camera channel.
2. Bounded Client Queues: Isolated queues (default max 5 frames) per subscriber.
3. Slow-Client Protection: Non-blocking drop-oldest eviction prevents consumer lag from
   stalling the upstream camera capture loop.
4. Reference Counting with Grace Period: Streams automatically spin up on first subscriber
   and cleanly shut down 30s after the last subscriber disconnects.
5. Thread-Safe Lifecycle: All subscription, unsubscription, and frame dispatches are protected
   by reentrant synchronization primitives.
"""

import time
import uuid
import threading
from collections import deque
from typing import Dict, Optional, Tuple, Any, List, Callable
import numpy as np

from engines.video_engine.stream_manager import stream_manager
from core.security.crypto import credential_vault
from database.database_manager import db_manager
from database.models.devices import Device, DeviceChannel, StreamProfile, DeviceCredential
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("frame_distribution_hub")


class ClientSubscription:
    """
    Dedicated client subscription queue.
    Buffers incoming decoded frames for a specific client (e.g. a WebRTC peer connection
    or an MJPEG HTTP response generator) with strict bound and drop-oldest policy.
    """

    def __init__(self, channel_id: str, client_id: str, max_queue_size: int = 5) -> None:
        self.channel_id = channel_id
        self.client_id = client_id
        self.max_queue_size = max(1, max_queue_size)
        self._queue: deque = deque(maxlen=self.max_queue_size)
        self._cond = threading.Condition(threading.Lock())
        self.is_active: bool = True
        self.total_frames_delivered: int = 0
        self.total_frames_dropped: int = 0
        self.created_at: float = time.monotonic()
        self.last_delivered_at: float = 0.0

    def push_frame(self, frame: np.ndarray, timestamp: float) -> bool:
        """
        Receives an upstream frame and deposits it into the bounded queue.
        Non-blocking: if the queue is full, evicts oldest frame immediately.
        Returns True if queued without drop, False if oldest frame was evicted.
        """
        with self._cond:
            if not self.is_active:
                return False

            evicted = False
            if len(self._queue) >= self.max_queue_size:
                self.total_frames_dropped += 1
                evicted = True

            self._queue.append((frame, timestamp))
            self.total_frames_delivered += 1
            self.last_delivered_at = timestamp
            self._cond.notify()
            return not evicted

    def get_frame(self, timeout: float = 1.0) -> Optional[Tuple[np.ndarray, float]]:
        """
        Retrieves the next frame, blocking up to timeout seconds.
        Returns (frame, timestamp) or None if timeout elapsed or subscription closed.
        """
        with self._cond:
            deadline = time.monotonic() + timeout
            while self.is_active and len(self._queue) == 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._cond.wait(remaining)

            if not self.is_active or len(self._queue) == 0:
                return None

            return self._queue.popleft()

    def get_latest_frame_nowait(self) -> Optional[Tuple[np.ndarray, float]]:
        """Non-blocking peek/pop of newest available frame."""
        with self._cond:
            if not self.is_active or len(self._queue) == 0:
                return None
            frame_item = self._queue[-1]
            self._queue.clear()
            return frame_item

    def close(self) -> None:
        """Closes subscription and wakes up any waiting consumer threads."""
        with self._cond:
            self.is_active = False
            self._queue.clear()
            self._cond.notify_all()


class ChannelDistributor:
    """
    Manages client subscriptions and frame fan-out for a single camera channel.
    Handles reference-counted upstream lifecycle on StreamManager.
    """

    def __init__(self, channel_id: str, idle_grace_period_sec: float = 30.0) -> None:
        self.channel_id = channel_id
        self.idle_grace_period_sec = idle_grace_period_sec
        self._subscribers: Dict[str, ClientSubscription] = {}
        self._lock = threading.RLock()
        self._upstream_started_by_hub = False
        self._idle_timer: Optional[threading.Timer] = None
        self._callback_registered = False
        self.total_frames_broadcast: int = 0
        self.last_broadcast_at: float = 0.0

    def _frame_callback(self, ch_id: str, frame: np.ndarray, timestamp: float) -> None:
        """
        Synchronous callback called by RTSPStreamWorker.
        Instantly distributes frame across all client queues in a non-blocking manner.
        Frames are distributed as read-only views to guarantee that no subscriber can
        mutate or corrupt the shared underlying frame buffer.
        """
        with self._lock:
            subs = list(self._subscribers.values())

        if not subs:
            return

        self.total_frames_broadcast += 1
        self.last_broadcast_at = timestamp

        # Provide an immutable buffer backed by a read-only memoryview sharing the same memory.
        # Guarantees at Python C-API level that flags.writeable CANNOT be restored and
        # neither the array, nor its .base, nor .base.base can be mutated.
        ro_memory = memoryview(frame).toreadonly()
        immutable_frame = np.frombuffer(ro_memory, dtype=frame.dtype).reshape(frame.shape)

        for sub in subs:
            try:
                sub.push_frame(immutable_frame, timestamp)
            except Exception as e:
                logger.debug("Error delivering frame to client %s on channel %s: %s", sub.client_id, self.channel_id, e)

    def ensure_upstream_running(self) -> bool:
        """
        Ensures an active RTSP stream worker is running on StreamManager for this channel.
        If already active (e.g. from desktop or prior subscriber), binds callback.
        If not active, looks up camera credentials and launches worker.
        """
        with self._lock:
            # Cancel any pending idle shutdown timer
            if self._idle_timer:
                self._idle_timer.cancel()
                self._idle_timer = None

            # 1. Check if StreamManager already has a worker for this channel
            existing_worker = stream_manager._workers.get(self.channel_id)
            if existing_worker and existing_worker.is_alive():
                if not self._callback_registered:
                    stream_manager.register_frame_callback(self.channel_id, self._frame_callback)
                    self._callback_registered = True
                return True

            # 2. Need to provision and launch upstream worker
            rtsp_url, camera_name, is_test = self._resolve_camera_source()
            if not rtsp_url:
                logger.error("Unable to resolve RTSP source for channel [%s]", self.channel_id)
                return False

            try:
                stream_manager.start_stream(
                    channel_id=self.channel_id,
                    rtsp_url=rtsp_url,
                    channel_name=camera_name,
                    max_buffer_size=15,
                    frame_callback=self._frame_callback,
                    is_test_stream=is_test,
                )
                self._upstream_started_by_hub = True
                self._callback_registered = True
                logger.info("Launched upstream StreamManager worker for channel [%s] (test=%s)", self.channel_id, is_test)
                return True
            except Exception as e:
                logger.error("Failed to start upstream worker for channel [%s]: %s", self.channel_id, e)
                return False

    def _resolve_camera_source(self) -> Tuple[Optional[str], str, bool]:
        """
        Resolves camera configuration, decrypted credentials, and RTSP URL from database.
        Falls back to synthetic test stream if camera is simulated or in test mode.
        """
        # If channel ID looks like a simulated/test channel or starts with test_
        if self.channel_id.startswith("test_") or self.channel_id.startswith("ch_") or self.channel_id.startswith("sim_"):
            return f"test://simulated_camera_{self.channel_id}", f"Simulated Camera {self.channel_id}", True

        try:
            with db_manager.get_session() as session:
                # Query by DeviceChannel ID
                channel = session.query(DeviceChannel).filter_by(id=self.channel_id).first()
                if not channel:
                    # Query by Device ID where primary channel exists
                    device = session.query(Device).filter_by(id=self.channel_id, is_deleted=False).first()
                    if device and device.channels:
                        channel = device.channels[0]
                    else:
                        device = None

                if channel:
                    device = channel.device
                    profile = (
                        session.query(StreamProfile)
                        .filter_by(channel_id=channel.id, profile_type="MAIN")
                        .first()
                    )
                    if not profile:
                        profile = session.query(StreamProfile).filter_by(channel_id=channel.id).first()

                    if profile and profile.rtsp_url:
                        raw_url = profile.rtsp_url
                        is_test = raw_url.startswith("test://")
                        return raw_url, channel.name, is_test

                    # Fallback to constructing RTSP URL from Device and Credential
                    if device:
                        cred = session.query(DeviceCredential).filter_by(device_id=device.id).first()
                        user = cred.username if cred else "admin"
                        pwd = credential_vault.decrypt_password(cred.encrypted_password) if cred else ""
                        port = device.rtsp_port or 554
                        path = "/live"
                        url = f"rtsp://{user}:{pwd}@{device.ip_address}:{port}{path}"
                        return url, device.name, False

        except Exception as e:
            logger.warning("Database query failed while resolving channel [%s]: %s", self.channel_id, e)

        # Fallback to synthetic stream so UI remains functional
        return f"test://simulated_camera_{self.channel_id}", f"Camera {self.channel_id}", True

    def add_subscriber(self, client_id: str, max_queue_size: int = 5) -> ClientSubscription:
        """Registers a new client subscriber and ensures upstream stream is running."""
        with self._lock:
            self.ensure_upstream_running()

            # Evict any existing subscription for this client_id
            if client_id in self._subscribers:
                self._subscribers[client_id].close()

            sub = ClientSubscription(
                channel_id=self.channel_id,
                client_id=client_id,
                max_queue_size=max_queue_size,
            )
            self._subscribers[client_id] = sub
            logger.info(
                "Added subscriber [%s] to channel [%s]. Total active subscribers: %d",
                client_id, self.channel_id, len(self._subscribers)
            )
            return sub

    def remove_subscriber(self, client_id: str) -> None:
        """Removes a subscriber. If subscriber count hits zero, initiates idle shutdown timer."""
        with self._lock:
            sub = self._subscribers.pop(client_id, None)
            if sub:
                sub.close()
                logger.info(
                    "Removed subscriber [%s] from channel [%s]. Remaining: %d",
                    client_id, self.channel_id, len(self._subscribers)
                )

            if len(self._subscribers) == 0 and self._upstream_started_by_hub:
                self._schedule_idle_shutdown()

    def _schedule_idle_shutdown(self) -> None:
        """Schedules idle shutdown of upstream RTSP stream after grace period."""
        if self._idle_timer:
            self._idle_timer.cancel()

        def _timeout_handler():
            with self._lock:
                if len(self._subscribers) == 0 and self._upstream_started_by_hub:
                    logger.info("Grace period (%.1fs) elapsed with zero subscribers. Stopping upstream [%s].", self.idle_grace_period_sec, self.channel_id)
                    self._stop_upstream()

        self._idle_timer = threading.Timer(self.idle_grace_period_sec, _timeout_handler)
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _stop_upstream(self) -> None:
        """Halts the upstream RTSP stream worker on StreamManager atomically if no consumers remain."""
        with self._lock:
            if not self._upstream_started_by_hub:
                # If stream was not started by hub, only detach our callback
                if self._callback_registered:
                    stream_manager.unregister_frame_callback(self.channel_id, self._frame_callback)
                    self._callback_registered = False
                return

            # Hub started the stream. Atomically attempt idle shutdown:
            # stop_stream_if_idle acquires stream_manager._lock, unregisters hub callback,
            # checks for any active consumers/callbacks/polls, and only stops if genuinely idle.
            stopped = stream_manager.stop_stream_if_idle(
                channel_id=self.channel_id,
                exclude_callback=self._frame_callback
            )

            if stopped:
                self._upstream_started_by_hub = False
                self._callback_registered = False
                logger.info("Hub cleanly shut down idle upstream worker for channel [%s].", self.channel_id)
            else:
                # Ownership successfully transferred to surviving native consumers!
                self._upstream_started_by_hub = False
                if self._callback_registered:
                    stream_manager.unregister_frame_callback(self.channel_id, self._frame_callback)
                    self._callback_registered = False
                logger.info(
                    "Hub transferred upstream ownership of channel [%s] to active native consumers.",
                    self.channel_id
                )

    def get_stats(self) -> Dict[str, Any]:
        """Returns diagnostic telemetry for this channel's distribution."""
        with self._lock:
            return {
                "channel_id": self.channel_id,
                "active_subscribers": len(self._subscribers),
                "upstream_started_by_hub": self._upstream_started_by_hub,
                "callback_registered": self._callback_registered,
                "total_frames_broadcast": self.total_frames_broadcast,
                "last_broadcast_at": self.last_broadcast_at,
                "subscribers": [
                    {
                        "client_id": s.client_id,
                        "queue_size": len(s._queue),
                        "frames_delivered": s.total_frames_delivered,
                        "frames_dropped": s.total_frames_dropped,
                        "is_active": s.is_active,
                    }
                    for s in self._subscribers.values()
                ],
            }

    def close(self) -> None:
        """Cleans up all subscribers and halts upstream stream."""
        with self._lock:
            if self._idle_timer:
                self._idle_timer.cancel()
                self._idle_timer = None

            for sub in list(self._subscribers.values()):
                sub.close()
            self._subscribers.clear()

            self._stop_upstream()


class FrameDistributionHub:
    """
    Central Video Gateway Hub.
    Manages channel distributors across all surveillance camera feeds.
    """

    def __init__(self, default_grace_period_sec: float = 30.0) -> None:
        self.default_grace_period_sec = default_grace_period_sec
        self._distributors: Dict[str, ChannelDistributor] = {}
        self._lock = threading.RLock()

    def subscribe(
        self,
        channel_id: str,
        client_id: Optional[str] = None,
        max_queue_size: int = 5,
    ) -> ClientSubscription:
        """Subscribes a client to a camera channel's frame stream."""
        cid = client_id or str(uuid.uuid4())
        with self._lock:
            distributor = self._distributors.get(channel_id)
            if not distributor:
                distributor = ChannelDistributor(channel_id, self.default_grace_period_sec)
                self._distributors[channel_id] = distributor

            return distributor.add_subscriber(cid, max_queue_size=max_queue_size)

    def unsubscribe(self, channel_id: str, client_id: str) -> None:
        """Unsubscribes a client from a camera channel's frame stream."""
        with self._lock:
            distributor = self._distributors.get(channel_id)
            if distributor:
                distributor.remove_subscriber(client_id)

    def get_channel_stats(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Returns stats for a specific channel distributor."""
        with self._lock:
            distributor = self._distributors.get(channel_id)
            return distributor.get_stats() if distributor else None

    def get_all_stats(self) -> Dict[str, Any]:
        """Returns stats across all active distributors."""
        with self._lock:
            return {
                "active_channels": len(self._distributors),
                "channels": {ch_id: d.get_stats() for ch_id, d in self._distributors.items()},
            }

    def stop_all(self) -> None:
        """Halts all distributors and cleans up background timers and subscriptions."""
        logger.info("Stopping all FrameDistributionHub distributors...")
        with self._lock:
            for distributor in self._distributors.values():
                distributor.close()
            self._distributors.clear()
        logger.info("FrameDistributionHub shutdown completed.")


# Global singleton instance
frame_distribution_hub = FrameDistributionHub()
