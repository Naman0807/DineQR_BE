from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict
from typing import Optional
import enum


class TableStatus(str, enum.Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"

class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class OrderStatus(str, enum.Enum):
    RECEIVED = "received"
    PREPARING = "preparing"
    SERVED = "served"


class OrderItemStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"


class PaymentStatus(str, enum.Enum):
    UNPAID = "unpaid"
    PAID = "paid"


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    CARD = "card"
    UPI = "upi"


class MenuCategoryBase(BaseModel):
    name: str
    display_order: int = 0


class MenuCategoryCreate(MenuCategoryBase):
    pass


class MenuCategoryUpdate(BaseModel):
    name: Optional[str] = None
    display_order: Optional[int] = None


class MenuCategoryResponse(MenuCategoryBase):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MenuItemBase(BaseModel):
    category_id: str
    name: str
    description: Optional[str] = None
    price: Decimal
    is_available: bool = True
    image_url: Optional[str] = None


class MenuItemCreate(MenuItemBase):
    pass


class MenuItemUpdate(BaseModel):
    category_id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    is_available: Optional[bool] = None
    image_url: Optional[str] = None


class MenuItemResponse(MenuItemBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MenuItemWithCategory(MenuItemResponse):
    category: MenuCategoryResponse

    model_config = ConfigDict(from_attributes=True)


class TableBase(BaseModel):
    table_number: int


class TableCreate(TableBase):
    pass


class TableResponse(TableBase):
    id: str
    qr_token: str
    status: TableStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TableWithQRResponse(TableResponse):
    qr_code_url: str


class OrderItemCreate(BaseModel):
    menu_item_id: str
    quantity: int
    special_instructions: Optional[str] = None


class OrderItemResponse(BaseModel):
    id: str
    menu_item_id: str
    menu_item_name: str
    quantity: int
    unit_price: Decimal
    special_instructions: Optional[str]
    status: OrderItemStatus

    model_config = ConfigDict(from_attributes=True)


class OrderCreate(BaseModel):
    session_id: str
    items: list[OrderItemCreate]


class OrderUpdate(BaseModel):
    status: OrderStatus


class OrderResponse(BaseModel):
    id: str
    session_id: str
    status: OrderStatus
    total_amount: Decimal
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse]

    model_config = ConfigDict(from_attributes=True)


class OrderSessionResponse(BaseModel):
    id: str
    table_id: str
    table_number: int
    session_status: SessionStatus
    started_at: datetime
    ended_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class BillBase(BaseModel):
    subtotal: Decimal
    tax_amount: Decimal
    discount_amount: Decimal = Decimal("0.00")


class BillCreate(BillBase):
    session_id: str


class BillUpdate(BaseModel):
    discount_amount: Optional[Decimal] = None
    payment_status: Optional[PaymentStatus] = None
    payment_method: Optional[PaymentMethod] = None


class BillResponse(BaseModel):
    id: str
    session_id: str
    subtotal: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    final_total: Decimal
    payment_status: PaymentStatus
    payment_method: Optional[PaymentMethod]
    created_at: datetime
    paid_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class BillWithOrdersResponse(BillResponse):
    orders: list[OrderResponse]

    model_config = ConfigDict(from_attributes=True)


class OrderSessionWithOrdersResponse(OrderSessionResponse):
    orders: list[OrderResponse]

    model_config = ConfigDict(from_attributes=True)
