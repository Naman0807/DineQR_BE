from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta

from app.database import get_db
from app.models.models import OTPVerification, OrderSession, SessionStatus
from app.schemas.schemas import SendOTPRequest, VerifyOTPRequest, CustomerAuthResponse
from app.utils.otp import generate_numeric_otp, send_otp_sms, DEV_PHONE_NUMBER, DEV_OTP_CODE
from app.auth.jwt import create_access_token
from app.utils.logger import logger

router = APIRouter(prefix="/api/customer", tags=["Customer Auth"])
SERVICE = "customer_auth"


@router.post("/send-otp")
async def send_otp(request: SendOTPRequest, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "POST", "/send-otp", phone=request.phone_number)
    
    # 1. Validate Session
    result = await db.execute(select(OrderSession).where(OrderSession.id == request.session_id))
    session = result.scalar_one_or_none()
    
    if not session or session.session_status != SessionStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Invalid or inactive session.")

    # 2. Generate OTP and Set Expiry (5 minutes)
    otp_code = generate_numeric_otp(6)
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    # 3. Save to Database
    db_otp = OTPVerification(
        phone_number=request.phone_number,
        otp_code=otp_code,
        restaurant_id=session.restaurant_id,
        table_id=session.table_id,
        session_id=session.id,
        expires_at=expires_at
    )
    db.add(db_otp)
    await db.commit()

    # 4. Send SMS via Fast2SMS
    sms_sent = await send_otp_sms(request.phone_number, otp_code)
    if not sms_sent:
        raise HTTPException(status_code=500, detail="Failed to send OTP SMS")

    return {"message": "OTP sent successfully. Valid for 5 minutes."}


@router.post("/verify-otp", response_model=CustomerAuthResponse)
async def verify_otp(request: VerifyOTPRequest, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "POST", "/verify-otp", phone=request.phone_number)

    # Development mode: bypass OTP check for dev phone number
    if request.phone_number == DEV_PHONE_NUMBER and request.otp_code == DEV_OTP_CODE:
        # Find or create a valid session for dev mode
        result = await db.execute(
            select(OrderSession).where(
                OrderSession.id == request.session_id,
                OrderSession.session_status == SessionStatus.ACTIVE
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=400, detail="Invalid or inactive session.")

        token_data = {
            "sub": request.phone_number,
            "session_id": request.session_id,
            "role": "customer"
        }
        access_token = create_access_token(
            data=token_data,
            expires_delta=timedelta(hours=1)
        )
        return CustomerAuthResponse(access_token=access_token)

    # 1. Find the latest unused, unexpired OTP for this session and phone
    result = await db.execute(
        select(OTPVerification).where(
            OTPVerification.session_id == request.session_id,
            OTPVerification.phone_number == request.phone_number,
            OTPVerification.is_used == False,
            OTPVerification.expires_at > datetime.utcnow()
        ).order_by(OTPVerification.created_at.desc())
    )
    db_otp = result.scalars().first()

    if not db_otp or db_otp.otp_code != request.otp_code:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    # 2. Mark OTP as used
    db_otp.is_used = True
    await db.commit()

    # 3. Generate 1-Hour Customer JWT Token
    token_data = {
        "sub": request.phone_number,
        "session_id": request.session_id,
        "role": "customer"
    }
    
    access_token = create_access_token(
        data=token_data, 
        expires_delta=timedelta(hours=1)
    )

    return CustomerAuthResponse(access_token=access_token)
