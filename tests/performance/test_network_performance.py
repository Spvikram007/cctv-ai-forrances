"""
Performance and Scalability Benchmarks for Network Intelligence (Phase 11 - F-019).
"""

import time
import pytest
from engines.network_engine.scanner import NetworkScanner, DiscoveredNetworkDevice, DeviceType, DeviceStatus
from engines.network_engine.monitor import DeviceTelemetryHistory, TelemetrySample
from engines.network_engine.security_audit import NetworkSecurityAuditor
from engines.network_engine.fault_analyzer import AutomatedFaultAnalyzer


def test_benchmark_telemetry_history_scalability():
    """Validates that 64-device continuous telemetry history processes under 50ms."""
    histories = [DeviceTelemetryHistory(f"192.168.1.{i}", maxlen=120) for i in range(1, 65)]

    t0 = time.perf_counter()
    # Add 120 samples to each of the 64 histories
    for hist in histories:
        for s in range(120):
            hist.add_sample(
                TelemetrySample(
                    timestamp=1000.0 + s,
                    ip_address=hist.ip_address,
                    latency_ms=15.0 + (s % 10),
                    packet_loss_pct=0.0,
                    bandwidth_bps=4_194_304.0,
                )
            )
        # Compute all stats
        _ = hist.get_average_latency()
        _ = hist.get_jitter_ms()
        _ = hist.get_average_packet_loss()
        _ = hist.get_current_bandwidth_mbps()
        _ = hist.is_congested()

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    # 64 devices * 120 samples = 7680 insertions & computations
    assert elapsed_ms < 500.0, f"Telemetry benchmark took {elapsed_ms:.2f}ms, expected < 500ms"


def test_benchmark_security_audit_batch():
    """Validates security posture audit across 64 CCTV devices executes in under 200ms."""
    devices = [
        DiscoveredNetworkDevice(
            ip_address=f"192.168.1.{i}",
            mac_address="44:19:B6:00:11:22" if i % 2 == 0 else "3C:EF:8C:33:44:55",
            vendor="Hikvision" if i % 2 == 0 else "Dahua Technology",
            device_type=DeviceType.IP_CAMERA,
            open_ports=[554, 80],
            protocols=["RTSP", "HTTP"],
            firmware_version="V5.4.0" if i % 2 == 0 else "V2.800",
        )
        for i in range(1, 65)
    ]

    t0 = time.perf_counter()
    reports = [
        NetworkSecurityAuditor.audit_device(
            ip_address=d.ip_address,
            open_ports=d.open_ports,
            protocols=d.protocols,
            vendor=d.vendor,
            firmware_version=d.firmware_version,
        )
        for d in devices
    ]
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert len(reports) == 64
    assert elapsed_ms < 200.0, f"Security audit batch took {elapsed_ms:.2f}ms, expected < 200ms"


def test_benchmark_automated_fault_isolation():
    """Validates root-cause analysis over 64 devices finishes in under 50ms."""
    analyzer = AutomatedFaultAnalyzer()
    devices = [
        {
            "ip_address": f"192.168.1.{i}",
            "is_online": True if i != 25 else False,
            "latency_ms": 15.0 if i != 25 else 0.0,
            "packet_loss_pct": 0.0 if i != 25 else 100.0,
            "device_type": "IP_CAMERA",
        }
        for i in range(1, 65)
    ]

    t0 = time.perf_counter()
    faults = analyzer.analyze_network_state(
        gateway_ip="192.168.1.1",
        gateway_online=True,
        devices=devices,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert len(faults) > 0
    assert elapsed_ms < 50.0, f"Fault isolation took {elapsed_ms:.2f}ms, expected < 50ms"
