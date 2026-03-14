"""Add restaurant settings fields (address, phone, logo_url, description)

Revision ID: 006
Revises: 005
Create Date: 2026-03-02
"""
from alembic import op
import sqlalchemy as sa
from typing import Union, Sequence

revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('restaurants', sa.Column('address', sa.Text(), nullable=True))
    op.add_column('restaurants', sa.Column('phone', sa.String(20), nullable=True))
    op.add_column('restaurants', sa.Column('logo_url', sa.String(500), nullable=True))
    op.add_column('restaurants', sa.Column('description', sa.Text(), nullable=True))

def downgrade() -> None:
    op.drop_column('restaurants', 'description')
    op.drop_column('restaurants', 'logo_url')
    op.drop_column('restaurants', 'phone')
    op.drop_column('restaurants', 'address')
