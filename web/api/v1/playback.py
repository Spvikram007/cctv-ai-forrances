"""
Historical Video Playback Metadata REST API Router.
Requires 'playback:view' permission.
(W3.3 provides playback timeline and recording index; video gateway W4 will deliver stream segments).
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from database.models.recordings import Recording
from web.schemas.common import StandardResponse
from web.api.deps import get_db, require_permission, get_correlation_id

router = APIRouter(prefix="/playback", tags=["Video Playback & Recordings"])


@router.get("/recordings", response_model=StandardResponse[List[Dict[str, Any]]])
async def list_recording_segments(
    request: Request,
    channel_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: Dict[str, Any] = Depends(require_permission("playback:view")),
    db: Session = Depends(get_db)
):
    """Lists indexed video recordings and timeline segments."""
    cid = get_correlation_id(request)
    query = db.query(Recording).filter(Recording.is_deleted == False)

    if channel_id:
        query = query.filter(Recording.channel_id == channel_id)

    recordings = query.order_by(Recording.start_time.desc()).offset(offset).limit(limit).all()

    results = [
        {
            "id": r.id,
            "channel_id": r.channel_id,
            "recording_type": r.recording_type,
            "stream_type": r.stream_type,
            "start_time": r.start_time.isoformat() if r.start_time else None,
            "end_time": r.end_time.isoformat() if r.end_time else None,
            "duration_sec": r.duration_sec,
            "file_size_mb": round(r.file_size_bytes / (1024 * 1024), 2) if r.file_size_bytes else 0.0,
            "codec": r.codec,
            "resolution": f"{r.resolution_width}x{r.resolution_height}",
            "fps": r.fps,
            "status": r.status,
            "is_locked": r.is_locked,
        }
        for r in recordings
    ]
    return StandardResponse.ok(results, correlation_id=cid)
