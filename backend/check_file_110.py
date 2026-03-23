#!/usr/bin/env python3
"""Check extracted data for file 110 and simulate IIF export."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db.base import SessionLocal
from app.models.file import File
from app.models.extracted_data import ExtractedData
from datetime import datetime

db = SessionLocal()
try:
    file = db.query(File).filter(File.id == 110).first()
    if not file:
        print("File 110 not found")
        sys.exit(1)
    
    print(f"File 110: {file.filename}")
    print(f"Workspace: {file.workspace_id}")
    
    extracted = db.query(ExtractedData).filter(ExtractedData.file_id == 110).first()
    if not extracted or not extracted.processed_data:
        print("No extracted data found")
        sys.exit(1)
    
    data = extracted.processed_data
    transactions = data.get('transactions', [])
    print(f"\nTotal transactions: {len(transactions)}")
    
    # Check statement period
    stmt_start = data.get('statement_period_start')
    stmt_end = data.get('statement_period_end')
    print(f"Statement period: {stmt_start} to {stmt_end}")
    
    # Analyze dates
    print("\n=== DATE ANALYSIS ===")
    date_formats = {}
    mmdd_dates = []
    yyyymmdd_dates = []
    
    for trans in transactions:
        date = trans.get('date', '')
        date_str = str(date)
        
        if '/' in date_str and len(date_str) <= 5:
            date_formats['MM/DD'] = date_formats.get('MM/DD', 0) + 1
            mmdd_dates.append((date_str, trans.get('amount'), trans.get('description', '')[:40]))
        elif '2025' in date_str:
            date_formats['YYYY-MM-DD (2025)'] = date_formats.get('YYYY-MM-DD (2025)', 0) + 1
            yyyymmdd_dates.append((date_str, trans.get('amount'), trans.get('description', '')[:40]))
        elif '2026' in date_str:
            date_formats['YYYY-MM-DD (2026)'] = date_formats.get('YYYY-MM-DD (2026)', 0) + 1
    
    print(f"\nDate format distribution:")
    for fmt, count in date_formats.items():
        print(f"  {fmt}: {count}")
    
    if mmdd_dates:
        print(f"\n⚠️  Found {len(mmdd_dates)} transactions with MM/DD format (no year):")
        for date, amount, desc in mmdd_dates[:10]:
            print(f"    {date} | ${amount} | {desc}")
    
    # Simulate IIF date conversion
    print("\n=== IIF DATE CONVERSION SIMULATION ===")
    print("How MM/DD dates would be converted to IIF format:")
    current_year = datetime.now().year
    current_date = datetime.now()
    
    sample_mmdd = mmdd_dates[:5] if mmdd_dates else []
    for date_str, amount, desc in sample_mmdd:
        try:
            dt = datetime.strptime(date_str, '%m/%d')
            dt_with_year = dt.replace(year=current_year)
            
            if dt_with_year > current_date:
                days_ahead = (dt_with_year - current_date).days
                months_ahead = (dt_with_year.year - current_date.year) * 12 + (dt_with_year.month - current_date.month)
                
                if days_ahead > 60 or (months_ahead > 0 and dt_with_year.month != current_date.month):
                    dt_with_year = dt.replace(year=current_year - 1)
                    print(f"  {date_str} -> {dt_with_year.strftime('%m/%d/%y')} (using PREVIOUS year {current_year - 1})")
                else:
                    print(f"  {date_str} -> {dt_with_year.strftime('%m/%d/%y')} (using CURRENT year {current_year})")
            else:
                print(f"  {date_str} -> {dt_with_year.strftime('%m/%d/%y')} (past date, using {current_year})")
        except Exception as e:
            print(f"  {date_str} -> ERROR: {e}")
    
    # Compare with bank statement
    print("\n=== COMPARISON WITH BANK STATEMENT ===")
    print("Bank statement period: 01/01/25 to 01/31/25 (2025)")
    print("Expected dates should be in 2025")
    
    # Check first few transactions from bank statement
    bank_statement_dates = [
        ('01/02', 1455.41, 'BANKCARD 8076 MTOT DEP'),
        ('01/02', 1277.54, 'BANKCARD 8076 MTOT DEP'),
        ('01/02', 1234.97, 'STRIPE TRANSFER'),
        ('01/03', 3119.96, 'Beyond Menu'),
        ('01/03', 1793.53, 'BANKCARD 8076 MTOT DEP'),
    ]
    
    print("\nChecking if bank statement transactions match extracted data:")
    for b_date, b_amount, b_desc in bank_statement_dates:
        # Find matching transaction
        matches = [t for t in transactions 
                  if b_date in str(t.get('date', '')) 
                  and abs(float(t.get('amount', 0)) - b_amount) < 0.01
                  and b_desc.lower() in (t.get('description', '') or '').lower()]
        
        if matches:
            match = matches[0]
            print(f"  ✓ {b_date} ${b_amount:,.2f} - Date in DB: {match.get('date')}")
        else:
            print(f"  ✗ {b_date} ${b_amount:,.2f} - NOT FOUND")
    
    # Amount totals
    print("\n=== AMOUNT TOTALS ===")
    total_deposits = sum(t.get('amount', 0) for t in transactions if t.get('amount', 0) > 0)
    total_withdrawals = sum(abs(t.get('amount', 0)) for t in transactions if t.get('amount', 0) < 0)
    print(f"Total deposits (positive): ${total_deposits:,.2f}")
    print(f"Total withdrawals (negative): ${total_withdrawals:,.2f}")
    print(f"Bank statement shows: Credits $63,638.99, Debits $70,677.40")
    
except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()
finally:
    db.close()
