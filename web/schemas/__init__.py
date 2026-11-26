"""
Pydantic schemas package for CCTV AI Web API.
"""

from web.schemas.common import StandardResponse, ErrorDetail, PaginationParams
from web.schemas.auth import LoginRequest, LoginResponse, UserProfileResponse, SessionInfo
from web.schemas.system import HealthResponse, ReadinessResponse, SystemStatusResponse

__all__ = [
    "StandardResponse",
    "ErrorDetail",
    "PaginationParams",
    "LoginRequest",
    "LoginResponse",
    "UserProfileResponse",
    "SessionInfo",
    "HealthResponse",
    "ReadinessResponse",
    "SystemStatusResponse",
]
