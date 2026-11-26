"""
Unit and Integration Tests for Workspace API Endpoints (Milestone W3.3).
Covers:
  1. WebSocket Single-Use Ticket and Cookie Authentication.
  2. Alarm listing, summary, and acknowledgment workflow.
  3. Video Analytics rules and inference status.
  4. Storage pools and volume disk telemetry.
  5. Audit log query and cryptographic integrity verification.
  6. User and role administration.
  7. Historical playback recordings metadata.
  8. System platform settings.
"""

import pytest
import uuid
from starlette.testclient import TestClient
from web.api.app import app
from web.config import web_settings
from database.database_manager import db_manager
from database.models.users import User, Role
from database.models.alarms import Alarm
from database.models.analytics import AnalyticsRule
from database.models.recordings import StorageVolume, Recording
from core.security.user_service import user_service
from core.events.event_bus import bus

client = TestClient(app, base_url="http://127.0.0.1:8000")


@pytest.fixture(scope="module", autouse=True)
def setup_workspace_test_data():
    """Seeds test accounts and sample domain objects in the isolated test DB."""
    roles: dict[str, str] = {}
    with db_manager.get_session() as session:
        roles = {r.name: r.id for r in session.query(Role).all()}

    # Create admin user
    user_service.create_user("ws_test_admin", "Admin#Pass2026", "WS Admin", roles["Super Administrator"])
    # Create operator user
    user_service.create_user("ws_test_op", "Op#Pass2026", "WS Operator", roles["CCTV Operator"])

    # Seed an Alarm
    with db_manager.get_session() as session:
        alarm = Alarm(
            title="Perimeter Breach Zone 1",
            category="SECURITY",
            source_subsystem="AI_ANALYTICS",
            severity="CRITICAL",
            status="NEW",
            description="Person crossing tripwire"
        )
        session.add(alarm)

        # Seed an Analytics Rule
        rule = AnalyticsRule(
            channel_id="ch_test_1",
            name="North Gate Tripwire",
            rule_type="TRIPWIRE",
            severity="CRITICAL",
            confidence_threshold=0.85,
            is_active=True
        )
        session.add(rule)

        # Seed a Storage Volume
        vol = StorageVolume(
            name="Hot Pool Volume 1",
            mount_path="storage",
            is_active=True,
            is_default=True
        )
        session.add(vol)


@pytest.fixture(scope="module")
def admin_token():
    ok, s, _ = user_service.authenticate("ws_test_admin", "Admin#Pass2026")
    assert ok is True and s is not None
    return s["session_token"]


@pytest.fixture(scope="module")
def op_token():
    ok, s, _ = user_service.authenticate("ws_test_op", "Op#Pass2026")
    assert ok is True and s is not None
    return s["session_token"]


def test_websocket_ticket_issuance_and_consumption(admin_token):
    """Verifies single-use WebSocket ticket issuance and immediate consumption."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.post("/api/v1/auth/ws-ticket", headers=headers)
    assert res.status_code == 200
    ticket = res.json()["data"]["ticket"]
    assert ticket is not None

    # Connect with ticket query parameter
    with client.websocket_connect(f"/api/v1/ws/events?ticket={ticket}") as ws:
        msg = ws.receive_json()
        assert msg["event"] == "connected"
        assert msg["username"] == "ws_test_admin"

    # Re-using the same ticket must be rejected (single-use guarantee)
    with pytest.raises(Exception):
        with client.websocket_connect(f"/api/v1/ws/events?ticket={ticket}") as ws:
            pass


def test_websocket_cookie_authentication(admin_token):
    """Verifies browser cookie authentication without any token in the URL query string."""
    cookies = {web_settings.session_cookie_name: admin_token}
    with client.websocket_connect("/api/v1/ws/events", cookies=cookies) as ws:
        msg = ws.receive_json()
        assert msg["event"] == "connected"
        assert msg["username"] == "ws_test_admin"


def test_alarms_api_workflow(admin_token):
    """Verifies alarm listing, summary counters, and acknowledgment."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Summary
    res_sum = client.get("/api/v1/alarms/summary", headers=headers)
    assert res_sum.status_code == 200
    data_sum = res_sum.json()["data"]
    assert data_sum["total"] >= 1
    assert data_sum["critical"] >= 1

    # List
    res_list = client.get("/api/v1/alarms?status=NEW", headers=headers)
    assert res_list.status_code == 200
    alarms = res_list.json()["data"]
    assert len(alarms) >= 1
    alarm_id = alarms[0]["id"]

    # Acknowledge
    res_ack = client.post(f"/api/v1/alarms/{alarm_id}/acknowledge", headers=headers)
    assert res_ack.status_code == 200
    assert res_ack.json()["data"]["status"] == "ACKNOWLEDGED"


def test_analytics_api(admin_token):
    """Verifies analytics rules and hardware inference status."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    res_rules = client.get("/api/v1/analytics/rules", headers=headers)
    assert res_rules.status_code == 200
    assert len(res_rules.json()["data"]) >= 1

    res_status = client.get("/api/v1/analytics/status", headers=headers)
    assert res_status.status_code == 200
    assert res_status.json()["data"]["hardware_tier"] == "INTEL_GPU_OPENVINO"


def test_storage_api(admin_token, op_token):
    """Verifies storage pools and RBAC protection (operator lacks storage:manage)."""
    # Operator -> 403
    res_op = client.get("/api/v1/storage/pools", headers={"Authorization": f"Bearer {op_token}"})
    assert res_op.status_code == 403

    # Admin -> 200
    res_admin = client.get("/api/v1/storage/pools", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 200
    assert isinstance(res_admin.json()["data"], list)


def test_reports_and_audit_integrity_api(admin_token):
    """Verifies audit log listing and live cryptographic verification."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    res_logs = client.get("/api/v1/reports/audit-logs", headers=headers)
    assert res_logs.status_code == 200
    assert isinstance(res_logs.json()["data"], list)

    res_verify = client.get("/api/v1/reports/audit-integrity", headers=headers)
    assert res_verify.status_code == 200
    assert res_verify.json()["data"]["is_valid"] is True


def test_users_and_roles_api(admin_token, op_token):
    """Verifies user/role listing and RBAC enforcement."""
    # Operator -> 403
    res_op = client.get("/api/v1/users", headers={"Authorization": f"Bearer {op_token}"})
    assert res_op.status_code == 403

    # Admin -> 200
    res_users = client.get("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_users.status_code == 200
    assert len(res_users.json()["data"]) >= 2

    res_roles = client.get("/api/v1/roles", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_roles.status_code == 200
    assert len(res_roles.json()["data"]) >= 6


def test_playback_recordings_api(admin_token):
    """Verifies recording metadata indexing endpoint."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/playback/recordings", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json()["data"], list)


def test_system_settings_api(admin_token, op_token):
    """Verifies settings configuration endpoint and RBAC."""
    # Operator lacks system:config -> 403
    res_op = client.get("/api/v1/system/settings", headers={"Authorization": f"Bearer {op_token}"})
    assert res_op.status_code == 403

    # Admin -> 200
    res_admin = client.get("/api/v1/system/settings", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 200
    assert "allowed_subnets" in res_admin.json()["data"]
