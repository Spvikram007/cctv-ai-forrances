"""
Authentication & Session Management API Router (Phase 15 Milestone W2).
Reuses existing UserService, password hashing, lockout logic, and audit trail.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from sqlalchemy.orm import Session

from web.schemas.common import StandardResponse
from web.schemas.auth import LoginRequest, LoginResponse, UserProfileResponse, SessionInfo
from web.api.deps import get_db, get_current_user, get_current_active_user, get_session_token, get_correlation_id, require_permission
from web.config import web_settings
from core.security.user_service import user_service
from core.security.rbac import rbac_service
from core.security.audit_service import audit_service
from database.models.users import User, UserSession
from web.api.websocket.tickets import ws_ticket_manager

router = APIRouter(prefix="/auth", tags=["Authentication & Sessions"])


@router.post("/login", response_model=StandardResponse[LoginResponse])
async def login(
    login_data: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Authenticates operator with username and password.
    Enforces brute-force lockout (5 failed attempts = 15m lockout), Super Administrator immunity,
    and automatic SHA-256 to bcrypt upgrade. Sets secure HttpOnly session cookie.
    """
    cid = get_correlation_id(request)
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("User-Agent", "Web Client")

    success, session_dict, message = user_service.authenticate(
        username=login_data.username,
        password=login_data.password,
        ip_address=client_ip,
        user_agent=f"{login_data.client_name} - {user_agent}"
    )

    if not success or not session_dict:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": message}
        )

    # Set HttpOnly, SameSite Session Cookie
    response.set_cookie(
        key=web_settings.session_cookie_name,
        value=session_dict["session_token"],
        max_age=web_settings.session_lifetime_minutes * 60,
        httponly=True,
        secure=web_settings.cookie_secure,
        samesite=web_settings.cookie_samesite,
        path="/"
    )

    res_data = LoginResponse(
        session_id=session_dict["session_id"],
        session_token=session_dict["session_token"],
        user_id=session_dict["user_id"],
        username=session_dict["username"],
        full_name=session_dict["full_name"],
        role_name=session_dict["role_name"],
        expires_at=session_dict["expires_at"]
    )

    return StandardResponse.ok(res_data, correlation_id=cid)


@router.post("/logout", response_model=StandardResponse[Dict[str, str]])
async def logout(
    request: Request,
    response: Response,
    current_user: Dict[str, Any] = Depends(get_current_user),
    token: Optional[str] = Depends(get_session_token)
):
    """Revokes active session token and clears the authentication cookie."""
    cid = get_correlation_id(request)
    if token:
        user_service.logout(token)

    # Clear cookie
    response.delete_cookie(
        key=web_settings.session_cookie_name,
        path="/"
    )

    return StandardResponse.ok({"message": "Successfully logged out."}, correlation_id=cid)


@router.get("/me", response_model=StandardResponse[UserProfileResponse])
async def get_current_operator_profile(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Returns profile, role, and fine-grained permissions for the authenticated operator."""
    cid = get_correlation_id(request)
    user_id = current_user["user_id"]

    user = db.query(User).filter_by(id=user_id, is_active=True).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    permissions = list(rbac_service.get_user_permissions(user_id, session=db))

    profile = UserProfileResponse(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        role_id=user.role_id,
        role_name=user.role.name if user.role else "Unknown",
        is_active=user.is_active,
        permissions=permissions,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None
    )

    return StandardResponse.ok(profile, correlation_id=cid)


@router.post("/refresh", response_model=StandardResponse[Dict[str, Any]])
async def refresh_session(
    request: Request,
    response: Response,
    current_user: Dict[str, Any] = Depends(get_current_active_user),
    token: Optional[str] = Depends(get_session_token)
):
    """Extends the session idle timer and refreshes cookie expiration."""
    cid = get_correlation_id(request)
    # validate_session in get_current_user already refreshed last_seen_at
    if token:
        response.set_cookie(
            key=web_settings.session_cookie_name,
            value=token,
            max_age=web_settings.session_lifetime_minutes * 60,
            httponly=True,
            secure=web_settings.cookie_secure,
            samesite=web_settings.cookie_samesite,
            path="/"
        )

    return StandardResponse.ok({
        "status": "refreshed",
        "username": current_user["username"],
        "expires_at": current_user.get("expires_at", "")
    }, correlation_id=cid)


@router.get("/sessions", response_model=StandardResponse[List[SessionInfo]])
async def list_active_sessions(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lists active operator sessions. Non-administrators can only view their own sessions;
    operators with 'user:manage' can view all active sessions across the platform.
    """
    cid = get_correlation_id(request)
    user_id = current_user["user_id"]
    can_manage_users = rbac_service.has_permission(user_id, "user:manage", session=db)

    query = db.query(UserSession).filter(UserSession.is_revoked == False)
    if not can_manage_users:
        query = query.filter(UserSession.user_id == user_id)

    sessions = query.order_by(UserSession.last_seen_at.desc()).all()

    current_token = get_session_token(request)
    results = [
        SessionInfo(
            session_id=s.id,
            user_id=s.user_id,
            username=s.user.username if s.user else "unknown",
            ip_address=s.ip_address,
            user_agent=s.user_agent,
            created_at=s.created_at.isoformat() if s.created_at else "",
            last_seen_at=s.last_seen_at.isoformat() if s.last_seen_at else "",
            expires_at=s.expires_at.isoformat() if s.expires_at else "",
            is_current=(s.session_token == current_token)
        )
        for s in sessions
    ]

    return StandardResponse.ok(results, correlation_id=cid)


@router.delete("/sessions/{session_id}", response_model=StandardResponse[Dict[str, str]])
async def revoke_session(
    session_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Revokes a specific active session."""
    cid = get_correlation_id(request)
    user_id = current_user["user_id"]
    can_manage_users = rbac_service.has_permission(user_id, "user:manage", session=db)

    user_session = db.query(UserSession).filter_by(id=session_id).first()
    if not user_session:
        raise HTTPException(status_code=404, detail="Session not found.")

    if user_session.user_id != user_id and not can_manage_users:
        raise HTTPException(status_code=403, detail="Cannot revoke another operator's session.")

    setattr(user_session, "is_revoked", True)
    db.commit()

    audit_service.log_event(
        action="SESSION_REVOKED",
        category="AUTH",
        resource_type="session",
        resource_id=session_id,
        status="SUCCESS",
        user_id=user_id,
        username=current_user["username"],
        details={"revoked_user_id": user_session.user_id}
    )

    return StandardResponse.ok({"message": f"Session '{session_id}' successfully revoked."}, correlation_id=cid)


@router.post("/ws-ticket", response_model=StandardResponse[Dict[str, Any]])
async def create_websocket_ticket(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_active_user),
    token: Optional[str] = Depends(get_session_token)
):
    """
    Issues a short-lived (60s), single-use ticket for WebSocket authentication.
    Prevents long-lived session tokens from being exposed in browser query strings,
    proxy logs, or browser history.
    """
    cid = get_correlation_id(request)
    user_id = current_user["user_id"]
    session_token = token or ""
    ticket = ws_ticket_manager.create_ticket(user_id=user_id, session_token=session_token, lifetime_seconds=60)
    return StandardResponse.ok({"ticket": ticket, "expires_in": 60}, correlation_id=cid)
