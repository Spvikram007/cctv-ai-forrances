"""
Unit tests for Automated Fault Isolation Engine (Phase 11 - F-019).
"""

import pytest
from engines.network_engine.fault_analyzer import (
    AutomatedFaultAnalyzer,
    FaultType,
    FaultAnalysisReport,
    FaultIsolationMatrix,
)


def test_gateway_offline_isolation():
    analyzer = AutomatedFaultAnalyzer()
    reports = analyzer.analyze_network_state(
        gateway_ip="192.168.1.1",
        gateway_online=False,
        devices=[{"ip_address": "192.168.1.10", "is_online": False}],
    )

    types = [r.fault_type for r in reports]
    assert FaultType.NETWORK_DISCONNECTION in types
    gw_rep = next(r for r in reports if r.fault_type == FaultType.NETWORK_DISCONNECTION)
    assert gw_rep.severity == "CRITICAL"
    assert "192.168.1.1" in gw_rep.affected_ips
    assert gw_rep.requires_operator_approval is True


def test_nvr_failure_isolation():
    analyzer = AutomatedFaultAnalyzer()
    nvr_mappings = {
        "192.168.1.100": ["192.168.1.101", "192.168.1.102", "192.168.1.103"]
    }
    devices = [
        {"ip_address": "192.168.1.100", "is_online": False, "device_type": "NVR"},
        {"ip_address": "192.168.1.101", "is_online": False, "device_type": "IP_CAMERA"},
        {"ip_address": "192.168.1.102", "is_online": False, "device_type": "IP_CAMERA"},
        {"ip_address": "192.168.1.103", "is_online": False, "device_type": "IP_CAMERA"},
    ]

    reports = analyzer.analyze_network_state(
        gateway_ip="192.168.1.1",
        gateway_online=True,
        devices=devices,
        nvr_mappings=nvr_mappings,
    )

    types = [r.fault_type for r in reports]
    assert FaultType.NVR_FAILURE in types
    nvr_rep = next(r for r in reports if r.fault_type == FaultType.NVR_FAILURE)
    assert nvr_rep.severity == "CRITICAL"
    assert "192.168.1.100" in nvr_rep.affected_ips


def test_isolated_camera_hardware_failure():
    analyzer = AutomatedFaultAnalyzer()
    # 9 devices online, 1 offline
    devices = [{"ip_address": f"192.168.1.{i}", "is_online": True} for i in range(10, 19)]
    devices.append({"ip_address": "192.168.1.20", "is_online": False, "device_type": "IP_CAMERA"})

    reports = analyzer.analyze_network_state(
        gateway_ip="192.168.1.1",
        gateway_online=True,
        devices=devices,
    )

    types = [r.fault_type for r in reports]
    assert FaultType.CAMERA_HARDWARE_FAILURE in types
    cam_rep = next(r for r in reports if r.fault_type == FaultType.CAMERA_HARDWARE_FAILURE)
    assert cam_rep.affected_ips == ["192.168.1.20"]


def test_bandwidth_congestion_fault():
    analyzer = AutomatedFaultAnalyzer()
    devices = [
        {"ip_address": "192.168.1.10", "is_online": True, "latency_ms": 185.0, "packet_loss_pct": 8.0},
        {"ip_address": "192.168.1.11", "is_online": True, "latency_ms": 220.0, "packet_loss_pct": 12.0},
        {"ip_address": "192.168.1.12", "is_online": True, "latency_ms": 190.0, "packet_loss_pct": 7.0},
    ]

    reports = analyzer.analyze_network_state(
        gateway_ip="192.168.1.1",
        gateway_online=True,
        devices=devices,
    )

    types = [r.fault_type for r in reports]
    assert FaultType.BANDWIDTH_CONGESTION in types
    cong_rep = next(r for r in reports if r.fault_type == FaultType.BANDWIDTH_CONGESTION)
    assert len(cong_rep.affected_ips) == 3


def test_healthy_state_no_fault():
    analyzer = AutomatedFaultAnalyzer()
    devices = [
        {"ip_address": "192.168.1.10", "is_online": True, "latency_ms": 15.0, "packet_loss_pct": 0.0},
        {"ip_address": "192.168.1.11", "is_online": True, "latency_ms": 22.0, "packet_loss_pct": 0.0},
    ]

    reports = analyzer.analyze_network_state(
        gateway_ip="192.168.1.1",
        gateway_online=True,
        devices=devices,
    )

    assert len(reports) == 1
    assert reports[0].fault_type == FaultType.NO_FAULT
