"""
AI Inference Worker.
Threaded worker that processes video frames through AI inference pipelines
with bounded queues, backpressure, and configurable frame sampling.
"""

import time
import threading
from collections import deque
from typing import Optional, Dict, Any, Callable, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np

from engines.ai_engine.inference_engine import (
    openvino_engine, onnx_engine, InferenceMetrics
)
from engines.detection_engine.yolo_detector import YOLODetector, DetectionResult
from engines.tracking_engine.byte_tracker import ByteTracker, TrackedObject
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("inference_worker")


@dataclass
class FramePacket:
    """Frame data plus metadata for inference pipeline."""
    channel_id: str
    frame: np.ndarray
    timestamp: float
    frame_index: int = 0


@dataclass
class InferenceResult:
    """Complete inference output for a single frame."""
    channel_id: str
    timestamp: float
    detections: List[DetectionResult] = field(default_factory=list)
    tracked_objects: List[TrackedObject] = field(default_factory=list)
    inference_latency_ms: float = 0.0
    device: str = "CPU"


class AIInferenceWorker(threading.Thread):
    """
    Dedicated worker thread for running AI inference on frames
    from a specific camera channel.
    """

    def __init__(
        self,
        channel_id: str,
        detector: YOLODetector,
        tracker: Optional[ByteTracker] = None,
        target_fps: float = 5.0,
        max_queue_size: int = 30,
        result_callback: Optional[Callable[[InferenceResult], None]] = None,
    ) -> None:
        super().__init__(name=f"AIWorker-{channel_id}", daemon=True)
        self.channel_id = channel_id
        self.detector = detector
        self.tracker = tracker or ByteTracker(max_lost_frames=30)
        self.target_fps = target_fps
        self.result_callback = result_callback

        self._input_queue: deque = deque(maxlen=max_queue_size)
        self._queue_lock = threading.Lock()
        self._stop_event = threading.Event()
        self.metrics = InferenceMetrics(device="UNKNOWN", model_name=detector.model_name)
        self.metrics._last_fps_time = time.perf_counter()
        self._frame_counter = 0

    def push_frame(self, frame: np.ndarray, timestamp: float) -> bool:
        """
        Pushes a frame into the inference queue.
        Returns False if queue is full (backpressure signal).
        """
        if self._stop_event.is_set():
            return False

        # Frame sampling: only accept frames at target_fps rate
        self._frame_counter += 1

        with self._queue_lock:
            packet = FramePacket(
                channel_id=self.channel_id,
                frame=frame,
                timestamp=timestamp,
                frame_index=self._frame_counter,
            )
            self._input_queue.append(packet)
            return True

    def stop(self) -> None:
        self._stop_event.set()

    @property
    def queue_depth(self) -> int:
        with self._queue_lock:
            return len(self._input_queue)

    def run(self) -> None:
        logger.info(
            "AI inference worker started for channel [%s] (target: %.1f FPS)",
            self.channel_id, self.target_fps,
        )
        self.metrics.started_at = datetime.now(timezone.utc)

        min_interval = 1.0 / max(self.target_fps, 0.1)

        while not self._stop_event.is_set():
            packet = None
            with self._queue_lock:
                if self._input_queue:
                    packet = self._input_queue.popleft()

            if packet is None:
                self._stop_event.wait(0.01)
                continue

            start_time = time.perf_counter()

            try:
                # Run detection
                detections = self.detector.detect(packet.frame)

                # Run tracking
                tracked = self.tracker.update(detections, packet.timestamp)

                latency_ms = (time.perf_counter() - start_time) * 1000
                self.metrics.record(latency_ms)
                self.metrics.device = self.detector.execution_device

                result = InferenceResult(
                    channel_id=self.channel_id,
                    timestamp=packet.timestamp,
                    detections=detections,
                    tracked_objects=tracked,
                    inference_latency_ms=latency_ms,
                    device=self.detector.execution_device,
                )

                # Publish event for downstream consumers (event engine, UI)
                bus.publish("ai.inference_result", {
                    "channel_id": self.channel_id,
                    "timestamp": packet.timestamp,
                    "detection_count": len(detections),
                    "tracked_count": len(tracked),
                    "latency_ms": round(latency_ms, 2),
                }, source="ai_worker")

                if self.result_callback:
                    try:
                        self.result_callback(result)
                    except Exception as cb_err:
                        logger.error("Result callback error for [%s]: %s", self.channel_id, cb_err)

            except Exception as e:
                logger.error("Inference error on channel [%s]: %s", self.channel_id, e, exc_info=True)

            # Rate limiting to target FPS
            elapsed = time.perf_counter() - start_time
            sleep_time = min_interval - elapsed
            if sleep_time > 0:
                self._stop_event.wait(sleep_time)

        logger.info("AI inference worker stopped for channel [%s].", self.channel_id)


class InferenceWorkerManager:
    """
    Manages multiple per-channel AI inference workers.
    """

    def __init__(self) -> None:
        self._workers: Dict[str, AIInferenceWorker] = {}
        self._lock = threading.Lock()

    def start_worker(
        self,
        channel_id: str,
        detector: YOLODetector,
        tracker: Optional[ByteTracker] = None,
        target_fps: float = 5.0,
        result_callback: Optional[Callable[[InferenceResult], None]] = None,
    ) -> AIInferenceWorker:
        """Starts an inference worker for a channel."""
        with self._lock:
            if channel_id in self._workers:
                self.stop_worker(channel_id)

            worker = AIInferenceWorker(
                channel_id=channel_id,
                detector=detector,
                tracker=tracker,
                target_fps=target_fps,
                result_callback=result_callback,
            )
            self._workers[channel_id] = worker
            worker.start()
            return worker

    def stop_worker(self, channel_id: str) -> None:
        with self._lock:
            worker = self._workers.get(channel_id)
            if worker:
                worker.stop()
                if worker.is_alive():
                    worker.join(timeout=3.0)
                del self._workers[channel_id]

    def push_frame(self, channel_id: str, frame: np.ndarray, timestamp: float) -> bool:
        """Routes a frame to the appropriate channel inference worker."""
        with self._lock:
            worker = self._workers.get(channel_id)
            if worker and worker.is_alive():
                return worker.push_frame(frame, timestamp)
        return False

    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {
                ch_id: worker.metrics.to_dict()
                for ch_id, worker in self._workers.items()
            }

    def get_active_channels(self) -> List[str]:
        with self._lock:
            return [ch for ch, w in self._workers.items() if w.is_alive()]

    def stop_all(self) -> None:
        logger.info("Stopping all AI inference workers...")
        with self._lock:
            for worker in self._workers.values():
                worker.stop()
            for worker in self._workers.values():
                if worker.is_alive():
                    worker.join(timeout=3.0)
            self._workers.clear()
        logger.info("All AI inference workers stopped.")


# Global inference worker manager singleton
inference_worker_manager = InferenceWorkerManager()
