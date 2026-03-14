from datetime import datetime
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_password_hash
from app.auth.dependencies import get_current_superadmin
from app.database import get_db
from app.models.models import Restaurant, RestaurantStatus, User, UserRole
from app.schemas.schemas import RestaurantSettingsUpdate, RestaurantSettingsResponse

router = APIRouter(prefix="/api/superadmin", tags=["Superadmin"])


class RestaurantStatusUpdate(BaseModel):
    status: str


class CreateRestaurantAdminRequest(BaseModel):
    restaurant_name: str
    admin_username: str
    admin_email: EmailStr
    admin_password: str


class UpdateRestaurantAdminRequest(BaseModel):
    restaurant_name: str | None = None
    admin_username: str | None = None
    admin_email: EmailStr | None = None
    admin_password: str | None = None


class RestaurantResponse(BaseModel):
    id: str
    name: str
    slug: str
    status: str
    created_at: datetime
    admin_username: str
    admin_email: str


class RestaurantListResponse(BaseModel):
    restaurants: list[RestaurantResponse]


def generate_slug(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug


async def get_unique_slug(db: AsyncSession, name: str) -> str:
    base_slug = generate_slug(name)
    slug = base_slug
    counter = 2
    while True:
        result = await db.execute(select(Restaurant.id).where(Restaurant.slug == slug))
        if result.scalar_one_or_none() is None:
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


def build_restaurant_response(restaurant: Restaurant) -> RestaurantResponse:
    admin_user = next(
        (u for u in restaurant.users if u.role == UserRole.ADMIN),
        restaurant.users[0] if restaurant.users else None,
    )
    return RestaurantResponse(
        id=restaurant.id,
        name=restaurant.name,
        slug=restaurant.slug,
        status=restaurant.status.value,
        created_at=restaurant.created_at,
        admin_username=admin_user.username if admin_user else "",
        admin_email=admin_user.email if admin_user else "",
    )


@router.get("/restaurants", response_model=RestaurantListResponse)
async def get_restaurants(
    current_user: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    result = await db.execute(select(Restaurant).options(selectinload(Restaurant.users)))
    restaurants = result.scalars().all()
    return RestaurantListResponse(restaurants=[build_restaurant_response(r) for r in restaurants])


@router.post("/restaurants", response_model=RestaurantResponse, status_code=status.HTTP_201_CREATED)
async def create_restaurant_admin(
    payload: CreateRestaurantAdminRequest,
    current_user: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    existing_user_result = await db.execute(
        select(User).where((User.username == payload.admin_username) | (User.email == payload.admin_email))
    )
    existing_user = existing_user_result.scalar_one_or_none()
    if existing_user:
        if existing_user.username == payload.admin_username:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    slug = await get_unique_slug(db, payload.restaurant_name)
    restaurant = Restaurant(
        name=payload.restaurant_name,
        slug=slug,
        status=RestaurantStatus.ACTIVE,
    )
    db.add(restaurant)
    await db.flush()

    admin_user = User(
        username=payload.admin_username,
        email=payload.admin_email,
        hashed_password=get_password_hash(payload.admin_password),
        role=UserRole.ADMIN,
        restaurant_id=restaurant.id,
        is_active=True,
    )
    db.add(admin_user)
    await db.commit()

    result = await db.execute(
        select(Restaurant).options(selectinload(Restaurant.users)).where(Restaurant.id == restaurant.id)
    )
    created_restaurant = result.scalar_one()
    return build_restaurant_response(created_restaurant)


@router.put("/restaurants/{restaurant_id}", response_model=RestaurantResponse)
async def update_restaurant_admin(
    restaurant_id: str,
    payload: UpdateRestaurantAdminRequest,
    current_user: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    result = await db.execute(
        select(Restaurant).options(selectinload(Restaurant.users)).where(Restaurant.id == restaurant_id)
    )
    restaurant = result.scalar_one_or_none()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    admin_user = next((u for u in restaurant.users if u.role == UserRole.ADMIN), None)
    if not admin_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant admin not found")

    if payload.admin_username and payload.admin_username != admin_user.username:
        existing_username = await db.execute(select(User.id).where(User.username == payload.admin_username))
        if existing_username.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
        admin_user.username = payload.admin_username

    if payload.admin_email and payload.admin_email != admin_user.email:
        existing_email = await db.execute(select(User.id).where(User.email == payload.admin_email))
        if existing_email.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        admin_user.email = payload.admin_email

    if payload.admin_password:
        admin_user.hashed_password = get_password_hash(payload.admin_password)

    if payload.restaurant_name:
        restaurant.name = payload.restaurant_name

    await db.commit()
    await db.refresh(restaurant)
    return build_restaurant_response(restaurant)


@router.patch("/restaurants/{restaurant_id}/status", response_model=RestaurantResponse)
async def update_restaurant_status(
    restaurant_id: str,
    status_update: RestaurantStatusUpdate,
    current_user: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    result = await db.execute(
        select(Restaurant).options(selectinload(Restaurant.users)).where(Restaurant.id == restaurant_id)
    )
    restaurant = result.scalar_one_or_none()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    try:
        restaurant.status = RestaurantStatus(status_update.status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status value. Must be 'pending', 'active', or 'deactivated'",
        )

    await db.commit()
    await db.refresh(restaurant)
    return build_restaurant_response(restaurant)


@router.delete("/restaurants/{restaurant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_restaurant(
    restaurant_id: str,
    current_user: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    restaurant = result.scalar_one_or_none()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    await db.delete(restaurant)
    await db.commit()


@router.get("/restaurants/{restaurant_id}/settings", response_model=RestaurantSettingsResponse)
async def get_restaurant_settings(
    restaurant_id: str,
    current_user: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Get settings for a specific restaurant (Superadmin)."""
    result = await db.execute(
        select(Restaurant).where(Restaurant.id == restaurant_id)
    )
    restaurant = result.scalar_one_or_none()
    
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    
    result = await db.execute(
        select(User).where(User.restaurant_id == restaurant_id).where(User.role == UserRole.ADMIN)
    )
    admin_user = result.scalar_one_or_none()
    
    if not admin_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant admin not found")
    
    return RestaurantSettingsResponse(
        restaurant_id=restaurant.id,
        restaurant_name=restaurant.name,
        restaurant_slug=restaurant.slug,
        restaurant_tax=float(restaurant.tax),
        admin_email=admin_user.email,
        admin_phone=admin_user.phone_number,
    )


@router.put("/restaurants/{restaurant_id}/settings", response_model=RestaurantSettingsResponse)
async def update_restaurant_settings(
    restaurant_id: str,
    settings_data: RestaurantSettingsUpdate,
    current_user: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Update settings for a specific restaurant (Superadmin)."""
    result = await db.execute(
        select(Restaurant).where(Restaurant.id == restaurant_id)
    )
    restaurant = result.scalar_one_or_none()
    
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    
    result = await db.execute(
        select(User).where(User.restaurant_id == restaurant_id).where(User.role == UserRole.ADMIN)
    )
    admin_user = result.scalar_one_or_none()
    
    if not admin_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant admin not found")
    
    if settings_data.restaurant_name is not None:
        restaurant.name = settings_data.restaurant_name
    if settings_data.restaurant_tax is not None:
        restaurant.tax = settings_data.restaurant_tax
    
    if settings_data.admin_email is not None:
        result = await db.execute(
            select(User).where(User.email == settings_data.admin_email).where(User.id != admin_user.id)
        )
        existing_user = result.scalar_one_or_none()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered by another user"
            )
        admin_user.email = settings_data.admin_email
    
    # Handle admin_phone update
    if settings_data.admin_phone is not None:
        admin_user.phone_number = settings_data.admin_phone
    
    await db.commit()
    await db.refresh(restaurant)
    await db.refresh(admin_user)
    
    return RestaurantSettingsResponse(
        restaurant_id=restaurant.id,
        restaurant_name=restaurant.name,
        restaurant_slug=restaurant.slug,
        restaurant_tax=float(restaurant.tax),
        admin_email=admin_user.email,
        admin_phone=admin_user.phone_number,
    )
