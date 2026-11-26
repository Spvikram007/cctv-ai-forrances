"""
FastAPI Application Factory & Lifecycle Management (Phase 15 Milestone W2).
Configures middleware pipeline, exception handlers, routers, and CORS.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from web.config import web_settings
from web.api.middleware.correlation import CorrelationIdMiddleware
from web.api.middleware.security import SecurityHeadersMiddleware
from web.api.middleware.subnet import LANSubnetFilterMiddleware
from web.api.websocket.hub import ws_hub
from web.api.v1.router import v1_router
from web.schemas.common import StandardResponse
from core.logging.logger import get_logger

logger = get_logger("web_app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages FastAPI application startup and shutdown lifecycle.
    Binds WebSocketHub to the running event loop without blocking Qt or other services.
    """
    loop = asyncio.get_running_loop()
    ws_hub.set_event_loop(loop)
    logger.info("CCTV AI FastAPI Web Gateway initialized on event loop.")

    yield

    logger.info("CCTV AI FastAPI Web Gateway shutting down...")


def create_app() -> FastAPI:
    """Creates and configures the production-ready FastAPI application."""
    app = FastAPI(
        title="CCTV AI Intelligence Platform - LAN Web Gateway",
        description="High-performance, secure LAN Web Gateway for the CCTV AI Intelligence Platform.",
        version="1.5.0-alpha",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan
    )

    # 1. Custom Middlewares (Applied in reverse order: innermost first)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(LANSubnetFilterMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    # 2. CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=web_settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"]
    )

    # 3. Standardized Exception Handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        cid = getattr(request.state, "correlation_id", "sys")
        code = "HTTP_ERROR"
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        details = None

        if isinstance(exc.detail, dict):
            code = exc.detail.get("code", "HTTP_ERROR")
            message = exc.detail.get("message", message)
            details = exc.detail.get("details", None)

        return JSONResponse(
            status_code=exc.status_code,
            content=StandardResponse.fail(
                code=code,
                message=message,
                correlation_id=cid,
                details=details
            ).model_dump()
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        cid = getattr(request.state, "correlation_id", "sys")
        errors = exc.errors()
        err_msg = "; ".join([f"{'.'.join(str(l) for l in err['loc'])}: {err['msg']}" for err in errors])
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=StandardResponse.fail(
                code="VALIDATION_ERROR",
                message=f"Request validation failed: {err_msg}",
                correlation_id=cid,
                details=errors
            ).model_dump()
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        cid = getattr(request.state, "correlation_id", "sys")
        logger.error("Unhandled exception processing request (Correlation: %s): %s", cid, exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=StandardResponse.fail(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected server error occurred. Please contact the surveillance administrator.",
                correlation_id=cid
            ).model_dump()
        )

    # 4. Mount Master API v1 Router
    app.include_router(v1_router)

    return app


# Application singleton
app = create_app()
