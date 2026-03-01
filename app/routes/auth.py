from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.models.models import User, UserRole, Restaurant, RestaurantStatus
from app.auth import verify_password, create_access_token, get_password_hash
from app.auth.dependencies import get_current_user
from app.utils.logger import logger

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
SERVICE = "auth"


def generate_slug(name: str) -> str:
    import re
    slug = name.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    restaurant_name: str | None = None
    role: str = "admin"
    phone_number: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    restaurant_id: str | None = None
    restaurant_name: str | None = None
    phone_number: str | None = None

    class Config:
        from_attributes = True


@router.post("/login", response_model=TokenResponse)
async def login(login_data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return JWT token."""
    logger.api_request(SERVICE, "POST", "/login", username=login_data.username)
    
    result = await db.execute(
        select(User).options(selectinload(User.restaurant)).where(User.username == login_data.username)
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
    
    if user.role == UserRole.ADMIN and user.restaurant:
        if user.restaurant.status == RestaurantStatus.PENDING:
            logger.api_error(SERVICE, "POST", "/login", "Restaurant pending approval", username=login_data.username)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your restaurant account is pending approval. Please contact superadmin.",
            )
        elif user.restaurant.status == RestaurantStatus.DEACTIVATED:
            logger.api_error(SERVICE, "POST", "/login", "Restaurant deactivated", username=login_data.username)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your restaurant account has been deactivated.",
            )
    
    access_token = create_access_token(data={"sub": user.id, "role": user.role.value, "restaurant_id": user.restaurant_id})
    logger.api_response(SERVICE, "POST", "/login", 200, user_id=str(user.id))
    
    return TokenResponse(access_token=access_token)


@router.post("/register")
async def register(register_data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user and return registration response."""
    logger.api_request(SERVICE, "POST", "/register", username=register_data.username, email=register_data.email)
    
    result = await db.execute(
        select(User).where((User.username == register_data.username) | (User.email == register_data.email))
    )
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        if existing_user.username == register_data.username:
            logger.api_error(SERVICE, "POST", "/register", "Username already exists", username=register_data.username)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered",
            )
        else:
            logger.api_error(SERVICE, "POST", "/register", "Email already exists", email=register_data.email)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
    
    try:
        role = UserRole(register_data.role.lower())
    except ValueError:
        logger.api_error(SERVICE, "POST", "/register", "Invalid role", role=register_data.role)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {[r.value for r in UserRole]}",
        )

    if role != UserRole.ADMIN:
        logger.api_error(SERVICE, "POST", "/register", "Only admin registration is allowed", role=role.value)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only restaurant admin registration is allowed.",
        )
    
    if not register_data.restaurant_name or not register_data.restaurant_name.strip():
        logger.api_error(SERVICE, "POST", "/register", "Restaurant name is required for admin registration")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Restaurant name is required for admin registration",
        )

    slug = generate_slug(register_data.restaurant_name)
    new_restaurant = Restaurant(
        name=register_data.restaurant_name,
        slug=slug,
        status=RestaurantStatus.PENDING,
    )
    db.add(new_restaurant)
    await db.commit()
    await db.refresh(new_restaurant)
    restaurant_id = new_restaurant.id

    hashed_password = get_password_hash(register_data.password)
    new_user = User(
        username=register_data.username,
        email=register_data.email,
        phone_number=register_data.phone_number,
        hashed_password=hashed_password,
        role=role,
        restaurant_id=restaurant_id,
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    logger.api_response(SERVICE, "POST", "/register", 200, user_id=str(new_user.id))

    return {"message": "Registration submitted. Your restaurant is pending approval.", "restaurant_slug": slug}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.database import get_db
    
    # Get fresh user with restaurant loaded
    async for db in get_db():
        result = await db.execute(
            select(User)
            .options(selectinload(User.restaurant))
            .where(User.id == current_user.id)
        )
        user = result.scalar_one_or_none()
        break
    
    restaurant_name = user.restaurant.name if user and user.restaurant else None
    
    logger.api_request(SERVICE, "GET", "/me", user_id=str(current_user.id))
    logger.api_response(SERVICE, "GET", "/me", 200, user_id=str(current_user.id))
    return UserResponse(
        id=str(current_user.id),
        username=current_user.username,
        email=current_user.email,
        role=current_user.role.value,
        is_active=current_user.is_active,
        restaurant_id=current_user.restaurant_id,
        restaurant_name=restaurant_name,
        phone_number=current_user.phone_number,
    )
