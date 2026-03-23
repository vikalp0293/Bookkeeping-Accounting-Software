"""add workspace company_account_map and queue company_file

Revision ID: add_multi_company
Revises: add_file_document_type
Create Date: 2026-03-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'add_multi_company'
down_revision = 'add_file_document_type'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'workspaces',
        sa.Column('company_account_map', postgresql.JSON(astext_type=sa.Text()), nullable=True)
    )
    op.add_column(
        'qb_transaction_queue',
        sa.Column('company_file', sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('qb_transaction_queue', 'company_file')
    op.drop_column('workspaces', 'company_account_map')
