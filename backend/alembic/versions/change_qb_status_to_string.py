"""change qb status to string

Revision ID: change_qb_status_to_string
Revises: add_qb_transaction_queue
Create Date: 2026-01-09 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'change_qb_status_to_string'
down_revision = 'add_qb_transaction_queue'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Change status column from ENUM to String
    # First, alter the column to text type
    op.execute("""
        ALTER TABLE qb_transaction_queue 
        ALTER COLUMN status TYPE VARCHAR USING status::text
    """)
    
    # Optionally drop the enum type (commented out to be safe)
    # op.execute("DROP TYPE IF EXISTS qb_transaction_status")


def downgrade() -> None:
    # Recreate enum type
    qb_transaction_status = postgresql.ENUM(
        'pending', 'queued', 'syncing', 'synced', 'failed',
        name='qb_transaction_status',
        create_type=True
    )
    qb_transaction_status.create(op.get_bind(), checkfirst=True)
    
    # Change column back to enum
    op.execute("""
        ALTER TABLE qb_transaction_queue 
        ALTER COLUMN status TYPE qb_transaction_status 
        USING status::qb_transaction_status
    """)

