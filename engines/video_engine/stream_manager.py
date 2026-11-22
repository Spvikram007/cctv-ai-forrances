"""
Multi-Channel RTSP Stream Manager.
Orchestrates stream workers across up to 64 channels, handles lifecycle,
frame extraction, and dispatches telemetry to the EventBus.
"""

import threading
from typing import Dict, Optional, Tuple, Callable, Any, List
import numpy as np

from engines.video_engine.rtsp_streamer import RTSPStreamWorker
from engines.video_engine.stream_metrics import StreamTelemetry, StreamState
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("stream_manager")


class StreamManager:
    """Central controller for all active video stream worker threads."""

    def __init__(self, max_channels: int = 64) -> None:
        self.max_channels = max_channels
        self._workers: Dict[str, RTSPStreamWorker] = {}
        self._lock = threading.RLock()

    def start_stream(
        self,
        channel_id: str,
        rtsp_url: str,
        channel_name: str = "Camera",
        max_buffer_size: int = 30,
        frame_callback: Optional[Callable[[str, np.ndarray, float], None]] = None,
        is_test_stream: bool = False,
    ) -> RTSPStreamWorker:
        """Starts or restarts an RTSP stream worker for a designated channel."""
        with self._lock:
            if len(self._workers) >= self.max_channels and channel_id not in self._workers:
                raise ValueError(f"Cannot exceed maximum capacity of {self.max_channels} channels.")

            if channel_id in self._workers:
                logger.info("Stopping existing worker for channel [%s] before replacement.", channel_id)
                self.stop_stream(channel_id)

            worker = RTSPStreamWorker(
                channel_id=channel_id,
                rtsp_url=rtsp_url,
                channel_name=channel_name,
                max_buffer_size=max_buffer_size,
                frame_callback=frame_callback,
                is_test_stream=is_test_stream,
            )
            self._workers[channel_id] = worker
            worker.start()

            bus.publish("stream.started", {"channel_id": channel_id, "channel_name": channel_name})
            return worker

    def stop_stream(self, channel_id: str) -> None:
        """Gracefully halts a specific channel's stream worker."""
        with self._lock:
            worker = self._workers.get(channel_id)
            if worker:
                worker.stop()
                if worker.is_alive():
                    worker.join(timeout=3.0)
                del self._workers[channel_id]
                bus.publish("stream.stopped", {"channel_id": channel_id})

    def get_latest_frame(self, channel_id: str) -> Optional[Tuple[np.ndarray, float]]:
        """Retrieves newest frame for a channel."""
        with self._lock:
            worker = self._workers.get(channel_id)
            if worker:
                return worker.get_latest_frame()
        return None

    def get_telemetry(self, channel_id: str) -> Optional[StreamTelemetry]:
        """Returns health telemetry for a given channel."""
        with self._lock:
            worker = self._workers.get(channel_id)
            if worker:
                return worker.telemetry
        return None

    def get_all_telemetry(self) -> Dict[str, Dict[str, Any]]:
        """Returns snapshot telemetry for all active channels."""
        with self._lock:
            return {ch_id: worker.telemetry.to_dict() for ch_id, worker in self._workers.items()}

    def active_stream_count(self) -> int:
        with self._lock:
            return sum(1 for w in self._workers.values() if w.telemetry.state == StreamState.ONLINE)

    def register_frame_callback(self, channel_id: str, callback: Callable[[str, np.ndarray, float], None]) -> None:
        """Registers a frame consumer callback on a channel's stream worker."""
        with self._lock:
            worker = self._workers.get(channel_id)
            if worker:
                worker.add_frame_callback(callback)

    def unregister_frame_callback(self, channel_id: str, callback: Callable[[str, np.ndarray, float], None]) -> None:
        """Removes a frame consumer callback from a channel's stream worker."""
        with self._lock:
            worker = self._workers.get(channel_id)
            if worker:
                worker.remove_frame_callback(callback)

    def stop_all(self) -> None:
        """Halts all active stream workers during application shutdown."""
        logger.info("Halting all active RTSP stream workers...")
        with self._lock:
            for worker in self._workers.values():
                worker.stop()
            for worker in self._workers.values():
                if worker.is_alive():
                    worker.join(timeout=2.0)
            self._workers.clear()
        logger.info("All RTSP stream workers successfully stopped.")


# Global stream manager singleton
stream_manager = StreamManager()
