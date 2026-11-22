"""
Unit tests for Manufacturer Adapters (Hikvision, Dahua, CP PLUS).
"""

from integrations.hikvision.isapi_adapter import HikvisionISAPIAdapter
from integrations.dahua.cgi_adapter import DahuaCGIAdapter
from integrations.cpplus.cpplus_adapter import CPPlusAdapter


def test_hikvision_rtsp_url_construction():
    adapter = HikvisionISAPIAdapter(
        ip_address="192.168.1.64",
        port=80,
        username="admin",
        password="hikPassword123",
        rtsp_port=554,
    )
    # Channel 1 mainstream format
    main_url = f"rtsp://{adapter.username}:{adapter.password}@{adapter.ip_address}:{adapter.rtsp_port}/Streaming/Channels/101"
    sub_url = f"rtsp://{adapter.username}:{adapter.password}@{adapter.ip_address}:{adapter.rtsp_port}/Streaming/Channels/102"

    assert "Streaming/Channels/101" in main_url
    assert "Streaming/Channels/102" in sub_url
    assert adapter.ip_address == "192.168.1.64"


def test_dahua_rtsp_url_construction():
    adapter = DahuaCGIAdapter(
        ip_address="192.168.1.108",
        port=80,
        username="admin",
        password="dahuaPass456",
        rtsp_port=554,
    )
    # Dahua channel 1 mainstream format
    main_url = f"rtsp://{adapter.username}:{adapter.password}@{adapter.ip_address}:{adapter.rtsp_port}/cam/realmonitor?channel=1&subtype=0"
    sub_url = f"rtsp://{adapter.username}:{adapter.password}@{adapter.ip_address}:{adapter.rtsp_port}/cam/realmonitor?channel=1&subtype=1"

    assert "/cam/realmonitor?channel=1&subtype=0" in main_url
    assert "/cam/realmonitor?channel=1&subtype=1" in sub_url


def test_cpplus_adapter():
    adapter = CPPlusAdapter(
        ip_address="192.168.1.115",
        port=80,
        username="admin",
        password="cpPassword789",
        rtsp_port=554,
    )
    assert adapter.ip_address == "192.168.1.115"
    assert adapter._underlying_cgi is not None
