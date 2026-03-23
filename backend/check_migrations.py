#!/usr/bin/env python3
"""
Check database migration status
Verifies all tables exist and migrations are up to date
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, inspect, text
from app.core.config import settings
from app.db.base import Base
from app.models import (
    User, Workspace, File, ExtractedData, LoginSession,
    Payee, PayeeCorrection, Vendor, Category, ReviewQueue, 
    LocalDirectory, QBTransactionQueue
)

def check_tables():
    """Check if all expected tables exist in the database"""
    engine = create_engine(settings.DATABASE_URL)
    inspector = inspect(engine)
    
    # Get all tables in database
    existing_tables = set(inspector.get_table_names())
    
    # Expected tables from models
    expected_tables = {
        'users',
        'login_sessions',
        'workspaces',
        'files',
        'extracted_data',
        'categories',
        'vendors',
        'payees',
        'payee_corrections',
        'review_queue',
        'local_directories',
        'qb_transaction_queue'
    }
    
    print("=" * 60)
    print("Database Migration Status Check")
    print("=" * 60)
    print()
    
    # Check each expected table
    missing_tables = []
    for table in expected_tables:
        if table in existing_tables:
            print(f"✓ {table}")
        else:
            print(f"✗ {table} - MISSING")
            missing_tables.append(table)
    
    print()
    print("=" * 60)
    
    if missing_tables:
        print(f"❌ {len(missing_tables)} table(s) are missing:")
        for table in missing_tables:
            print(f"   - {table}")
        print()
        print("Action required: Run migrations")
        print("   Command: alembic upgrade head")
        return False
    else:
        print("✅ All tables exist in database")
        return True

def check_alembic_version():
    """Check current Alembic migration version"""
    try:
        engine = create_engine(settings.DATABASE_URL)
        with engine.connect() as conn:
            # Check if alembic_version table exists
            inspector = inspect(engine)
            if 'alembic_version' not in inspector.get_table_names():
                print("⚠️  Alembic version table not found")
                print("   This might be a fresh database")
                return None
            
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            if row:
                current_version = row[0]
                print(f"Current migration version: {current_version}")
                return current_version
            else:
                print("⚠️  No migration version found")
                return None
    except Exception as e:
        print(f"⚠️  Could not check Alembic version: {e}")
        return None

def check_enums():
    """Check if all required ENUM types exist"""
    engine = create_engine(settings.DATABASE_URL)
    
    expected_enums = {
        'filestatus': ['UPLOADED', 'PROCESSING', 'COMPLETED', 'FAILED'],
        'reviewpriority': ['HIGH', 'MEDIUM', 'LOW'],
        'reviewstatus': ['PENDING', 'IN_REVIEW', 'APPROVED', 'REJECTED', 'COMPLETED', 'SKIPPED'],
        'reviewreason': ['LOW_CONFIDENCE', 'MISSING_FIELDS', 'NON_ENGLISH', 'NO_PAYEE_MATCH', 'USER_FLAGGED', 'PAYEE_CORRECTION', 'OTHER'],
        'qb_transaction_status': ['pending', 'queued', 'syncing', 'synced', 'failed']
    }
    
    print()
    print("=" * 60)
    print("ENUM Types Check")
    print("=" * 60)
    
    with engine.connect() as conn:
        for enum_name, enum_values in expected_enums.items():
            try:
                # Check if enum exists by querying pg_type
                result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_type 
                        WHERE typname = :enum_name
                    )
                """), {"enum_name": enum_name})
                
                exists = result.fetchone()[0]
                if exists:
                    print(f"✓ {enum_name}")
                else:
                    print(f"✗ {enum_name} - MISSING")
            except Exception as e:
                print(f"⚠️  Error checking {enum_name}: {e}")

if __name__ == "__main__":
    print()
    tables_ok = check_tables()
    print()
    version = check_alembic_version()
    print()
    check_enums()
    print()
    print("=" * 60)
    
    if tables_ok:
        print("✅ Database appears to be up to date")
        print()
        print("To verify migrations are current, run:")
        print("   alembic current")
        print("   alembic heads")
    else:
        print("❌ Database is missing tables")
        print()
        print("Run migrations with:")
        print("   alembic upgrade head")
    print("=" * 60)

