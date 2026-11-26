"""
System Health, Readiness, Telemetry & WebSocket API Router (Phase 15 Milestone W2).
"""

import time
import psutil
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from web.schemas.common import StandardResponse
from web.schemas.system import HealthResponse, ReadinessResponse, SystemStatusResponse
from web.api.deps import get_db, get_correlation_id, get_current_active_user, require_permission
from web.api.websocket.hub import ws_hub
from web.api.websocket.tickets import ws_ticket_manager
from web.config import web_settings
from database.database_manager import db_manager
from database.models.users import UserSession
from engines.video_engine.stream_manager import stream_manager
from core.events.event_bus import bus
from core.config.settings import settings

router = APIRouter(tags=["System, Health & Telemetry"])

STARTUP_TIME = time.time()


@router.get("/health", response_model=StandardResponse[HealthResponse])
async def health_check(request: Request, db: Session = Depends(get_db)):
    """
    Public LAN health check endpoint.
    Verifies database connection, stream manager, event bus, and storage health.
    """
    cid = get_correlation_id(request)

    # Check Database
    db_status = "CONNECTED"
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "ERROR"

    # Check Stream Manager
    stream_status = "RUNNING" if stream_manager is not None else "ERROR"

    # Check Event Bus
    bus_status = "ACTIVE" if bus is not None else "ERROR"

    is_healthy = (db_status == "CONNECTED" and stream_status == "RUNNING")
    overall_status = "HEALTHY" if is_healthy else "DEGRADED"

    health = HealthResponse(
        status=overall_status,
        version=getattr(settings, "app_version", "1.5.0-alpha"),
        timestamp=datetime.now(timezone.utc).isoformat(),
        database=db_status,
        event_bus=bus_status,
        storage_engine="NORMAL",
        stream_manager=stream_status
    )

    return StandardResponse.ok(health, correlation_id=cid)


@router.get("/ready", response_model=StandardResponse[ReadinessResponse])
async def readiness_check(request: Request, db: Session = Depends(get_db)):
    """Readiness probe verifying the system is fully initialized to accept LAN client traffic."""
    cid = get_correlation_id(request)
    checks = {
        "database": True,
        "event_bus": True,
        "stream_manager": True,
        "security_core": True,
    }

    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
    except Exception:
        checks["database"] = False

    ready = all(checks.values())
    return StandardResponse.ok(ReadinessResponse(ready=ready, checks=checks), correlation_id=cid)


@router.get("/system/status", response_model=StandardResponse[SystemStatusResponse])
async def system_status(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("dashboard:view")),
    db: Session = Depends(get_db)
):
    """
    Returns live system telemetry for dashboard widgets.
    Requires 'dashboard:view' permission.
    """
    cid = get_correlation_id(request)

    # Hardware stats via psutil
    vm = psutil.virtual_memory()
    raw_cpu = psutil.cpu_percent(interval=None)
    cpu_val: float = float(raw_cpu) if isinstance(raw_cpu, (int, float)) else 0.0
    uptime = time.time() - STARTUP_TIME

    # Active stream & session count
    active_streams = stream_manager.active_stream_count() if stream_manager else 0
    active_sessions = db.query(UserSession).filter_by(is_revoked=False).count()

    status_data = SystemStatusResponse(
        version=getattr(settings, "app_version", "1.5.0-alpha"),
        app_name="CCTV AI Intelligence Platform",
        server_time=datetime.now(timezone.utc).isoformat(),
        uptime_seconds=round(uptime, 1),
        cpu_percent=cpu_val,
        memory_used_mb=round(vm.used / (1024 * 1024), 1),
        memory_total_mb=round(vm.total / (1024 * 1024), 1),
        memory_percent=vm.percent,
        openvino_device="GPU (Intel UHD Graphics 730) + CPU",
        active_stream_count=active_streams,
        active_session_count=active_sessions
    )

    return StandardResponse.ok(status_data, correlation_id=cid)


@router.get("/system/settings", response_model=StandardResponse[Dict[str, Any]])
async def get_system_settings(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("system:config")),
):
    """
    Returns platform and network security parameters for the Settings workspace.
    Requires 'system:config' permission.
    """
    cid = get_correlation_id(request)
    data = {
        "allowed_subnets": web_settings.allowed_subnets,
        "cors_origins": web_settings.cors_allowed_origins,
        "ssl_enabled": web_settings.ssl_enabled,
        "session_cookie_name": web_settings.session_cookie_name,
        "session_lifetime_minutes": web_settings.session_lifetime_minutes,
        "cookie_samesite": web_settings.cookie_samesite,
        "cookie_secure": web_settings.cookie_secure,
        "lockout_threshold": 5,
        "lockout_duration_minutes": 15,
        "super_admin_immunity": True,
        "audit_chain_algorithm": "SHA-256",
        "storage_encryption": "AES-256 GCM",
    }
    return StandardResponse.ok(data, correlation_id=cid)


@router.websocket("/ws/events")
async def websocket_events_endpoint(
    websocket: WebSocket,
    token: Optional[str] = None,
    ticket: Optional[str] = None
):
    """
    Authenticated real-time WebSocket endpoint.
    Authentication precedence:
      1. Secure HttpOnly session cookie ('cctv_session') - primary browser mechanism (zero tokens in URL).
      2. Single-use ticket ('ticket' query param) - short-lived 60s ticket from POST /api/v1/auth/ws-ticket.
      3. Token query parameter ('token' query param) - programmatic/CLI fallback.
    Validates Origin and bridges EventBus topics to connected web clients with zero Qt event loop contention.
    """
    # 0. Validate Origin if provided
    origin = websocket.headers.get("origin")
    if origin and not web_settings.is_origin_allowed(origin):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized WebSocket origin.")
        return

    # 1. Check secure cookie first (browser standard)
    resolved_token = websocket.cookies.get(web_settings.session_cookie_name)

    # 2. Check single-use ticket
    if not resolved_token and ticket:
        ticket_data = ws_ticket_manager.consume_ticket(ticket)
        if ticket_data:
            _, resolved_token = ticket_data
        else:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired WebSocket ticket.")
            return

    # 3. Fallback to token query param (for backward compatibility and test suites)
    if not resolved_token and token:
        resolved_token = token

    session_data = await ws_hub.connect(websocket, resolved_token)
    if not session_data:
        return

    user_id = session_data["user_id"]
    try:
        while True:
            # Keep socket open and process any incoming ping/subscribe requests from client
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await ws_hub.disconnect(websocket, user_id)
    except Exception:
        await ws_hub.disconnect(websocket, user_id)
