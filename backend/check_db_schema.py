#!/usr/bin/env python3
"""
Connect to the database from .env and report missing tables and columns
compared to the application models.
"""
import os
import sys

# Ensure backend root is on path so app imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, inspect, text
from app.core.config import settings
from app.db.base import Base

# Import all models so Base.metadata is fully populated
from app.models import (  # noqa: F401
    User, Workspace, File, ExtractedData, LoginSession,
    Payee, PayeeCorrection, Vendor, Category, ReviewQueue,
    LocalDirectory, QBTransactionQueue, UserActivityLog,
)


def main():
    url = settings.DATABASE_URL
    # Mask password in output
    display_url = url
    if "@" in url and ":" in url:
        try:
            before_at = url.split("@")[0]
            user_part = before_at.split("//")[-1]
            if ":" in user_part:
                user = user_part.split(":")[0]
                display_url = url.replace(user_part, f"{user}:****", 1)
        except Exception:
            pass

    print(f"Connecting to: {display_url}")
    print()

    engine = create_engine(
        url,
        connect_args={"options": "-c search_path=public"},
    )

    inspector = inspect(engine)

    # Get existing tables in public schema
    try:
        existing_tables = set(inspector.get_table_names())
    except Exception as e:
        print(f"Error listing tables: {e}")
        # Try raw SQL in case inspector has schema issues
        with engine.connect() as conn:
            r = conn.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            ))
            existing_tables = {row[0] for row in r}
    existing_tables.discard("alembic_version")

    # Expected tables from models
    expected_tables = set(Base.metadata.tables.keys())

    missing_tables = sorted(expected_tables - existing_tables)
    extra_tables = sorted(existing_tables - expected_tables)

    # Build expected columns per table from Base.metadata
    expected_columns = {}
    for name, table in Base.metadata.tables.items():
        expected_columns[name] = {c.name for c in table.c}

    # Get actual columns per table
    actual_columns = {}
    for t in existing_tables:
        try:
            actual_columns[t] = {c["name"] for c in inspector.get_columns(t)}
        except Exception as e:
            actual_columns[t] = set()
            print(f"  Warning: could not get columns for {t}: {e}")

    # Report
    print("=" * 60)
    print("MISSING TABLES (in models but not in DB)")
    print("=" * 60)
    if missing_tables:
        for t in missing_tables:
            cols = expected_columns.get(t, set())
            print(f"  - {t}")
            if cols:
                print(f"    Expected columns: {', '.join(sorted(cols))}")
        print()
    else:
        print("  (none)")
        print()

    print("=" * 60)
    print("MISSING COLUMNS (table exists but column missing)")
    print("=" * 60)
    any_missing_cols = False
    for t in sorted(expected_tables & existing_tables):
        exp = expected_columns.get(t, set())
        act = actual_columns.get(t, set())
        missing = sorted(exp - act)
        if missing:
            any_missing_cols = True
            print(f"  Table: {t}")
            print(f"    Missing columns: {', '.join(missing)}")
            print()
    if not any_missing_cols:
        print("  (none)")
        print()

    if extra_tables:
        print("=" * 60)
        print("EXTRA TABLES (in DB but not in models)")
        print("=" * 60)
        for t in extra_tables:
            print(f"  - {t}")
        print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Expected tables: {len(expected_tables)}")
    print(f"  Existing tables: {len(existing_tables)}")
    print(f"  Missing tables: {len(missing_tables)}")
    print(f"  Tables with missing columns: {sum(1 for t in (expected_tables & existing_tables) if (expected_columns.get(t, set()) - actual_columns.get(t, set())))}")
    print()

    if missing_tables or any_missing_cols:
        print("To fix: run migrations against this database:")
        print("  cd backend && ./venv/bin/alembic upgrade head")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
