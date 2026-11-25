"""
Unit tests for Network Performance Monitoring (Phase 11.1 - F-019, Release 1.1.1-alpha).
Tests RFC 3550 interarrival jitter, mean latency variation distinction,
measured vs estimated bandwidth attribution, and telemetry congestion isolation.
"""

import time
import pytest
from engines.network_engine.monitor import (
    TelemetrySample,
    DeviceTelemetryHistory,
    NetworkPerformanceMonitor,
)


def test_device_telemetry_history_metrics():
    """Test standard latency, packet loss, bandwidth, and mean latency variation calculation."""
    hist = DeviceTelemetryHistory("192.168.1.50", maxlen=10)

    # Add 4 samples with varying latencies: 10, 20, 15, 25
    hist.add_sample(TelemetrySample(
        timestamp=time.time(),
        ip_address="192.168.1.50",
        latency_ms=10.0,
        packet_loss_pct=0.0,
        bandwidth_bps=4_000_000.0,
        is_online=True,
        bandwidth_source="RTP_STREAM_COUNTER",
        measured_bandwidth_bps=4_000_000.0,
    ))
    hist.add_sample(TelemetrySample(
        timestamp=time.time(),
        ip_address="192.168.1.50",
        latency_ms=20.0,
        packet_loss_pct=0.0,
        bandwidth_bps=4_200_000.0,
        is_online=True,
        bandwidth_source="RTP_STREAM_COUNTER",
        measured_bandwidth_bps=4_200_000.0,
    ))
    hist.add_sample(TelemetrySample(
        timestamp=time.time(),
        ip_address="192.168.1.50",
        latency_ms=15.0,
        packet_loss_pct=0.0,
        bandwidth_bps=4_100_000.0,
        is_online=True,
        bandwidth_source="RTP_STREAM_COUNTER",
        measured_bandwidth_bps=4_100_000.0,
    ))
    hist.add_sample(TelemetrySample(
        timestamp=time.time(),
        ip_address="192.168.1.50",
        latency_ms=25.0,
        packet_loss_pct=0.0,
        bandwidth_bps=4_300_000.0,
        is_online=True,
        bandwidth_source="RTP_STREAM_COUNTER",
        measured_bandwidth_bps=4_300_000.0,
    ))

    assert hist.get_average_latency() == pytest.approx(17.5, 0.1)
    # Mean latency variation: (|20-10| + |15-20| + |25-15|) / 3 = 25 / 3 = 8.33 ms
    assert hist.get_mean_latency_variation_ms() == pytest.approx(8.33, 0.1)
    # Without RTP timestamps, RFC 3550 jitter must be None
    assert hist.get_rfc3550_jitter_ms() is None
    # Backward compatible jitter returns mean latency variation when RTP timing absent
    assert hist.get_jitter_ms() == pytest.approx(8.33, 0.1)
    assert hist.get_average_packet_loss() == 0.0
    assert hist.get_current_measured_bandwidth_mbps() == 4.3
    assert hist.get_uptime_percentage() == 100.0
    assert hist.is_congested() is False


def test_rfc3550_smoothed_interarrival_jitter():
    """Verify true RFC 3550 Section 6.4.1 interarrival jitter algorithm with RTP timestamps."""
    hist = DeviceTelemetryHistory("192.168.1.55", maxlen=10)

    # Standard 90 kHz video clock
    # Packet 1: arrival = 0.000, rtp_timestamp = 0
    hist.record_rtp_packet(arrival_time=1.000, rtp_timestamp=0, clock_rate=90000)
    assert hist.get_rfc3550_jitter_ms() is None  # Needs at least 2 packets

    # Packet 2: send time was +0.0333s (3000 ticks at 90kHz), arrival was +0.040s (1.040)
    # D(1, 2) = (1.040 - 3000/90000) - (1.000 - 0) = (1.040 - 0.03333) - 1.000 = 0.00667s (6.67ms)
    # J = 0 + (0.00667 - 0) / 16 = 0.0004167s (0.42 ms)
    hist.record_rtp_packet(arrival_time=1.040, rtp_timestamp=3000, clock_rate=90000)
    jitter = hist.get_rfc3550_jitter_ms()
    assert jitter is not None
    assert jitter > 0.0
    assert hist.get_jitter_ms() == jitter


def test_measured_vs_estimated_bandwidth():
    """Verify distinction between real measured byte counters and estimated stream bitrate."""
    hist = DeviceTelemetryHistory("192.168.1.75", maxlen=10)

    # 1. Estimated sample
    hist.add_sample(TelemetrySample(
        timestamp=time.time(),
        ip_address="192.168.1.75",
        latency_ms=10.0,
        packet_loss_pct=0.0,
        bandwidth_bps=4_194_304.0,
        estimated_bitrate_bps=4_194_304.0,
        measured_bandwidth_bps=0.0,
        bandwidth_source="ESTIMATED",
    ))
    assert hist.get_current_measured_bandwidth_mbps() == 0.0
    assert hist.get_current_bandwidth_mbps() == pytest.approx(4.19, 0.05)
    sample = hist.get_latest_sample()
    assert sample is not None
    assert sample.bandwidth_source == "ESTIMATED"

    # 2. Measured counter sample
    hist.add_sample(TelemetrySample(
        timestamp=time.time(),
        ip_address="192.168.1.75",
        latency_ms=12.0,
        packet_loss_pct=0.0,
        bandwidth_bps=6_200_000.0,
        measured_bandwidth_bps=6_200_000.0,
        estimated_bitrate_bps=4_194_304.0,
        bandwidth_source="RTP_STREAM_COUNTER",
    ))
    assert hist.get_current_measured_bandwidth_mbps() == pytest.approx(6.2, 0.05)
    assert hist.get_latest_sample().bandwidth_source == "RTP_STREAM_COUNTER"


def test_congestion_detection():
    """Verify network congestion detection under high latency and packet loss conditions."""
    hist = DeviceTelemetryHistory("192.168.1.60", maxlen=10)

    # Normal
    hist.add_sample(TelemetrySample(timestamp=time.time(), ip_address="192.168.1.60", latency_ms=20.0, packet_loss_pct=0.0, bandwidth_bps=4_000_000.0))
    hist.add_sample(TelemetrySample(timestamp=time.time(), ip_address="192.168.1.60", latency_ms=30.0, packet_loss_pct=0.0, bandwidth_bps=4_000_000.0))
    assert hist.is_congested(latency_threshold_ms=150.0) is False

    # Congestion spike (latencies > 150ms and packet loss > 5%)
    hist.add_sample(TelemetrySample(timestamp=time.time(), ip_address="192.168.1.60", latency_ms=180.0, packet_loss_pct=8.0, bandwidth_bps=1_000_000.0))
    hist.add_sample(TelemetrySample(timestamp=time.time(), ip_address="192.168.1.60", latency_ms=210.0, packet_loss_pct=10.0, bandwidth_bps=1_000_000.0))
    hist.add_sample(TelemetrySample(timestamp=time.time(), ip_address="192.168.1.60", latency_ms=195.0, packet_loss_pct=6.0, bandwidth_bps=1_000_000.0))

    assert hist.is_congested(latency_threshold_ms=150.0, loss_threshold_pct=5.0) is True


def test_chart_data_conversion():
    """Test data formatting for UI visualization charts."""
    hist = DeviceTelemetryHistory("192.168.1.70", maxlen=5)
    hist.add_sample(TelemetrySample(timestamp=100.0, ip_address="192.168.1.70", latency_ms=12.0, packet_loss_pct=0.0, bandwidth_bps=2_000_000.0))
    hist.add_sample(TelemetrySample(timestamp=101.0, ip_address="192.168.1.70", latency_ms=14.0, packet_loss_pct=1.0, bandwidth_bps=2_500_000.0))

    data = hist.to_chart_data()
    assert len(data["timestamps"]) == 2
    assert data["latencies"] == [12.0, 14.0]
    assert data["bandwidths_mbps"] == [2.0, 2.5]
    assert data["packet_loss"] == [0.0, 1.0]


def test_network_performance_monitor_registration():
    """Verify device registration, telemetry callbacks, and unregistration in the monitor."""
    monitor = NetworkPerformanceMonitor(poll_interval_sec=5.0)
    h1 = monitor.register_device("192.168.1.10")
    assert h1.ip_address == "192.168.1.10"
    assert monitor.get_device_history("192.168.1.10") is not None

    received_callbacks = []
    def on_telemetry(ip, sample, congested):
        received_callbacks.append((ip, sample.latency_ms, congested))

    monitor.add_telemetry_callback(on_telemetry)
    monitor.record_external_sample(
        "192.168.1.10",
        latency_ms=35.0,
        bandwidth_bps=5_000_000.0,
        bandwidth_source="INTERFACE_COUNTER",
        measured_bandwidth_bps=5_000_000.0,
    )

    assert len(received_callbacks) == 1
    assert received_callbacks[0][0] == "192.168.1.10"
    assert received_callbacks[0][1] == 35.0
    assert received_callbacks[0][2] is False

    monitor.unregister_device("192.168.1.10")
    assert monitor.get_device_history("192.168.1.10") is None
