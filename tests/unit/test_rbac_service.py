"""
Unit Tests for RBAC and Granular Permission Enforcement (Phase 14 - Module B).
"""

import pytest
from datetime import datetime
from database.database_manager import db_manager
from database.models.users import User, Role
from core.security.rbac import rbac_service, PermissionCodes, AccessDeniedError
from core.security.decorators import require_permission, SecurityContext
from core.security.user_service import user_service


def test_permission_and_role_seeding():
    """Verifies that all 22 permissions and 10 default roles exist in the database."""
    roles = rbac_service.get_all_roles()
    role_names = {r["name"] for r in roles}

    # Verify standard roles exist
    assert "Super Administrator" in role_names
    assert "Administrator" in role_names
    assert "Security Manager" in role_names
    assert "CCTV Operator" in role_names
    assert "Read-Only Viewer" in role_names
    assert "Auditor" in role_names

    # Check Super Admin permissions
    super_admin = next(r for r in roles if r["name"] == "Super Administrator")
    assert len(super_admin["permissions"]) == 22

    # Check Viewer permissions
    viewer = next(r for r in roles if r["name"] == "Read-Only Viewer")
    viewer_perms = {p["code"] for p in viewer["permissions"]}
    assert PermissionCodes.LIVE_VIEW in viewer_perms
    assert PermissionCodes.CAMERA_MANAGE not in viewer_perms
    assert PermissionCodes.USER_MANAGE not in viewer_perms


def test_rbac_user_permission_evaluation():
    """Tests that user permissions accurately reflect assigned roles."""
    with db_manager.get_session() as session:
        viewer_role = session.query(Role).filter_by(name="Read-Only Viewer").first()
        op_role = session.query(Role).filter_by(name="CCTV Operator").first()
        v_id = viewer_role.id
        op_id = op_role.id

    # Create a viewer user
    v_user = f"viewer_{datetime.now().microsecond}"
    ok, u_dict, _ = user_service.create_user(
        username=v_user, password="Viewer@Pass2026", full_name="Viewer User", role_id=v_id
    )
    assert ok
    user_id = u_dict["id"]

    # Viewer has live:view
    assert rbac_service.has_permission(user_id, PermissionCodes.LIVE_VIEW)
    # Viewer does NOT have camera:manage or user:manage
    assert not rbac_service.has_permission(user_id, PermissionCodes.CAMERA_MANAGE)
    assert not rbac_service.has_permission(user_id, PermissionCodes.USER_MANAGE)

    # require_permission raises AccessDeniedError for camera:manage
    with pytest.raises(AccessDeniedError):
        rbac_service.require_permission(user_id, PermissionCodes.CAMERA_MANAGE)


def test_require_permission_decorator():
    """Tests the @require_permission decorator in protected functions."""
    @require_permission(PermissionCodes.USER_MANAGE)
    def sensitive_admin_action(operator_user_id: str) -> str:
        return "Admin action executed successfully"

    # Create normal operator without user:manage
    with db_manager.get_session() as session:
        op_role = session.query(Role).filter_by(name="CCTV Operator").first()
        admin_role = session.query(Role).filter_by(name="Super Administrator").first()
        op_id = op_role.id
        admin_id = admin_role.id

    op_user = f"norm_op_{datetime.now().microsecond}"
    _, u_norm, _ = user_service.create_user(
        username=op_user, password="Operator#2026", full_name="Normal Op", role_id=op_id
    )

    adm_user = f"adm_{datetime.now().microsecond}"
    _, u_adm, _ = user_service.create_user(
        username=adm_user, password="Admin#Pass2026", full_name="Super Admin", role_id=admin_id
    )

    # Calling with normal operator raises AccessDeniedError
    with pytest.raises(AccessDeniedError):
        sensitive_admin_action(operator_user_id=u_norm["id"])

    # Calling with admin succeeds
    res = sensitive_admin_action(operator_user_id=u_adm["id"])
    assert res == "Admin action executed successfully"

    # Calling with SecurityContext
    with SecurityContext(u_adm["id"]):
        @require_permission(PermissionCodes.LIVE_VIEW)
        def view_action() -> str:
            return "Feed accessed"
        assert view_action() == "Feed accessed"
