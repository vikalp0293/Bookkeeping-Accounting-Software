"""add qb transaction queue

Revision ID: add_qb_transaction_queue
Revises: add_payee_review_queue
Create Date: 2026-01-07 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_qb_transaction_queue'
down_revision = 'add_payee_review_queue'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create qb_transaction_status enum (with checkfirst to avoid errors if it already exists)
    qb_transaction_status = postgresql.ENUM(
        'pending', 'queued', 'syncing', 'synced', 'failed',
        name='qb_transaction_status',
        create_type=True
    )
    qb_transaction_status.create(op.get_bind(), checkfirst=True)
    
    # Create enum for table use (with create_type=False since we already created it)
    qb_transaction_status_table = postgresql.ENUM(
        'pending', 'queued', 'syncing', 'synced', 'failed',
        name='qb_transaction_status',
        create_type=False  # Don't try to create, we already did it above
    )
    
    # Create qb_transaction_queue table
    op.create_table('qb_transaction_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=False),
        sa.Column('transaction_index', sa.Integer(), nullable=True),
        sa.Column('transaction_id', sa.String(), nullable=True),
        sa.Column('transaction_data', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('status', qb_transaction_status_table, nullable=False, server_default='pending'),
        sa.Column('qbxml_request', sa.Text(), nullable=True),
        sa.Column('qbxml_response', sa.Text(), nullable=True),
        sa.Column('qb_transaction_id', sa.String(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('sync_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_sync_attempt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_qb_transaction_queue_id'), 'qb_transaction_queue', ['id'], unique=False)
    op.create_index(op.f('ix_qb_transaction_queue_workspace_id'), 'qb_transaction_queue', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_qb_transaction_queue_file_id'), 'qb_transaction_queue', ['file_id'], unique=False)
    op.create_index(op.f('ix_qb_transaction_queue_status'), 'qb_transaction_queue', ['status'], unique=False)
    op.create_index(op.f('ix_qb_transaction_queue_created_at'), 'qb_transaction_queue', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_qb_transaction_queue_created_at'), table_name='qb_transaction_queue')
    op.drop_index(op.f('ix_qb_transaction_queue_status'), table_name='qb_transaction_queue')
    op.drop_index(op.f('ix_qb_transaction_queue_file_id'), table_name='qb_transaction_queue')
    op.drop_index(op.f('ix_qb_transaction_queue_workspace_id'), table_name='qb_transaction_queue')
    op.drop_index(op.f('ix_qb_transaction_queue_id'), table_name='qb_transaction_queue')
    op.drop_table('qb_transaction_queue')
    
    # Drop enum
    qb_transaction_status = postgresql.ENUM(
        'pending', 'queued', 'syncing', 'synced', 'failed',
        name='qb_transaction_status'
    )
    qb_transaction_status.drop(op.get_bind(), checkfirst=True)

