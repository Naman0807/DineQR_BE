# Add restaurant_id columns and foreign key constraint
"""
Revision ID: 002
Revises: 001
Create Date: 2024-01-02

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add foreign key constraint for users.restaurant_id (column was created in 001)
    op.create_foreign_key(
        'fk_users_restaurant_id',
        'users', 'restaurants',
        ['restaurant_id'], ['id'],
        ondelete='CASCADE'
    )

    op.add_column('tables', sa.Column('restaurant_id', sa.String(36), nullable=True))
    op.create_index('ix_tables_restaurant_id', 'tables', ['restaurant_id'])

    op.add_column('menu_categories', sa.Column('restaurant_id', sa.String(36), nullable=True))
    op.create_index('ix_menu_categories_restaurant_id', 'menu_categories', ['restaurant_id'])

    op.add_column('order_sessions', sa.Column('restaurant_id', sa.String(36), nullable=True))
    op.create_index('ix_order_sessions_restaurant_id', 'order_sessions', ['restaurant_id'])


def downgrade() -> None:
    op.drop_index('ix_order_sessions_restaurant_id', 'order_sessions')
    op.drop_column('order_sessions', 'restaurant_id')

    op.drop_index('ix_menu_categories_restaurant_id', 'menu_categories')
    op.drop_column('menu_categories', 'restaurant_id')

    op.drop_index('ix_tables_restaurant_id', 'tables')
    op.drop_column('tables', 'restaurant_id')

    op.drop_constraint('fk_users_restaurant_id', 'users', type_='foreignkey')
