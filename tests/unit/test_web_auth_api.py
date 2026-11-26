"""
Unit and Integration Tests for FastAPI Web Authentication & Session API (Milestone W2).
"""

import pytest
from starlette.testclient import TestClient
from web.api.app import app
from database.database_manager import db_manager
from database.models.users import User, Role
from core.security.user_service import user_service

client = TestClient(app, base_url="http://127.0.0.1:8000")


@pytest.fixture(scope="module", autouse=True)
def setup_test_users():
    """Ensures test operator and admin exist."""
    with db_manager.get_session() as session:
        admin_role = session.query(Role).filter_by(name="Super Administrator").first()
        viewer_role = session.query(Role).filter_by(name="Read-Only Viewer").first()
        a_id = admin_role.id
        v_id = viewer_role.id

    # Create test web admin
    user_service.create_user(
        username="web_test_admin",
        password="Admin#Password2026",
        full_name="Web Test Admin",
        role_id=a_id
    )

    # Create test web viewer
    user_service.create_user(
        username="web_test_viewer",
        password="Viewer#Password2026",
        full_name="Web Test Viewer",
        role_id=v_id
    )


def test_login_success_and_cookie():
    """Tests successful login, session token issuance, and HttpOnly cookie generation."""
    res = client.post("/api/v1/auth/login", json={
        "username": "web_test_admin",
        "password": "Admin#Password2026",
        "client_name": "PyTest Browser"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "data" in data
    assert data["data"]["username"] == "web_test_admin"
    assert "session_token" in data["data"]
    assert "cctv_session" in res.cookies
    assert "X-Correlation-ID" in res.headers


def test_login_invalid_password():
    """Tests failed login returns 401 with standard error envelope."""
    res = client.post("/api/v1/auth/login", json={
        "username": "web_test_admin",
        "password": "WrongPassword123!",
        "client_name": "PyTest Browser"
    })
    assert res.status_code == 401
    data = res.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INVALID_CREDENTIALS"


def test_get_current_user_profile():
    """Tests /api/v1/auth/me returns operator profile, role, and fine-grained permissions."""
    # First login
    login_res = client.post("/api/v1/auth/login", json={
        "username": "web_test_admin",
        "password": "Admin#Password2026"
    })
    token = login_res.json()["data"]["session_token"]

    # Test /me using Authorization header
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()["data"]
    assert me_data["username"] == "web_test_admin"
    assert me_data["role_name"] == "Super Administrator"
    assert len(me_data["permissions"]) == 22
    assert "user:manage" in me_data["permissions"]
    assert "system:config" in me_data["permissions"]

    # Test /me using cookie
    client.cookies.set("cctv_session", token)
    me_cookie_res = client.get("/api/v1/auth/me")
    assert me_cookie_res.status_code == 200
    assert me_cookie_res.json()["data"]["username"] == "web_test_admin"


def test_session_refresh_and_logout():
    """Tests session refresh and subsequent logout revoking the token."""
    login_res = client.post("/api/v1/auth/login", json={
        "username": "web_test_admin",
        "password": "Admin#Password2026"
    })
    token = login_res.json()["data"]["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Refresh
    ref_res = client.post("/api/v1/auth/refresh", headers=headers)
    assert ref_res.status_code == 200
    assert ref_res.json()["data"]["status"] == "refreshed"

    # Logout
    logout_res = client.post("/api/v1/auth/logout", headers=headers)
    assert logout_res.status_code == 200

    # Subsequent /me with revoked token returns 401
    unauth_res = client.get("/api/v1/auth/me", headers=headers)
    assert unauth_res.status_code == 401


def test_list_and_revoke_sessions():
    """Tests active session listing and remote session revocation."""
    login_res = client.post("/api/v1/auth/login", json={
        "username": "web_test_admin",
        "password": "Admin#Password2026"
    })
    token = login_res.json()["data"]["session_token"]
    sess_id = login_res.json()["data"]["session_id"]
    headers = {"Authorization": f"Bearer {token}"}

    # List sessions
    sess_list_res = client.get("/api/v1/auth/sessions", headers=headers)
    assert sess_list_res.status_code == 200
    sessions = sess_list_res.json()["data"]
    assert len(sessions) >= 1
    found = any(s["session_id"] == sess_id for s in sessions)
    assert found is True

    # Revoke session
    del_res = client.delete(f"/api/v1/auth/sessions/{sess_id}", headers=headers)
    assert del_res.status_code == 200
