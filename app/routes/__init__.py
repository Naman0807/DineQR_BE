from fastapi import APIRouter
from app.routes.menu import router as menu_router
from app.routes.tables import router as tables_router, public_router as tables_public_router
from app.routes.orders import router as orders_router
from app.routes.bills import router as bills_router
from app.routes.auth import router as auth_router
from app.routes.superadmin import router as superadmin_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(menu_router)
api_router.include_router(tables_router)
api_router.include_router(tables_public_router)
api_router.include_router(orders_router)
api_router.include_router(bills_router)
api_router.include_router(superadmin_router)
