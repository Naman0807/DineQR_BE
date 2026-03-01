from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy import select
from sqlalchemy.orm import selectinload

import uvicorn

from app.config import get_settings
from app.database import init_db, async_session
from app.routes import api_router
from app.websocket.manager import ConnectionManager
from app.auth.jwt import decode_access_token, get_password_hash
from app.models.models import User, UserRole, Table, Restaurant
from app.utils.logger import logger

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[MAIN] Initializing database...")
    await init_db()
    logger.info("[MAIN] Database initialized successfully")

    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == settings.SUPERADMIN_USERNAME))
        existing_superadmin = result.scalar_one_or_none()
        
        if not existing_superadmin:
            superadmin = User(
                username=settings.SUPERADMIN_USERNAME,
                email="superadmin@dineqr.local",
                role=UserRole.SUPERADMIN,
                hashed_password=get_password_hash(settings.SUPERADMIN_PASSWORD),
                is_active=True,
            )
            db.add(superadmin)
            await db.commit()
            logger.info("[MAIN] Superadmin user created successfully")
        else:
            logger.info("[MAIN] Superadmin user already exists")

    app.state.manager = ConnectionManager()
    logger.info("[MAIN] WebSocket manager initialized")
    yield


app = FastAPI(
    title="DineQR API",
    description="Real-Time QR Ordering System API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "Accept", "ngrok-skip-browser-warning"],
)

app.include_router(api_router)


@app.get("/")
async def root():
    logger.api_request("main", "GET", "/")
    logger.api_response("main", "GET", "/", 200)
    return {"message": "DineQR API is running", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    logger.api_request("main", "GET", "/health")
    logger.api_response("main", "GET", "/health", 200)
    return {"status": "healthy"}


@app.websocket("/ws/admin")
async def websocket_admin(
    websocket: WebSocket,
    token: str = Query(...)
):
    """WebSocket endpoint for admin connections with JWT authentication."""
    logger.info("[WEBSOCKET] Admin connection initiated")
    
    # Validate JWT token
    payload = decode_access_token(token)
    if payload is None:
        logger.warning("[WEBSOCKET] Admin connection rejected: Invalid or expired token")
        await websocket.close(code=4001, reason="Invalid or expired token")
        return
    
    user_id = payload.get("sub")
    role = payload.get("role")
    
    if not user_id or role != UserRole.ADMIN.value:
        logger.warning("[WEBSOCKET] Admin connection rejected: Unauthorized")
        await websocket.close(code=4003, reason="Unauthorized: Admin access required")
        return
    
    # Verify user exists and is active
    async with async_session() as db:
        result = await db.execute(select(User).where(User.id == user_id).options(selectinload(User.restaurant)))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            logger.warning("[WEBSOCKET] Admin connection rejected: User not found or inactive")
            await websocket.close(code=4001, reason="User not found or inactive")
            return
        
        restaurant_id = user.restaurant_id
    
    manager = websocket.app.state.manager
    await manager.connect_admin(websocket, restaurant_id)
    logger.info("[WEBSOCKET] Admin connected successfully", user_id=user_id)
    try:
        while True:
            data = await websocket.receive_text()
            logger.info("[WEBSOCKET] Admin received message", data=data[:100])
    except WebSocketDisconnect:
        manager.disconnect_admin(websocket, restaurant_id)
        logger.info("[WEBSOCKET] Admin disconnected", user_id=user_id)


@app.websocket("/ws/table/{table_id}")
async def websocket_table(
    websocket: WebSocket,
    table_id: str,
    token: str = Query(default=None)
):
    """WebSocket endpoint for table connections with optional token validation."""
    logger.info("[WEBSOCKET] Table connection initiated", table_id=table_id)
    
    # Validate table exists
    async with async_session() as db:
        result = await db.execute(select(Table).where(Table.id == table_id).options(selectinload(Table.restaurant)))
        table = result.scalar_one_or_none()
        
        if not table:
            logger.warning("[WEBSOCKET] Table connection rejected: Table not found", table_id=table_id)
            await websocket.close(code=4004, reason="Table not found")
            return
        
        restaurant_id = table.restaurant_id
        
        # If token is provided, validate it (optional for customer connections)
        if token is not None and token != table.qr_token:
            # Try to validate as JWT token (for authenticated sessions)
            payload = decode_access_token(token)
            if payload is None:
                logger.warning("[WEBSOCKET] Table connection rejected: Invalid token", table_id=table_id)
                await websocket.close(code=4001, reason="Invalid token")
                return
    
    manager = websocket.app.state.manager
    await manager.connect_table(websocket, table_id, restaurant_id)
    logger.info("[WEBSOCKET] Table connected successfully", table_id=table_id)
    try:
        while True:
            data = await websocket.receive_text()
            logger.info("[WEBSOCKET] Table received message", table_id=table_id, data=data[:100])
    except WebSocketDisconnect:
        manager.disconnect_table(websocket, table_id)
        logger.info("[WEBSOCKET] Table disconnected", table_id=table_id)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)