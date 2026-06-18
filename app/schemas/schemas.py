from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict
from typing import Optional
import enum


class TableStatus(str, enum.Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"

class SessionStatus(str, enum.Enum):
    PENDING = "pending"
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
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


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
    restaurant_slug: Optional[str] = None

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
    customer_id: Optional[str] = None


class OrderUpdate(BaseModel):
    status: OrderStatus


class OrderResponse(BaseModel):
    id: str
    session_id: str
    customer_id: Optional[str] = None
    status: OrderStatus
    total_amount: Decimal
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse]
    table_number: int | None = None

    model_config = ConfigDict(from_attributes=True)


class OrderSessionResponse(BaseModel):
    id: str
    table_id: str
    table_number: int
    session_status: SessionStatus
    requires_approval: bool = False
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


class PaymentCreate(BaseModel):
    bill_id: str
    customer_id: Optional[str] = None
    amount: Decimal
    payment_method: PaymentMethod


class PaymentResponse(BaseModel):
    id: str
    bill_id: str
    customer_id: Optional[str] = None
    amount: Decimal
    payment_method: PaymentMethod
    status: PaymentStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BillResponse(BaseModel):
    id: str
    session_id: str
    subtotal: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    final_total: Decimal
    created_at: datetime
    paid_at: Optional[datetime]
    table_number: int | None = None
    payments: list[PaymentResponse] = []

    model_config = ConfigDict(from_attributes=True)


class BillWithOrdersResponse(BillResponse):
    orders: list[OrderResponse]

    model_config = ConfigDict(from_attributes=True)



class OrderSessionWithOrdersResponse(OrderSessionResponse):
    orders: list[OrderResponse]

    model_config = ConfigDict(from_attributes=True)


# Restaurant Schemas
class RestaurantBase(BaseModel):
    name: str
    tax: float = 10.00


class RestaurantCreate(RestaurantBase):
    slug: str


class RestaurantUpdate(BaseModel):
    name: Optional[str] = None
    tax: Optional[float] = None
    slug: Optional[str] = None


class RestaurantResponse(RestaurantBase):
    id: str
    slug: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Settings Schemas
class RestaurantSettingsUpdate(BaseModel):
    restaurant_name: Optional[str] = None
    admin_email: Optional[str] = None
    admin_phone: Optional[str] = None
    restaurant_tax: Optional[float] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    logo_url: Optional[str] = None
    description: Optional[str] = None


class RestaurantSettingsResponse(BaseModel):
    restaurant_id: str
    restaurant_name: str
    restaurant_slug: str
    restaurant_tax: float
    admin_email: str
    admin_phone: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    logo_url: Optional[str] = None
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# Customer Registration Schema (direct auth - no OTP)
class CustomerRegisterRequest(BaseModel):
    name: str
    phone_number: str
    session_id: str


class CustomerAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int = 60

class PayBillRequest(BaseModel):
    payment_method: PaymentMethod
    customer_id: Optional[str] = None
