"""
Add restaurant_id to remaining tables and create customers table.

Revision ID: 004
Revises: 003
Create Date: 2026-03-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import func

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add restaurant_id to menu_items
    op.add_column(
        "menu_items", sa.Column("restaurant_id", sa.String(36), nullable=True)
    )
    op.create_index("ix_menu_items_restaurant_id", "menu_items", ["restaurant_id"])
    op.create_foreign_key(
        "fk_menu_items_restaurant_id",
        "menu_items",
        "restaurants",
        ["restaurant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Add restaurant_id to orders
    op.add_column(
        "orders", sa.Column("restaurant_id", sa.String(36), nullable=True)
    )
    op.create_index("ix_orders_restaurant_id", "orders", ["restaurant_id"])
    op.create_foreign_key(
        "fk_orders_restaurant_id",
        "orders",
        "restaurants",
        ["restaurant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Add restaurant_id to order_items
    op.add_column(
        "order_items", sa.Column("restaurant_id", sa.String(36), nullable=True)
    )
    op.create_index("ix_order_items_restaurant_id", "order_items", ["restaurant_id"])
    op.create_foreign_key(
        "fk_order_items_restaurant_id",
        "order_items",
        "restaurants",
        ["restaurant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Add restaurant_id to bills
    op.add_column(
        "bills", sa.Column("restaurant_id", sa.String(36), nullable=True)
    )
    op.create_index("ix_bills_restaurant_id", "bills", ["restaurant_id"])
    op.create_foreign_key(
        "fk_bills_restaurant_id",
        "bills",
        "restaurants",
        ["restaurant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Create customers table
    op.create_table(
        "customers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column("phone_number", sa.String(20), nullable=True),
        sa.Column(
            "restaurant_id", sa.String(36), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime, server_default=func.now()),
        sa.UniqueConstraint("phone_number", name="uq_customers_phone_number"),
    )
    op.create_index("ix_customers_restaurant_id", "customers", ["restaurant_id"])


def downgrade() -> None:
    # Drop customers table
    op.drop_index("ix_customers_restaurant_id", "customers")
    op.drop_table("customers")

    # Drop restaurant_id from bills
    op.drop_constraint("fk_bills_restaurant_id", "bills", type_="foreignkey")
    op.drop_index("ix_bills_restaurant_id", "bills")
    op.drop_column("bills", "restaurant_id")

    # Drop restaurant_id from order_items
    op.drop_constraint("fk_order_items_restaurant_id", "order_items", type_="foreignkey")
    op.drop_index("ix_order_items_restaurant_id", "order_items")
    op.drop_column("order_items", "restaurant_id")

    # Drop restaurant_id from orders
    op.drop_constraint("fk_orders_restaurant_id", "orders", type_="foreignkey")
    op.drop_index("ix_orders_restaurant_id", "orders")
    op.drop_column("orders", "restaurant_id")

    # Drop restaurant_id from menu_items
    op.drop_constraint("fk_menu_items_restaurant_id", "menu_items", type_="foreignkey")
    op.drop_index("ix_menu_items_restaurant_id", "menu_items")
    op.drop_column("menu_items", "restaurant_id")
