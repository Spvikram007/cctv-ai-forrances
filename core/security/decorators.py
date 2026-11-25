"""
Security Decorators and Context Utilities (Phase 14 - Module B).
Enforces backend RBAC checks, least-privilege verification, and thread-local security context.
"""

import functools
import threading
from typing import Optional, Callable, Any
from core.security.rbac import rbac_service, AccessDeniedError

# Thread-local storage for tracking active authenticated operator
_thread_security_context = threading.local()


def set_current_user_id(user_id: Optional[str]) -> None:
    """Sets the active operator user ID for the current thread."""
    _thread_security_context.user_id = user_id


def get_current_user_id() -> Optional[str]:
    """Retrieves the active operator user ID from thread-local context."""
    return getattr(_thread_security_context, "user_id", None)


class SecurityContext:
    """Context manager for executing a code block under a specific operator identity."""

    def __init__(self, user_id: Optional[str]) -> None:
        self.user_id = user_id
        self._prev_user_id: Optional[str] = None

    def __enter__(self) -> "SecurityContext":
        self._prev_user_id = get_current_user_id()
        set_current_user_id(self.user_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        set_current_user_id(self._prev_user_id)


def require_permission(permission_code: str) -> Callable:
    """
    Function decorator enforcing backend RBAC authorization.
    Extracts operator ID either from keyword argument 'operator_user_id' or thread context.
    Raises AccessDeniedError if the user lacks the permission.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            operator_id = kwargs.get("operator_user_id") or get_current_user_id()
            if not operator_id:
                raise AccessDeniedError(
                    f"Authentication required: No operator identity provided for operation requiring '{permission_code}'."
                )
            rbac_service.require_permission(operator_id, permission_code)
            return func(*args, **kwargs)
        return wrapper
    return decorator
