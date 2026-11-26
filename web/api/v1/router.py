"""
Master API v1 Router Aggregation.
"""

from fastapi import APIRouter
from web.api.v1.auth import router as auth_router
from web.api.v1.system import router as system_router
from web.api.v1.cameras import router as cameras_router
from web.api.v1.alarms import router as alarms_router
from web.api.v1.analytics import router as analytics_router
from web.api.v1.storage import router as storage_router
from web.api.v1.reports import router as reports_router
from web.api.v1.users import router as users_router
from web.api.v1.playback import router as playback_router
from web.api.v1.rbac_test import router as rbac_test_router

v1_router = APIRouter(prefix="/api/v1")

# Include domain routers
v1_router.include_router(auth_router)
v1_router.include_router(system_router)
v1_router.include_router(cameras_router)
v1_router.include_router(alarms_router)
v1_router.include_router(analytics_router)
v1_router.include_router(storage_router)
v1_router.include_router(reports_router)
v1_router.include_router(users_router)
v1_router.include_router(playback_router)
v1_router.include_router(rbac_test_router)
