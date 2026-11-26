"""
Cryptographic Audit Ledger & Compliance Reports REST API Router.
Requires 'audit:view' permission.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from database.models.users import AuditLog
from web.schemas.common import StandardResponse
from web.api.deps import get_db, require_permission, get_correlation_id
from core.security.audit_service import audit_service

router = APIRouter(prefix="/reports", tags=["Reports & Audit"])


@router.get("/audit-logs", response_model=StandardResponse[List[Dict[str, Any]]])
async def list_audit_logs(
    request: Request,
    category: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: Dict[str, Any] = Depends(require_permission("audit:view")),
    db: Session = Depends(get_db)
):
    """Queries immutable Merkle hash-chained audit logs with pagination."""
    cid = get_correlation_id(request)
    query = db.query(AuditLog)

    if category:
        query = query.filter(AuditLog.category == category.upper())
    if username:
        query = query.filter(AuditLog.username.ilike(f"%{username.strip()}%"))
    if status_filter:
        query = query.filter(AuditLog.status == status_filter.upper())

    logs = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()

    results = [
        {
            "id": l.id,
            "created_at": l.created_at.isoformat() if l.created_at else None,
            "action": l.action,
            "category": l.category or "SYSTEM",
            "status": l.status or "SUCCESS",
            "username": l.username or "system",
            "resource_type": l.resource_type,
            "resource_id": l.resource_id,
            "correlation_id": l.correlation_id,
            "record_hash": l.record_hash,
            "prev_hash": l.prev_hash,
        }
        for l in logs
    ]
    return StandardResponse.ok(results, correlation_id=cid)


@router.get("/audit-integrity", response_model=StandardResponse[Dict[str, Any]])
async def verify_audit_integrity(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("audit:view")),
):
    """Performs live cryptographic verification of the SHA-256 Merkle chain."""
    cid = get_correlation_id(request)
    is_valid, record_count, message = audit_service.verify_audit_integrity()

    data = {
        "is_valid": is_valid,
        "record_count": record_count,
        "algorithm": "SHA-256",
        "details": message or "Audit chain verified successfully with zero tampering.",
    }
    return StandardResponse.ok(data, correlation_id=cid)
