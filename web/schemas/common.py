"""
Standard Pydantic response models and envelopes for the CCTV AI Web API.
"""

from typing import Generic, TypeVar, Optional, Any, Dict, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    details: Optional[Any] = Field(None, description="Optional diagnostic details or validation errors")


class StandardResponse(BaseModel, Generic[T]):
    success: bool = Field(True, description="Indicates whether the API call succeeded")
    data: Optional[T] = Field(None, description="Response payload")
    error: Optional[ErrorDetail] = Field(None, description="Error detail if success is False")
    correlation_id: str = Field(..., description="Unique request tracing ID")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="UTC timestamp")

    @classmethod
    def ok(cls, data: T, correlation_id: str = "sys") -> "StandardResponse[T]":
        return cls(
            success=True,
            data=data,
            error=None,
            correlation_id=correlation_id,
            timestamp=datetime.now(timezone.utc).isoformat()
        )

    @classmethod
    def fail(cls, code: str, message: str, correlation_id: str = "sys", details: Optional[Any] = None) -> "StandardResponse[None]":
        return cls(
            success=False,
            data=None,
            error=ErrorDetail(code=code, message=message, details=details),
            correlation_id=correlation_id,
            timestamp=datetime.now(timezone.utc).isoformat()
        )


class PaginationParams(BaseModel):
    page: int = Field(1, ge=1, description="Page number (1-based)")
    page_size: int = Field(50, ge=1, le=500, description="Items per page")
    sort_by: Optional[str] = Field(None, description="Field name to sort on")
    sort_order: str = Field("desc", pattern="^(asc|desc)$", description="Sort order: asc or desc")
