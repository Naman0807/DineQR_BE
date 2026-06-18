from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, cast, String, func
from sqlalchemy.orm import selectinload
from typing import List
from decimal import Decimal

from app.database import get_db
from app.models.models import (
    Order, OrderItem, OrderSession, MenuItem, Table, User, Restaurant,
    OrderStatus, OrderItemStatus, SessionStatus
)
from app.schemas import (
    OrderCreate, OrderUpdate, OrderResponse, OrderItemResponse,
    OrderSessionResponse, OrderSessionWithOrdersResponse
)
from app.websocket.manager import ConnectionManager
from app.auth.dependencies import get_current_admin_user, get_current_customer
from app.utils.logger import logger

router = APIRouter(prefix="/api/orders", tags=["Orders"])
SERVICE = "orders"


def get_manager(request: Request) -> ConnectionManager:
    """Get the WebSocket manager from app.state."""
    return request.app.state.manager


def serialize_order_item(item: OrderItem) -> OrderItemResponse:
    """Serialize an OrderItem to OrderItemResponse."""
    return OrderItemResponse(
        id=item.id,
        menu_item_id=item.menu_item_id,
        menu_item_name=item.menu_item.name if item.menu_item else "Unknown",
        quantity=item.quantity,
        unit_price=item.unit_price,
        special_instructions=item.special_instructions,
        status=item.status,
    )


def serialize_order_response(order: Order) -> OrderResponse:
    """Serialize an Order to OrderResponse."""
    return OrderResponse(
        id=order.id,
        session_id=order.session_id,
        customer_id=order.customer_id,
        status=order.status,
        total_amount=order.total_amount,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=[serialize_order_item(item) for item in order.items],
        table_number=order.table_number,
    )


def serialize_order(order: Order) -> dict:
    return {
        "id": order.id,
        "session_id": order.session_id,
        "customer_id": order.customer_id,
        "status": order.status.value,
        "total_amount": float(order.total_amount),
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
        "items": [
            {
                "id": item.id,
                "menu_item_id": item.menu_item_id,
                "menu_item_name": item.menu_item.name if item.menu_item else "Unknown",
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
                "special_instructions": item.special_instructions,
                "status": item.status.value,
            }
            for item in order.items
        ],
        "table_id": order.session.table_id if order.session else None,
        "table_number": order.session.table.table_number if order.session and order.session.table else None,
    }


@router.get("/active", response_model=List[OrderResponse])
async def get_active_orders(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    logger.api_request(SERVICE, "GET", "/active", skip=skip, limit=limit)
    result = await db.execute(
        select(Order)
        .options(
            selectinload(Order.items).selectinload(OrderItem.menu_item),
            selectinload(Order.session).selectinload(OrderSession.table)
        )
        .join(OrderSession)
        .where(
            func.lower(cast(OrderSession.session_status, String)) == SessionStatus.ACTIVE.value,
            OrderSession.restaurant_id == current_user.restaurant_id
        )
        .order_by(Order.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    orders = result.scalars().all()
    logger.api_response(SERVICE, "GET", "/active", 200, count=len(orders))
    return [serialize_order_response(order) for order in orders]


@router.patch("/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: str, 
    update: OrderUpdate, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
    manager: ConnectionManager = Depends(get_manager)
):
    logger.api_request(SERVICE, "PATCH", f"/{order_id}/status", order_id=order_id, status=update.status.value if update.status else None)
    result = await db.execute(
        select(Order)
        .options(
            selectinload(Order.items).selectinload(OrderItem.menu_item),
            selectinload(Order.session).selectinload(OrderSession.table)
        )
        .join(OrderSession)
        .where(
            Order.id == order_id,
            OrderSession.restaurant_id == current_user.restaurant_id
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        logger.api_error(SERVICE, "PATCH", f"/{order_id}/status", "Order not found", order_id=order_id)
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = update.status
    if update.status == OrderStatus.SERVED:
        for item in order.items:
            item.status = OrderItemStatus.COMPLETED

    await db.commit()
    await db.refresh(order)

    result = await db.execute(
        select(Order)
        .options(
            selectinload(Order.items).selectinload(OrderItem.menu_item),
            selectinload(Order.session).selectinload(OrderSession.table)
        )
        .join(OrderSession)
        .where(
            Order.id == order_id,
            OrderSession.restaurant_id == current_user.restaurant_id
        )
    )
    order = result.scalar_one()

    await manager.broadcast_order_updated(serialize_order(order), order.session.table_id, order.session.table.restaurant_id)
    logger.api_response(SERVICE, "PATCH", f"/{order_id}/status", 200, order_id=order_id, status=update.status.value)

    return serialize_order_response(order)


@router.post("/{restaurant_slug}/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    restaurant_slug: str,
    order: OrderCreate, 
    db: AsyncSession = Depends(get_db),
    manager: ConnectionManager = Depends(get_manager),
    customer_payload: dict = Depends(get_current_customer)
):
    logger.api_request(SERVICE, "POST", f"/{restaurant_slug}/", session_id=order.session_id, item_count=len(order.items))
    
    result = await db.execute(select(Restaurant).where(Restaurant.slug == restaurant_slug))
    restaurant = result.scalar_one_or_none()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    result = await db.execute(
        select(OrderSession)
        .options(selectinload(OrderSession.table))
        .where(OrderSession.id == order.session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        logger.api_error(SERVICE, "POST", f"/{restaurant_slug}/", "Session not found", session_id=order.session_id)
        raise HTTPException(status_code=404, detail="Session not found")
    if session.restaurant_id != restaurant.id:
        raise HTTPException(status_code=403, detail="Session does not belong to this restaurant")
    if session.session_status != SessionStatus.ACTIVE:
        logger.api_error(SERVICE, "POST", f"/{restaurant_slug}/", "Session is not active", session_id=order.session_id)
        raise HTTPException(status_code=400, detail="Session is not active")

    # Ensure the token belongs to the session they are trying to order for
    if customer_payload.get("session_id") != order.session_id:
        raise HTTPException(status_code=403, detail="Token does not match the active session.")

    total_amount = Decimal("0.00")
    order_items = []

    for item_data in order.items:
        result = await db.execute(select(MenuItem).where(MenuItem.id == item_data.menu_item_id))
        menu_item = result.scalar_one_or_none()
        if not menu_item:
            logger.api_error(SERVICE, "POST", "/", f"Menu item {item_data.menu_item_id} not found", menu_item_id=item_data.menu_item_id)
            raise HTTPException(status_code=404, detail=f"Menu item {item_data.menu_item_id} not found")
        if not menu_item.is_available:
            logger.api_error(SERVICE, "POST", "/", f"Menu item {menu_item.name} is not available", menu_item=menu_item.name)
            raise HTTPException(status_code=400, detail=f"Menu item {menu_item.name} is not available")

        order_item = OrderItem(
            menu_item_id=item_data.menu_item_id,
            quantity=item_data.quantity,
            unit_price=menu_item.price,
            special_instructions=item_data.special_instructions,
        )
        order_items.append(order_item)
        total_amount += menu_item.price * item_data.quantity

    db_order = Order(
        session_id=order.session_id,
        customer_id=customer_payload.get("sub"),
        total_amount=total_amount,
        status=OrderStatus.RECEIVED,
    )
    db_order.items = order_items
    db.add(db_order)
    await db.commit()
    await db.refresh(db_order)

    result = await db.execute(
        select(Order)
        .options(
            selectinload(Order.items).selectinload(OrderItem.menu_item),
            selectinload(Order.session).selectinload(OrderSession.table)
        )
        .where(Order.id == db_order.id)
    )
    db_order = result.scalar_one()

    await manager.broadcast_order_created(serialize_order(db_order), session.table_id, session.table.restaurant_id)
    logger.api_response(SERVICE, "POST", f"/{restaurant_slug}/", 201, order_id=str(db_order.id), total_amount=float(total_amount))

    return serialize_order_response(db_order)


@router.get("/{restaurant_slug}/session/{session_id}", response_model=List[OrderResponse])
async def get_orders_by_session(restaurant_slug: str, session_id: str, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "GET", f"/{restaurant_slug}/session/{session_id}", session_id=session_id)
    
    result = await db.execute(select(Restaurant).where(Restaurant.slug == restaurant_slug))
    restaurant = result.scalar_one_or_none()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    result = await db.execute(
        select(Order)
        .options(
            selectinload(Order.items).selectinload(OrderItem.menu_item),
            selectinload(Order.session).selectinload(OrderSession.table)
        )
        .join(OrderSession)
        .where(
            Order.session_id == session_id,
            OrderSession.restaurant_id == restaurant.id
        )
        .order_by(Order.created_at.desc())
    )
    orders = result.scalars().all()
    logger.api_response(SERVICE, "GET", f"/{restaurant_slug}/session/{session_id}", 200, count=len(orders))
    return [serialize_order_response(order) for order in orders]


@router.get("/{restaurant_slug}/{order_id}", response_model=OrderResponse)
async def get_order(restaurant_slug: str, order_id: str, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "GET", f"/{restaurant_slug}/{order_id}", order_id=order_id)
    
    result = await db.execute(select(Restaurant).where(Restaurant.slug == restaurant_slug))
    restaurant = result.scalar_one_or_none()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    result = await db.execute(
        select(Order)
        .options(
            selectinload(Order.items).selectinload(OrderItem.menu_item),
            selectinload(Order.session).selectinload(OrderSession.table)
        )
        .join(OrderSession)
        .where(
            Order.id == order_id,
            OrderSession.restaurant_id == restaurant.id
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        logger.api_error(SERVICE, "GET", f"/{restaurant_slug}/{order_id}", "Order not found", order_id=order_id)
        raise HTTPException(status_code=404, detail="Order not found")
    logger.api_response(SERVICE, "GET", f"/{restaurant_slug}/{order_id}", 200, order_id=order_id)
    return serialize_order_response(order)


@router.get("/{restaurant_slug}/sessions/{session_id}", response_model=OrderSessionWithOrdersResponse)
async def get_session_with_orders(restaurant_slug: str, session_id: str, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "GET", f"/{restaurant_slug}/sessions/{session_id}", session_id=session_id)
    
    result = await db.execute(select(Restaurant).where(Restaurant.slug == restaurant_slug))
    restaurant = result.scalar_one_or_none()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    result = await db.execute(
        select(OrderSession)
        .options(
            selectinload(OrderSession.table),
            selectinload(OrderSession.orders).selectinload(Order.items).selectinload(OrderItem.menu_item)
        )
        .where(
            OrderSession.id == session_id,
            OrderSession.restaurant_id == restaurant.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        logger.api_error(SERVICE, "GET", f"/{restaurant_slug}/sessions/{session_id}", "Session not found", session_id=session_id)
        raise HTTPException(status_code=404, detail="Session not found")

    logger.api_response(SERVICE, "GET", f"/{restaurant_slug}/sessions/{session_id}", 200, session_id=session_id, order_count=len(session.orders))

    return OrderSessionWithOrdersResponse(
        id=session.id,
        table_id=session.table_id,
        table_number=session.table.table_number,
        session_status=session.session_status,
        started_at=session.started_at,
        ended_at=session.ended_at,
        orders=[serialize_order_response(order) for order in session.orders],
    )
