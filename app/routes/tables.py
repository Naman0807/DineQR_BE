from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import qrcode
import io
import base64

from app.database import get_db
from app.models.models import Table, OrderSession, SessionStatus, TableStatus, User
from app.schemas import TableCreate, TableResponse, TableWithQRResponse
from app.auth.dependencies import get_current_admin_user
from app.utils.logger import logger

router = APIRouter(prefix="/api/tables", tags=["Tables"])
SERVICE = "tables"


def generate_qr_code_base64(qr_token: str, base_url: str = "http://localhost:3000") -> str:
    qr_url = f"{base_url}/menu?table={qr_token}"
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(qr_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()


@router.get("/", response_model=List[TableResponse])
async def get_tables(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records to return"),
    db: AsyncSession = Depends(get_db)
):
    logger.api_request(SERVICE, "GET", "/", skip=skip, limit=limit)
    result = await db.execute(
        select(Table)
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
    result = await db.execute(select(Table).where(Table.table_number == table.table_number))
    if result.scalar_one_or_none():
        logger.api_error(SERVICE, "POST", "/", "Table number already exists", table_number=table.table_number)
        raise HTTPException(status_code=400, detail="Table number already exists")
    db_table = Table(**table.model_dump())
    db.add(db_table)
    await db.commit()
    await db.refresh(db_table)
    qr_code_url = generate_qr_code_base64(db_table.qr_token)
    logger.api_response(SERVICE, "POST", "/", 201, table_id=str(db_table.id), table_number=db_table.table_number)
    return TableWithQRResponse(**{**db_table.__dict__, "qr_code_url": qr_code_url})


@router.get("/{table_id}", response_model=TableResponse)
async def get_table(table_id: str, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "GET", f"/{table_id}", table_id=table_id)
    result = await db.execute(select(Table).where(Table.id == table_id))
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
    logger.api_response(SERVICE, "GET", f"/by-token/{qr_token}", 200, table_id=str(table.id), table_number=table.table_number)
    return table


@router.get("/{table_id}/qr", response_model=TableWithQRResponse)
async def get_table_qr(table_id: str, db: AsyncSession = Depends(get_db)):
    logger.api_request(SERVICE, "GET", f"/{table_id}/qr", table_id=table_id)
    result = await db.execute(select(Table).where(Table.id == table_id))
    table = result.scalar_one_or_none()
    if not table:
        logger.api_error(SERVICE, "GET", f"/{table_id}/qr", "Table not found", table_id=table_id)
        raise HTTPException(status_code=404, detail="Table not found")
    qr_code_url = generate_qr_code_base64(table.qr_token)
    logger.api_response(SERVICE, "GET", f"/{table_id}/qr", 200, table_id=table_id)
    return TableWithQRResponse(**{**table.__dict__, "qr_code_url": qr_code_url})


@router.delete("/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_table(
    table_id: str, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    logger.api_request(SERVICE, "DELETE", f"/{table_id}", table_id=table_id)
    result = await db.execute(select(Table).where(Table.id == table_id))
    table = result.scalar_one_or_none()
    if not table:
        logger.api_error(SERVICE, "DELETE", f"/{table_id}", "Table not found", table_id=table_id)
        raise HTTPException(status_code=404, detail="Table not found")
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
            OrderSession.session_status == SessionStatus.ACTIVE
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
