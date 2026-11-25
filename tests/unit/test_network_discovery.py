"""
Unit tests for Network Discovery and Subnet Scanner (Phase 11 - F-019).
"""

import pytest
import ipaddress
from unittest.mock import patch, MagicMock

from engines.network_engine.scanner import (
    DeviceType,
    DeviceStatus,
    DiscoveredNetworkDevice,
    NetworkScanner,
    validate_cidr_block,
    lookup_vendor_by_mac,
    get_default_gateway,
    get_local_subnets,
)


def test_validate_cidr_block_valid():
    net = validate_cidr_block("192.168.1.0/24")
    assert isinstance(net, ipaddress.IPv4Network)
    assert net.num_addresses == 256

    net2 = validate_cidr_block("10.0.0.0/28")
    assert net2.num_addresses == 16


def test_validate_cidr_block_rejections():
    # Empty
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_cidr_block("")

    # Invalid format
    with pytest.raises(ValueError, match="Invalid IPv4 CIDR"):
        validate_cidr_block("not_an_ip")

    # Global internet scan 0.0.0.0/0
    with pytest.raises(ValueError, match="0.0.0.0/0 global Internet scan is strictly prohibited"):
        validate_cidr_block("0.0.0.0/0")

    # Multicast
    with pytest.raises(ValueError, match="Multicast network"):
        validate_cidr_block("224.0.0.0/24")

    # Loopback
    with pytest.raises(ValueError, match="Loopback network"):
        validate_cidr_block("127.0.0.0/8")

    # Exceeding max hosts
    with pytest.raises(ValueError, match="exceeding single-pass limit"):
        validate_cidr_block("192.168.1.0/24", max_hosts=100)


def test_lookup_vendor_by_mac():
    # Hikvision
    assert lookup_vendor_by_mac("44:19:B6:11:22:33") == "Hikvision"
    assert lookup_vendor_by_mac("44-19-b6-aa-bb-cc") == "Hikvision"

    # Dahua
    assert lookup_vendor_by_mac("3C:EF:8C:00:11:22") == "Dahua Technology"

    # CP PLUS
    assert lookup_vendor_by_mac("D8:B0:4C:12:34:56") == "CP PLUS"

    # Axis
    assert lookup_vendor_by_mac("00:40:8C:AB:CD:EF") == "Axis Communications"

    # Cisco
    assert lookup_vendor_by_mac("00:00:0C:01:02:03") == "Cisco Systems"

    # Unknown
    assert lookup_vendor_by_mac("02:00:00:00:00:01") == "Unknown Vendor"
    assert lookup_vendor_by_mac("Unknown") == "Unknown Vendor"


def test_classify_device():
    # Gateway
    dt_gw = NetworkScanner._classify_device(
        ip_str="192.168.1.1",
        mac="00:00:0C:01:02:03",
        vendor="Cisco Systems",
        open_ports=[80, 53],
        protocols=["HTTP", "DNS"],
        default_gateway="192.168.1.1",
    )
    assert dt_gw == DeviceType.GATEWAY

    # Camera via RTSP port
    dt_cam = NetworkScanner._classify_device(
        ip_str="192.168.1.50",
        mac="44:19:B6:11:22:33",
        vendor="Hikvision",
        open_ports=[554, 80],
        protocols=["RTSP", "HTTP"],
    )
    assert dt_cam == DeviceType.IP_CAMERA

    # NVR via port 37777
    dt_nvr = NetworkScanner._classify_device(
        ip_str="192.168.1.100",
        mac="3C:EF:8C:00:11:22",
        vendor="Dahua Technology",
        open_ports=[37777, 80, 554],
        protocols=["DAHUA-RPC", "HTTP", "RTSP"],
    )
    assert dt_nvr == DeviceType.NVR

    # Managed Switch
    dt_sw = NetworkScanner._classify_device(
        ip_str="192.168.1.2",
        mac="00:00:0C:01:02:03",
        vendor="Cisco Systems",
        open_ports=[80, 22],
        protocols=["HTTP", "SSH"],
    )
    assert dt_sw == DeviceType.SWITCH

    # Host
    dt_host = NetworkScanner._classify_device(
        ip_str="192.168.1.15",
        mac="00:1B:21:01:02:03",
        vendor="Intel",
        open_ports=[22],
        protocols=["SSH"],
    )
    assert dt_host == DeviceType.HOST


def test_detect_duplicate_ips():
    d1 = DiscoveredNetworkDevice(ip_address="192.168.1.50", mac_address="44:19:B6:11:22:33")
    d2 = DiscoveredNetworkDevice(ip_address="192.168.1.51", mac_address="44:19:B6:11:22:33")
    devices = [d1, d2]

    NetworkScanner._detect_duplicate_ips(devices, {})
    assert d1.is_duplicate_ip is True
    assert d2.is_duplicate_ip is True
    assert len(d1.conflicting_macs) > 0


def test_network_scanner_mocked_scan():
    scanner = NetworkScanner(max_threads=4, socket_timeout=0.1)

    # Mock probe_host
    def mock_probe(ip_str, *args, **kwargs):
        if ip_str == "192.168.10.1":
            return DiscoveredNetworkDevice(
                ip_address=ip_str,
                mac_address="00:00:0C:11:22:33",
                vendor="Cisco Systems",
                device_type=DeviceType.GATEWAY,
                open_ports=[80],
                latency_ms=2.0,
            )
        elif ip_str == "192.168.10.10":
            return DiscoveredNetworkDevice(
                ip_address=ip_str,
                mac_address="44:19:B6:AA:BB:CC",
                vendor="Hikvision",
                device_type=DeviceType.IP_CAMERA,
                open_ports=[554, 8000],
                latency_ms=12.5,
            )
        return None

    progress_events = []
    def on_prog(done, total, found):
        progress_events.append((done, total, len(found)))

    with patch.object(scanner, "probe_host", side_effect=mock_probe):
        results = scanner.scan_network("192.168.10.0/28", progress_callback=on_prog)

    assert len(results) == 2
    assert results[0].ip_address == "192.168.10.1"
    assert results[0].device_type == DeviceType.GATEWAY
    assert results[1].ip_address == "192.168.10.10"
    assert results[1].device_type == DeviceType.IP_CAMERA


def test_compute_scan_scope_boundaries_and_batching():
    """Verify compute_scan_scope calculates usable hosts, boundaries, and safety batches."""
    from engines.network_engine.scanner import compute_scan_scope

    # 1. Standard /24
    scope_24 = compute_scan_scope("192.168.1.0/24")
    assert scope_24.total_hosts == 256
    assert scope_24.first_usable_ip == "192.168.1.1"
    assert scope_24.last_usable_ip == "192.168.1.254"
    assert scope_24.batch_count == 1

    # 2. Scope /22 (1024 addresses -> 1 batch of 1024)
    scope_22 = compute_scan_scope("10.0.0.0/22")
    assert scope_22.total_hosts == 1024
    assert scope_22.first_usable_ip == "10.0.0.1"
    assert scope_22.last_usable_ip == "10.0.3.254"
    assert scope_22.batch_count == 1
    assert scope_22.requires_operator_confirmation is True

    # 3. Large scope /20 (4096 addresses -> 4 batches of 1024)
    scope_20 = compute_scan_scope("10.10.0.0/20")
    assert scope_20.total_hosts == 4096
    assert scope_20.batch_count == 4
    assert scope_20.requires_operator_confirmation is True


def test_record_scan_audit_logging(tmp_path):
    """Verify record_scan_audit writes immutable structured audit entries."""
    import os
    import json
    from engines.network_engine.scanner import compute_scan_scope, record_scan_audit

    audit_file = str(tmp_path / "test_scan_audit.jsonl")
    scope = compute_scan_scope("192.168.50.0/24")
    record_scan_audit(
        scope=scope,
        discovered_count=5,
        operator="test_operator",
        audit_log_path=audit_file,
    )

    assert os.path.exists(audit_file)
    with open(audit_file, "r", encoding="utf-8") as f:
        line = f.readline().strip()
        record = json.loads(line)

    assert record["cidr"] == "192.168.50.0/24"
    assert record["total_hosts"] == 256
    assert record["discovered_devices"] == 5
    assert record["operator"] == "test_operator"
    assert "timestamp" in record
