from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, cast, String, func, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from typing import List
import qrcode
import io
import base64
from PIL import Image, ImageDraw, ImageFont
import textwrap

from app.database import get_db
from app.models.models import Table, OrderSession, SessionStatus, TableStatus, User, Restaurant, Bill
from app.schemas import TableCreate, TableResponse, TableWithQRResponse
from app.auth.dependencies import get_current_admin_user
from app.utils.logger import logger

router = APIRouter(prefix="/api/tables", tags=["Tables"])
SERVICE = "tables"


def generate_qr_code_base64(
    qr_token: str, 
    restaurant_slug: str, 
    restaurant_name: str = None,
    table_number: int = None,
    base_url: str = "http://localhost:5173"
) -> str:
    """Generate QR code with text overlay (restaurant name, table number, URL)."""
    qr_url = f"{base_url}/{restaurant_slug}/menu?table={qr_token}"
    
    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert QR to PIL Image
    qr_pil = qr_img.convert("RGBA")
    
    # Calculate dimensions
    qr_width, qr_height = qr_pil.size
    
    # Text area heights
    top_text_height = 60 if restaurant_name else 20
    bottom_text_height = 60 if table_number else 40
    
    # Total image dimensions
    total_width = qr_width
    total_height = qr_height + top_text_height + bottom_text_height
    
    # Create new image with white background
    final_img = Image.new("RGBA", (total_width, total_height), "white")
    
    # Paste QR code in the middle
    qr_y_offset = top_text_height
    final_img.paste(qr_pil, (0, qr_y_offset))
    
    # Draw text on image
    draw = ImageDraw.Draw(final_img)
    
    # Use default font (load_default works across all platforms)
    title_font = ImageFont.load_default()
    small_font = ImageFont.load_default()
    url_font = ImageFont.load_default()
    
    # Draw restaurant name at top (centered)
    if restaurant_name:
        # Wrap text if too long
        max_width = total_width - 20
        wrapped_name = textwrap.fill(restaurant_name, width=25)
        bbox = draw.textbbox((0, 0), wrapped_name, font=title_font)
        text_width = bbox[2] - bbox[0]
        text_x = (total_width - text_width) // 2
        draw.text((text_x, 10), wrapped_name, fill="black", font=title_font)
    
    # Draw "Table: X" below restaurant name
    if table_number:
        table_text = f"Table: {table_number}"
        bbox = draw.textbbox((0, 0), table_text, font=small_font)
        text_width = bbox[2] - bbox[0]
        text_x = (total_width - text_width) // 2
        draw.text((text_x, top_text_height - 20 if restaurant_name else 30), table_text, fill="black", font=small_font)
    
    # Draw URL at bottom (centered)
    url_y = total_height - 25
    # Wrap URL if too long
    wrapped_url = textwrap.fill(qr_url, width=40)
    bbox = draw.textbbox((0, 0), wrapped_url, font=url_font)
    text_width = bbox[2] - bbox[0]
    text_x = (total_width - text_width) // 2
    draw.text((text_x, url_y), wrapped_url, fill="gray", font=url_font)
    
    # Save to buffer
    buffered = io.BytesIO()
    final_img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()


@router.get("/", response_model=List[TableResponse])
async def get_tables(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    logger.api_request(SERVICE, "GET", "/", skip=skip, limit=limit)
    result = await db.execute(
        select(Table)
        .where(Table.restaurant_id == current_user.restaurant_id)
        .order_by(Table.table_number)
        .offset(skip)
        .limit(limit)
    )
    tables = result.scalars().all()
    logger.api_response(SERVICE, "GET", "/", 200, count=len(tables))
    return tables


@router.post("/", response_model=TableWithQRResponse, status_code=status.HTTP_201_CREATED)
async def create_table(
    table: TableCreate, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    logger.api_request(SERVICE, "POST", "/", table_number=table.table_number)
    result = await db.execute(
        select(Table).where(
            Table.table_number == table.table_number,
            Table.restaurant_id == current_user.restaurant_id
        )
    )
    if result.scalar_one_or_none():
        logger.api_error(SERVICE, "POST", "/", "Table number already exists", table_number=table.table_number)
        raise HTTPException(status_code=400, detail="Table number already exists")
    restaurant_result = await db.execute(select(Restaurant).where(Restaurant.id == current_user.restaurant_id))
    restaurant = restaurant_result.scalar_one_or_none()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    db_table = Table(**table.model_dump(), restaurant_id=current_user.restaurant_id)
    db.add(db_table)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.api_error(
            SERVICE,
            "POST",
            "/",
            "Table number already exists (constraint conflict)",
            table_number=table.table_number,
        )
        raise HTTPException(
            status_code=400,
            detail="Table number already exists for this restaurant.",
        )
    await db.refresh(db_table)
    qr_code_url = generate_qr_code_base64(
        db_table.qr_token, 
        restaurant.slug,
        restaurant_name=restaurant.name,
        table_number=db_table.table_number
    )
    logger.api_response(SERVICE, "POST", "/", 201, table_id=str(db_table.id), table_number=db_table.table_number)
    return TableWithQRResponse(**{**db_table.__dict__, "restaurant_slug": restaurant.slug, "qr_code_url": qr_code_url})


@router.get("/{table_id}", response_model=TableResponse)
async def get_table(
    table_id: str, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    logger.api_request(SERVICE, "GET", f"/{table_id}", table_id=table_id)
    result = await db.execute(
        select(Table).where(
            Table.id == table_id,
            Table.restaurant_id == current_user.restaurant_id
        )
    )
    table = result.scalar_one_or_none()
    if not table:
        logger.api_error(SERVICE, "GET", f"/{table_id}", "Table not found", table_id=table_id)
        raise HTTPException(status_code=404, detail="Table not found")
    logger.api_response(SERVICE, "GET", f"/{table_id}", 200, table_id=table_id, table_number=table.table_number)
    return table


@router.get("/by-token/{qr_token}", response_model=TableResponse)
async def get_table_by_token(qr_token: str, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "GET", f"/by-token/{qr_token}", qr_token=qr_token[:8] + "...")
    result = await db.execute(select(Table).where(Table.qr_token == qr_token))
    table = result.scalar_one_or_none()
    if not table:
        logger.api_error(SERVICE, "GET", f"/by-token/{qr_token}", "Invalid QR token")
        raise HTTPException(status_code=404, detail="Invalid QR token")
    restaurant_result = await db.execute(select(Restaurant).where(Restaurant.id == table.restaurant_id))
    restaurant = restaurant_result.scalar_one_or_none()
    logger.api_response(SERVICE, "GET", f"/by-token/{qr_token}", 200, table_id=str(table.id), table_number=table.table_number)
    return TableResponse(**{**table.__dict__, "restaurant_slug": restaurant.slug if restaurant else None})


@router.get("/{table_id}/qr", response_model=TableWithQRResponse)
async def get_table_qr(
    table_id: str, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    logger.api_request(SERVICE, "GET", f"/{table_id}/qr", table_id=table_id)
    result = await db.execute(
        select(Table).where(
            Table.id == table_id,
            Table.restaurant_id == current_user.restaurant_id
        )
    )
    table = result.scalar_one_or_none()
    if not table:
        logger.api_error(SERVICE, "GET", f"/{table_id}/qr", "Table not found", table_id=table_id)
        raise HTTPException(status_code=404, detail="Table not found")
    restaurant_result = await db.execute(select(Restaurant).where(Restaurant.id == table.restaurant_id))
    restaurant = restaurant_result.scalar_one_or_none()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    qr_code_url = generate_qr_code_base64(
        table.qr_token, 
        restaurant.slug,
        restaurant_name=restaurant.name,
        table_number=table.table_number
    )
    logger.api_response(SERVICE, "GET", f"/{table_id}/qr", 200, table_id=table_id)
    return TableWithQRResponse(**{**table.__dict__, "restaurant_slug": restaurant.slug, "qr_code_url": qr_code_url})


@router.delete("/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_table(
    table_id: str, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    logger.api_request(SERVICE, "DELETE", f"/{table_id}", table_id=table_id)
    result = await db.execute(
        select(Table)
        .options(selectinload(Table.sessions))
        .where(
            Table.id == table_id,
            Table.restaurant_id == current_user.restaurant_id
        )
    )
    table = result.scalar_one_or_none()
    if not table:
        logger.api_error(SERVICE, "DELETE", f"/{table_id}", "Table not found", table_id=table_id)
        raise HTTPException(status_code=404, detail="Table not found")
    
    # Get all session IDs for this table
    session_ids = [session.id for session in table.sessions]
    
    # Delete related bills first to avoid NOT NULL constraint violation on session_id
    if session_ids:
        await db.execute(
            delete(Bill).where(Bill.session_id.in_(session_ids))
        )
    
    await db.delete(table)
    await db.commit()
    logger.api_response(SERVICE, "DELETE", f"/{table_id}", 204, table_id=table_id)


@router.post("/{qr_token}/session", response_model=dict)
async def get_or_create_session(qr_token: str, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "POST", f"/{qr_token[:8]}.../session")
    result = await db.execute(select(Table).where(Table.qr_token == qr_token))
    table = result.scalar_one_or_none()
    if not table:
        logger.api_error(SERVICE, "POST", f"/{qr_token[:8]}.../session", "Invalid QR token")
        raise HTTPException(status_code=404, detail="Invalid QR token")

    result = await db.execute(
        select(OrderSession).where(
            OrderSession.table_id == table.id,
            func.lower(cast(OrderSession.session_status, String)) == SessionStatus.ACTIVE.value
        )
    )
    active_session = result.scalar_one_or_none()

    if active_session:
        logger.api_response(SERVICE, "POST", f"/{qr_token[:8]}.../session", 200, 
                          table_id=str(table.id), session_id=str(active_session.id), action="retrieved")
        return {"table_id": table.id, "table_number": table.table_number, "session_id": active_session.id}

    new_session = OrderSession(table_id=table.id)
    table.status = TableStatus.OCCUPIED
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    logger.api_response(SERVICE, "POST", f"/{qr_token[:8]}.../session", 201,
                       table_id=str(table.id), session_id=str(new_session.id), action="created")
    return {"table_id": table.id, "table_number": table.table_number, "session_id": new_session.id}


public_router = APIRouter(prefix="/api/tables/public", tags=["Tables - Public"])


@public_router.get("/{restaurant_slug}/by-token/{qr_token}", response_model=TableResponse)
async def get_table_by_token_public(
    restaurant_slug: str,
    qr_token: str,
    db: AsyncSession = Depends(get_db)
):
    logger.api_request(SERVICE, "GET", f"/public/{restaurant_slug}/by-token/{qr_token[:8]}...")
    result = await db.execute(select(Restaurant).where(Restaurant.slug == restaurant_slug))
    restaurant = result.scalar_one_or_none()
    if not restaurant:
        logger.api_error(SERVICE, "GET", f"/public/{restaurant_slug}/by-token/", "Restaurant not found")
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    result = await db.execute(
        select(Table).where(
            Table.qr_token == qr_token,
            Table.restaurant_id == restaurant.id
        )
    )
    table = result.scalar_one_or_none()
    if not table:
        logger.api_error(SERVICE, "GET", f"/public/{restaurant_slug}/by-token/{qr_token[:8]}...", "Invalid QR token")
        raise HTTPException(status_code=404, detail="Invalid QR token")
    logger.api_response(SERVICE, "GET", f"/public/{restaurant_slug}/by-token/{qr_token[:8]}...", 200, table_id=str(table.id), table_number=table.table_number)
    return table


@public_router.post("/{restaurant_slug}/{qr_token}/session", response_model=dict)
async def get_or_create_session_public(
    restaurant_slug: str,
    qr_token: str,
    db: AsyncSession = Depends(get_db)
):
    logger.api_request(SERVICE, "POST", f"/public/{restaurant_slug}/{qr_token[:8]}.../session")
    result = await db.execute(select(Restaurant).where(Restaurant.slug == restaurant_slug))
    restaurant = result.scalar_one_or_none()
    if not restaurant:
        logger.api_error(SERVICE, "POST", f"/public/{restaurant_slug}/", "Restaurant not found")
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    result = await db.execute(
        select(Table).where(
            Table.qr_token == qr_token,
            Table.restaurant_id == restaurant.id
        )
    )
    table = result.scalar_one_or_none()
    if not table:
        logger.api_error(SERVICE, "POST", f"/public/{restaurant_slug}/{qr_token[:8]}.../session", "Invalid QR token")
        raise HTTPException(status_code=404, detail="Invalid QR token")

    result = await db.execute(
        select(OrderSession).where(
            OrderSession.table_id == table.id,
            func.lower(cast(OrderSession.session_status, String)) == SessionStatus.ACTIVE.value
        )
    )
    active_session = result.scalar_one_or_none()

    if active_session:
        logger.api_response(SERVICE, "POST", f"/public/{restaurant_slug}/{qr_token[:8]}.../session", 200, 
                          table_id=str(table.id), session_id=str(active_session.id), action="retrieved")
        return {"table_id": table.id, "table_number": table.table_number, "session_id": active_session.id}

    new_session = OrderSession(table_id=table.id, restaurant_id=restaurant.id)
    table.status = TableStatus.OCCUPIED
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    logger.api_response(SERVICE, "POST", f"/public/{restaurant_slug}/{qr_token[:8]}.../session", 201,
                       table_id=str(table.id), session_id=str(new_session.id), action="created")
    return {"table_id": table.id, "table_number": table.table_number, "session_id": new_session.id}
