"""
Dynamic LAN Subnet Access Control Middleware.
"""

import json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from web.config import web_settings
from core.logging.logger import get_logger

logger = get_logger("web_subnet_filter")


class LANSubnetFilterMiddleware(BaseHTTPMiddleware):
    """
    Guarantees the web interface can only be accessed from authorized local subnets.
    Blocks external or unauthorized interfaces dynamically.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Strictly use trusted server-side socket peer address (request.client.host)
        # Never allow client-supplied headers (e.g. X-Forwarded-For) to bypass LAN security
        client_ip = request.client.host if request.client else "127.0.0.1"

        # Check against dynamic subnets
        if not web_settings.is_ip_allowed(client_ip):
            cid = getattr(request.state, "correlation_id", "unauth")
            logger.warning("Blocked connection attempt from unauthorized IP: %s (Correlation: %s)", client_ip, cid)
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "ACCESS_DENIED_LAN_ONLY",
                        "message": f"Connection from IP '{client_ip}' is not permitted. Access is restricted to authorized LAN subnets.",
                        "details": {"client_ip": client_ip, "allowed_subnets": web_settings.allowed_subnets}
                    },
                    "correlation_id": cid,
                }
            )

        return await call_next(request)
