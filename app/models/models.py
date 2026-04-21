import uuid
import secrets
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Text, Integer, Numeric, Boolean, DateTime, ForeignKey, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property
from app.database import Base
import enum


def generate_uuid() -> str:
    return str(uuid.uuid4())


def generate_qr_token() -> str:
    return f"res_tbl_{secrets.token_hex(6)}"


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


class UserRole(str, enum.Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    STAFF = "staff"


class RestaurantStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"


class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    status: Mapped[RestaurantStatus] = mapped_column(SQLEnum(RestaurantStatus, native_enum=False), default=RestaurantStatus.PENDING)
    tax: Mapped[float] = mapped_column(Numeric(5, 2), default=Decimal("10.00"))
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="restaurant", cascade="all, delete-orphan")
    tables: Mapped[list["Table"]] = relationship(back_populates="restaurant", cascade="all, delete-orphan")
    menu_categories: Mapped[list["MenuCategory"]] = relationship(back_populates="restaurant", cascade="all, delete-orphan")
    order_sessions: Mapped[list["OrderSession"]] = relationship(back_populates="restaurant", cascade="all, delete-orphan")
    menu_items: Mapped[list["MenuItem"]] = relationship(back_populates="restaurant", cascade="all, delete-orphan")
    orders: Mapped[list["Order"]] = relationship(back_populates="restaurant", cascade="all, delete-orphan")
    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="restaurant", cascade="all, delete-orphan")
    bills: Mapped[list["Bill"]] = relationship(back_populates="restaurant", cascade="all, delete-orphan")
    customers: Mapped[list["Customer"]] = relationship(back_populates="restaurant", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole, native_enum=False), default=UserRole.STAFF)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    restaurant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=True)

    restaurant: Mapped["Restaurant | None"] = relationship(back_populates="users")


class Table(Base):
    __tablename__ = "tables"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "table_number", name="uq_tables_restaurant_id_table_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    table_number: Mapped[int] = mapped_column(Integer, nullable=False)
    qr_token: Mapped[str] = mapped_column(String(50), unique=True, default=generate_qr_token)
    status: Mapped[TableStatus] = mapped_column(SQLEnum(TableStatus, native_enum=False), default=TableStatus.AVAILABLE)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    restaurant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=True)

    sessions: Mapped[list["OrderSession"]] = relationship(back_populates="table", cascade="all, delete-orphan")
    restaurant: Mapped["Restaurant | None"] = relationship(back_populates="tables")


class MenuCategory(Base):
    __tablename__ = "menu_categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    restaurant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=True)

    items: Mapped[list["MenuItem"]] = relationship(back_populates="category", cascade="all, delete-orphan")
    restaurant: Mapped["Restaurant | None"] = relationship(back_populates="menu_categories")


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    category_id: Mapped[str] = mapped_column(String(36), ForeignKey("menu_categories.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    restaurant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=True)

    category: Mapped["MenuCategory"] = relationship(back_populates="items")
    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="menu_item")
    restaurant: Mapped["Restaurant | None"] = relationship(back_populates="menu_items")


class OrderSession(Base):
    __tablename__ = "order_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    table_id: Mapped[str] = mapped_column(String(36), ForeignKey("tables.id", ondelete="CASCADE"), nullable=False)
    session_status: Mapped[SessionStatus] = mapped_column(SQLEnum(SessionStatus, native_enum=False), default=SessionStatus.ACTIVE)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    restaurant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=True)

    table: Mapped["Table"] = relationship(back_populates="sessions")
    orders: Mapped[list["Order"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    bill: Mapped["Bill | None"] = relationship(back_populates="session", uselist=False)
    restaurant: Mapped["Restaurant | None"] = relationship(back_populates="order_sessions")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("order_sessions.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(SQLEnum(OrderStatus, native_enum=False), default=OrderStatus.RECEIVED)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    restaurant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=True)

    session: Mapped["OrderSession"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    restaurant: Mapped["Restaurant | None"] = relationship(back_populates="orders")

    @hybrid_property
    def table_number(self) -> int | None:
        """Get table number from the session's table."""
        if self.session and self.session.table:
            return self.session.table.table_number
        return None


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    menu_item_id: Mapped[str] = mapped_column(String(36), ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    special_instructions: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[OrderItemStatus] = mapped_column(SQLEnum(OrderItemStatus, native_enum=False), default=OrderItemStatus.PENDING)
    restaurant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=True)

    order: Mapped["Order"] = relationship(back_populates="items")
    menu_item: Mapped["MenuItem"] = relationship(back_populates="order_items")
    restaurant: Mapped["Restaurant | None"] = relationship(back_populates="order_items")


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("order_sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    final_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_status: Mapped[PaymentStatus] = mapped_column(SQLEnum(PaymentStatus, native_enum=False), default=PaymentStatus.UNPAID)
    payment_method: Mapped[PaymentMethod | None] = mapped_column(SQLEnum(PaymentMethod, native_enum=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    restaurant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=True)

    session: Mapped["OrderSession"] = relationship(back_populates="bill")
    restaurant: Mapped["Restaurant | None"] = relationship(back_populates="bills")

    @hybrid_property
    def table_number(self) -> int | None:
        """Get table number from the session's table."""
        if self.session and self.session.table:
            return self.session.table.table_number
        return None


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    restaurant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    restaurant: Mapped["Restaurant | None"] = relationship(back_populates="customers")
