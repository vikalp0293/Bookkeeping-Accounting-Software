"""add payee review queue local directory models

Revision ID: add_payee_review_queue
Revises: db0c4c45dea2
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_payee_review_queue'
down_revision = 'db0c4c45dea2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create categories table
    op.create_table('categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('parent_category_id', sa.Integer(), nullable=True),
        sa.Column('quickbooks_account', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['parent_category_id'], ['categories.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_categories_id'), 'categories', ['id'], unique=False)
    op.create_index(op.f('ix_categories_name'), 'categories', ['name'], unique=True)
    
    # Create vendors table
    op.create_table('vendors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('subcategory', sa.String(), nullable=True),
        sa.Column('common_payee_patterns', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('quickbooks_vendor_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_vendors_id'), 'vendors', ['id'], unique=False)
    op.create_index(op.f('ix_vendors_name'), 'vendors', ['name'], unique=True)
    
    # Create payees table
    op.create_table('payees',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('normalized_name', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('aliases', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('vendor_id', sa.Integer(), nullable=True),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], ),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_payees_id'), 'payees', ['id'], unique=False)
    op.create_index(op.f('ix_payees_normalized_name'), 'payees', ['normalized_name'], unique=False)
    
    # Create payee_corrections table
    op.create_table('payee_corrections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payee_id', sa.Integer(), nullable=False),
        sa.Column('original_payee', sa.String(), nullable=False),
        sa.Column('corrected_payee', sa.String(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('transaction_id', sa.String(), nullable=True),
        sa.Column('correction_reason', sa.String(), nullable=True),
        sa.Column('similarity_score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['payee_id'], ['payees.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_payee_corrections_id'), 'payee_corrections', ['id'], unique=False)
    
    # Create review_queue table
    op.create_table('review_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=False),
        sa.Column('transaction_id', sa.String(), nullable=True),
        sa.Column('review_reason', sa.Enum('LOW_CONFIDENCE', 'MISSING_FIELDS', 'NON_ENGLISH', 'NO_PAYEE_MATCH', 'USER_FLAGGED', 'PAYEE_CORRECTION', 'OTHER', name='reviewreason'), nullable=False),
        sa.Column('priority', sa.Enum('HIGH', 'MEDIUM', 'LOW', name='reviewpriority'), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'IN_REVIEW', 'APPROVED', 'REJECTED', 'COMPLETED', 'SKIPPED', name='reviewstatus'), nullable=True),
        sa.Column('assigned_to', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_review_queue_id'), 'review_queue', ['id'], unique=False)
    
    # Create local_directories table
    op.create_table('local_directories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('directory_path', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('scan_interval_minutes', sa.Integer(), nullable=True),
        sa.Column('last_scan_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id')
    )
    op.create_index(op.f('ix_local_directories_id'), 'local_directories', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_local_directories_id'), table_name='local_directories')
    op.drop_table('local_directories')
    op.drop_index(op.f('ix_review_queue_id'), table_name='review_queue')
    op.drop_table('review_queue')
    op.drop_index(op.f('ix_payee_corrections_id'), table_name='payee_corrections')
    op.drop_table('payee_corrections')
    op.drop_index(op.f('ix_payees_normalized_name'), table_name='payees')
    op.drop_index(op.f('ix_payees_id'), table_name='payees')
    op.drop_table('payees')
    op.drop_index(op.f('ix_vendors_name'), table_name='vendors')
    op.drop_index(op.f('ix_vendors_id'), table_name='vendors')
    op.drop_table('vendors')
    op.drop_index(op.f('ix_categories_name'), table_name='categories')
    op.drop_index(op.f('ix_categories_id'), table_name='categories')
    op.drop_table('categories')

