"""
Integration tests for Network Intelligence Workspace UI (Phase 11 - F-019).
"""

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from engines.network_engine.scanner import DiscoveredNetworkDevice, DeviceType, DeviceStatus
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

    # Test Inventory Filter
    widget.txt_filter.setText("Hikvision")
    widget._apply_inventory_filter()
    assert widget.tbl_inventory.isRowHidden(0) is False
    assert widget.tbl_inventory.isRowHidden(1) is True

    # Clean close
    widget.monitor.stop()
    widget.close()
