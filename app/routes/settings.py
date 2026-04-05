from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models.models import User, Restaurant, UserRole
from app.auth.dependencies import get_current_admin_user
from app.schemas.schemas import RestaurantSettingsUpdate, RestaurantSettingsResponse
from app.utils.logger import logger

router = APIRouter(prefix="/api/settings", tags=["Settings"])
SERVICE = "settings"

@router.get("", response_model=RestaurantSettingsResponse)
async def get_settings(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current restaurant settings for the admin."""
    logger.api_request(SERVICE, "GET", "", user_id=str(current_user.id))
    
    if not current_user.restaurant_id:
        logger.api_error(SERVICE, "GET", "", "No restaurant associated", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No restaurant associated with this account"
        )
    
    result = await db.execute(
        select(Restaurant).where(Restaurant.id == current_user.restaurant_id)
    )
    restaurant = result.scalar_one_or_none()
    
    if not restaurant:
        logger.api_error(SERVICE, "GET", "", "Restaurant not found", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found"
        )
    
    result = await db.execute(
        select(User).where(User.restaurant_id == current_user.restaurant_id).where(User.role == UserRole.ADMIN)
    )
    admin_user = result.scalar_one_or_none()
    
    if not admin_user:
        logger.api_error(SERVICE, "GET", "", "Admin user not found", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin user not found"
        )
    
    logger.api_response(SERVICE, "GET", "", 200, user_id=str(current_user.id))
    
    return RestaurantSettingsResponse(
        restaurant_id=restaurant.id,
        restaurant_name=restaurant.name,
        restaurant_slug=restaurant.slug,
        restaurant_tax=float(restaurant.tax),
        admin_email=admin_user.email,
        admin_phone=admin_user.phone_number,
        address=restaurant.address,
        phone=restaurant.phone,
        logo_url=restaurant.logo_url,
        description=restaurant.description,
    )


@router.put("", response_model=RestaurantSettingsResponse)
async def update_settings(
    settings_data: RestaurantSettingsUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Update restaurant settings (name, email, tax)."""
    logger.api_request(SERVICE, "PUT", "", user_id=str(current_user.id), data=settings_data.model_dump())
    
    if not current_user.restaurant_id:
        logger.api_error(SERVICE, "PUT", "", "No restaurant associated", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No restaurant associated with this account"
        )
    
    result = await db.execute(
        select(Restaurant).where(Restaurant.id == current_user.restaurant_id)
    )
    restaurant = result.scalar_one_or_none()
    
    if not restaurant:
        logger.api_error(SERVICE, "PUT", "", "Restaurant not found", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found"
        )
    
    if settings_data.restaurant_name is not None:
        restaurant.name = settings_data.restaurant_name
    if settings_data.restaurant_tax is not None:
        restaurant.tax = settings_data.restaurant_tax
    if settings_data.address is not None:
        restaurant.address = settings_data.address
    if settings_data.logo_url is not None:
        restaurant.logo_url = settings_data.logo_url
    if settings_data.description is not None:
        restaurant.description = settings_data.description
    
    if settings_data.phone is not None:
        if current_user.role != UserRole.SUPERADMIN:
            logger.api_error(SERVICE, "PUT", "", "Only superadmin can update phone", user_id=str(current_user.id))
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superadmin can update phone number"
            )
        if not settings_data.phone:
            logger.api_error(SERVICE, "PUT", "", "Phone number is required", user_id=str(current_user.id))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number is required"
            )
        restaurant.phone = settings_data.phone
        current_user.phone_number = settings_data.phone
    
    if settings_data.admin_email is not None:
        result = await db.execute(
            select(User).where(User.email == settings_data.admin_email).where(User.id != current_user.id)
        )
        existing_user = result.scalar_one_or_none()
        if existing_user:
            logger.api_error(SERVICE, "PUT", "", "Email already in use", email=settings_data.admin_email)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered by another user"
            )
        current_user.email = settings_data.admin_email
    
    # Handle admin_phone update
    if settings_data.admin_phone is not None:
        if current_user.role != UserRole.SUPERADMIN:
            logger.api_error(SERVICE, "PUT", "", "Only superadmin can update admin phone", user_id=str(current_user.id))
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superadmin can update phone number"
            )
        current_user.phone_number = settings_data.admin_phone
    
    await db.commit()
    await db.refresh(restaurant)
    await db.refresh(current_user)
    
    logger.api_response(SERVICE, "PUT", "", 200, user_id=str(current_user.id))
    
    return RestaurantSettingsResponse(
        restaurant_id=restaurant.id,
        restaurant_name=restaurant.name,
        restaurant_slug=restaurant.slug,
        restaurant_tax=float(restaurant.tax),
        admin_email=current_user.email,
        admin_phone=current_user.phone_number,
        address=restaurant.address,
        phone=restaurant.phone,
        logo_url=restaurant.logo_url,
        description=restaurant.description,
    )
