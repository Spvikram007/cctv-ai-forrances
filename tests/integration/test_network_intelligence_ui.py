"""
Integration tests for Network Intelligence Workspace UI (Phase 11.1 - F-019, Release 1.1.1-alpha).
Tests PySide6 workspace tabs, device filtering, telemetry columns (8 columns),
security audit CVE findings columns (9 columns), and scanner confirmation prompts.
"""

from unittest.mock import patch
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from engines.network_engine.scanner import DiscoveredNetworkDevice, DeviceType, DeviceStatus
from engines.network_engine.security_audit import SecurityAuditReport, CVEFinding, CVEConfidence
from modules.network_intelligence.topology_view import InteractiveTopologyCanvas
from modules.network_intelligence.network_workspace_widget import NetworkIntelligenceWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def test_topology_canvas_initialization(qapp):
    canvas = InteractiveTopologyCanvas()
    assert canvas is not None

    devs = [
        DiscoveredNetworkDevice(
            ip_address="192.168.1.10",
            vendor="Hikvision",
            device_type=DeviceType.IP_CAMERA,
            status=DeviceStatus.ONLINE,
            latency_ms=12.0,
        ),
        DiscoveredNetworkDevice(
            ip_address="192.168.1.100",
            vendor="Dahua Technology",
            device_type=DeviceType.NVR,
            status=DeviceStatus.ONLINE,
            latency_ms=8.0,
        ),
    ]

    canvas.set_devices(devs, gateway_ip="192.168.1.1")
    assert len(canvas.nodes) == 3  # Gateway + 2 devices
    assert "192.168.1.1" in canvas.nodes
    assert "192.168.1.10" in canvas.nodes
    assert "192.168.1.100" in canvas.nodes


def test_network_intelligence_widget_lifecycle(qapp):
    with patch("PySide6.QtWidgets.QMessageBox.information"), \
         patch("PySide6.QtWidgets.QMessageBox.warning"), \
         patch("PySide6.QtWidgets.QMessageBox.critical"), \
         patch("PySide6.QtWidgets.QMessageBox.question"):
        widget = NetworkIntelligenceWidget()
        assert widget is not None
        assert widget.tabs.count() == 5

        # Check tab titles
        tab_titles = [widget.tabs.tabText(i) for i in range(widget.tabs.count())]
        assert "Device Inventory" in tab_titles
        assert "Topology Map" in tab_titles
        assert "Performance & Bandwidth" in tab_titles
        assert "CCTV Diagnostics & Faults" in tab_titles
        assert "Security & Vulnerability Audit" in tab_titles

        # Verify updated column counts for Phase 11.1
        # Telemetry: 8 columns (IP, Avg Latency, Mean Latency Var, Packet Loss, Measured BW, Bitrate Source, Uptime, Congestion)
        assert widget.tbl_telemetry.columnCount() == 8
        # Security: 9 columns (Host IP, CVE ID, CVSS, Vendor Profile, Confidence, Advisory Date, Details, Mitigation, Source URL)
        assert widget.tbl_cve.columnCount() == 9

        # Test device update in UI
        mock_devs = [
            DiscoveredNetworkDevice(
                ip_address="192.168.1.20",
                mac_address="44:19:B6:00:11:22",
                vendor="Hikvision",
                device_type=DeviceType.IP_CAMERA,
                status=DeviceStatus.ONLINE,
                latency_ms=18.5,
                open_ports=[554, 80],
            ),
            DiscoveredNetworkDevice(
                ip_address="192.168.1.21",
                mac_address="3C:EF:8C:33:44:55",
                vendor="Dahua Technology",
                device_type=DeviceType.NVR,
                status=DeviceStatus.ONLINE,
                latency_ms=9.0,
                open_ports=[37777, 80, 554],
            ),
        ]

        widget._update_devices(mock_devs)
        assert widget.tbl_inventory.rowCount() == 2
        assert widget.tbl_inventory.item(0, 0).text() == "192.168.1.20"
        assert widget.tbl_inventory.item(1, 0).text() == "192.168.1.21"

        # Verify Telemetry table was populated with 8 columns
        assert widget.tbl_telemetry.rowCount() == 2
        assert widget.tbl_telemetry.item(0, 0).text() == "192.168.1.20"
        assert widget.tbl_telemetry.item(0, 5).text() == "ESTIMATED"

        # Test Inventory Filter
        widget.txt_filter.setText("Hikvision")
        widget._apply_inventory_filter()
        assert widget.tbl_inventory.isRowHidden(0) is False
        assert widget.tbl_inventory.isRowHidden(1) is True

        # Test Security Audit population with 9 columns and confidence badges
        mock_finding = CVEFinding(
            cve_id="CVE-2021-36260",
            vendor="Hikvision",
            model="DS-2CD2042WD-I",
            affected_versions="< V5.5.800",
            detected_version="V5.4.5",
            cvss_score=9.8,
            confidence=CVEConfidence.CONFIRMED_VULNERABLE.value,
            description="Command injection in Hikvision web server",
            mitigation="Upgrade to V5.5.800",
            source_url="https://nvd.nist.gov/vuln/detail/CVE-2021-36260",
            advisory_date="2021-09-22",
            status_note="CONFIRMED_VULNERABLE",
        )
        mock_sec_rep = SecurityAuditReport(
            ip_address="192.168.1.20",
            vendor="Hikvision",
            model="DS-2CD2042WD-I",
            firmware_version="V5.4.5",
            security_score=40,
            grade="F",
            cve_findings=[mock_finding],
        )
        widget._on_security_finished([mock_sec_rep])
        assert widget.tbl_cve.rowCount() == 1
        assert widget.tbl_cve.item(0, 0).text() == "192.168.1.20"
        assert widget.tbl_cve.item(0, 1).text() == "CVE-2021-36260"
        assert widget.tbl_cve.item(0, 4).text() == "CONFIRMED_VULNERABLE"
        assert widget.tbl_cve.item(0, 5).text() == "2021-09-22"
        assert widget.tbl_cve.item(0, 8).text() == "https://nvd.nist.gov/vuln/detail/CVE-2021-36260"

        # Clean close
        widget.monitor.stop()
        widget.close()
