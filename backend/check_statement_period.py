#!/usr/bin/env python3
"""Check statement period for file 110."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db.base import SessionLocal
from app.models.extracted_data import ExtractedData

db = SessionLocal()
try:
    extracted = db.query(ExtractedData).filter(ExtractedData.file_id == 110).first()
    if extracted and extracted.processed_data:
        data = extracted.processed_data
        stmt_start = data.get('statement_period_start')
        stmt_end = data.get('statement_period_end')
        
        print('=== STATEMENT PERIOD (from extracted data) ===')
        print(f'Start Date: {stmt_start}')
        print(f'End Date: {stmt_end}')
        print()
        
        # Check actual transaction date range
        transactions = data.get('transactions', [])
        if transactions:
            dates = [t.get('date') for t in transactions if t.get('date')]
            if dates:
                print('=== ACTUAL TRANSACTION DATE RANGE ===')
                print(f'Earliest transaction: {min(dates)}')
                print(f'Latest transaction: {max(dates)}')
                print(f'Total transactions: {len(transactions)}')
                print()
                
                # Count transactions within vs outside statement period
                if stmt_start and stmt_end:
                    within = [t for t in transactions 
                             if t.get('date') and 
                             stmt_start <= t.get('date') <= stmt_end]
                    outside = [t for t in transactions 
                              if t.get('date') and 
                              (t.get('date') < stmt_start or t.get('date') > stmt_end)]
                    
                    print(f'Transactions WITHIN statement period ({stmt_start} to {stmt_end}): {len(within)}')
                    print(f'Transactions OUTSIDE statement period: {len(outside)}')
                    print()
                    
                    if outside:
                        print('Sample transactions OUTSIDE statement period:')
                        for t in outside[:10]:
                            print(f'  {t.get("date")} - ${t.get("amount", 0):,.2f} - {t.get("description", "")[:50]}')
                    
                    # Calculate totals
                    within_total = sum(t.get('amount', 0) for t in within if t.get('amount', 0) > 0)
                    outside_total = sum(t.get('amount', 0) for t in outside if t.get('amount', 0) > 0)
                    print()
                    print(f'Total deposits WITHIN period: ${within_total:,.2f}')
                    print(f'Total deposits OUTSIDE period: ${outside_total:,.2f}')
                    print(f'Bank statement shows: $63,638.99 (January only)')
    
except Exception as e:
    import traceback
    print(f'Error: {e}')
    traceback.print_exc()
finally:
    db.close()
