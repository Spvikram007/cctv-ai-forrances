"""
Unit tests for Network Performance Monitoring (Phase 11 - F-019).
"""

import time
import pytest
from engines.network_engine.monitor import (
    TelemetrySample,
    DeviceTelemetryHistory,
    NetworkPerformanceMonitor,
)


def test_device_telemetry_history_metrics():
    hist = DeviceTelemetryHistory("192.168.1.50", maxlen=10)

    # Add 5 samples
    hist.add_sample(TelemetrySample(timestamp=time.time(), ip_address="192.168.1.50", latency_ms=10.0, packet_loss_pct=0.0, bandwidth_bps=4_000_000.0, is_online=True))
    hist.add_sample(TelemetrySample(timestamp=time.time(), ip_address="192.168.1.50", latency_ms=20.0, packet_loss_pct=0.0, bandwidth_bps=4_200_000.0, is_online=True))
    hist.add_sample(TelemetrySample(timestamp=time.time(), ip_address="192.168.1.50", latency_ms=15.0, packet_loss_pct=0.0, bandwidth_bps=4_100_000.0, is_online=True))
    hist.add_sample(TelemetrySample(timestamp=time.time(), ip_address="192.168.1.50", latency_ms=25.0, packet_loss_pct=0.0, bandwidth_bps=4_300_000.0, is_online=True))

    assert hist.get_average_latency() == pytest.approx(17.5, 0.1)
    assert hist.get_jitter_ms() == pytest.approx(8.33, 0.1)
    assert hist.get_average_packet_loss() == 0.0
    assert hist.get_current_bandwidth_mbps() == 4.3
    assert hist.get_uptime_percentage() == 100.0
    assert hist.is_congested() is False


def test_congestion_detection():
    hist = DeviceTelemetryHistory("192.168.1.60", maxlen=10)

    # Normal
    hist.add_sample(TelemetrySample(timestamp=time.time(), ip_address="192.168.1.60", latency_ms=20.0, packet_loss_pct=0.0, bandwidth_bps=4_000_000.0))
    hist.add_sample(TelemetrySample(timestamp=time.time(), ip_address="192.168.1.60", latency_ms=30.0, packet_loss_pct=0.0, bandwidth_bps=4_000_000.0))
    assert hist.is_congested(latency_threshold_ms=150.0) is False

    # Congestion spike (latencies > 150ms)
    hist.add_sample(TelemetrySample(timestamp=time.time(), ip_address="192.168.1.60", latency_ms=180.0, packet_loss_pct=8.0, bandwidth_bps=1_000_000.0))
    hist.add_sample(TelemetrySample(timestamp=time.time(), ip_address="192.168.1.60", latency_ms=210.0, packet_loss_pct=10.0, bandwidth_bps=1_000_000.0))
    hist.add_sample(TelemetrySample(timestamp=time.time(), ip_address="192.168.1.60", latency_ms=195.0, packet_loss_pct=6.0, bandwidth_bps=1_000_000.0))

    assert hist.is_congested(latency_threshold_ms=150.0, loss_threshold_pct=5.0) is True


def test_chart_data_conversion():
    hist = DeviceTelemetryHistory("192.168.1.70", maxlen=5)
    hist.add_sample(TelemetrySample(timestamp=100.0, ip_address="192.168.1.70", latency_ms=12.0, packet_loss_pct=0.0, bandwidth_bps=2_000_000.0))
    hist.add_sample(TelemetrySample(timestamp=101.0, ip_address="192.168.1.70", latency_ms=14.0, packet_loss_pct=1.0, bandwidth_bps=2_500_000.0))

    data = hist.to_chart_data()
    assert len(data["timestamps"]) == 2
    assert data["latencies"] == [12.0, 14.0]
    assert data["bandwidths_mbps"] == [2.0, 2.5]
    assert data["packet_loss"] == [0.0, 1.0]


def test_network_performance_monitor_registration():
    monitor = NetworkPerformanceMonitor(poll_interval_sec=5.0)
    h1 = monitor.register_device("192.168.1.10")
    assert h1.ip_address == "192.168.1.10"
    assert monitor.get_device_history("192.168.1.10") is not None

    received_callbacks = []
    def on_telemetry(ip, sample, congested):
        received_callbacks.append((ip, sample.latency_ms, congested))

    monitor.add_telemetry_callback(on_telemetry)
    monitor.record_external_sample("192.168.1.10", latency_ms=35.0, bandwidth_bps=5_000_000.0)

    assert len(received_callbacks) == 1
    assert received_callbacks[0][0] == "192.168.1.10"
    assert received_callbacks[0][1] == 35.0
    assert received_callbacks[0][2] is False

    monitor.unregister_device("192.168.1.10")
    assert monitor.get_device_history("192.168.1.10") is None
