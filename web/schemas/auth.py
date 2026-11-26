"""
Authentication and session Pydantic schemas.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100, description="Username or operator ID")
    password: str = Field(..., min_length=1, max_length=256, description="Password")
    client_name: Optional[str] = Field("Web Browser", description="Client identifier or user agent summary")


class LoginResponse(BaseModel):
    session_id: str = Field(..., description="Unique session identifier")
    session_token: str = Field(..., description="Cryptographically secure session token")
    user_id: str = Field(..., description="User unique ID")
    username: str = Field(..., description="Operator username")
    full_name: str = Field(..., description="Operator full name")
    role_name: str = Field(..., description="Assigned surveillance role")
    expires_at: str = Field(..., description="UTC session expiration timestamp")


class UserProfileResponse(BaseModel):
    user_id: str
    username: str
    full_name: str
    email: Optional[str] = None
    role_id: str
    role_name: str
    is_active: bool
    permissions: List[str] = Field(default_factory=list, description="List of granted permission codes")
    last_login_at: Optional[str] = None


class SessionInfo(BaseModel):
    session_id: str
    user_id: str
    username: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: str
    last_seen_at: Optional[str] = None
    expires_at: str
    is_current: bool = False
