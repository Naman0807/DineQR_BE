from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.models.models import User
from app.auth import verify_password, create_access_token
from app.auth.dependencies import get_current_admin_user
from app.utils.logger import logger

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
SERVICE = "auth"


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


@router.post("/login", response_model=TokenResponse)
async def login(login_data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return JWT token."""
    logger.api_request(SERVICE, "POST", "/login", username=login_data.username)
    
    result = await db.execute(
        select(User).where(User.username == login_data.username)
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(login_data.password, user.hashed_password):
        logger.api_error(SERVICE, "POST", "/login", "Invalid credentials", username=login_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        logger.api_error(SERVICE, "POST", "/login", "User inactive", username=login_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.id, "role": user.role.value})
    logger.api_response(SERVICE, "POST", "/login", 200, user_id=str(user.id))
    
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_admin_user)):
    """Get current authenticated user info."""
    logger.api_request(SERVICE, "GET", "/me", user_id=str(current_user.id))
    logger.api_response(SERVICE, "GET", "/me", 200, user_id=str(current_user.id))
    return UserResponse(
        id=str(current_user.id),
        username=current_user.username,
        email=current_user.email,
        role=current_user.role.value,
        is_active=current_user.is_active,
    )
