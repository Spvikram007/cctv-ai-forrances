"""
Request correlation ID middleware for end-to-end tracing across REST and audit logs.
"""

import uuid
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Ensures every incoming request carries a unique X-Correlation-ID."""

    async def dispatch(self, request: Request, call_next) -> Response:
        cid = request.headers.get("X-Correlation-ID")
        if not cid:
            timestamp_part = int(time.time())
            random_part = uuid.uuid4().hex[:8]
            cid = f"req-{timestamp_part}-{random_part}"

        # Store in request state for downstream handlers
        request.state.correlation_id = cid

        response: Response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response
