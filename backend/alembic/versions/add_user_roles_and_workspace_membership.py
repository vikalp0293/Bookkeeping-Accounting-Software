"""add user roles and workspace membership

Revision ID: add_user_roles_ws_membership
Revises: add_multi_company
Create Date: 2026-02-03

Adds:
- users.role (superuser/admin/reviewer/accountant)
- users.workspace_id (FK to workspaces.id) for workspace membership

Data migration:
- role = 'superuser' where users.is_superuser is true else 'admin'
- workspace_id set to the first workspace owned by the user (if any)
"""

from alembic import op
import sqlalchemy as sa


revision = "add_user_roles_ws_membership"
down_revision = "add_multi_company"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add columns (nullable first for safe backfill)
    op.add_column("users", sa.Column("role", sa.String(), nullable=True))
    op.add_column("users", sa.Column("workspace_id", sa.Integer(), nullable=True))

    op.create_foreign_key(
        "fk_users_workspace_id_workspaces",
        "users",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_workspace_id", "users", ["workspace_id"])
    op.create_index("ix_users_role", "users", ["role"])

    # 2) Backfill role based on existing is_superuser
    op.execute(
        "UPDATE users SET role = CASE WHEN is_superuser THEN 'superuser' ELSE 'admin' END"
    )

    # 3) Backfill workspace membership using owned workspace (if any)
    #    (Reviewer/Accountant do not exist yet; existing users become Admins.)
    op.execute(
        """
        UPDATE users u
        SET workspace_id = sub.workspace_id
        FROM (
          SELECT owner_id, MIN(id) AS workspace_id
          FROM workspaces
          GROUP BY owner_id
        ) sub
        WHERE u.id = sub.owner_id
        """
    )

    # 4) Enforce role not null with default
    op.alter_column("users", "role", existing_type=sa.String(), nullable=False, server_default="admin")


def downgrade() -> None:
    op.alter_column("users", "role", existing_type=sa.String(), nullable=True, server_default=None)
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_workspace_id", table_name="users")
    op.drop_constraint("fk_users_workspace_id_workspaces", "users", type_="foreignkey")
    op.drop_column("users", "workspace_id")
    op.drop_column("users", "role")

