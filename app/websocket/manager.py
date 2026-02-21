from fastapi import WebSocket
from typing import Dict, Set
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.admin_connections: Set[WebSocket] = set()
        self.table_connections: Dict[str, Set[WebSocket]] = {}

    async def connect_admin(self, websocket: WebSocket):
        await websocket.accept()
        self.admin_connections.add(websocket)
        logger.info(f"Admin connected. Total admin connections: {len(self.admin_connections)}")

    async def connect_table(self, websocket: WebSocket, table_id: str):
        await websocket.accept()
        if table_id not in self.table_connections:
            self.table_connections[table_id] = set()
        self.table_connections[table_id].add(websocket)
        logger.info(f"Table {table_id} connected. Total connections for table: {len(self.table_connections[table_id])}")

    def disconnect_admin(self, websocket: WebSocket):
        self.admin_connections.discard(websocket)
        logger.info(f"Admin disconnected. Total admin connections: {len(self.admin_connections)}")

    def disconnect_table(self, websocket: WebSocket, table_id: str):
        if table_id in self.table_connections:
            self.table_connections[table_id].discard(websocket)
            if not self.table_connections[table_id]:
                del self.table_connections[table_id]
        logger.info(f"Table {table_id} disconnected")

    async def broadcast_to_admins(self, event_type: str, data: dict):
        message = json.dumps({"event": event_type, "data": data})
        disconnected = set()
        for connection in self.admin_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.add(connection)
        for conn in disconnected:
            self.admin_connections.discard(conn)

    async def broadcast_to_table(self, table_id: str, event_type: str, data: dict):
        message = json.dumps({"event": event_type, "data": data})
        if table_id in self.table_connections:
            disconnected = set()
            for connection in self.table_connections[table_id]:
                try:
                    await connection.send_text(message)
                except Exception:
                    disconnected.add(connection)
            for conn in disconnected:
                self.table_connections[table_id].discard(conn)

    async def broadcast_order_created(self, order_data: dict, table_id: str):
        await self.broadcast_to_admins("order_created", order_data)

    async def broadcast_order_updated(self, order_data: dict, table_id: str):
        await self.broadcast_to_admins("order_updated", order_data)
        await self.broadcast_to_table(table_id, "order_updated", order_data)

    async def broadcast_item_status_updated(self, item_data: dict, table_id: str):
        await self.broadcast_to_table(table_id, "item_status_updated", item_data)


manager = ConnectionManager()
