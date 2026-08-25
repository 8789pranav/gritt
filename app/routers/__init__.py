"""API router package."""

from app.routers.auth import router as auth_router
from app.routers.spelling import router as spelling_router
from app.routers.logic import router as logic_router
from app.routers.speaking import router as speaking_router
from app.routers.comprehension import router as comprehension_router
from app.routers.admin import router as admin_router
from app.routers.report import router as report_router
from app.routers.payment import router as payment_router

all_routers = [
    auth_router,
    spelling_router,
    logic_router,
    speaking_router,
    comprehension_router,
    admin_router,
    report_router,
    payment_router,
]

__all__ = ["all_routers"]
