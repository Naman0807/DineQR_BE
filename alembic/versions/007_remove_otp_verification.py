"""Remove OTP verification table"""

from alembic import op
import sqlalchemy as sa

revision = '007_remove_otp'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('otp_verifications')


def downgrade() -> None:
    op.create_table(
        'otp_verifications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('phone_number', sa.String(20), nullable=False),
        sa.Column('otp_code', sa.String(10), nullable=False),
        sa.Column('restaurant_id', sa.String(36), nullable=True),
        sa.Column('table_id', sa.String(36), nullable=True),
        sa.Column('session_id', sa.String(36), nullable=True),
        sa.Column('is_used', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime, servers_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('expires_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_otp_verifications_phone_number', 'otp_verifications', ['phone_number'])