from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
from decimal import Decimal
from datetime import datetime as dt, timezone, timedelta

from app.database import get_db
from app.models.models import (
    Bill, Order, OrderSession, OrderItem, Table, User, Restaurant,
    SessionStatus, PaymentStatus, TableStatus, OrderStatus
)
from app.schemas import (
    BillCreate, BillUpdate, BillResponse, BillWithOrdersResponse,
    OrderResponse, OrderItemResponse
)
from app.auth.dependencies import get_current_admin_user
from app.utils.logger import logger
from app.utils.pdf_generator import generate_bill_pdf

router = APIRouter(prefix="/api/bills", tags=["Bills"])
SERVICE = "bills"
IST = timezone(timedelta(hours=5, minutes=30))


@router.post("/", response_model=BillResponse, status_code=status.HTTP_201_CREATED)
async def create_bill(
    bill: BillCreate, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    logger.api_request(SERVICE, "POST", "/", session_id=bill.session_id)
    try:
        result = await db.execute(
            select(OrderSession)
            .options(selectinload(OrderSession.table))
            .where(OrderSession.id == bill.session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            logger.api_error(SERVICE, "POST", "/", "Session not found", session_id=bill.session_id)
            raise HTTPException(status_code=404, detail="Session not found")
        if session.restaurant_id != current_user.restaurant_id:
            logger.api_error(SERVICE, "POST", "/", "Session belongs to different restaurant", session_id=bill.session_id)
            raise HTTPException(status_code=403, detail="Session belongs to a different restaurant")
        if session.session_status != SessionStatus.ACTIVE:
            logger.api_error(SERVICE, "POST", "/", "Session is not active", session_id=bill.session_id)
            raise HTTPException(status_code=400, detail="Session is not active")

        result = await db.execute(
            select(Bill).where(Bill.session_id == bill.session_id)
        )
        existing_bill = result.scalar_one_or_none()
        if existing_bill:
            logger.api_error(SERVICE, "POST", "/", "Bill already exists", session_id=bill.session_id)
            raise HTTPException(status_code=400, detail="Bill already exists for this session")

        result = await db.execute(
            select(Order).where(Order.session_id == bill.session_id)
        )
        orders = result.scalars().all()

        subtotal = sum(order.total_amount for order in orders)
        final_total = subtotal + bill.tax_amount - bill.discount_amount

        db_bill = Bill(
            session_id=bill.session_id,
            subtotal=subtotal,
            tax_amount=bill.tax_amount,
            discount_amount=bill.discount_amount,
            final_total=final_total,
            payment_status=PaymentStatus.UNPAID,
        )
        db.add(db_bill)
        await db.commit()
        
        # Eagerly load session and table relationships for response serialization
        result = await db.execute(
            select(Bill)
            .options(selectinload(Bill.session).selectinload(OrderSession.table))
            .where(Bill.id == db_bill.id)
        )
        db_bill = result.scalar_one()
        
        logger.api_response(SERVICE, "POST", "/", 201, bill_id=str(db_bill.id), final_total=float(final_total))
        return db_bill
    except HTTPException:
        raise
    except Exception as e:
        logger.api_error(SERVICE, "POST", "/", str(e), session_id=bill.session_id)
        raise


@router.get("/{restaurant_slug}/session/{session_id}", response_model=BillWithOrdersResponse)
async def get_bill_by_session(restaurant_slug: str, session_id: str, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "GET", f"/{restaurant_slug}/session/{session_id}", session_id=session_id)
    result = await db.execute(select(Restaurant).where(Restaurant.slug == restaurant_slug))
    restaurant = result.scalar_one_or_none()
    if not restaurant:
        logger.api_error(SERVICE, "GET", f"/{restaurant_slug}/session/{session_id}", "Restaurant not found")
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    result = await db.execute(
        select(Bill)
        .options(
            selectinload(Bill.session).selectinload(OrderSession.table),
            selectinload(Bill.session)
            .selectinload(OrderSession.orders)
            .selectinload(Order.items)
            .selectinload(OrderItem.menu_item),
        )
        .join(OrderSession, Bill.session_id == OrderSession.id)
        .where(Bill.session_id == session_id, OrderSession.restaurant_id == restaurant.id)
    )
    bill = result.scalar_one_or_none()
    if not bill:
        logger.api_error(SERVICE, "GET", f"/{restaurant_slug}/session/{session_id}", "Bill not found", session_id=session_id)
        raise HTTPException(status_code=404, detail="Bill not found")
    logger.api_response(SERVICE, "GET", f"/{restaurant_slug}/session/{session_id}", 200, bill_id=str(bill.id))
    
    orders_data = []
    for order in (bill.session.orders if bill.session else []):
        items_data = [
            OrderItemResponse(
                id=str(item.id),
                menu_item_id=str(item.menu_item_id),
                menu_item_name=item.menu_item.name if item.menu_item else "",
                quantity=item.quantity,
                unit_price=item.unit_price,
                special_instructions=item.special_instructions,
                status=item.status
            )
            for item in order.items
        ]
        orders_data.append(OrderResponse(
            id=str(order.id),
            session_id=str(order.session_id),
            status=order.status,
            total_amount=order.total_amount,
            created_at=order.created_at,
            updated_at=order.updated_at,
            items=items_data,
            table_number=order.table_number,
        ))
    
    return BillWithOrdersResponse(
        id=str(bill.id),
        session_id=str(bill.session_id),
        subtotal=bill.subtotal,
        tax_amount=bill.tax_amount,
        discount_amount=bill.discount_amount,
        final_total=bill.final_total,
        payment_status=bill.payment_status,
        payment_method=bill.payment_method,
        created_at=bill.created_at,
        paid_at=bill.paid_at,
        orders=orders_data
    )


@router.get("/by-session/{session_id}", response_model=BillWithOrdersResponse)
async def get_bill_by_session_for_admin(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    logger.api_request(SERVICE, "GET", f"/by-session/{session_id}", session_id=session_id)
    result = await db.execute(
        select(Bill)
        .options(
            selectinload(Bill.session).selectinload(OrderSession.table),
            selectinload(Bill.session)
            .selectinload(OrderSession.orders)
            .selectinload(Order.items)
            .selectinload(OrderItem.menu_item),
        )
        .join(OrderSession, Bill.session_id == OrderSession.id)
        .where(Bill.session_id == session_id, OrderSession.restaurant_id == current_user.restaurant_id)
    )
    bill = result.scalar_one_or_none()
    if not bill:
        logger.api_error(SERVICE, "GET", f"/by-session/{session_id}", "Bill not found", session_id=session_id)
        raise HTTPException(status_code=404, detail="Bill not found")
    logger.api_response(SERVICE, "GET", f"/by-session/{session_id}", 200, bill_id=str(bill.id))

    orders_data = []
    for order in (bill.session.orders if bill.session else []):
        items_data = [
            OrderItemResponse(
                id=str(item.id),
                menu_item_id=str(item.menu_item_id),
                menu_item_name=item.menu_item.name if item.menu_item else "",
                quantity=item.quantity,
                unit_price=item.unit_price,
                special_instructions=item.special_instructions,
                status=item.status,
            )
            for item in order.items
        ]
        orders_data.append(
            OrderResponse(
                id=str(order.id),
                session_id=str(order.session_id),
                status=order.status,
                total_amount=order.total_amount,
                created_at=order.created_at,
                updated_at=order.updated_at,
                items=items_data,
                table_number=order.table_number,
            )
        )

    return BillWithOrdersResponse(
        id=str(bill.id),
        session_id=str(bill.session_id),
        subtotal=bill.subtotal,
        tax_amount=bill.tax_amount,
        discount_amount=bill.discount_amount,
        final_total=bill.final_total,
        payment_status=bill.payment_status,
        payment_method=bill.payment_method,
        created_at=bill.created_at,
        paid_at=bill.paid_at,
        orders=orders_data,
    )


@router.get("/{bill_id}/pdf", response_model=None)
async def get_bill_pdf(
    bill_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Generate PDF for a specific bill."""
    logger.api_request(SERVICE, "GET", f"/{bill_id}/pdf", bill_id=bill_id)
    
    result = await db.execute(
        select(Bill)
        .options(
            selectinload(Bill.session).selectinload(OrderSession.table),
            selectinload(Bill.session)
            .selectinload(OrderSession.orders)
            .selectinload(Order.items)
            .selectinload(OrderItem.menu_item),
        )
        .join(OrderSession, Bill.session_id == OrderSession.id)
        .where(Bill.id == bill_id, OrderSession.restaurant_id == current_user.restaurant_id)
    )
    bill = result.scalar_one_or_none()
    
    if not bill:
        logger.api_error(SERVICE, "GET", f"/{bill_id}/pdf", "Bill not found", bill_id=bill_id)
        raise HTTPException(status_code=404, detail="Bill not found")
    
    # Get restaurant details
    result = await db.execute(
        select(Restaurant).where(Restaurant.id == current_user.restaurant_id)
    )
    restaurant = result.scalar_one_or_none()
    
    # Get table number from the loaded session
    table_number = 0
    if bill.session and bill.session.table:
        table_number = bill.session.table.table_number
    
    # Build orders data for PDF
    orders_data = []
    for order in (bill.session.orders if bill.session else []):
        items_data = [
            {
                "menu_item_name": item.menu_item.name if item.menu_item else "Unknown",
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
            }
            for item in order.items
        ]
        orders_data.append({"items": items_data})
    
    # Generate PDF
    pdf_bytes = generate_bill_pdf(
        restaurant_name=restaurant.name if restaurant else "Restaurant",
        restaurant_address=restaurant.address if restaurant and restaurant.address else "",
        restaurant_phone=restaurant.phone if restaurant and restaurant.phone else "",
        table_number=table_number,
        bill_date=bill.created_at,
        orders=orders_data,
        subtotal=bill.subtotal,
        tax_amount=bill.tax_amount,
        discount_amount=bill.discount_amount,
        final_total=bill.final_total,
        payment_status=bill.payment_status.value,
        payment_method=bill.payment_method.value if bill.payment_method else None,
    )
    
    logger.api_response(SERVICE, "GET", f"/{bill_id}/pdf", 200, bill_id=bill_id)
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=bill_{bill_id}.pdf"}
    )

@router.get("/{bill_id}/details", response_model=BillWithOrdersResponse)
async def get_bill_details(
    bill_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Get full details of a specific bill including all orders and items."""
    logger.api_request(SERVICE, "GET", f"/{bill_id}/details", bill_id=bill_id)
    result = await db.execute(
        select(Bill)
        .options(
            selectinload(Bill.session).selectinload(OrderSession.table),
            selectinload(Bill.session)
            .selectinload(OrderSession.orders)
            .selectinload(Order.items)
            .selectinload(OrderItem.menu_item),
        )
        .join(OrderSession, Bill.session_id == OrderSession.id)
        .where(Bill.id == bill_id, OrderSession.restaurant_id == current_user.restaurant_id)
    )
    bill = result.scalar_one_or_none()
    if not bill:
        logger.api_error(SERVICE, "GET", f"/{bill_id}/details", "Bill not found", bill_id=bill_id)
        raise HTTPException(status_code=404, detail="Bill not found")
    
    logger.api_response(SERVICE, "GET", f"/{bill_id}/details", 200, bill_id=str(bill.id))

    orders_data = []
    for order in (bill.session.orders if bill.session else []):
        items_data = [
            OrderItemResponse(
                id=str(item.id),
                menu_item_id=str(item.menu_item_id),
                menu_item_name=item.menu_item.name if item.menu_item else "",
                quantity=item.quantity,
                unit_price=item.unit_price,
                special_instructions=item.special_instructions,
                status=item.status,
            )
            for item in order.items
        ]
        orders_data.append(
            OrderResponse(
                id=str(order.id),
                session_id=str(order.session_id),
                status=order.status,
                total_amount=order.total_amount,
                created_at=order.created_at,
                updated_at=order.updated_at,
                items=items_data,
                table_number=order.table_number,
            )
        )

    return BillWithOrdersResponse(
        id=str(bill.id),
        session_id=str(bill.session_id),
        subtotal=bill.subtotal,
        tax_amount=bill.tax_amount,
        discount_amount=bill.discount_amount,
        final_total=bill.final_total,
        payment_status=bill.payment_status,
        payment_method=bill.payment_method,
        created_at=bill.created_at,
        paid_at=bill.paid_at,
        orders=orders_data,
    )


@router.get("/{restaurant_slug}/{bill_id}", response_model=BillResponse)
async def get_bill(restaurant_slug: str, bill_id: str, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "GET", f"/{restaurant_slug}/{bill_id}", bill_id=bill_id)
    result = await db.execute(select(Restaurant).where(Restaurant.slug == restaurant_slug))
    restaurant = result.scalar_one_or_none()
    if not restaurant:
        logger.api_error(SERVICE, "GET", f"/{restaurant_slug}/{bill_id}", "Restaurant not found")
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    result = await db.execute(
        select(Bill)
        .join(OrderSession, Bill.session_id == OrderSession.id)
        .options(selectinload(Bill.session).selectinload(OrderSession.table))
        .where(Bill.id == bill_id, OrderSession.restaurant_id == restaurant.id)
    )
    bill = result.scalar_one_or_none()
    if not bill:
        logger.api_error(SERVICE, "GET", f"/{restaurant_slug}/{bill_id}", "Bill not found", bill_id=bill_id)
        raise HTTPException(status_code=404, detail="Bill not found")
    logger.api_response(SERVICE, "GET", f"/{restaurant_slug}/{bill_id}", 200, bill_id=bill_id)
    return bill




@router.patch("/{bill_id}", response_model=BillResponse)
async def update_bill(
    bill_id: str, 
    update: BillUpdate, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    logger.api_request(SERVICE, "PATCH", f"/{bill_id}", bill_id=bill_id)
    result = await db.execute(
        select(Bill)
        .options(selectinload(Bill.session).selectinload(OrderSession.table))
        .join(OrderSession, Bill.session_id == OrderSession.id)
        .where(Bill.id == bill_id, OrderSession.restaurant_id == current_user.restaurant_id)
    )
    bill = result.scalar_one_or_none()
    if not bill:
        logger.api_error(SERVICE, "PATCH", f"/{bill_id}", "Bill not found", bill_id=bill_id)
        raise HTTPException(status_code=404, detail="Bill not found")

    if update.discount_amount is not None:
        bill.discount_amount = update.discount_amount
        bill.final_total = bill.subtotal + bill.tax_amount - bill.discount_amount

    if update.payment_status == PaymentStatus.PAID:
        bill.payment_status = PaymentStatus.PAID
        bill.payment_method = update.payment_method
        bill.paid_at = dt.now(IST)

        bill.session.session_status = SessionStatus.CLOSED
        bill.session.ended_at = dt.now(IST)
        bill.session.table.status = TableStatus.AVAILABLE

    await db.commit()
    await db.refresh(bill)
    logger.api_response(SERVICE, "PATCH", f"/{bill_id}", 200, bill_id=bill_id, payment_status=bill.payment_status.value)
    return bill


@router.post("/{bill_id}/pay", response_model=BillResponse)
async def pay_bill(
    bill_id: str, 
    payment_method: str, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    logger.api_request(SERVICE, "POST", f"/{bill_id}/pay", bill_id=bill_id, payment_method=payment_method)
    result = await db.execute(
        select(Bill)
        .options(selectinload(Bill.session).selectinload(OrderSession.table))
        .join(OrderSession, Bill.session_id == OrderSession.id)
        .where(Bill.id == bill_id, OrderSession.restaurant_id == current_user.restaurant_id)
    )
    bill = result.scalar_one_or_none()
    if not bill:
        logger.api_error(SERVICE, "POST", f"/{bill_id}/pay", "Bill not found", bill_id=bill_id)
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.payment_status == PaymentStatus.PAID:
        logger.api_error(SERVICE, "POST", f"/{bill_id}/pay", "Bill already paid", bill_id=bill_id)
        raise HTTPException(status_code=400, detail="Bill already paid")

    bill.payment_status = PaymentStatus.PAID
    bill.payment_method = payment_method
    bill.paid_at = dt.utcnow()

    bill.session.session_status = SessionStatus.CLOSED
    bill.session.ended_at = dt.utcnow()
    bill.session.table.status = TableStatus.AVAILABLE

    await db.commit()
    await db.refresh(bill)
    logger.api_response(SERVICE, "POST", f"/{bill_id}/pay", 200, bill_id=bill_id, status="paid")
    return bill


@router.get("/", response_model=List[BillResponse])
async def get_all_bills(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records to return"),
    start_date: Optional[dt] = Query(None, description="Filter bills from this date"),
    end_date: Optional[dt] = Query(None, description="Filter bills until this date"),
    payment_status: Optional[PaymentStatus] = Query(None, description="Filter by payment status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Get all bills for the restaurant with optional filtering."""
    logger.api_request(SERVICE, "GET", "/", skip=skip, limit=limit, 
                       start_date=start_date, end_date=end_date, payment_status=payment_status)
    
    query = (
        select(Bill)
        .join(OrderSession, Bill.session_id == OrderSession.id)
        .options(selectinload(Bill.session).selectinload(OrderSession.table))
        .where(OrderSession.restaurant_id == current_user.restaurant_id)
    )
    
    # Add date range filter
    if start_date:
        query = query.where(Bill.created_at >= start_date)
    if end_date:
        query = query.where(Bill.created_at <= end_date)
    
    # Add payment status filter
    if payment_status:
        query = query.where(Bill.payment_status == payment_status)
    
    query = query.order_by(Bill.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    bills = result.scalars().all()
    logger.api_response(SERVICE, "GET", "/", 200, count=len(bills))
    return bills


