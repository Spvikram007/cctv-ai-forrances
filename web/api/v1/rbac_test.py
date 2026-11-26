"""
RBAC Verification Test Endpoints (Phase 15 Milestone W2).
Demonstrates server-side permission barriers across multiple operational permissions.
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends, Request
from web.schemas.common import StandardResponse
from web.api.deps import require_permission, get_correlation_id

router = APIRouter(prefix="/test/rbac", tags=["RBAC Verification Tests"])


@router.get("/live-view", response_model=StandardResponse[Dict[str, str]])
async def test_live_view_permission(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("live:view"))
):
    """Protected by 'live:view' permission."""
    cid = get_correlation_id(request)
    return StandardResponse.ok({
        "message": "Authorized for live camera monitoring grid.",
        "user": current_user["username"],
        "permission": "live:view"
    }, correlation_id=cid)


@router.get("/camera-manage", response_model=StandardResponse[Dict[str, str]])
async def test_camera_manage_permission(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("camera:manage"))
):
    """Protected by 'camera:manage' permission."""
    cid = get_correlation_id(request)
    return StandardResponse.ok({
        "message": "Authorized to configure and manage surveillance cameras.",
        "user": current_user["username"],
        "permission": "camera:manage"
    }, correlation_id=cid)


@router.get("/user-manage", response_model=StandardResponse[Dict[str, str]])
async def test_user_manage_permission(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("user:manage"))
):
    """Protected by 'user:manage' permission."""
    cid = get_correlation_id(request)
    return StandardResponse.ok({
        "message": "Authorized for user account and security administration.",
        "user": current_user["username"],
        "permission": "user:manage"
    }, correlation_id=cid)


@router.get("/system-config", response_model=StandardResponse[Dict[str, str]])
async def test_system_config_permission(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("system:config"))
):
    """Protected by 'system:config' permission (Super Admin / Admin only)."""
    cid = get_correlation_id(request)
    return StandardResponse.ok({
        "message": "Authorized for core system and network configuration.",
        "user": current_user["username"],
        "permission": "system:config"
    }, correlation_id=cid)
