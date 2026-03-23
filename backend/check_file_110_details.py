#!/usr/bin/env python3
"""Check detailed transactions for file 110."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db.base import SessionLocal
from app.models.extracted_data import ExtractedData

db = SessionLocal()
try:
    extracted = db.query(ExtractedData).filter(ExtractedData.file_id == 110).first()
    if not extracted or not extracted.processed_data:
        print("No extracted data")
        sys.exit(1)
    
    transactions = extracted.processed_data.get('transactions', [])
    print(f"Total transactions: {len(transactions)}\n")
    
    # Show first 20 transactions
    print("First 20 transactions:")
    print("-" * 100)
    for i, trans in enumerate(transactions[:20], 1):
        date = trans.get('date', 'N/A')
        amount = trans.get('amount', 0)
        desc = (trans.get('description', '') or '')[:60]
        trans_type = trans.get('transaction_type', 'UNKNOWN')
        print(f"{i:3}. {date} | ${amount:10,.2f} | {trans_type:10} | {desc}")
    
    # Check for specific amounts from bank statement
    print("\n" + "=" * 100)
    print("Looking for specific bank statement transactions:")
    target_amounts = [1455.41, 1277.54, 1234.97, 3119.96, 1793.53]
    for target in target_amounts:
        matches = [t for t in transactions if abs(float(t.get('amount', 0)) - target) < 0.01]
        if matches:
            for m in matches:
                print(f"  Found ${target:,.2f}: Date={m.get('date')}, Desc={m.get('description', '')[:50]}")
        else:
            print(f"  NOT FOUND: ${target:,.2f}")
    
    # Check date range
    print("\n" + "=" * 100)
    print("Date range in extracted data:")
    dates = [t.get('date') for t in transactions if t.get('date')]
    if dates:
        print(f"  Earliest: {min(dates)}")
        print(f"  Latest: {max(dates)}")
    
    # Check for duplicates
    print("\n" + "=" * 100)
    print("Checking for duplicate amounts:")
    from collections import Counter
    amounts = [round(float(t.get('amount', 0)), 2) for t in transactions]
    amount_counts = Counter(amounts)
    duplicates = {amt: count for amt, count in amount_counts.items() if count > 1}
    if duplicates:
        print(f"  Found {len(duplicates)} amounts that appear multiple times:")
        for amt, count in list(duplicates.items())[:10]:
            print(f"    ${amt:,.2f}: {count} times")
    else:
        print("  No duplicate amounts found")
    
except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()
finally:
    db.close()
