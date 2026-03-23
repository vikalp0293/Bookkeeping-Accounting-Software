"""add user activity logs

Revision ID: add_user_activity_logs
Revises: 
Create Date: 2026-01-23 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_user_activity_logs'
down_revision = 'add_quickbooks_account_name'  # Latest migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create user_activity_logs table
    op.create_table(
        'user_activity_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=True),
        sa.Column('action_type', sa.String(), nullable=False),
        sa.Column('resource_type', sa.String(), nullable=True),
        sa.Column('resource_id', sa.Integer(), nullable=True),
        sa.Column('details', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_activity_logs_id'), 'user_activity_logs', ['id'], unique=False)
    op.create_index(op.f('ix_user_activity_logs_user_id'), 'user_activity_logs', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_activity_logs_workspace_id'), 'user_activity_logs', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_user_activity_logs_action_type'), 'user_activity_logs', ['action_type'], unique=False)
    op.create_index(op.f('ix_user_activity_logs_created_at'), 'user_activity_logs', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_activity_logs_created_at'), table_name='user_activity_logs')
    op.drop_index(op.f('ix_user_activity_logs_action_type'), table_name='user_activity_logs')
    op.drop_index(op.f('ix_user_activity_logs_workspace_id'), table_name='user_activity_logs')
    op.drop_index(op.f('ix_user_activity_logs_user_id'), table_name='user_activity_logs')
    op.drop_index(op.f('ix_user_activity_logs_id'), table_name='user_activity_logs')
    op.drop_table('user_activity_logs')
