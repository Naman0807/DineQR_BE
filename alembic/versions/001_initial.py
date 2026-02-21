# Initial empty database

Revision ID: 001
Revises:
Create Date: 2024-01-01

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tables',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('table_number', sa.Integer, unique=True, nullable=False),
        sa.Column('qr_token', sa.String(50), unique=True),
        sa.Column('status', sa.String(20), default='available'),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
    )

    op.create_table(
        'menu_categories',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('display_order', sa.Integer, default=0),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
    )

    op.create_table(
        'menu_items',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('category_id', sa.String(36), sa.ForeignKey('menu_categories.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('price', sa.Numeric(10, 2), nullable=False),
        sa.Column('is_available', sa.Boolean, default=True),
        sa.Column('image_url', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_table(
        'order_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('table_id', sa.String(36), sa.ForeignKey('tables.id', ondelete='CASCADE'), nullable=False),
        sa.Column('session_status', sa.String(20), default='active'),
        sa.Column('started_at', sa.DateTime, default=sa.func.now()),
        sa.Column('ended_at', sa.DateTime, nullable=True),
    )

    op.create_table(
        'orders',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('order_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(20), default='received'),
        sa.Column('total_amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_table(
        'order_items',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('order_id', sa.String(36), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('menu_item_id', sa.String(36), sa.ForeignKey('menu_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('quantity', sa.Integer, nullable=False),
        sa.Column('unit_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('special_instructions', sa.String(500), nullable=True),
        sa.Column('status', sa.String(20), default='pending'),
    )

    op.create_table(
        'bills',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('order_sessions.id', ondelete='CASCADE'), unique=True, nullable=False),
        sa.Column('subtotal', sa.Numeric(10, 2), nullable=False),
        sa.Column('tax_amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('discount_amount', sa.Numeric(10, 2), default=0),
        sa.Column('final_total', sa.Numeric(10, 2), nullable=False),
        sa.Column('payment_status', sa.String(20), default='unpaid'),
        sa.Column('payment_method', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('paid_at', sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_table('bills')
    op.drop_table('order_items')
    op.drop_table('orders')
    op.drop_table('order_sessions')
    op.drop_table('menu_items')
    op.drop_table('menu_categories')
    op.drop_table('tables')
