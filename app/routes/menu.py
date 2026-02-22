from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
import qrcode
import io
import base64

from app.database import get_db
from app.models.models import MenuCategory, MenuItem, Table
from app.schemas import (
    MenuCategoryCreate, MenuCategoryUpdate, MenuCategoryResponse,
    MenuItemCreate, MenuItemUpdate, MenuItemResponse, MenuItemWithCategory,
    TableCreate, TableResponse, TableWithQRResponse
)
from app.utils.logger import logger

router = APIRouter(prefix="/api/menu", tags=["Menu"])
SERVICE = "menu"


@router.get("/categories", response_model=List[MenuCategoryResponse])
async def get_categories(db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "GET", "/categories")
    result = await db.execute(select(MenuCategory).order_by(MenuCategory.display_order))
    categories = result.scalars().all()
    logger.api_response(SERVICE, "GET", "/categories", 200, count=len(categories))
    return categories


@router.post("/categories", response_model=MenuCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(category: MenuCategoryCreate, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "POST", "/categories", name=category.name)
    db_category = MenuCategory(**category.model_dump())
    db.add(db_category)
    await db.commit()
    await db.refresh(db_category)
    logger.api_response(SERVICE, "POST", "/categories", 201, category_id=str(db_category.id), name=db_category.name)
    return db_category


@router.put("/categories/{category_id}", response_model=MenuCategoryResponse)
async def update_category(category_id: str, category: MenuCategoryUpdate, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "PUT", f"/categories/{category_id}", category_id=category_id)
    result = await db.execute(select(MenuCategory).where(MenuCategory.id == category_id))
    db_category = result.scalar_one_or_none()
    if not db_category:
        logger.api_error(SERVICE, "PUT", f"/categories/{category_id}", "Category not found", category_id=category_id)
        raise HTTPException(status_code=404, detail="Category not found")
    for key, value in category.model_dump(exclude_unset=True).items():
        setattr(db_category, key, value)
    await db.commit()
    await db.refresh(db_category)
    logger.api_response(SERVICE, "PUT", f"/categories/{category_id}", 200, category_id=category_id)
    return db_category


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: str, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "DELETE", f"/categories/{category_id}", category_id=category_id)
    result = await db.execute(select(MenuCategory).where(MenuCategory.id == category_id))
    db_category = result.scalar_one_or_none()
    if not db_category:
        logger.api_error(SERVICE, "DELETE", f"/categories/{category_id}", "Category not found", category_id=category_id)
        raise HTTPException(status_code=404, detail="Category not found")
    await db.delete(db_category)
    await db.commit()
    logger.api_response(SERVICE, "DELETE", f"/categories/{category_id}", 204, category_id=category_id)


@router.get("/items", response_model=List[MenuItemWithCategory])
async def get_menu_items(available_only: bool = False, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "GET", "/items", available_only=available_only)
    query = select(MenuItem).options(selectinload(MenuItem.category))
    if available_only:
        query = query.where(MenuItem.is_available == True)
    query = query.order_by(MenuItem.category_id, MenuItem.name)
    result = await db.execute(query)
    items = result.scalars().all()
    logger.api_response(SERVICE, "GET", "/items", 200, count=len(items))
    return items


@router.get("/items/category/{category_id}", response_model=List[MenuItemResponse])
async def get_items_by_category(category_id: str, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "GET", f"/items/category/{category_id}", category_id=category_id)
    result = await db.execute(
        select(MenuItem).where(MenuItem.category_id == category_id).order_by(MenuItem.name)
    )
    items = result.scalars().all()
    logger.api_response(SERVICE, "GET", f"/items/category/{category_id}", 200, count=len(items))
    return items


@router.post("/items", response_model=MenuItemResponse, status_code=status.HTTP_201_CREATED)
async def create_menu_item(item: MenuItemCreate, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "POST", "/items", name=item.name, category_id=item.category_id)
    result = await db.execute(select(MenuCategory).where(MenuCategory.id == item.category_id))
    if not result.scalar_one_or_none():
        logger.api_error(SERVICE, "POST", "/items", "Category not found", category_id=item.category_id)
        raise HTTPException(status_code=404, detail="Category not found")
    db_item = MenuItem(**item.model_dump())
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    logger.api_response(SERVICE, "POST", "/items", 201, item_id=str(db_item.id), name=db_item.name)
    return db_item


@router.put("/items/{item_id}", response_model=MenuItemResponse)
async def update_menu_item(item_id: str, item: MenuItemUpdate, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "PUT", f"/items/{item_id}", item_id=item_id)
    result = await db.execute(select(MenuItem).where(MenuItem.id == item_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        logger.api_error(SERVICE, "PUT", f"/items/{item_id}", "Menu item not found", item_id=item_id)
        raise HTTPException(status_code=404, detail="Menu item not found")
    for key, value in item.model_dump(exclude_unset=True).items():
        setattr(db_item, key, value)
    await db.commit()
    await db.refresh(db_item)
    logger.api_response(SERVICE, "PUT", f"/items/{item_id}", 200, item_id=item_id)
    return db_item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_menu_item(item_id: str, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "DELETE", f"/items/{item_id}", item_id=item_id)
    result = await db.execute(select(MenuItem).where(MenuItem.id == item_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        logger.api_error(SERVICE, "DELETE", f"/items/{item_id}", "Menu item not found", item_id=item_id)
        raise HTTPException(status_code=404, detail="Menu item not found")
    await db.delete(db_item)
    await db.commit()
    logger.api_response(SERVICE, "DELETE", f"/items/{item_id}", 204, item_id=item_id)


@router.patch("/items/{item_id}/availability", response_model=MenuItemResponse)
async def toggle_item_availability(item_id: str, is_available: bool, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "PATCH", f"/items/{item_id}/availability", item_id=item_id, is_available=is_available)
    result = await db.execute(select(MenuItem).where(MenuItem.id == item_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        logger.api_error(SERVICE, "PATCH", f"/items/{item_id}/availability", "Menu item not found", item_id=item_id)
        raise HTTPException(status_code=404, detail="Menu item not found")
    db_item.is_available = is_available
    await db.commit()
    await db.refresh(db_item)
    logger.api_response(SERVICE, "PATCH", f"/items/{item_id}/availability", 200, item_id=item_id, is_available=is_available)
    return db_item
