"""
Recording Manager Controller.
Coordinates multi-channel recording workers, dispatches stream frames,
and schedules event triggers.
"""

import threading
from typing import Dict, Optional, List, Any
import numpy as np

from engines.recording_engine.recorder import ChannelRecordingWorker, RecordingRecoveryService
from engines.video_engine.stream_manager import stream_manager
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("recording_manager")


class RecordingManager:
    """Central controller for all channel video recording workers."""

    def __init__(self) -> None:
        self._recorders: Dict[str, ChannelRecordingWorker] = {}
        self._lock = threading.RLock()

    def start_recording(
        self,
        channel_id: str,
        channel_name: str = "Camera",
        recording_type: str = "CONTINUOUS",
        stream_type: str = "MAIN",
        segment_duration_sec: int = 60,
        output_dir: Optional[str] = None,
    ) -> ChannelRecordingWorker:
        """Starts a recording worker for a designated channel."""
        with self._lock:
            if channel_id in self._recorders:
                self.stop_recording(channel_id)

            worker = ChannelRecordingWorker(
                channel_id=channel_id,
                channel_name=channel_name,
                recording_type=recording_type,
                stream_type=stream_type,
                segment_duration_sec=segment_duration_sec,
                output_dir=output_dir,
            )
            self._recorders[channel_id] = worker
            worker.start()

            # Register consumer ownership on StreamManager
            stream_manager.add_consumer(channel_id, f"recorder_{channel_id}")

            # Attach frame callback to StreamManager so frames flow automatically to recorder
            def frame_hook(ch: str, frame: np.ndarray, ts: float) -> None:
                rec = self._recorders.get(ch)
                if rec and rec.is_alive():
                    rec.push_frame(frame, ts)

            setattr(worker, "_frame_hook", frame_hook)
            stream_manager.register_frame_callback(channel_id, frame_hook)

            bus.publish("recording.started", {"channel_id": channel_id, "mode": recording_type})
            return worker

    def stop_recording(self, channel_id: str) -> None:
        """Stops and finalizes recording for a channel."""
        with self._lock:
            worker = self._recorders.get(channel_id)
            if worker:
                stream_manager.remove_consumer(channel_id, f"recorder_{channel_id}")
                if hasattr(worker, "_frame_hook"):
                    stream_manager.unregister_frame_callback(channel_id, getattr(worker, "_frame_hook"))
                worker.stop()
                if worker.is_alive():
                    worker.join(timeout=3.0)
                del self._recorders[channel_id]
                bus.publish("recording.stopped", {"channel_id": channel_id})

    def trigger_event_recording(self, channel_id: str, event_name: str = "Motion", duration_sec: Optional[float] = None) -> None:
        """Notifies a recording worker that an event occurred to trigger event segmenting."""
        with self._lock:
            worker = self._recorders.get(channel_id)
            if worker and worker.is_alive():
                worker.trigger_event(duration_sec)

    def is_recording(self, channel_id: str) -> bool:
        with self._lock:
            worker = self._recorders.get(channel_id)
            return worker is not None and worker.is_alive()

    def get_active_channels(self) -> List[str]:
        with self._lock:
            return [ch for ch, w in self._recorders.items() if w.is_alive()]

    def stop_all(self) -> None:
        """Stops all active recorders cleanly during application shutdown."""
        logger.info("Stopping all active recording workers...")
        with self._lock:
            for ch, worker in list(self._recorders.items()):
                stream_manager.remove_consumer(ch, f"recorder_{ch}")
                if hasattr(worker, "_frame_hook"):
                    stream_manager.unregister_frame_callback(ch, getattr(worker, "_frame_hook"))
                worker.stop()
            for worker in self._recorders.values():
                if worker.is_alive():
                    worker.join(timeout=3.0)
            self._recorders.clear()
        logger.info("All recording workers successfully stopped.")


# Global recording manager singleton
recording_manager = RecordingManager()
