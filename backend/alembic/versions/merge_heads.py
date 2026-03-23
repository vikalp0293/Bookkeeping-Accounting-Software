"""merge heads: extracted_data_updated_at_def and add_payee_qb_expense

Revision ID: merge_heads_001
Revises: extracted_data_updated_at_def, add_payee_qb_expense
Create Date: 2026-02-03

"""
from alembic import op
import sqlalchemy as sa

revision = 'merge_heads_001'
down_revision = ('extracted_data_updated_at_def', 'add_payee_qb_expense')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
