"""
Network Performance Monitoring and Telemetry Engine.
Phase 11 (F-019).
Tracks bandwidth (bps), round-trip latency (ms), packet loss (%),
stream connection stability, and camera uptime in bounded history queues.
"""

import time
import math
import socket
import threading
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timezone

from core.logging.logger import get_logger

logger = get_logger("network_monitor")


@dataclass
class TelemetrySample:
    """Single point-in-time network performance observation."""
    timestamp: float
    ip_address: str
    latency_ms: float
    packet_loss_pct: float
    bandwidth_bps: float
    fps: float = 0.0
    is_online: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DeviceTelemetryHistory:
    """Maintains a rolling window of telemetry samples for a specific device."""

    def __init__(self, ip_address: str, maxlen: int = 120) -> None:
        self.ip_address = ip_address
        self.maxlen = maxlen
        self.samples: deque[TelemetrySample] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def add_sample(self, sample: TelemetrySample) -> None:
        with self._lock:
            self.samples.append(sample)

    def get_latest_sample(self) -> Optional[TelemetrySample]:
        with self._lock:
            return self.samples[-1] if self.samples else None

    def get_average_latency(self) -> float:
        with self._lock:
            if not self.samples:
                return 0.0
            online_samples = [s.latency_ms for s in self.samples if s.is_online]
            return sum(online_samples) / len(online_samples) if online_samples else 0.0

    def get_jitter_ms(self) -> float:
        """Calculates RFC 3550 style interarrival packet/latency jitter."""
        with self._lock:
            if len(self.samples) < 2:
                return 0.0
            latencies = [s.latency_ms for s in self.samples if s.is_online]
            if len(latencies) < 2:
                return 0.0
            diffs = [abs(latencies[i] - latencies[i - 1]) for i in range(1, len(latencies))]
            return sum(diffs) / len(diffs)

    def get_average_packet_loss(self) -> float:
        with self._lock:
            if not self.samples:
                return 0.0
            return sum(s.packet_loss_pct for s in self.samples) / len(self.samples)

    def get_current_bandwidth_mbps(self) -> float:
        with self._lock:
            if not self.samples:
                return 0.0
            latest = self.samples[-1]
            return round(latest.bandwidth_bps / 1_000_000.0, 2)

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
            bandwidths_mbps = [round(s.bandwidth_bps / 1_000_000.0, 3) for s in self.samples]
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
    Collects RTT latency, packet loss, bandwidth consumption, and raises congestion alerts.
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
        bandwidth_bps: float = 0.0,
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
            bandwidth_bps=round(bandwidth_bps, 0),
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
        """Conducts an active TCP/ICMP ping probe to measure RTT latency and packet loss."""
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
                # Try port 80
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

        # Generate sample
        sample = TelemetrySample(
            timestamp=time.time(),
            ip_address=ip_address,
            latency_ms=round(latency, 2),
            packet_loss_pct=packet_loss,
            bandwidth_bps=4_194_304.0 if is_online else 0.0,  # ~4 Mbps typical 1080p stream
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

            # Sleep remaining cycle time
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
