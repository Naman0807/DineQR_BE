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
    Bill, Payment, Order, OrderSession, OrderItem, Table, User, Restaurant,
    SessionStatus, PaymentStatus, PaymentMethod, TableStatus, OrderStatus
)
from app.schemas import (
    BillCreate, BillUpdate, BillResponse, BillWithOrdersResponse,
    PayBillRequest, PaymentResponse,
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
            restaurant_id=current_user.restaurant_id,
        )
        db.add(db_bill)
        await db.commit()

        result = await db.execute(
            select(Bill)
            .options(
                selectinload(Bill.session).selectinload(OrderSession.table),
                selectinload(Bill.payments),
            )
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


def _build_bill_with_orders(bill: Bill) -> BillWithOrdersResponse:
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
        orders_data.append(OrderResponse(
            id=str(order.id),
            session_id=str(order.session_id),
            customer_id=order.customer_id,
            status=order.status,
            total_amount=order.total_amount,
            created_at=order.created_at,
            updated_at=order.updated_at,
            items=items_data,
            table_number=order.table_number,
        ))

    payments_data = [
        PaymentResponse(
            id=str(p.id),
            bill_id=str(p.bill_id),
            customer_id=p.customer_id,
            amount=p.amount,
            payment_method=p.payment_method,
            status=p.status,
            created_at=p.created_at,
        )
        for p in (bill.payments or [])
    ]

    return BillWithOrdersResponse(
        id=str(bill.id),
        session_id=str(bill.session_id),
        subtotal=bill.subtotal,
        tax_amount=bill.tax_amount,
        discount_amount=bill.discount_amount,
        final_total=bill.final_total,
        created_at=bill.created_at,
        paid_at=bill.paid_at,
        table_number=bill.table_number,
        orders=orders_data,
        payments=payments_data,
    )


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
            selectinload(Bill.payments),
        )
        .join(OrderSession, Bill.session_id == OrderSession.id)
        .where(Bill.session_id == session_id, OrderSession.restaurant_id == restaurant.id)
    )
    bill = result.scalar_one_or_none()
    if not bill:
        logger.api_error(SERVICE, "GET", f"/{restaurant_slug}/session/{session_id}", "Bill not found", session_id=session_id)
        raise HTTPException(status_code=404, detail="Bill not found")
    logger.api_response(SERVICE, "GET", f"/{restaurant_slug}/session/{session_id}", 200, bill_id=str(bill.id))
    return _build_bill_with_orders(bill)


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
            selectinload(Bill.payments),
        )
        .join(OrderSession, Bill.session_id == OrderSession.id)
        .where(Bill.session_id == session_id, OrderSession.restaurant_id == current_user.restaurant_id)
    )
    bill = result.scalar_one_or_none()
    if not bill:
        logger.api_error(SERVICE, "GET", f"/by-session/{session_id}", "Bill not found", session_id=session_id)
        raise HTTPException(status_code=404, detail="Bill not found")
    logger.api_response(SERVICE, "GET", f"/by-session/{session_id}", 200, bill_id=str(bill.id))
    return _build_bill_with_orders(bill)


@router.get("/{bill_id}/details", response_model=BillWithOrdersResponse)
async def get_bill_details(
    bill_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Get full details of a specific bill including all orders, items, and payments."""
    logger.api_request(SERVICE, "GET", f"/{bill_id}/details", bill_id=bill_id)
    result = await db.execute(
        select(Bill)
        .options(
            selectinload(Bill.session).selectinload(OrderSession.table),
            selectinload(Bill.session)
            .selectinload(OrderSession.orders)
            .selectinload(Order.items)
            .selectinload(OrderItem.menu_item),
            selectinload(Bill.payments),
        )
        .join(OrderSession, Bill.session_id == OrderSession.id)
        .where(Bill.id == bill_id, OrderSession.restaurant_id == current_user.restaurant_id)
    )
    bill = result.scalar_one_or_none()
    if not bill:
        logger.api_error(SERVICE, "GET", f"/{bill_id}/details", "Bill not found", bill_id=bill_id)
        raise HTTPException(status_code=404, detail="Bill not found")
    logger.api_response(SERVICE, "GET", f"/{bill_id}/details", 200, bill_id=str(bill.id))
    return _build_bill_with_orders(bill)




@router.get("/{bill_id}/pdf", response_model=None)
async def get_bill_pdf(
    bill_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Generate PDF for a specific bill."""
    logger.api_request(SERVICE, "GET", f"/{bill_id}/pdf", bill_id=bill_id)
    logger.info(f"Generating PDF for bill: {bill_id}")
    logger.info(f"Current user: {current_user.id}, restaurant_id: {current_user.restaurant_id}")
    result = await db.execute(
        select(Bill)
        .options(
            selectinload(Bill.session).selectinload(OrderSession.table),
            selectinload(Bill.session)
            .selectinload(OrderSession.orders)
            .selectinload(Order.items)
            .selectinload(OrderItem.menu_item),
            selectinload(Bill.payments),
        )
        .join(OrderSession, Bill.session_id == OrderSession.id)
        .where(Bill.id == bill_id, OrderSession.restaurant_id == current_user.restaurant_id)
    )
    bill = result.scalar_one_or_none()

    if not bill:
        logger.api_error(SERVICE, "GET", f"/{bill_id}/pdf", "Bill not found", bill_id=bill_id)
        raise HTTPException(status_code=404, detail="Bill not found")

    result = await db.execute(
        select(Restaurant).where(Restaurant.id == current_user.restaurant_id)
    )
    restaurant = result.scalar_one_or_none()

    table_number = 0
    if bill.session and bill.session.table:
        table_number = bill.session.table.table_number

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

    payments_data = []
    for p in (bill.payments or []):
        payments_data.append({
            "amount": float(p.amount),
            "payment_method": p.payment_method.value if hasattr(p.payment_method, 'value') else str(p.payment_method),
            "status": p.status.value if hasattr(p.status, 'value') else str(p.status),
        })

    total_paid = sum(p["amount"] for p in payments_data if p["status"] == "completed")
    payment_status = "paid" if total_paid >= float(bill.final_total) else "partial" if total_paid > 0 else "unpaid"

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
        payment_status=payment_status,
        payments=payments_data,
    )

    logger.api_response(SERVICE, "GET", f"/{bill_id}/pdf", 200, bill_id=bill_id)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=bill_{bill_id}.pdf"}
    )


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
        .options(
            selectinload(Bill.session).selectinload(OrderSession.table),
            selectinload(Bill.payments),
        )
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

    await db.commit()
    await db.refresh(bill)
    logger.api_response(SERVICE, "PATCH", f"/{bill_id}", 200, bill_id=bill_id)
    return bill




@router.get("/{bill_id}/payments", response_model=List[PaymentResponse])
async def get_bill_payments(
    bill_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """List all payments for a bill."""
    logger.api_request(SERVICE, "GET", f"/{bill_id}/payments", bill_id=bill_id)

    result = await db.execute(
        select(Bill)
        .join(OrderSession, Bill.session_id == OrderSession.id)
        .where(Bill.id == bill_id, OrderSession.restaurant_id == current_user.restaurant_id)
    )
    bill = result.scalar_one_or_none()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    result = await db.execute(
        select(Payment).where(Payment.bill_id == bill_id).order_by(Payment.created_at.desc())
    )
    payments = result.scalars().all()
    logger.api_response(SERVICE, "GET", f"/{bill_id}/payments", 200, count=len(payments))
    return payments


@router.post("/{bill_id}/pay", response_model=BillResponse)
async def pay_bill(
    bill_id: str,
    pay_request: PayBillRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Pay a bill in full. Creates a single Payment record."""
    logger.api_request(SERVICE, "POST", f"/{bill_id}/pay", bill_id=bill_id, payment_method=pay_request.payment_method.value)

    result = await db.execute(
        select(Bill)
        .options(
            selectinload(Bill.session).selectinload(OrderSession.table),
            selectinload(Bill.payments),
        )
        .join(OrderSession, Bill.session_id == OrderSession.id)
        .where(Bill.id == bill_id, OrderSession.restaurant_id == current_user.restaurant_id)
    )
    bill = result.scalar_one_or_none()
    if not bill:
        logger.api_error(SERVICE, "POST", f"/{bill_id}/pay", "Bill not found", bill_id=bill_id)
        raise HTTPException(status_code=404, detail="Bill not found")

    db_payment = Payment(
        bill_id=bill_id,
        customer_id=pay_request.customer_id,
        amount=bill.final_total,
        payment_method=pay_request.payment_method,
        status=PaymentStatus.COMPLETED,
        restaurant_id=current_user.restaurant_id,
    )
    db.add(db_payment)

    bill.paid_at = dt.utcnow()
    bill.session.session_status = SessionStatus.CLOSED
    bill.session.ended_at = dt.utcnow()
    bill.session.table.status = TableStatus.AVAILABLE

    await db.commit()
    await db.refresh(bill)
    logger.api_response(SERVICE, "POST", f"/{bill_id}/pay", 200, bill_id=bill_id, status="paid")
    return bill

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
        .options(
            selectinload(Bill.session).selectinload(OrderSession.table),
            selectinload(Bill.payments),
        )
        .where(Bill.id == bill_id, OrderSession.restaurant_id == restaurant.id)
    )
    bill = result.scalar_one_or_none()
    if not bill:
        logger.api_error(SERVICE, "GET", f"/{restaurant_slug}/{bill_id}", "Bill not found", bill_id=bill_id)
        raise HTTPException(status_code=404, detail="Bill not found")
    logger.api_response(SERVICE, "GET", f"/{restaurant_slug}/{bill_id}", 200, bill_id=bill_id)
    return bill


@router.get("/", response_model=List[BillResponse])
async def get_all_bills(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records to return"),
    start_date: Optional[dt] = Query(None, description="Filter bills from this date"),
    end_date: Optional[dt] = Query(None, description="Filter bills until this date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Get all bills for the restaurant with optional date filtering."""
    logger.api_request(SERVICE, "GET", "/", skip=skip, limit=limit, start_date=start_date, end_date=end_date)

    query = (
        select(Bill)
        .join(OrderSession, Bill.session_id == OrderSession.id)
        .options(
            selectinload(Bill.session).selectinload(OrderSession.table),
            selectinload(Bill.payments),
        )
        .where(OrderSession.restaurant_id == current_user.restaurant_id)
    )

    if start_date:
        query = query.where(Bill.created_at >= start_date)
    if end_date:
        query = query.where(Bill.created_at <= end_date)

    query = query.order_by(Bill.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    bills = result.scalars().all()
    logger.api_response(SERVICE, "GET", "/", 200, count=len(bills))
    return bills


@router.delete("/{bill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bill(
    bill_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Delete a bill."""
    logger.api_request(SERVICE, "DELETE", f"/{bill_id}")

    query = select(Bill).join(OrderSession).where(
        Bill.id == bill_id,
        OrderSession.restaurant_id == current_user.restaurant_id
    )
    result = await db.execute(query)
    bill = result.scalar_one_or_none()

    if not bill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bill not found")

    await db.delete(bill)
    await db.commit()

    logger.api_response(SERVICE, "DELETE", f"/{bill_id}", 204)
    return None
