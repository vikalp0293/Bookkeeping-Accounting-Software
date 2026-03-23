"""add file document_type

Revision ID: add_file_document_type
Revises: merge_heads_001
Create Date: 2025-02-03

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_file_document_type'
down_revision = 'merge_heads_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('files', sa.Column('document_type', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('files', 'document_type')
