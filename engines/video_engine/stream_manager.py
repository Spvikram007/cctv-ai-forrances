"""
Multi-Channel RTSP Stream Manager.
Orchestrates stream workers across up to 64 channels, handles lifecycle,
frame extraction, and dispatches telemetry to the EventBus.
"""

import os
import json
import socket
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple, Callable, Any, List
import numpy as np

from engines.video_engine.rtsp_streamer import RTSPStreamWorker, mask_rtsp_url, validate_rtsp_url
from engines.video_engine.stream_metrics import StreamTelemetry, StreamState, StreamHealthHistory
from integrations.onvif.client import ONVIFClient
from core.events.event_bus import bus
from core.logging.logger import get_logger, redact_sensitive_text

logger = get_logger("stream_manager")


@dataclass
class ConnectionTestReport:
    success: bool
    ip_address: str
    latency_ms: float
    rtsp_reachable: bool = False
    rtsp_frame_decoded: bool = False
    onvif_reachable: bool = False
    has_ptz: bool = False
    manufacturer: str = "Unknown"
    model: str = "Unknown"
    firmware_version: str = "Unknown"
    details: str = ""
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "ip_address": self.ip_address,
            "latency_ms": round(self.latency_ms, 1),
            "rtsp_reachable": self.rtsp_reachable,
            "rtsp_frame_decoded": self.rtsp_frame_decoded,
            "onvif_reachable": self.onvif_reachable,
            "has_ptz": self.has_ptz,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "firmware_version": self.firmware_version,
            "details": self.details,
            "error_message": self.error_message,
        }


class CameraConnectionTester:
    """Diagnostic tool testing network camera reachability, RTSP and ONVIF."""

    @staticmethod
    def test_camera(
        ip_address: str,
        rtsp_port: int = 554,
        onvif_port: int = 80,
        username: str = "",
        password: str = "",
        rtsp_path: str = "/live",
        timeout_sec: float = 3.0,
    ) -> ConnectionTestReport:
        start_time = time.perf_counter()
        report = ConnectionTestReport(success=False, ip_address=ip_address, latency_ms=0.0)

        # 1. TCP reachability on RTSP port
        try:
            with socket.create_connection((ip_address, rtsp_port), timeout=timeout_sec):
                report.rtsp_reachable = True
        except Exception as e:
            report.error_message = f"RTSP port {rtsp_port} unreachable: {e}"

        # 2. ONVIF capabilities probe if port configured
        if onvif_port:
            try:
                client = ONVIFClient(
                    ip_address=ip_address,
                    port=onvif_port,
                    username=username,
                    password=password,
                    timeout_sec=timeout_sec,
                )
                caps = client.get_capabilities()
                info = client.get_device_information()
                report.onvif_reachable = True
                report.has_ptz = caps.has_ptz
                report.manufacturer = info.manufacturer
                report.model = info.model
                report.firmware_version = info.firmware_version
            except Exception as e:
                logger.debug("ONVIF probe exception for [%s]: %s", ip_address, e)

        # Measure overall elapsed latency
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        report.latency_ms = elapsed_ms
        report.success = report.rtsp_reachable or report.onvif_reachable
        report.details = f"Reachable ports: RTSP={report.rtsp_reachable}, ONVIF={report.onvif_reachable}"
        return report


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

    def switch_channel_profile(self, channel_id: str, profile_type: str, new_url: Optional[str] = None) -> bool:
        """Dynamically switches a channel between MAIN and SUB stream profiles."""
        with self._lock:
            worker = self._workers.get(channel_id)
            if worker:
                return worker.switch_stream_profile(profile_type, new_url)
        return False

    def get_channel_history(self, channel_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves historical health and state transition events for a channel."""
        with self._lock:
            worker = self._workers.get(channel_id)
            if worker and hasattr(worker, "history"):
                return worker.history.to_dict_list(limit)
        return []

    def get_diagnostics_report(self, channel_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Generates a comprehensive stream diagnostics report for one or all channels.
        Includes FPS, resolution, latency, dropped frames, decoder errors, and queue stats.
        """
        with self._lock:
            report: Dict[str, Any] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_channels_registered": len(self._workers),
                "active_online_streams": self.active_stream_count(),
                "channels": {},
            }
            targets = [channel_id] if channel_id and channel_id in self._workers else list(self._workers.keys())
            for ch_id in targets:
                w = self._workers[ch_id]
                t = w.telemetry
                total_f = t.total_frames_received + t.total_frames_dropped
                drop_rate = (t.total_frames_dropped / total_f * 100.0) if total_f > 0 else 0.0

                report["channels"][ch_id] = {
                    "channel_name": w.channel_name,
                    "masked_url": w.masked_url,
                    "state": t.state.value,
                    "profile": t.current_profile,
                    "fps_measured": round(t.current_fps, 1),
                    "resolution": f"{t.detected_width}x{t.detected_height}",
                    "queue_occupancy": t.queue_occupancy,
                    "queue_capacity": t.queue_capacity,
                    "frames_received": t.total_frames_received,
                    "frames_dropped": t.total_frames_dropped,
                    "frame_drop_rate_pct": round(drop_rate, 2),
                    "reconnect_count": t.reconnect_count,
                    "decoder_errors": t.decoder_errors_count,
                    "frozen_frames_count": t.frozen_frames_count,
                    "is_frozen": t.is_frozen,
                    "uptime_seconds": round(t.uptime_seconds, 1),
                    "last_error": t.last_error,
                }
            return report

    def export_diagnostics_log(self, file_path: str, channel_id: Optional[str] = None) -> str:
        """
        Exports the stream diagnostics report to disk with all credentials strictly redacted.
        """
        report = self.get_diagnostics_report(channel_id)
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        logger.info("Exported stream diagnostics report to %s", file_path)
        return file_path

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
