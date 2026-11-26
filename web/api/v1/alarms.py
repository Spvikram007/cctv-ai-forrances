"""
Alarm Management REST API Router.
Provides alarm querying, summary KPIs, acknowledgment, and resolution.
Enforces RBAC: 'alarm:view' for listing/summary, 'alarm:manage' for triage actions.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session

from database.models.alarms import Alarm
from web.schemas.common import StandardResponse
from web.api.deps import get_db, require_permission, get_correlation_id
from core.security.audit_service import audit_service
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("alarms_api")
router = APIRouter(prefix="/alarms", tags=["Alarms & Incidents"])


def _serialize_alarm(a: Alarm) -> Dict[str, Any]:
    return {
        "id": a.id,
        "title": a.title,
        "description": a.description,
        "category": a.category,
        "source_subsystem": a.source_subsystem,
        "severity": a.severity,
        "priority": a.priority,
        "status": a.status,
        "camera_id": a.camera_id,
        "first_detected_at": a.first_detected_at.isoformat() if a.first_detected_at else None,
        "last_detected_at": a.last_detected_at.isoformat() if a.last_detected_at else None,
        "occurrence_count": a.occurrence_count or 1,
        "assigned_operator": a.assigned_operator,
        "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
        "acknowledged_by": a.acknowledged_by,
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        "resolved_by": a.resolved_by,
    }


@router.get("", response_model=StandardResponse[List[Dict[str, Any]]])
async def list_alarms(
    request: Request,
    status_filter: Optional[str] = Query(None, alias="status"),
    severity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: Dict[str, Any] = Depends(require_permission("alarm:view")),
    db: Session = Depends(get_db)
):
    """Lists alarms with optional status and severity filtering."""
    cid = get_correlation_id(request)
    query = db.query(Alarm).filter(Alarm.is_deleted == False)

    if status_filter:
        query = query.filter(Alarm.status == status_filter.upper())
    if severity:
        query = query.filter(Alarm.severity == severity.upper())

    alarms = query.order_by(Alarm.last_detected_at.desc()).offset(offset).limit(limit).all()
    results = [_serialize_alarm(a) for a in alarms]
    return StandardResponse.ok(results, correlation_id=cid)


@router.get("/summary", response_model=StandardResponse[Dict[str, Any]])
async def get_alarms_summary(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("alarm:view")),
    db: Session = Depends(get_db)
):
    """Returns aggregated alarm KPI counters for dashboard widgets."""
    cid = get_correlation_id(request)
    base = db.query(Alarm).filter(Alarm.is_deleted == False)

    total = base.count()
    active = base.filter(Alarm.status.in_(["NEW", "ACKNOWLEDGED", "IN_PROGRESS", "REOPENED"])).count()
    critical = base.filter(Alarm.status.in_(["NEW", "ACKNOWLEDGED", "IN_PROGRESS"]), Alarm.severity == "CRITICAL").count()
    warning = base.filter(Alarm.status.in_(["NEW", "ACKNOWLEDGED", "IN_PROGRESS"]), Alarm.severity.in_(["WARNING", "HIGH"])).count()
    acknowledged = base.filter(Alarm.status == "ACKNOWLEDGED").count()
    resolved = base.filter(Alarm.status == "RESOLVED").count()

    summary = {
        "total": total,
        "active": active,
        "critical": critical,
        "warning": warning,
        "acknowledged": acknowledged,
        "resolved": resolved,
    }
    return StandardResponse.ok(summary, correlation_id=cid)


@router.post("/{alarm_id}/acknowledge", response_model=StandardResponse[Dict[str, Any]])
async def acknowledge_alarm(
    alarm_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("alarm:manage")),
    db: Session = Depends(get_db)
):
    """Transitions alarm to ACKNOWLEDGED status."""
    cid = get_correlation_id(request)
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id, Alarm.is_deleted == False).first()
    if not alarm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alarm not found.")

    username = current_user["username"]
    now = datetime.now(timezone.utc)
    setattr(alarm, "status", "ACKNOWLEDGED")
    setattr(alarm, "acknowledged_at", now)
    setattr(alarm, "acknowledged_by", username)
    db.commit()

    audit_service.log_event(
        action="ALARM_ACKNOWLEDGED",
        category="ALARM",
        resource_type="alarm",
        resource_id=alarm_id,
        status="SUCCESS",
        user_id=current_user["user_id"],
        username=username,
        details={"title": alarm.title, "severity": alarm.severity}
    )

    bus.publish("alarm.acknowledged", {"alarm_id": alarm_id, "by": username})
    return StandardResponse.ok(_serialize_alarm(alarm), correlation_id=cid)


@router.post("/{alarm_id}/resolve", response_model=StandardResponse[Dict[str, Any]])
async def resolve_alarm(
    alarm_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("alarm:manage")),
    db: Session = Depends(get_db)
):
    """Transitions alarm to RESOLVED status."""
    cid = get_correlation_id(request)
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id, Alarm.is_deleted == False).first()
    if not alarm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alarm not found.")

    username = current_user["username"]
    now = datetime.now(timezone.utc)
    setattr(alarm, "status", "RESOLVED")
    setattr(alarm, "resolved_at", now)
    setattr(alarm, "resolved_by", username)
    db.commit()

    audit_service.log_event(
        action="ALARM_RESOLVED",
        category="ALARM",
        resource_type="alarm",
        resource_id=alarm_id,
        status="SUCCESS",
        user_id=current_user["user_id"],
        username=username,
        details={"title": alarm.title}
    )

    bus.publish("alarm.resolved", {"alarm_id": alarm_id, "by": username})
    return StandardResponse.ok(_serialize_alarm(alarm), correlation_id=cid)
