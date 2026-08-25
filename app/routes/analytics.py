from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from typing import List
from datetime import datetime as dt, timezone, timedelta

from app.database import get_db
from app.models.models import (
    Bill, Payment, Order, OrderSession, OrderItem, MenuItem, MenuCategory,
    Customer, User
)
from app.schemas import (
    RevenueOverview, RevenueTrendPoint, PaymentMethodBreakdown,
    MenuItemPerformance, CategoryPerformance, CustomerSummary, TopCustomer
)
from app.auth.dependencies import get_current_admin_user
from app.utils.logger import logger

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])
SERVICE = "analytics"
IST = timezone(timedelta(hours=5, minutes=30))


def get_date_range(start_date: dt | None = None, end_date: dt | None = None):
    now = dt.utcnow()
    start = start_date or now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = end_date or now
    return start, end


@router.get("/overview", response_model=RevenueOverview)
async def get_revenue_overview(
    start_date: dt | None = Query(None, description="Start date"),
    end_date: dt | None = Query(None, description="End date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    logger.api_request(SERVICE, "GET", "/overview")
    try:
        start, end = get_date_range(start_date, end_date)

        result = await db.execute(
            select(
                func.count(Bill.id).label('total_bills'),
                func.sum(case((Bill.paid_at.isnot(None), 1), else_=0)).label('paid_bills'),
                func.sum(case((Bill.paid_at.is_(None), 1), else_=0)).label('unpaid_bills'),
                func.coalesce(func.avg(Bill.final_total), 0).label('average_order_value'),
                func.coalesce(func.sum(Bill.tax_amount), 0).label('total_tax_collected'),
                func.coalesce(func.sum(Bill.discount_amount), 0).label('total_discounts'),
            )
            .join(OrderSession, Bill.session_id == OrderSession.id)
            .where(
                OrderSession.restaurant_id == current_user.restaurant_id,
                Bill.created_at >= start,
                Bill.created_at <= end,
            )
        )
        bill_row = result.one()

        result = await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .join(Bill, Payment.bill_id == Bill.id)
            .join(OrderSession, Bill.session_id == OrderSession.id)
            .where(
                OrderSession.restaurant_id == current_user.restaurant_id,
                Payment.status == 'completed',
                Payment.created_at >= start,
                Payment.created_at <= end,
            )
        )
        total_revenue = float(result.scalar())

        overview = RevenueOverview(
            total_revenue=total_revenue,
            total_bills=bill_row.total_bills or 0,
            paid_bills=bill_row.paid_bills or 0,
            unpaid_bills=bill_row.unpaid_bills or 0,
            average_order_value=float(bill_row.average_order_value),
            total_tax_collected=float(bill_row.total_tax_collected),
            total_discounts=float(bill_row.total_discounts),
        )

        logger.api_response(SERVICE, "GET", "/overview", 200)
        return overview
    except Exception as e:
        logger.api_error(SERVICE, "GET", "/overview", str(e))
        raise


@router.get("/revenue/trend", response_model=List[RevenueTrendPoint])
async def get_revenue_trend(
    granularity: str = Query("day", regex="^(day|week|month)$", description="Time bucket: day, week, or month"),
    start_date: dt | None = Query(None, description="Start date"),
    end_date: dt | None = Query(None, description="End date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    logger.api_request(SERVICE, "GET", "/revenue/trend", granularity=granularity)
    try:
        start, end = get_date_range(start_date, end_date)

        result = await db.execute(
            select(
                func.date_trunc(granularity, Bill.created_at).label('bucket'),
                func.coalesce(func.sum(Payment.amount), 0).label('revenue'),
                func.count(func.distinct(Bill.id)).label('bill_count'),
            )
            .join(OrderSession, Bill.session_id == OrderSession.id)
            .join(Payment, Payment.bill_id == Bill.id)
            .where(
                OrderSession.restaurant_id == current_user.restaurant_id,
                Payment.status == 'completed',
                Bill.created_at >= start,
                Bill.created_at <= end,
            )
            .group_by(func.date_trunc(granularity, Bill.created_at))
            .order_by(func.date_trunc(granularity, Bill.created_at))
        )
        rows = result.all()

        trend = [
            RevenueTrendPoint(
                date=row.bucket.isoformat().split("T")[0] if row.bucket else "",
                revenue=float(row.revenue),
                bill_count=row.bill_count,
            )
            for row in rows
        ]

        logger.api_response(SERVICE, "GET", "/revenue/trend", 200, count=len(trend))
        return trend
    except Exception as e:
        logger.api_error(SERVICE, "GET", "/revenue/trend", str(e))
        raise


@router.get("/revenue/by-method", response_model=List[PaymentMethodBreakdown])
async def get_revenue_by_method(
    start_date: dt | None = Query(None, description="Start date"),
    end_date: dt | None = Query(None, description="End date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    logger.api_request(SERVICE, "GET", "/revenue/by-method")
    try:
        start, end = get_date_range(start_date, end_date)

        result = await db.execute(
            select(
                Payment.payment_method.label('method'),
                func.coalesce(func.sum(Payment.amount), 0).label('total_amount'),
                func.count(Payment.id).label('count'),
            )
            .join(Bill, Payment.bill_id == Bill.id)
            .join(OrderSession, Bill.session_id == OrderSession.id)
            .where(
                OrderSession.restaurant_id == current_user.restaurant_id,
                Payment.status == 'completed',
                Payment.created_at >= start,
                Payment.created_at <= end,
            )
            .group_by(Payment.payment_method)
        )
        rows = result.all()

        breakdown = [
            PaymentMethodBreakdown(
                method=str(row.method),
                total_amount=float(row.total_amount),
                count=row.count,
            )
            for row in rows
        ]

        logger.api_response(SERVICE, "GET", "/revenue/by-method", 200, count=len(breakdown))
        return breakdown
    except Exception as e:
        logger.api_error(SERVICE, "GET", "/revenue/by-method", str(e))
        raise


@router.get("/menu/top-items", response_model=List[MenuItemPerformance])
async def get_top_menu_items(
    limit: int = Query(10, ge=1, le=100, description="Number of items to return"),
    start_date: dt | None = Query(None, description="Start date"),
    end_date: dt | None = Query(None, description="End date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    logger.api_request(SERVICE, "GET", "/menu/top-items", limit=limit)
    try:
        start, end = get_date_range(start_date, end_date)

        result = await db.execute(
            select(
                MenuItem.id.label('menu_item_id'),
                MenuItem.name.label('name'),
                MenuCategory.name.label('category_name'),
                func.sum(OrderItem.quantity).label('total_quantity'),
                func.coalesce(func.sum(OrderItem.quantity * OrderItem.unit_price), 0).label('total_revenue'),
            )
            .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
            .join(Order, OrderItem.order_id == Order.id)
            .join(OrderSession, Order.session_id == OrderSession.id)
            .join(MenuCategory, MenuItem.category_id == MenuCategory.id)
            .where(
                OrderSession.restaurant_id == current_user.restaurant_id,
                Order.created_at >= start,
                Order.created_at <= end,
            )
            .group_by(MenuItem.id, MenuItem.name, MenuCategory.name)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(limit)
        )
        rows = result.all()

        items = [
            MenuItemPerformance(
                menu_item_id=str(row.menu_item_id),
                name=row.name,
                category_name=row.category_name,
                total_quantity=row.total_quantity,
                total_revenue=float(row.total_revenue),
            )
            for row in rows
        ]

        logger.api_response(SERVICE, "GET", "/menu/top-items", 200, count=len(items))
        return items
    except Exception as e:
        logger.api_error(SERVICE, "GET", "/menu/top-items", str(e))
        raise


@router.get("/menu/category-performance", response_model=List[CategoryPerformance])
async def get_category_performance(
    start_date: dt | None = Query(None, description="Start date"),
    end_date: dt | None = Query(None, description="End date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    logger.api_request(SERVICE, "GET", "/menu/category-performance")
    try:
        start, end = get_date_range(start_date, end_date)

        result = await db.execute(
            select(
                MenuCategory.id.label('category_id'),
                MenuCategory.name.label('name'),
                func.sum(OrderItem.quantity).label('total_quantity'),
                func.coalesce(func.sum(OrderItem.quantity * OrderItem.unit_price), 0).label('total_revenue'),
                func.count(func.distinct(OrderItem.menu_item_id)).label('item_count'),
            )
            .join(MenuItem, MenuItem.category_id == MenuCategory.id)
            .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
            .join(Order, OrderItem.order_id == Order.id)
            .join(OrderSession, Order.session_id == OrderSession.id)
            .where(
                OrderSession.restaurant_id == current_user.restaurant_id,
                Order.created_at >= start,
                Order.created_at <= end,
            )
            .group_by(MenuCategory.id, MenuCategory.name)
            .order_by(func.sum(OrderItem.quantity).desc())
        )
        rows = result.all()

        categories = [
            CategoryPerformance(
                category_id=str(row.category_id),
                name=row.name,
                total_quantity=row.total_quantity,
                total_revenue=float(row.total_revenue),
                item_count=row.item_count,
            )
            for row in rows
        ]

        logger.api_response(SERVICE, "GET", "/menu/category-performance", 200, count=len(categories))
        return categories
    except Exception as e:
        logger.api_error(SERVICE, "GET", "/menu/category-performance", str(e))
        raise


@router.get("/customers/summary", response_model=CustomerSummary)
async def get_customer_summary(
    start_date: dt | None = Query(None, description="Start date"),
    end_date: dt | None = Query(None, description="End date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    logger.api_request(SERVICE, "GET", "/customers/summary")
    try:
        start, end = get_date_range(start_date, end_date)

        # total_customers: distinct customers with orders in period
        result = await db.execute(
            select(func.count(func.distinct(Customer.id)))
            .join(Order, Order.customer_id == Customer.id)
            .join(OrderSession, Order.session_id == OrderSession.id)
            .where(
                OrderSession.restaurant_id == current_user.restaurant_id,
                Order.created_at >= start,
                Order.created_at <= end,
            )
        )
        total_customers = result.scalar() or 0

        # new_customers: created_at >= start
        result = await db.execute(
            select(func.count(func.distinct(Customer.id)))
            .join(Order, Order.customer_id == Customer.id)
            .join(OrderSession, Order.session_id == OrderSession.id)
            .where(
                OrderSession.restaurant_id == current_user.restaurant_id,
                Order.created_at >= start,
                Order.created_at <= end,
                Customer.created_at >= start,
            )
        )
        new_customers = result.scalar() or 0

        # returning_customers: created_at < start
        returning_customers = total_customers - new_customers

        # top_customers (limit 10)
        result = await db.execute(
            select(
                Customer.id.label('id'),
                Customer.name.label('name'),
                Customer.phone_number.label('phone_number'),
                func.count(func.distinct(OrderSession.id)).label('visit_count'),
                func.coalesce(func.sum(Payment.amount), 0).label('total_spent'),
            )
            .join(Payment, Payment.customer_id == Customer.id)
            .join(Bill, Payment.bill_id == Bill.id)
            .join(OrderSession, Bill.session_id == OrderSession.id)
            .where(
                OrderSession.restaurant_id == current_user.restaurant_id,
                Payment.status == 'completed',
                Payment.created_at >= start,
                Payment.created_at <= end,
            )
            .group_by(Customer.id, Customer.name, Customer.phone_number)
            .order_by(func.sum(Payment.amount).desc())
            .limit(10)
        )
        rows = result.all()

        top_customers = [
            TopCustomer(
                id=str(row.id),
                name=row.name,
                phone_number=row.phone_number,
                visit_count=row.visit_count,
                total_spent=float(row.total_spent),
            )
            for row in rows
        ]

        summary = CustomerSummary(
            total_customers=total_customers,
            new_customers=new_customers,
            returning_customers=returning_customers,
            top_customers=top_customers,
        )

        logger.api_response(SERVICE, "GET", "/customers/summary", 200)
        return summary
    except Exception as e:
        logger.api_error(SERVICE, "GET", "/customers/summary", str(e))
        raise
