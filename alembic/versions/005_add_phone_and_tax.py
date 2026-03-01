"""
Add phone_number to users and tax to restaurants.

Revision ID: 005
Revises: 004
Create Date: 2026-03-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("phone_number", sa.String(20), nullable=True)
    )

    op.add_column(
        "restaurants", sa.Column("tax", sa.Numeric(5, 2), nullable=True, server_default="10.00")
    )


def downgrade() -> None:
    op.drop_column("restaurants", "tax")
    op.drop_column("users", "phone_number")
