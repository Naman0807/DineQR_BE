"""
Add otp_verifications table for customer OTP authentication

Revision ID: 007
Revises: 006
Create Date: 2026-04-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'otp_verifications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('phone_number', sa.String(20), nullable=False),
        sa.Column('otp_code', sa.String(10), nullable=False),
        sa.Column('restaurant_id', sa.String(36), sa.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('table_id', sa.String(36), sa.ForeignKey('tables.id', ondelete='CASCADE'), nullable=False),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('order_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('is_used', sa.Boolean, server_default=sa.text('false'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_otp_verifications_phone_number', 'otp_verifications', ['phone_number'])


def downgrade() -> None:
    op.drop_index('ix_otp_verifications_phone_number', 'otp_verifications')
    op.drop_table('otp_verifications')
