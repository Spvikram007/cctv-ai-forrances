"""
Pydantic Schemas for Camera & Device Management (Phase 15 Milestone W2/W4).
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CameraCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Camera display name")
    ip_address: str = Field(..., min_length=1, max_length=45, description="IP address or hostname")
    port: int = Field(80, ge=1, le=65535, description="HTTP / Web port")
    rtsp_port: int = Field(554, ge=1, le=65535, description="RTSP streaming port")
    onvif_port: Optional[int] = Field(80, ge=1, le=65535, description="ONVIF service port")
    manufacturer: str = Field("GENERIC_ONVIF", max_length=50, description="Camera manufacturer / profile")
    model: Optional[str] = Field("IP Camera", max_length=50, description="Hardware model")
    rtsp_path: Optional[str] = Field("/live", max_length=200, description="RTSP path suffix")
    username: Optional[str] = Field("admin", max_length=100, description="Camera authentication username")
    password: Optional[str] = Field("", max_length=256, description="Camera authentication password")


class CameraUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    manufacturer: Optional[str] = Field(None, max_length=50)
    port: Optional[int] = Field(None, ge=1, le=65535)
    rtsp_port: Optional[int] = Field(None, ge=1, le=65535)
    onvif_port: Optional[int] = Field(None, ge=1, le=65535)


class CameraResponse(BaseModel):
    id: str = Field(..., description="Unique Device ID (UUID)")
    name: str = Field(..., description="Camera name")
    device_type: str = Field("CAMERA", description="Device type: CAMERA, NVR, DVR")
    manufacturer: str = Field(..., description="Manufacturer")
    ip_address: str = Field(..., description="IP Address")
    port: int = Field(..., description="HTTP port")
    rtsp_port: int = Field(..., description="RTSP port")
    onvif_port: Optional[int] = Field(None, description="ONVIF port")
    is_online: bool = Field(..., description="Current connection status")
    channel_id: Optional[str] = Field(None, description="Primary channel ID for streaming")
    rtsp_url: Optional[str] = Field(None, description="Redacted RTSP stream URL (no embedded credentials)")
    created_at: str = Field(..., description="Registration timestamp")
