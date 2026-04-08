from fastapi import APIRouter

from app.api.v1.analytics import router as analytics_router
from app.api.v1.audit import router as audit_router
from app.api.v1.ops import router as ops_router
from app.api.v1.saved_views import router as saved_views_router
from app.api.v1.auth import router as auth_router
from app.api.v1.customer_health import router as customer_health_router
from app.api.v1.customers import router as customers_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.emails import router as emails_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.parts import router as parts_router
from app.api.v1.prices import router as prices_router
from app.api.v1.quotes import router as quotes_router
from app.api.v1.settings import router as settings_router
from app.api.v1.users import router as users_router

v1_router = APIRouter()

v1_router.include_router(auth_router)
v1_router.include_router(dashboard_router)
v1_router.include_router(emails_router)
v1_router.include_router(parts_router)
v1_router.include_router(prices_router)
v1_router.include_router(customer_health_router)
v1_router.include_router(customers_router)
v1_router.include_router(quotes_router)
v1_router.include_router(analytics_router)
v1_router.include_router(notifications_router)
v1_router.include_router(settings_router)
v1_router.include_router(users_router)
v1_router.include_router(audit_router)
v1_router.include_router(ops_router)
v1_router.include_router(saved_views_router)
