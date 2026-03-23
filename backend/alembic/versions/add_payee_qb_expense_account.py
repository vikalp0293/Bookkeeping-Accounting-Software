"""add payee qb_expense_account_name

Revision ID: add_payee_qb_expense
Revises: add_quickbooks_account_name
Create Date: 2026-02-03 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_payee_qb_expense'
down_revision = 'add_quickbooks_account_name'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('payees', sa.Column('qb_expense_account_name', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('payees', 'qb_expense_account_name')
