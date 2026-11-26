"""
System telemetry, health, and status Pydantic schemas.
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., description="Overall health: HEALTHY, DEGRADED, UNHEALTHY")
    version: str = Field(..., description="Application version")
    timestamp: str = Field(..., description="UTC timestamp")
    database: str = Field(..., description="Database connection state")
    event_bus: str = Field(..., description="Event bus operational state")
    storage_engine: str = Field(..., description="Storage pool status")
    stream_manager: str = Field(..., description="Active camera stream manager status")


class ReadinessResponse(BaseModel):
    ready: bool = Field(..., description="True if server is ready to accept traffic")
    checks: Dict[str, bool] = Field(..., description="Readiness check breakdown")


class SystemStatusResponse(BaseModel):
    version: str
    app_name: str
    server_time: str
    uptime_seconds: float
    cpu_percent: float
    memory_used_mb: float
    memory_total_mb: float
    memory_percent: float
    openvino_device: str
    active_stream_count: int
    active_session_count: int
