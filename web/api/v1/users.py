"""
User Accounts and RBAC Roles Administration REST API Router.
Requires 'user:manage' or 'role:manage' permission.
"""

from typing import List, Dict, Any
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from database.models.users import User, Role
from web.schemas.common import StandardResponse
from web.api.deps import get_db, require_permission, get_correlation_id

router = APIRouter(tags=["Users & Roles"])


@router.get("/users", response_model=StandardResponse[List[Dict[str, Any]]])
async def list_users(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("user:manage")),
    db: Session = Depends(get_db)
):
    """Lists operator accounts and status."""
    cid = get_correlation_id(request)
    users = db.query(User).filter(User.is_deleted == False).order_by(User.created_at.asc()).all()

    results = [
        {
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name,
            "email": u.email,
            "role_id": u.role_id,
            "role_name": u.role.name if u.role else "Unknown",
            "is_active": u.is_active,
            "failed_login_attempts": u.failed_login_attempts or 0,
            "locked_until": u.locked_until.isoformat() if u.locked_until else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]
    return StandardResponse.ok(results, correlation_id=cid)


@router.get("/roles", response_model=StandardResponse[List[Dict[str, Any]]])
async def list_roles(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("user:manage")),
    db: Session = Depends(get_db)
):
    """Lists standard surveillance roles and their assigned permission codes."""
    cid = get_correlation_id(request)
    roles = db.query(Role).order_by(Role.name.asc()).all()

    results = []
    for r in roles:
        perms = [rp.permission.code for rp in r.permissions if rp.permission]
        results.append({
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "is_system": r.is_system,
            "permissions": perms,
            "permission_count": len(perms),
        })

    return StandardResponse.ok(results, correlation_id=cid)
