"""
FastAPI Dependencies for Database Sessions, Authentication, and RBAC Authorization.
Guarantees strict thread safety, isolated request-scoped sessions, and server-side RBAC.
"""

from typing import Generator, Optional, Dict, Any, Callable
from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.database_manager import db_manager
from core.security.user_service import user_service
from core.security.rbac import rbac_service
from core.security.decorators import set_current_user_id
from web.config import web_settings


def get_db() -> Generator[Session, None, None]:
    """
    Request-scoped SQLAlchemy database session generator.
    Provides a dedicated, thread-safe session per HTTP request and guarantees
    immediate cleanup upon request completion. Prevents cross-thread session bleeding.
    """
    with db_manager.get_session() as session:
        try:
            yield session
        finally:
            # Session is automatically rolled back or closed by db_manager context manager
            pass


def get_correlation_id(request: Request) -> str:
    """Retrieves unique request tracing ID from request state."""
    return getattr(request.state, "correlation_id", "sys-req")


def get_session_token(request: Request) -> Optional[str]:
    """
    Extracts the authentication session token from:
    1. 'Authorization: Bearer <token>' header (API / programmatic clients)
    2. HttpOnly 'cctv_session' cookie (browser mechanism)
    Explicit Authorization header takes precedence over browser cookies.
    """
    # 1. Check Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    # 2. Check secure cookie
    token = request.cookies.get(web_settings.session_cookie_name)
    if token:
        return token

    return None


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(get_session_token)
) -> Dict[str, Any]:
    """
    Validates the session token using the existing UserService.
    Rejects missing, expired, or revoked tokens with HTTP 401 Unauthorized.
    """
    cid = get_correlation_id(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Authentication required. Please log in."}
        )

    session_data = user_service.validate_session(token)
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "SESSION_EXPIRED", "message": "Session has expired or is invalid. Please log in again."}
        )

    # Set thread-local operator context for downstream core security / audit logging
    set_current_user_id(session_data["user_id"])
    return session_data


async def get_current_active_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Verifies that the authenticated operator account is active."""
    # UserService.validate_session already verifies user is_active and not locked
    return current_user


def require_permission(permission_code: str) -> Callable:
    """
    Factory creating a FastAPI dependency that enforces a specific RBAC permission.
    Reuses existing RBACService directly against the database role matrix.
    Raises HTTP 403 Forbidden if the user lacks the permission code.
    """
    async def permission_dependency(
        current_user: Dict[str, Any] = Depends(get_current_active_user)
    ) -> Dict[str, Any]:
        user_id = current_user["user_id"]
        if not rbac_service.has_permission(user_id, permission_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "ACCESS_DENIED",
                    "message": f"Access Denied: You do not possess the required permission '{permission_code}'.",
                    "required_permission": permission_code
                }
            )
        return current_user

    return permission_dependency
