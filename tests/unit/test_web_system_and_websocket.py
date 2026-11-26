"""
Unit and Integration Tests for System Telemetry, LAN Subnet Security, and WebSockets (Milestone W2).
"""

import pytest
import time
from starlette.testclient import TestClient
from web.api.app import app
from web.server import start_lan_server_thread, stop_lan_server
from web.config import web_settings
from core.security.user_service import user_service
from core.events.event_bus import bus

client = TestClient(app, base_url="http://127.0.0.1:8000")


@pytest.fixture(scope="module")
def admin_token():
    ok, s, _ = user_service.authenticate("web_test_admin", "Admin#Password2026")
    assert ok is True
    return s["session_token"]


def test_health_endpoint():
    """Tests public health check endpoint."""
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["data"]["status"] == "HEALTHY"
    assert data["data"]["database"] == "CONNECTED"
    assert data["data"]["event_bus"] == "ACTIVE"


def test_readiness_endpoint():
    """Tests readiness probe."""
    res = client.get("/api/v1/ready")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["ready"] is True
    assert data["checks"]["database"] is True


def test_system_status_endpoint(admin_token):
    """Tests system status telemetry endpoint."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/system/status", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["uptime_seconds"] >= 0
    assert data["memory_percent"] > 0
    assert "openvino_device" in data


def test_security_headers_and_correlation_id():
    """Tests security headers middleware and X-Correlation-ID presence."""
    res = client.get("/api/v1/health")
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert "X-Correlation-ID" in res.headers
    assert res.headers["X-Correlation-ID"].startswith("req-")


def test_lan_subnet_filtering_middleware():
    """
    Tests dynamic LAN subnet filter.
    Requests from public / non-LAN external socket IPs are blocked with 403 Forbidden.
    Verifies that client cannot spoof IP via headers.
    """
    # 1. Test unit logic directly on web_settings
    assert web_settings.is_ip_allowed("127.0.0.1") is True
    assert web_settings.is_ip_allowed("192.168.1.100") is True
    assert web_settings.is_ip_allowed("10.0.0.50") is True
    assert web_settings.is_ip_allowed("172.16.5.1") is True
    assert web_settings.is_ip_allowed("203.0.113.88") is False  # Public IP blocked!
    assert web_settings.is_ip_allowed("8.8.8.8") is False

    # 2. Test middleware blocking non-LAN socket peer
    external_client = TestClient(app, client=("203.0.113.88", 54321))
    res = external_client.get("/api/v1/health")
    assert res.status_code == 403
    data = res.json()
    assert data["success"] is False
    assert data["error"]["code"] == "ACCESS_DENIED_LAN_ONLY"

    # 3. Test that sending spoofed X-Forwarded-For header does NOT bypass LAN restriction
    spoofed_client = TestClient(app, client=("203.0.113.88", 54321))
    res_spoof = spoofed_client.get("/api/v1/health", headers={"X-Forwarded-For": "192.168.1.100"})
    assert res_spoof.status_code == 403
    assert res_spoof.json()["error"]["code"] == "ACCESS_DENIED_LAN_ONLY"


def test_websocket_authentication_and_eventbus_bridge(admin_token):
    """
    Tests WebSocket handshake authentication, ping/pong, and EventBus message reception.
    """
    # 1. Reject unauthenticated WebSocket
    with pytest.raises(Exception):
        with client.websocket_connect("/api/v1/ws/events") as ws:
            pass

    # 2. Authenticate with valid token
    with client.websocket_connect(f"/api/v1/ws/events?token={admin_token}") as ws:
        # Initial greeting
        greeting = ws.receive_json()
        assert greeting["event"] == "connected"
        assert greeting["username"] == "web_test_admin"

        # Test ping / pong
        ws.send_text("ping")
        assert ws.receive_text() == "pong"

        # Dispatch an EventBus event from background thread
        bus.publish("alarm.test_event", {"alert": "perimeter_breached", "id": 999})

        # WebSocket client receives the EventBus broadcast!
        received_event = ws.receive_json()
        assert received_event["topic"] == "alarm.test_event"
        assert received_event["data"]["alert"] == "perimeter_breached"
        assert received_event["data"]["id"] == 999


def test_lan_server_thread_lifecycle():
    """Tests non-blocking background server thread startup and graceful shutdown."""
    # Launch server on alternate test port
    test_port = 8448
    thread = start_lan_server_thread(host="127.0.0.1", port=test_port)
    assert thread.is_alive() is True

    # Allow startup
    time.sleep(1.0)

    # Stop server
    stop_lan_server()
    assert thread.is_alive() is False
