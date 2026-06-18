"""
Schema refactor: global customers, bill splitting, multiplayer orders, session approval

- Add 'pending' to SessionStatus enum (application-level, native_enum=False)
- Add customer_id FK to orders
- Add requires_approval to order_sessions
- Remove restaurant_id from customers (global customers)
- Remove payment_status, payment_method from bills
- Create payments table (1:N bill splitting)
- Migrate existing paid bills to Payment records

Revision ID: 007
Revises: 006
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from typing import Union, Sequence

revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Add customer_id to orders
    op.add_column('orders', sa.Column('customer_id', sa.String(36), sa.ForeignKey('customers.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_orders_customer_id', 'orders', ['customer_id'])

    # Step 2: Add requires_approval to order_sessions
    op.add_column('order_sessions', sa.Column('requires_approval', sa.Boolean(), server_default='false', nullable=False))

    # Step 3: Remove restaurant_id from customers (global customers)
    op.drop_constraint('customers_restaurant_id_fkey', 'customers', type_='foreignkey')
    op.drop_index('ix_customers_restaurant_id', table_name='customers')
    op.drop_column('customers', 'restaurant_id')
    op.alter_column('customers', 'phone_number',
                    existing_type=sa.String(20),
                    nullable=False)

    # Step 4: Create payments table BEFORE data migration
    op.create_table('payments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('bill_id', sa.String(36), sa.ForeignKey('bills.id', ondelete='CASCADE'), nullable=False),
        sa.Column('customer_id', sa.String(36), sa.ForeignKey('customers.id', ondelete='SET NULL'), nullable=True),
        sa.Column('amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('payment_method', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), server_default='pending', nullable=False),
        sa.Column('restaurant_id', sa.String(36), sa.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_payments_bill_id', 'payments', ['bill_id'])
    op.create_index('ix_payments_customer_id', 'payments', ['customer_id'])
    op.create_index('ix_payments_restaurant_id', 'payments', ['restaurant_id'])

    # Step 5: Migrate existing paid bills to Payment records before dropping columns
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT id, final_total, payment_method, restaurant_id, created_at "
            "FROM bills WHERE payment_status = 'paid'"
        )
    )
    for row in result:
        pm = row.payment_method if row.payment_method else 'cash'
        conn.execute(
            sa.text(
                "INSERT INTO payments (id, bill_id, customer_id, amount, payment_method, status, restaurant_id, created_at) "
                "VALUES (:id, :bill_id, NULL, :amount, :payment_method, 'completed', :restaurant_id, :created_at)"
            ),
            {
                "id": str(__import__('uuid').uuid4()),
                "bill_id": row[0],
                "amount": row[1],
                "payment_method": pm,
                "restaurant_id": row[3],
                "created_at": row[4],
            }
        )

    # Step 6: Drop payment_status and payment_method from bills
    op.drop_column('bills', 'payment_status')
    op.drop_column('bills', 'payment_method')


def downgrade() -> None:
    # Revert Step 6: Drop payments table
    op.drop_table('payments')

    # Revert Step 5: Restore payment columns on bills
    op.add_column('bills', sa.Column('payment_status', sa.String(20), server_default='unpaid', nullable=False))
    op.add_column('bills', sa.Column('payment_method', sa.String(20), nullable=True))

    # Revert Step 4: Delete migrated payment data (already dropped by cascade)
    # No action needed

    # Revert Step 3: Restore restaurant_id on customers
    op.add_column('customers', sa.Column('restaurant_id', sa.String(36), sa.ForeignKey('restaurants.id', ondelete='CASCADE'), nullable=True))
    op.create_index('ix_customers_restaurant_id', 'customers', ['restaurant_id'])
    op.alter_column('customers', 'phone_number',
                    existing_type=sa.String(20),
                    nullable=True)

    # Revert Step 2: Remove requires_approval
    op.drop_column('order_sessions', 'requires_approval')

    # Revert Step 1: Remove customer_id from orders
    op.drop_index('ix_orders_customer_id', table_name='orders')
    op.drop_column('orders', 'customer_id')
