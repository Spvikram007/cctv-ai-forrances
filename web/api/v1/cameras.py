"""
Camera and Device Management REST API Endpoints (Phase 15 Milestone W2/W4).
Enforces fine-grained RBAC:
  - POST /api/v1/cameras: requires 'camera:manage' permission.
  - GET  /api/v1/cameras: requires 'live:view' permission (allows Operators, Supervisors, Viewers).
  - GET  /api/v1/cameras/{id}: requires 'live:view' permission.
  - DELETE /api/v1/cameras/{id}: requires 'camera:manage' permission.
Guarantees zero camera credential exposure and full audit logging.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_

from database.models.devices import Device, DeviceChannel, StreamProfile, DeviceCredential
from web.schemas.common import StandardResponse
from web.schemas.cameras import CameraCreateRequest, CameraUpdateRequest, CameraResponse
from web.api.deps import get_db, require_permission, get_correlation_id
from core.security.crypto import credential_vault, mask_rtsp_url
from core.security.audit_service import audit_service
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("cameras_api")

router = APIRouter(prefix="/cameras", tags=["Cameras & Devices"])


def _serialize_device(dev: Device) -> CameraResponse:
    """Helper to convert Device SQLAlchemy entity to sanitized CameraResponse."""
    primary_channel = dev.channels[0] if dev.channels else None
    primary_profile = primary_channel.stream_profiles[0] if (primary_channel and primary_channel.stream_profiles) else None

    raw_rtsp_url = primary_profile.rtsp_url if primary_profile else None
    rtsp_url = mask_rtsp_url(raw_rtsp_url)

    created_at_str = dev.created_at.isoformat() if dev.created_at else datetime.now(timezone.utc).isoformat()

    return CameraResponse(
        id=dev.id,
        name=dev.name,
        device_type=dev.device_type or "CAMERA",
        manufacturer=dev.manufacturer or "GENERIC_ONVIF",
        ip_address=dev.ip_address,
        port=dev.port or 80,
        rtsp_port=dev.rtsp_port or 554,
        onvif_port=dev.onvif_port,
        is_online=bool(dev.is_online),
        channel_id=primary_channel.id if primary_channel else None,
        rtsp_url=rtsp_url,
        created_at=created_at_str
    )


@router.get("", response_model=StandardResponse[List[CameraResponse]])
async def list_cameras(
    request: Request,
    search: Optional[str] = Query(None, description="Search by camera name, IP, or manufacturer"),
    online_only: bool = Query(False, description="Filter only active online cameras"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: Dict[str, Any] = Depends(require_permission("live:view")),
    db: Session = Depends(get_db)
):
    """
    Lists surveillance cameras and video devices.
    Requires 'live:view' permission to allow CCTV Operators, Supervisors,
    Investigators, and Viewers to monitor feeds.
    Includes offline and standby cameras by default to avoid phantom exclusions.
    """
    cid = get_correlation_id(request)
    query = db.query(Device).filter(Device.is_deleted == False)

    if search:
        search_filter = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Device.name.ilike(search_filter),
                Device.ip_address.ilike(search_filter),
                Device.manufacturer.ilike(search_filter)
            )
        )

    if online_only:
        query = query.filter(Device.is_online == True)

    total_count = query.count()
    devices = query.order_by(Device.created_at.asc()).offset(offset).limit(limit).all()

    camera_list = [_serialize_device(d) for d in devices]

    return StandardResponse.ok(camera_list, correlation_id=cid)


@router.get("/{camera_id}", response_model=StandardResponse[CameraResponse])
async def get_camera_by_id(
    camera_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("live:view")),
    db: Session = Depends(get_db)
):
    """
    Retrieves camera details by Device ID.
    Requires 'live:view' permission.
    """
    cid = get_correlation_id(request)
    dev = db.query(Device).filter(Device.id == camera_id, Device.is_deleted == False).first()
    if not dev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CAMERA_NOT_FOUND", "message": f"Camera '{camera_id}' not found."}
        )

    return StandardResponse.ok(_serialize_device(dev), correlation_id=cid)


@router.post("", response_model=StandardResponse[CameraResponse], status_code=status.HTTP_201_CREATED)
async def register_camera(
    payload: CameraCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("camera:manage")),
    db: Session = Depends(get_db)
):
    """
    Registers a new camera or recording device with encrypted credentials.
    Requires 'camera:manage' permission.
    Emits central EventBus event and generates an immutable audit record.
    """
    cid = get_correlation_id(request)

    # 1. Check for duplicate IP and Port
    existing = db.query(Device).filter(
        Device.ip_address == payload.ip_address,
        Device.port == payload.port,
        Device.is_deleted == False
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "DUPLICATE_CAMERA",
                "message": f"A camera with IP '{payload.ip_address}' on port {payload.port} is already registered (ID: {existing.id})."
            }
        )

    # 2. Create Device record
    dev = Device(
        name=payload.name,
        device_type="CAMERA",
        manufacturer=payload.manufacturer,
        ip_address=payload.ip_address,
        port=payload.port,
        rtsp_port=payload.rtsp_port,
        onvif_port=payload.onvif_port,
        is_online=True  # Default to active on registration
    )
    db.add(dev)
    db.flush()

    # 3. Create Primary Channel
    ch = DeviceChannel(
        device_id=dev.id,
        channel_number=1,
        name=f"{payload.name} Ch 1",
        is_enabled=True
    )
    db.add(ch)
    db.flush()

    # 4. Create Stream Profile
    rtsp_path = payload.rtsp_path if payload.rtsp_path else "/live"
    if not rtsp_path.startswith("/"):
        rtsp_path = "/" + rtsp_path
    rtsp_url = f"rtsp://{payload.ip_address}:{payload.rtsp_port}{rtsp_path}"

    prof = StreamProfile(
        channel_id=ch.id,
        profile_type="MAIN",
        rtsp_url=rtsp_url,
        codec="H264",
        resolution_width=1920,
        resolution_height=1080,
        target_fps=25
    )
    db.add(prof)

    # 5. Store Encrypted Credentials if provided
    if payload.password:
        encrypted_pwd = credential_vault.encrypt_password(payload.password)
        cred = DeviceCredential(
            device_id=dev.id,
            username=payload.username or "admin",
            encrypted_password=encrypted_pwd,
            auth_type="DIGEST"
        )
        db.add(cred)

    db.commit()
    db.refresh(dev)

    # 6. Dispatch EventBus event
    bus.publish("camera.registered", {
        "device_id": dev.id,
        "name": dev.name,
        "ip_address": dev.ip_address,
        "manufacturer": dev.manufacturer
    })

    # 7. Audit log event
    audit_service.log_event(
        action="CAMERA_REGISTERED",
        category="CAMERA",
        resource_type="camera",
        resource_id=dev.id,
        status="SUCCESS",
        user_id=current_user.get("user_id"),
        username=current_user.get("username"),
        correlation_id=cid,
        details={
            "camera_name": dev.name,
            "ip_address": dev.ip_address,
            "port": dev.port,
            "manufacturer": dev.manufacturer
        }
    )

    logger.info("Camera registered successfully: %s [%s] (ID: %s) by user %s",
                dev.name, dev.ip_address, dev.id, current_user.get("username"))

    return StandardResponse.ok(_serialize_device(dev), correlation_id=cid)


@router.delete("/{camera_id}", response_model=StandardResponse[Dict[str, Any]])
async def delete_camera(
    camera_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("camera:manage")),
    db: Session = Depends(get_db)
):
    """
    Soft-deletes a camera device.
    Requires 'camera:manage' permission.
    """
    cid = get_correlation_id(request)
    dev = db.query(Device).filter(Device.id == camera_id, Device.is_deleted == False).first()
    if not dev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CAMERA_NOT_FOUND", "message": f"Camera '{camera_id}' not found."}
        )

    dev.is_deleted = True
    db.commit()

    # Dispatch EventBus event
    bus.publish("camera.deleted", {"device_id": camera_id, "name": dev.name})

    # Audit log event
    audit_service.log_event(
        action="CAMERA_DELETED",
        category="CAMERA",
        resource_type="camera",
        resource_id=camera_id,
        status="SUCCESS",
        user_id=current_user.get("user_id"),
        username=current_user.get("username"),
        correlation_id=cid,
        details={"camera_name": dev.name, "ip_address": dev.ip_address}
    )

    return StandardResponse.ok({"deleted": True, "id": camera_id}, correlation_id=cid)
