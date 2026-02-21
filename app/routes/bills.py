from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from decimal import Decimal
from datetime import datetime

from app.database import get_db
from app.models.models import (
    Bill, Order, OrderSession, Table,
    SessionStatus, PaymentStatus, TableStatus, OrderStatus
)
from app.schemas import (
    BillCreate, BillUpdate, BillResponse, BillWithOrdersResponse
)
from app.utils.logger import logger

router = APIRouter(prefix="/api/bills", tags=["Bills"])
SERVICE = "bills"


@router.post("/", response_model=BillResponse, status_code=status.HTTP_201_CREATED)
async def create_bill(bill: BillCreate, db: AsyncSession = Depends(get_db)):
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
        await db.refresh(db_bill)
        logger.api_response(SERVICE, "POST", "/", 201, bill_id=str(db_bill.id), final_total=float(final_total))
        return db_bill
    except HTTPException:
        raise
    except Exception as e:
        logger.api_error(SERVICE, "POST", "/", str(e), session_id=bill.session_id)
        raise


@router.get("/session/{session_id}", response_model=BillWithOrdersResponse)
async def get_bill_by_session(session_id: str, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "GET", f"/session/{session_id}", session_id=session_id)
    result = await db.execute(
        select(Bill)
        .options(
            selectinload(Bill.session).selectinload(OrderSession.orders)
            .selectinload(Order.items)
        )
        .where(Bill.session_id == session_id)
    )
    bill = result.scalar_one_or_none()
    if not bill:
        logger.api_error(SERVICE, "GET", f"/session/{session_id}", "Bill not found", session_id=session_id)
        raise HTTPException(status_code=404, detail="Bill not found")
    logger.api_response(SERVICE, "GET", f"/session/{session_id}", 200, bill_id=str(bill.id))
    return bill


@router.get("/{bill_id}", response_model=BillResponse)
async def get_bill(bill_id: str, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "GET", f"/{bill_id}", bill_id=bill_id)
    result = await db.execute(select(Bill).where(Bill.id == bill_id))
    bill = result.scalar_one_or_none()
    if not bill:
        logger.api_error(SERVICE, "GET", f"/{bill_id}", "Bill not found", bill_id=bill_id)
        raise HTTPException(status_code=404, detail="Bill not found")
    logger.api_response(SERVICE, "GET", f"/{bill_id}", 200, bill_id=bill_id)
    return bill


@router.patch("/{bill_id}", response_model=BillResponse)
async def update_bill(bill_id: str, update: BillUpdate, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "PATCH", f"/{bill_id}", bill_id=bill_id)
    result = await db.execute(
        select(Bill)
        .options(selectinload(Bill.session).selectinload(OrderSession.table))
        .where(Bill.id == bill_id)
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
        bill.paid_at = datetime.utcnow()

        bill.session.session_status = SessionStatus.CLOSED
        bill.session.ended_at = datetime.utcnow()
        bill.session.table.status = TableStatus.AVAILABLE

    await db.commit()
    await db.refresh(bill)
    logger.api_response(SERVICE, "PATCH", f"/{bill_id}", 200, bill_id=bill_id, payment_status=bill.payment_status.value)
    return bill


@router.post("/{bill_id}/pay", response_model=BillResponse)
async def pay_bill(bill_id: str, payment_method: str, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "POST", f"/{bill_id}/pay", bill_id=bill_id, payment_method=payment_method)
    result = await db.execute(
        select(Bill)
        .options(selectinload(Bill.session).selectinload(OrderSession.table))
        .where(Bill.id == bill_id)
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
    bill.paid_at = datetime.utcnow()

    bill.session.session_status = SessionStatus.CLOSED
    bill.session.ended_at = datetime.utcnow()
    bill.session.table.status = TableStatus.AVAILABLE

    await db.commit()
    await db.refresh(bill)
    logger.api_response(SERVICE, "POST", f"/{bill_id}/pay", 200, bill_id=bill_id, status="paid")
    return bill


@router.get("/", response_model=List[BillResponse])
async def get_all_bills(db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "GET", "/")
    result = await db.execute(select(Bill).order_by(Bill.created_at.desc()))
    bills = result.scalars().all()
    logger.api_response(SERVICE, "GET", "/", 200, count=len(bills))
    return bills
