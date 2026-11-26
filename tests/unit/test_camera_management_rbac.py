"""
Unit and Integration Tests for Camera & Device Management RBAC (Phase 15 - Milestone W2/W4).
Strict verification of all 10 authorization scenarios:
  1. Administrator can register a camera.
  2. CCTV Operator can retrieve the camera list.
  3. Supervisor can retrieve the camera list.
  4. Investigator can retrieve the camera list.
  5. Read-Only Viewer can retrieve the camera list.
  6. Users without live:view receive HTTP 403.
  7. Users without camera:manage cannot register or delete cameras.
  8. Unauthenticated requests receive HTTP 401.
  9. Duplicate camera registration returns HTTP 409.
  10. Offline cameras remain visible.
  11. RTSP URL credentials strictly masked (zero plaintext passwords in API).
"""

import pytest
import uuid
from starlette.testclient import TestClient
from web.api.app import app
from core.security.user_service import user_service
from core.security.crypto import credential_vault, mask_rtsp_url
from database.database_manager import db_manager
from database.models.devices import Device, DeviceChannel, StreamProfile, DeviceCredential
from database.models.users import Role, AuditLog

client = TestClient(app, base_url="http://127.0.0.1:8000")


@pytest.fixture(scope="module", autouse=True)
def setup_role_users():
    """Seeds test accounts for distinct surveillance roles."""
    roles: dict[str, str] = {}
    with db_manager.get_session() as session:
        roles = {r.name: r.id for r in session.query(Role).all()}

    # 1. Admin (camera:manage + live:view)
    user_service.create_user("web_test_admin", "Admin#Password2026", "Admin", roles["Super Administrator"])
    # 2. CCTV Operator (live:view, no camera:manage)
    user_service.create_user("web_test_cctv_op", "Op#Password2026", "CCTV Operator", roles["CCTV Operator"])
    # 3. Supervisor (live:view, no camera:manage)
    user_service.create_user("web_test_supervisor", "Super#Password2026", "Supervisor", roles["Supervisor"])
    # 4. Investigator (live:view, no camera:manage)
    user_service.create_user("web_test_investigator", "Invest#Password2026", "Investigator", roles["Investigator"])
    # 5. Read-Only Viewer (live:view, no camera:manage)
    user_service.create_user("web_test_viewer", "Viewer#Password2026", "Viewer", roles["Read-Only Viewer"])
    # 6. Auditor (no live:view, no camera:manage)
    user_service.create_user("web_test_auditor", "Audit#Password2026", "Auditor", roles["Auditor"])


@pytest.fixture(scope="module")
def admin_token():
    ok, s, _ = user_service.authenticate("web_test_admin", "Admin#Password2026")
    assert ok is True and s is not None
    return s["session_token"]


@pytest.fixture(scope="module")
def cctv_op_token():
    ok, s, _ = user_service.authenticate("web_test_cctv_op", "Op#Password2026")
    assert ok is True and s is not None
    return s["session_token"]


@pytest.fixture(scope="module")
def supervisor_token():
    ok, s, _ = user_service.authenticate("web_test_supervisor", "Super#Password2026")
    assert ok is True and s is not None
    return s["session_token"]


@pytest.fixture(scope="module")
def investigator_token():
    ok, s, _ = user_service.authenticate("web_test_investigator", "Invest#Password2026")
    assert ok is True and s is not None
    return s["session_token"]


@pytest.fixture(scope="module")
def viewer_token():
    ok, s, _ = user_service.authenticate("web_test_viewer", "Viewer#Password2026")
    assert ok is True and s is not None
    return s["session_token"]


@pytest.fixture(scope="module")
def auditor_token():
    ok, s, _ = user_service.authenticate("web_test_auditor", "Audit#Password2026")
    assert ok is True and s is not None
    return s["session_token"]


# 1. Administrator can register a camera
def test_post_camera_with_admin_permission(admin_token):
    u = uuid.uuid4().int
    unique_ip = f"10.{(u >> 16) % 250 + 1}.{(u >> 8) % 250 + 1}.{u % 250 + 1}"
    unique_port = 10000 + (u % 50000)
    payload = {
        "name": f"Entrance Security Dome {u % 10000}",
        "ip_address": unique_ip,
        "port": unique_port,
        "rtsp_port": 554,
        "onvif_port": 80,
        "manufacturer": "HIKVISION",
        "model": "DS-2CD2143G2-I",
        "rtsp_path": "/Streaming/Channels/101",
        "username": "admin",
        "password": "Camera#SecurePass2026"
    }

    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.post("/api/v1/cameras", json=payload, headers=headers)
    assert res.status_code == 201

    data = res.json()
    assert data["success"] is True
    cam = data["data"]
    assert cam["name"] == payload["name"]
    assert cam["ip_address"] == unique_ip
    assert cam["is_online"] is True
    assert cam["id"] is not None
    assert cam["channel_id"] is not None

    # CRITICAL: Credentials never leaked
    assert "password" not in cam
    assert "encrypted_password" not in cam
    assert "Camera#SecurePass2026" not in res.text

    # Verify database persistence
    with db_manager.get_session() as session:
        dev = session.query(Device).filter_by(id=cam["id"]).first()
        assert dev is not None
        assert dev.ip_address == unique_ip
        assert dev.is_deleted is False

        cred = session.query(DeviceCredential).filter_by(device_id=dev.id).first()
        assert cred is not None
        assert cred.encrypted_password != "Camera#SecurePass2026"
        assert credential_vault.decrypt_password(cred.encrypted_password) == "Camera#SecurePass2026"

        audit = session.query(AuditLog).filter_by(action="CAMERA_REGISTERED", resource_id=dev.id).first()
        assert audit is not None
        assert audit.status == "SUCCESS"


# 2. CCTV Operator can retrieve the camera list
def test_cctv_operator_can_list_cameras(cctv_op_token):
    headers = {"Authorization": f"Bearer {cctv_op_token}"}
    res = client.get("/api/v1/cameras", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)
    assert len(data["data"]) > 0


# 3. Supervisor can retrieve the camera list
def test_supervisor_can_list_cameras(supervisor_token):
    headers = {"Authorization": f"Bearer {supervisor_token}"}
    res = client.get("/api/v1/cameras", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)
    assert len(data["data"]) > 0


# 4. Investigator can retrieve the camera list
def test_investigator_can_list_cameras(investigator_token):
    headers = {"Authorization": f"Bearer {investigator_token}"}
    res = client.get("/api/v1/cameras", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)
    assert len(data["data"]) > 0


# 5. Read-Only Viewer can retrieve the camera list
def test_viewer_can_list_cameras(viewer_token):
    headers = {"Authorization": f"Bearer {viewer_token}"}
    res = client.get("/api/v1/cameras", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)
    assert len(data["data"]) > 0


# 6. Users without live:view receive HTTP 403
def test_user_without_live_view_receives_403(auditor_token):
    headers = {"Authorization": f"Bearer {auditor_token}"}
    res = client.get("/api/v1/cameras", headers=headers)
    assert res.status_code == 403
    data = res.json()
    assert data["success"] is False
    assert data["error"]["code"] == "ACCESS_DENIED"
    assert "live:view" in data["error"]["message"]


# 7. Users without camera:manage cannot register or delete cameras
def test_operator_and_supervisor_cannot_register_or_delete(cctv_op_token, supervisor_token, admin_token):
    u = uuid.uuid4().int
    unique_ip = f"10.{(u >> 16) % 250 + 1}.{(u >> 8) % 250 + 1}.{u % 250 + 1}"
    unique_port = 10000 + (u % 50000)
    payload = {
        "name": f"Operator Cam {u % 10000}",
        "ip_address": unique_ip,
        "port": unique_port,
        "rtsp_port": 554,
        "manufacturer": "DAHUA"
    }

    # Operator register -> 403
    res_op = client.post("/api/v1/cameras", json=payload, headers={"Authorization": f"Bearer {cctv_op_token}"})
    assert res_op.status_code == 403
    assert res_op.json()["error"]["code"] == "ACCESS_DENIED"

    # Supervisor register -> 403
    res_sup = client.post("/api/v1/cameras", json=payload, headers={"Authorization": f"Bearer {supervisor_token}"})
    assert res_sup.status_code == 403
    assert res_sup.json()["error"]["code"] == "ACCESS_DENIED"

    # Create dummy camera as admin to test deletion denial
    res_create = client.post("/api/v1/cameras", json=payload, headers={"Authorization": f"Bearer {admin_token}"})
    assert res_create.status_code == 201
    dev_id = res_create.json()["data"]["id"]

    # Operator delete -> 403
    del_op = client.delete(f"/api/v1/cameras/{dev_id}", headers={"Authorization": f"Bearer {cctv_op_token}"})
    assert del_op.status_code == 403

    # Supervisor delete -> 403
    del_sup = client.delete(f"/api/v1/cameras/{dev_id}", headers={"Authorization": f"Bearer {supervisor_token}"})
    assert del_sup.status_code == 403


# 8. Unauthenticated requests receive HTTP 401
def test_get_cameras_unauthenticated_returns_401():
    res = client.get("/api/v1/cameras")
    assert res.status_code == 401
    data = res.json()
    assert data["success"] is False
    assert data["error"]["code"] == "UNAUTHORIZED"


# 9. Duplicate camera registration returns HTTP 409
def test_duplicate_camera_registration_returns_409(admin_token):
    u = uuid.uuid4().int
    unique_ip = f"10.{(u >> 16) % 250 + 1}.{(u >> 8) % 250 + 1}.{u % 250 + 1}"
    unique_port = 10000 + (u % 50000)
    payload = {
        "name": f"North Gate {u % 10000}",
        "ip_address": unique_ip,
        "port": unique_port,
        "rtsp_port": 554,
        "manufacturer": "CP_PLUS"
    }
    headers = {"Authorization": f"Bearer {admin_token}"}
    res1 = client.post("/api/v1/cameras", json=payload, headers=headers)
    assert res1.status_code == 201

    res2 = client.post("/api/v1/cameras", json=payload, headers=headers)
    assert res2.status_code == 409
    data = res2.json()
    assert data["success"] is False
    assert data["error"]["code"] == "DUPLICATE_CAMERA"


# 10. Offline cameras remain visible
def test_offline_cameras_remain_visible(admin_token, viewer_token):
    # Insert a standby / offline camera directly in database
    u = uuid.uuid4().int
    offline_ip = f"10.{(u >> 16) % 250 + 1}.{(u >> 8) % 250 + 1}.{u % 250 + 1}"
    offline_port = 10000 + (u % 50000)
    with db_manager.get_session() as session:
        offline_dev = Device(
            name=f"Standby Cam {u % 10000}",
            device_type="CAMERA",
            manufacturer="TEST",
            ip_address=offline_ip,
            port=offline_port,
            rtsp_port=554,
            is_online=False,
            is_deleted=False
        )
        session.add(offline_dev)
        session.flush()
        ch = DeviceChannel(device_id=offline_dev.id, channel_number=1, name="Standby Ch 1")
        session.add(ch)
        session.flush()
        prof = StreamProfile(channel_id=ch.id, profile_type="MAIN", rtsp_url=f"rtsp://{offline_ip}:554/live")
        session.add(prof)
        dev_id = offline_dev.id

    # Retrieve via API as viewer (filter by unique IP to avoid pagination limit truncation)
    headers = {"Authorization": f"Bearer {viewer_token}"}
    res = client.get(f"/api/v1/cameras?search={offline_ip}", headers=headers)
    assert res.status_code == 200
    cameras = res.json()["data"]
    matching = [c for c in cameras if c["id"] == dev_id]
    assert len(matching) == 1
    assert matching[0]["is_online"] is False
    assert matching[0]["ip_address"] == offline_ip


# 11. RTSP URL credentials strictly masked
def test_rtsp_url_credentials_masked_in_api(admin_token, viewer_token):
    # Register device with credentials embedded in stream profile
    u = uuid.uuid4().int
    sensitive_ip = f"10.{(u >> 16) % 250 + 1}.{(u >> 8) % 250 + 1}.{u % 250 + 1}"
    sensitive_port = 10000 + (u % 50000)
    with db_manager.get_session() as session:
        dev = Device(
            name=f"Sensitive RTSP Cam {u % 10000}",
            device_type="CAMERA",
            manufacturer="TEST",
            ip_address=sensitive_ip,
            port=sensitive_port,
            rtsp_port=554,
            is_online=True,
            is_deleted=False
        )
        session.add(dev)
        session.flush()
        ch = DeviceChannel(device_id=dev.id, channel_number=1, name="Sensitive Ch 1")
        session.add(ch)
        session.flush()
        prof = StreamProfile(
            channel_id=ch.id,
            profile_type="MAIN",
            rtsp_url=f"rtsp://admin:superSecretPass999@{sensitive_ip}:554/live"
        )
        session.add(prof)
        dev_id = dev.id

    headers = {"Authorization": f"Bearer {viewer_token}"}
    res = client.get(f"/api/v1/cameras/{dev_id}", headers=headers)
    assert res.status_code == 200
    cam = res.json()["data"]
    # Password must NEVER appear
    assert "superSecretPass999" not in res.text
    assert cam["rtsp_url"] == f"rtsp://***:***@{sensitive_ip}:554/live"
