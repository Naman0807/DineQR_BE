from fastapi import WebSocket
from typing import Dict, Set, Optional
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.admin_connections: Dict[str, Set[WebSocket]] = {}
        self.table_connections: Dict[str, Set[WebSocket]] = {}
        self.table_restaurant_map: Dict[str, str] = {}

    async def connect_admin(self, websocket: WebSocket, restaurant_id: str):
        await websocket.accept()
        if restaurant_id not in self.admin_connections:
            self.admin_connections[restaurant_id] = set()
        self.admin_connections[restaurant_id].add(websocket)
        logger.info(f"Admin connected for restaurant {restaurant_id}. Total admin connections: {len(self.admin_connections[restaurant_id])}")

    async def connect_table(self, websocket: WebSocket, table_id: str, restaurant_id: Optional[str] = None):
        await websocket.accept()
        if table_id not in self.table_connections:
            self.table_connections[table_id] = set()
        self.table_connections[table_id].add(websocket)
        if restaurant_id:
            self.table_restaurant_map[table_id] = restaurant_id
        logger.info(f"Table {table_id} connected. Total connections for table: {len(self.table_connections[table_id])}")

    def disconnect_admin(self, websocket: WebSocket, restaurant_id: str):
        if restaurant_id in self.admin_connections:
            self.admin_connections[restaurant_id].discard(websocket)
            if not self.admin_connections[restaurant_id]:
                del self.admin_connections[restaurant_id]
        logger.info(f"Admin disconnected from restaurant {restaurant_id}")

    def disconnect_table(self, websocket: WebSocket, table_id: str):
        if table_id in self.table_connections:
            self.table_connections[table_id].discard(websocket)
            if not self.table_connections[table_id]:
                del self.table_connections[table_id]
        if table_id in self.table_restaurant_map:
            del self.table_restaurant_map[table_id]
        logger.info(f"Table {table_id} disconnected")

    async def broadcast_to_admins(self, event_type: str, data: dict, restaurant_id: Optional[str] = None):
        message = json.dumps({"event": event_type, "data": data})
        
        if restaurant_id:
            target_restaurants = [restaurant_id] if restaurant_id in self.admin_connections else []
        else:
            target_restaurants = list(self.admin_connections.keys())
        
        for rid in target_restaurants:
            disconnected = set()
            for connection in self.admin_connections.get(rid, set()):
                try:
                    await connection.send_text(message)
                except Exception:
                    disconnected.add(connection)
            for conn in disconnected:
                self.admin_connections[rid].discard(conn)

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

    async def broadcast_order_created(self, order_data: dict, table_id: str, restaurant_id: Optional[str] = None):
        await self.broadcast_to_admins("order_created", order_data, restaurant_id)

    async def broadcast_order_updated(self, order_data: dict, table_id: str, restaurant_id: Optional[str] = None):
        await self.broadcast_to_admins("order_updated", order_data, restaurant_id)
        await self.broadcast_to_table(table_id, "order_updated", order_data)

    async def broadcast_item_status_updated(self, item_data: dict, table_id: str):
        await self.broadcast_to_table(table_id, "item_status_updated", item_data)


manager = ConnectionManager()
