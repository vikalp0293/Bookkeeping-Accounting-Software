"""add extracted_data updated_at default

Revision ID: add_extracted_data_updated_at_default
Revises: add_user_activity_logs
Create Date: 2026-01-29

Sets server default for extracted_data.updated_at so new extraction records
get updated_at on insert. Fixes incorrect brief 'failed' status on upload
when check_and_reset_stuck_files runs before the extraction has updated the row.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'extracted_data_updated_at_def'
down_revision = 'add_user_activity_logs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE extracted_data ALTER COLUMN updated_at SET DEFAULT now()"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE extracted_data ALTER COLUMN updated_at DROP DEFAULT"
    )
