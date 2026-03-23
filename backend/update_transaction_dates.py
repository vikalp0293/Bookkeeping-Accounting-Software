#!/usr/bin/env python3
"""
Script to update all transaction dates in qb_transaction_queue to January 14, 2026.
Usage: python update_transaction_dates.py
"""
import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.base import SessionLocal
from app.models.qb_transaction_queue import QBTransactionQueue
from sqlalchemy.orm.attributes import flag_modified

def update_transaction_dates():
    """Update all transaction_data dates to 2026-01-14"""
    db = SessionLocal()
    try:
        # Get all records from qb_transaction_queue
        records = db.query(QBTransactionQueue).all()
        
        if not records:
            print("No records found in qb_transaction_queue table.")
            return
        
        updated_count = 0
        target_date = "2026-01-14"
        
        for record in records:
            if record.transaction_data:
                # Update the date field in transaction_data
                # Handle different possible structures
                updated = False
                
                # If transaction_data has a direct 'date' field
                if 'date' in record.transaction_data:
                    record.transaction_data['date'] = target_date
                    updated = True
                
                # If transaction_data contains a transaction object with date
                # (check for nested structures)
                if isinstance(record.transaction_data, dict):
                    # Check for common nested structures
                    for key in ['transaction', 'data', 'raw_data']:
                        if key in record.transaction_data and isinstance(record.transaction_data[key], dict):
                            if 'date' in record.transaction_data[key]:
                                record.transaction_data[key]['date'] = target_date
                                updated = True
                    
                    # Also check if it's a list of transactions
                    for key in ['transactions']:
                        if key in record.transaction_data and isinstance(record.transaction_data[key], list):
                            for trans in record.transaction_data[key]:
                                if isinstance(trans, dict) and 'date' in trans:
                                    trans['date'] = target_date
                                    updated = True
                            if record.transaction_data[key]:
                                updated = True
                
                if updated:
                    # Mark the JSON field as modified so SQLAlchemy detects the change
                    flag_modified(record, 'transaction_data')
                    updated_count += 1
        
        if updated_count > 0:
            db.commit()
            print(f"✅ Successfully updated {updated_count} transaction(s) with date {target_date}")
        else:
            print("⚠️  No transaction dates were found to update.")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error updating transaction dates: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == '__main__':
    update_transaction_dates()
