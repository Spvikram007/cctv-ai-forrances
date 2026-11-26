"""
Unit Tests for Server-Side RBAC Enforcement on FastAPI Routes (Milestone W2).
"""

import pytest
from starlette.testclient import TestClient
from web.api.app import app
from core.security.user_service import user_service

client = TestClient(app, base_url="http://127.0.0.1:8000")


@pytest.fixture(scope="module")
def auth_tokens():
    """Obtains auth tokens for admin and viewer users."""
    # Admin login
    ok_a, s_a, _ = user_service.authenticate("web_test_admin", "Admin#Password2026")
    assert ok_a is True
    admin_token = s_a["session_token"]

    # Viewer login
    ok_v, s_v, _ = user_service.authenticate("web_test_viewer", "Viewer#Password2026")
    assert ok_v is True
    viewer_token = s_v["session_token"]

    return {"admin": admin_token, "viewer": viewer_token}


def test_unauthenticated_request_rejected():
    """Unauthenticated access to any protected route must return 401 Unauthorized."""
    res = client.get("/api/v1/test/rbac/live-view")
    assert res.status_code == 401
    data = res.json()
    assert data["success"] is False
    assert data["error"]["code"] == "UNAUTHORIZED"


def test_viewer_rbac_permissions(auth_tokens):
    """Tests that a viewer can access live-view but is blocked from camera-manage, user-manage, system-config."""
    viewer_headers = {"Authorization": f"Bearer {auth_tokens['viewer']}"}

    # 1. live:view -> ALLOWED (200)
    res_live = client.get("/api/v1/test/rbac/live-view", headers=viewer_headers)
    assert res_live.status_code == 200
    assert res_live.json()["success"] is True

    # 2. camera:manage -> FORBIDDEN (403)
    res_cam = client.get("/api/v1/test/rbac/camera-manage", headers=viewer_headers)
    assert res_cam.status_code == 403
    assert res_cam.json()["error"]["code"] == "ACCESS_DENIED"

    # 3. user:manage -> FORBIDDEN (403)
    res_usr = client.get("/api/v1/test/rbac/user-manage", headers=viewer_headers)
    assert res_usr.status_code == 403
    assert res_usr.json()["error"]["code"] == "ACCESS_DENIED"

    # 4. system:config -> FORBIDDEN (403)
    res_sys = client.get("/api/v1/test/rbac/system-config", headers=viewer_headers)
    assert res_sys.status_code == 403
    assert res_sys.json()["error"]["code"] == "ACCESS_DENIED"


def test_admin_rbac_permissions(auth_tokens):
    """Tests that a Super Administrator possesses unrestricted access across all routes."""
    admin_headers = {"Authorization": f"Bearer {auth_tokens['admin']}"}

    for path in ["live-view", "camera-manage", "user-manage", "system-config"]:
        res = client.get(f"/api/v1/test/rbac/{path}", headers=admin_headers)
        assert res.status_code == 200
        assert res.json()["success"] is True
