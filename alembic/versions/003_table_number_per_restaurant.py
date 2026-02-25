"""
Make table numbers unique per restaurant instead of globally unique.

Revision ID: 003
Revises: 002
Create Date: 2026-02-24
"""

from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old global uniqueness on table_number if present.
    op.execute("ALTER TABLE tables DROP CONSTRAINT IF EXISTS tables_table_number_key")

    # Enforce per-restaurant uniqueness.
    op.create_unique_constraint(
        "uq_tables_restaurant_id_table_number",
        "tables",
        ["restaurant_id", "table_number"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_tables_restaurant_id_table_number", "tables", type_="unique")
    op.create_unique_constraint("tables_table_number_key", "tables", ["table_number"])
