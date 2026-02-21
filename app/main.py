from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

import uvicorn

from app.config import get_settings
from app.database import init_db
from app.routes import api_router
from app.websocket.manager import manager
from app.utils.logger import logger

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[MAIN] Initializing database...")
    await init_db()
    logger.info("[MAIN] Database initialized successfully")
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
    allow_methods=["*"],
    allow_headers=["*"],
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
async def websocket_admin(websocket: WebSocket):
    logger.info("[WEBSOCKET] Admin connection initiated")
    await manager.connect_admin(websocket)
    logger.info("[WEBSOCKET] Admin connected successfully")
    try:
        while True:
            data = await websocket.receive_text()
            logger.info("[WEBSOCKET] Admin received message", data=data[:100])
    except WebSocketDisconnect:
        manager.disconnect_admin(websocket)
        logger.info("[WEBSOCKET] Admin disconnected")


@app.websocket("/ws/table/{table_id}")
async def websocket_table(websocket: WebSocket, table_id: str):
    logger.info("[WEBSOCKET] Table connection initiated", table_id=table_id)
    await manager.connect_table(websocket, table_id)
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