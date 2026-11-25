"""
Network Performance Monitoring and Telemetry Engine.
Phase 11.1 (F-019, Release 1.1.1-alpha).
Tracks measured bandwidth (bps), estimated bitrate (bps), round-trip latency (ms),
packet loss (%), true RFC 3550 RTP interarrival jitter, mean latency variation,
and device uptime in thread-safe bounded history queues.
"""

import time
import math
import socket
import threading
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Callable, Any, Tuple
from datetime import datetime, timezone

from core.logging.logger import get_logger

logger = get_logger("network_monitor")


@dataclass
class TelemetrySample:
    """Single point-in-time network performance observation with measured vs estimated metrics."""
    timestamp: float
    ip_address: str
    latency_ms: float
    packet_loss_pct: float
    measured_bandwidth_bps: float = 0.0
    estimated_bitrate_bps: float = 0.0
    bandwidth_source: str = "ESTIMATED"  # "RTP_STREAM_COUNTER", "INTERFACE_COUNTER", "SNMP", "ESTIMATED"
    fps: float = 0.0
    is_online: bool = True
    bandwidth_bps: float = 0.0  # Backward-compatible convenience field

    def __post_init__(self) -> None:
        if self.bandwidth_bps == 0.0:
            self.bandwidth_bps = self.measured_bandwidth_bps if self.measured_bandwidth_bps > 0.0 else self.estimated_bitrate_bps
        elif self.measured_bandwidth_bps == 0.0 and self.estimated_bitrate_bps == 0.0:
            if self.bandwidth_source == "ESTIMATED":
                self.estimated_bitrate_bps = self.bandwidth_bps
            else:
                self.measured_bandwidth_bps = self.bandwidth_bps

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DeviceTelemetryHistory:
    """Maintains a rolling window of telemetry samples with RFC 3550 jitter and bandwidth tracking."""

    def __init__(self, ip_address: str, maxlen: int = 120) -> None:
        self.ip_address = ip_address
        self.maxlen = maxlen
        self.samples: deque[TelemetrySample] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

        # RFC 3550 smoothed jitter state (interarrival packet transit time difference)
        self._rfc3550_jitter_samples: float = 0.0
        self._last_arrival_time: Optional[float] = None
        self._last_rtp_timestamp: Optional[float] = None
        self._has_rtp_timing: bool = False

    def add_sample(self, sample: TelemetrySample) -> None:
        with self._lock:
            self.samples.append(sample)

    def record_rtp_packet(
        self,
        arrival_time: float,
        rtp_timestamp: float,
        clock_rate: int = 90000,
    ) -> None:
        """
        Calculates RFC 3550 Section 6.4.1 interarrival packet jitter.
        D(i, j) = (R_j - S_j) - (R_i - S_i)
        J = J + (|D| - J) / 16
        """
        with self._lock:
            # Convert rtp_timestamp to seconds using clock_rate (standard 90kHz for video)
            send_time_sec = rtp_timestamp / float(clock_rate)
            if self._last_arrival_time is not None and self._last_rtp_timestamp is not None:
                # D(i, j) = (R_j - S_j) - (R_i - S_i)
                d = (arrival_time - send_time_sec) - (self._last_arrival_time - self._last_rtp_timestamp)
                d_abs = abs(d)
                # Smoothed jitter formula
                self._rfc3550_jitter_samples += (d_abs - self._rfc3550_jitter_samples) / 16.0
                self._has_rtp_timing = True

            self._last_arrival_time = arrival_time
            self._last_rtp_timestamp = send_time_sec

    def get_rfc3550_jitter_ms(self) -> Optional[float]:
        """Returns the true RFC 3550 smoothed interarrival jitter in milliseconds, or None if only ping available."""
        with self._lock:
            if self._has_rtp_timing:
                return round(self._rfc3550_jitter_samples * 1000.0, 2)
            return None

    def get_mean_latency_variation_ms(self) -> float:
        """
        Calculates the mean absolute difference between successive latency measurements.
        (Previously mislabeled as RFC 3550 jitter; now explicitly labeled mean latency variation).
        """
        with self._lock:
            if len(self.samples) < 2:
                return 0.0
            latencies = [s.latency_ms for s in self.samples if s.is_online]
            if len(latencies) < 2:
                return 0.0
            diffs = [abs(latencies[i] - latencies[i - 1]) for i in range(1, len(latencies))]
            return round(sum(diffs) / len(diffs), 2)

    def get_jitter_ms(self) -> float:
        """Backward-compatible alias for mean latency variation or true RFC 3550 jitter."""
        rfc_jitter = self.get_rfc3550_jitter_ms()
        if rfc_jitter is not None:
            return rfc_jitter
        return self.get_mean_latency_variation_ms()

    def get_latest_sample(self) -> Optional[TelemetrySample]:
        with self._lock:
            return self.samples[-1] if self.samples else None

    def get_average_latency(self) -> float:
        with self._lock:
            if not self.samples:
                return 0.0
            online_samples = [s.latency_ms for s in self.samples if s.is_online]
            return round(sum(online_samples) / len(online_samples), 2) if online_samples else 0.0

    def get_average_packet_loss(self) -> float:
        with self._lock:
            if not self.samples:
                return 0.0
            return round(sum(s.packet_loss_pct for s in self.samples) / len(self.samples), 2)

    def get_current_measured_bandwidth_mbps(self) -> float:
        with self._lock:
            if not self.samples:
                return 0.0
            latest = self.samples[-1]
            return round(latest.measured_bandwidth_bps / 1_000_000.0, 2)

    def get_current_estimated_bitrate_mbps(self) -> float:
        with self._lock:
            if not self.samples:
                return 0.0
            latest = self.samples[-1]
            return round(latest.estimated_bitrate_bps / 1_000_000.0, 2)

    def get_current_bandwidth_mbps(self) -> float:
        """Returns measured bandwidth if available, otherwise returns estimated bitrate."""
        with self._lock:
            if not self.samples:
                return 0.0
            latest = self.samples[-1]
            bps = latest.measured_bandwidth_bps if latest.measured_bandwidth_bps > 0.0 else latest.bandwidth_bps
            return round(bps / 1_000_000.0, 2)

    def get_uptime_percentage(self) -> float:
        with self._lock:
            if not self.samples:
                return 100.0
            online_count = sum(1 for s in self.samples if s.is_online)
            return round((online_count / len(self.samples)) * 100.0, 1)

    def is_congested(self, latency_threshold_ms: float = 150.0, loss_threshold_pct: float = 5.0) -> bool:
        """Determines if the connection is experiencing network congestion."""
        with self._lock:
            if len(self.samples) < 3:
                return False
            recent = list(self.samples)[-3:]
            recent_latency = sum(s.latency_ms for s in recent) / len(recent)
            recent_loss = sum(s.packet_loss_pct for s in recent) / len(recent)
            return recent_latency > latency_threshold_ms or recent_loss > loss_threshold_pct

    def to_chart_data(self) -> Dict[str, List[Any]]:
        """Returns arrays for rendering time-series charts in PySide6."""
        with self._lock:
            timestamps = [s.timestamp for s in self.samples]
            latencies = [s.latency_ms for s in self.samples]
            bandwidths_mbps = [round((s.measured_bandwidth_bps if s.measured_bandwidth_bps > 0 else s.bandwidth_bps) / 1_000_000.0, 3) for s in self.samples]
            packet_loss = [s.packet_loss_pct for s in self.samples]
            return {
                "timestamps": timestamps,
                "latencies": latencies,
                "bandwidths_mbps": bandwidths_mbps,
                "packet_loss": packet_loss,
            }


class NetworkPerformanceMonitor:
    """
    Continuous background telemetry monitor for network cameras and infrastructure.
    Collects measured and estimated bandwidth, RTT latency, packet loss,
    and calculates RFC 3550 interarrival jitter.
    """

    def __init__(
        self,
        poll_interval_sec: float = 2.0,
        latency_threshold_ms: float = 150.0,
        loss_threshold_pct: float = 5.0,
    ) -> None:
        self.poll_interval_sec = poll_interval_sec
        self.latency_threshold_ms = latency_threshold_ms
        self.loss_threshold_pct = loss_threshold_pct

        self._devices: Dict[str, DeviceTelemetryHistory] = {}
        self._lock = threading.RLock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: List[Callable[[str, TelemetrySample, bool], None]] = []

    def register_device(self, ip_address: str, maxlen: int = 120) -> DeviceTelemetryHistory:
        with self._lock:
            if ip_address not in self._devices:
                self._devices[ip_address] = DeviceTelemetryHistory(ip_address, maxlen=maxlen)
            return self._devices[ip_address]

    def unregister_device(self, ip_address: str) -> None:
        with self._lock:
            self._devices.pop(ip_address, None)

    def get_device_history(self, ip_address: str) -> Optional[DeviceTelemetryHistory]:
        with self._lock:
            return self._devices.get(ip_address)

    def get_all_histories(self) -> Dict[str, DeviceTelemetryHistory]:
        with self._lock:
            return dict(self._devices)

    def add_telemetry_callback(self, cb: Callable[[str, TelemetrySample, bool], None]) -> None:
        self._callbacks.append(cb)

    def record_external_sample(
        self,
        ip_address: str,
        latency_ms: float,
        measured_bandwidth_bps: float = 0.0,
        estimated_bitrate_bps: float = 0.0,
        bandwidth_bps: float = 0.0,
        bandwidth_source: str = "ESTIMATED",
        packet_loss_pct: float = 0.0,
        fps: float = 0.0,
        is_online: bool = True,
    ) -> TelemetrySample:
        """Allows external stream workers or metrics engines to inject real-time video telemetry."""
        sample = TelemetrySample(
            timestamp=time.time(),
            ip_address=ip_address,
            latency_ms=round(latency_ms, 2),
            packet_loss_pct=round(packet_loss_pct, 1),
            measured_bandwidth_bps=round(measured_bandwidth_bps, 0),
            estimated_bitrate_bps=round(estimated_bitrate_bps, 0),
            bandwidth_bps=round(bandwidth_bps if bandwidth_bps > 0 else (measured_bandwidth_bps or estimated_bitrate_bps), 0),
            bandwidth_source=bandwidth_source,
            fps=round(fps, 1),
            is_online=is_online,
        )
        history = self.register_device(ip_address)
        history.add_sample(sample)

        congested = history.is_congested(self.latency_threshold_ms, self.loss_threshold_pct)
        for cb in self._callbacks:
            try:
                cb(ip_address, sample, congested)
            except Exception as e:
                logger.debug("Telemetry callback error: %s", e)
        return sample

    def probe_single_device(self, ip_address: str, timeout_sec: float = 1.0) -> TelemetrySample:
        """
        Conducts an active probe measuring RTT latency and packet loss.
        Queries active stream worker for measured byte counters if available.
        """
        t0 = time.perf_counter()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_sec)
        is_online = False
        latency = 0.0
        packet_loss = 0.0

        # Try connecting to port 554 (RTSP) or 80 (HTTP)
        try:
            res = sock.connect_ex((ip_address, 554))
            t1 = time.perf_counter()
            if res == 0:
                is_online = True
                latency = (t1 - t0) * 1000.0
            else:
                sock.close()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout_sec)
                t0 = time.perf_counter()
                res2 = sock.connect_ex((ip_address, 80))
                t1 = time.perf_counter()
                if res2 == 0:
                    is_online = True
                    latency = (t1 - t0) * 1000.0
                else:
                    is_online = False
                    packet_loss = 100.0
        except Exception:
            is_online = False
            packet_loss = 100.0
        finally:
            sock.close()

        # Check if an active RTSP stream worker is currently running for this IP
        measured_bw = 0.0
        bw_source = "ESTIMATED"
        estimated_bw = 4_194_304.0 if is_online else 0.0

        try:
            from engines.video_engine.stream_manager import stream_manager
            with stream_manager._lock:
                for cid, worker in stream_manager._workers.items():
                    if ip_address in worker.rtsp_url:
                        # Extract metrics from worker if online
                        if hasattr(worker, "metrics") and worker.metrics:
                            kbps = worker.metrics.bitrate_kbps
                            if kbps > 0:
                                measured_bw = kbps * 1000.0
                                bw_source = "RTP_STREAM_COUNTER"
                        break
        except Exception:
            pass

        sample = TelemetrySample(
            timestamp=time.time(),
            ip_address=ip_address,
            latency_ms=round(latency, 2),
            packet_loss_pct=packet_loss,
            measured_bandwidth_bps=measured_bw,
            estimated_bitrate_bps=estimated_bw,
            bandwidth_source=bw_source,
            fps=25.0 if is_online else 0.0,
            is_online=is_online,
        )
        return sample

    def _monitor_loop(self) -> None:
        """Internal background polling loop."""
        logger.info("Network performance monitoring loop started.")
        while self._running:
            start_cycle = time.time()
            with self._lock:
                ips_to_poll = list(self._devices.keys())

            for ip in ips_to_poll:
                if not self._running:
                    break
                sample = self.probe_single_device(ip)
                history = self._devices.get(ip)
                if history:
                    history.add_sample(sample)
                    congested = history.is_congested(self.latency_threshold_ms, self.loss_threshold_pct)
                    for cb in self._callbacks:
                        try:
                            cb(ip, sample, congested)
                        except Exception as e:
                            logger.debug("Monitor callback error: %s", e)

            elapsed = time.time() - start_cycle
            sleep_time = max(0.1, self.poll_interval_sec - elapsed)
            time.sleep(sleep_time)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="NetworkMonitorThread")
        self._thread.start()
        logger.info("Network performance monitor active.")

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Network performance monitor stopped.")
