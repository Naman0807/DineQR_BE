from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta

from app.database import get_db
from app.models.models import Customer, OrderSession, SessionStatus
from app.schemas.schemas import CustomerRegisterRequest, CustomerAuthResponse
from app.auth.jwt import create_access_token
from app.utils.logger import logger

router = APIRouter(prefix="/api/customer", tags=["Customer Auth"])
SERVICE = "customer_auth"


@router.post("/register", response_model=CustomerAuthResponse)
async def register_customer(request: CustomerRegisterRequest, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "POST", "/register", phone=request.phone_number)

    # 1. Validate Session exists and is active
    result = await db.execute(
        select(OrderSession).where(
            OrderSession.id == request.session_id,
            OrderSession.session_status == SessionStatus.ACTIVE
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=400, detail="Invalid or inactive session.")

    # 2. Find or create customer globally by phone_number
    result = await db.execute(
        select(Customer).where(Customer.phone_number == request.phone_number)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        customer = Customer(
            name=request.name,
            phone_number=request.phone_number,
        )
        db.add(customer)
        await db.commit()
        await db.refresh(customer)
        logger.info(f"[CUSTOMER] Created new customer: {customer.id} ({request.phone_number})")
    else:
        logger.info(f"[CUSTOMER] Existing customer: {customer.id} ({request.phone_number})")

    # 3. Generate 1-Hour Customer JWT Token with customer_id
    token_data = {
        "sub": customer.id,
        "name": request.name,
        "phone": request.phone_number,
        "session_id": request.session_id,
        "role": "customer"
    }

    access_token = create_access_token(
        data=token_data,
        expires_delta=timedelta(hours=1)
    )

    logger.info(f"[CUSTOMER] Registered/Linked: {request.phone_number} ({request.name}) → id={customer.id}")

    return CustomerAuthResponse(access_token=access_token)
