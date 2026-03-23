#!/usr/bin/env python3
"""
Apply missing tables/columns directly to the DB (server). Uses the same
DATABASE_URL as the app. Run from backend: ./venv/bin/python apply_missing_schema.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from app.core.config import settings

# Head revision after all migrations we need
TARGET_REVISION = "add_file_document_type"

def main():
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"options": "-c search_path=public"},
    )
    with engine.begin() as conn:
        # 1. user_activity_logs table (if missing)
        r = conn.execute(text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'user_activity_logs'
        """))
        if r.scalar() is None:
            print("Creating table user_activity_logs...")
            conn.execute(text("""
                CREATE TABLE user_activity_logs (
                    id SERIAL NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    workspace_id INTEGER NULL REFERENCES workspaces(id),
                    action_type VARCHAR NOT NULL,
                    resource_type VARCHAR NULL,
                    resource_id INTEGER NULL,
                    details JSON NULL,
                    ip_address VARCHAR NULL,
                    user_agent VARCHAR NULL,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
                )
            """))
            conn.execute(text("CREATE INDEX ix_user_activity_logs_id ON user_activity_logs (id)"))
            conn.execute(text("CREATE INDEX ix_user_activity_logs_user_id ON user_activity_logs (user_id)"))
            conn.execute(text("CREATE INDEX ix_user_activity_logs_workspace_id ON user_activity_logs (workspace_id)"))
            conn.execute(text("CREATE INDEX ix_user_activity_logs_action_type ON user_activity_logs (action_type)"))
            conn.execute(text("CREATE INDEX ix_user_activity_logs_created_at ON user_activity_logs (created_at)"))
            print("  Done.")
        else:
            print("Table user_activity_logs already exists.")

        # 2. files.document_type (if missing)
        r = conn.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'files' AND column_name = 'document_type'
        """))
        if r.scalar() is None:
            print("Adding column files.document_type...")
            conn.execute(text("ALTER TABLE files ADD COLUMN document_type VARCHAR NULL"))
            print("  Done.")
        else:
            print("Column files.document_type already exists.")

        # 3. payees.qb_expense_account_name (if missing)
        r = conn.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'payees' AND column_name = 'qb_expense_account_name'
        """))
        if r.scalar() is None:
            print("Adding column payees.qb_expense_account_name...")
            conn.execute(text("ALTER TABLE payees ADD COLUMN qb_expense_account_name VARCHAR NULL"))
            print("  Done.")
        else:
            print("Column payees.qb_expense_account_name already exists.")

        # 4. Ensure alembic_version reflects we're at head (so future alembic upgrade head is no-op)
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": TARGET_REVISION})
        print("Set alembic_version to", TARGET_REVISION)

    print("Schema update complete.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
