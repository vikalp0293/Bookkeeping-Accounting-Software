"""add quickbooks account name to workspace

Revision ID: add_quickbooks_account_name
Revises: change_qb_status_to_string
Create Date: 2026-01-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_quickbooks_account_name'
down_revision = 'change_qb_status_to_string'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add quickbooks_account_name column to workspaces table
    op.add_column('workspaces', sa.Column('quickbooks_account_name', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove quickbooks_account_name column from workspaces table
    op.drop_column('workspaces', 'quickbooks_account_name')

