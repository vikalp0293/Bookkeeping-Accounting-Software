#!/usr/bin/env python3
"""Check what dates would be in IIF export for workspace 1."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db.base import SessionLocal
from app.models.file import File
from app.models.extracted_data import ExtractedData
from datetime import datetime

db = SessionLocal()
try:
    # Get all files for workspace 1
    files = db.query(File).filter(File.workspace_id == 1).all()
    print(f'Total files in workspace 1: {len(files)}')
    print()
    
    all_transactions = []
    files_with_2023 = []
    
    for file in files:
        extracted = db.query(ExtractedData).filter(
            ExtractedData.file_id == file.id,
            ExtractedData.extraction_status == 'completed'
        ).first()
        
        if not extracted or not extracted.processed_data:
            continue
        
        data = extracted.processed_data
        transactions = data.get('transactions', [])
        
        # Check for 2023 dates
        has_2023 = any('2023' in str(t.get('date', '')) for t in transactions)
        if has_2023:
            files_with_2023.append((file.id, file.filename, len(transactions)))
            print(f'⚠️  File {file.id} ({file.filename[:50]}): {len(transactions)} transactions')
            # Show sample 2023 dates
            dates_2023 = [t.get('date') for t in transactions if '2023' in str(t.get('date', ''))]
            unique_2023_dates = sorted(set(dates_2023))[:5]
            print(f'    Sample 2023 dates: {unique_2023_dates}')
            print()
        
        # Collect all transactions
        for trans in transactions:
            all_transactions.append({
                'file_id': file.id,
                'filename': file.filename[:30],
                'date': trans.get('date'),
                'amount': trans.get('amount', 0),
                'description': (trans.get('description', '') or '')[:40]
            })
    
    print('=' * 80)
    print(f'Total transactions across all files: {len(all_transactions)}')
    print()
    
    # Check date distribution
    print('=== DATE DISTRIBUTION ===')
    date_years = {}
    for trans in all_transactions:
        date_str = str(trans.get('date', ''))
        if '2023' in date_str:
            date_years['2023'] = date_years.get('2023', 0) + 1
        elif '2024' in date_str:
            date_years['2024'] = date_years.get('2024', 0) + 1
        elif '2025' in date_str:
            date_years['2025'] = date_years.get('2025', 0) + 1
        elif '2026' in date_str:
            date_years['2026'] = date_years.get('2026', 0) + 1
    
    for year, count in sorted(date_years.items()):
        print(f'{year}: {count} transactions')
    
    # Find 2023 dates specifically
    print()
    print('=== 2023 TRANSACTIONS ===')
    trans_2023 = [t for t in all_transactions if '2023' in str(t.get('date', ''))]
    print(f'Found {len(trans_2023)} transactions with 2023 dates')
    
    if trans_2023:
        print('\nSample 2023 transactions:')
        for t in trans_2023[:10]:
            print(f'  File {t["file_id"]} ({t["filename"]}): {t["date"]} | ${t["amount"]:,.2f} | {t["description"]}')
        
        # Check for 01/09/2023 specifically
        jan_09_2023 = [t for t in trans_2023 if '2023-01-09' in str(t.get('date', '')) or '01/09/2023' in str(t.get('date', ''))]
        if jan_09_2023:
            print(f'\n⚠️  Found {len(jan_09_2023)} transactions on 01/09/2023:')
            for t in jan_09_2023[:5]:
                print(f'  File {t["file_id"]}: {t["date"]} | ${t["amount"]:,.2f} | {t["description"]}')
    
    # Simulate IIF date conversion for 2023 dates
    print()
    print('=== IIF DATE CONVERSION FOR 2023 DATES ===')
    if trans_2023:
        sample_2023 = trans_2023[0]
        date_str = str(sample_2023.get('date', ''))
        print(f'Sample 2023 date: {date_str}')
        
        # Simulate the IIF conversion logic
        try:
            if '2023' in date_str:
                # Try YYYY-MM-DD format
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                iif_date = dt.strftime('%m/%d/%y')
                print(f'  Converted to IIF: {iif_date} (MM/DD/YY format)')
        except Exception as e:
            print(f'  Conversion error: {e}')

except Exception as e:
    import traceback
    print(f'Error: {e}')
    traceback.print_exc()
finally:
    db.close()
