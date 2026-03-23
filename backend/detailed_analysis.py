#!/usr/bin/env python3
"""
Detailed analysis of sample PDFs to identify extractable fields.
"""
import sys
import os
import pdfplumber
import json

samples_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'samples')

def analyze_detailed(filepath, filename):
    """Detailed analysis of a PDF file."""
    print(f"\n{'='*80}")
    print(f"📄 Detailed Analysis: {filename}")
    print(f"{'='*80}\n")
    
    try:
        with pdfplumber.open(filepath) as pdf:
            num_pages = len(pdf.pages)
            print(f"Total Pages: {num_pages}\n")
            
            # Analyze first page in detail
            first_page = pdf.pages[0]
            text = first_page.extract_text()
            
            print("📝 Full Text (First Page):")
            print("-" * 80)
            print(text[:2000] if len(text) > 2000 else text)
            if len(text) > 2000:
                print(f"\n... (truncated, total length: {len(text)} characters)")
            print("-" * 80)
            
            # Extract tables
            tables = first_page.extract_tables()
            if tables:
                print(f"\n📊 Found {len(tables)} table(s) on first page:")
                for i, table in enumerate(tables[:2], 1):  # Show first 2 tables
                    print(f"\nTable {i}:")
                    if table and len(table) > 0:
                        # Show first few rows
                        for row_idx, row in enumerate(table[:5]):
                            print(f"  Row {row_idx + 1}: {row}")
                        if len(table) > 5:
                            print(f"  ... ({len(table) - 5} more rows)")
            
            # Look for common financial document patterns
            print("\n🔍 Key Information Detected:")
            lines = text.split('\n')
            keywords = ['date', 'amount', 'balance', 'account', 'transaction', 'check', 'deposit', 'withdrawal']
            found_info = {}
            
            for line in lines:
                line_lower = line.lower()
                for keyword in keywords:
                    if keyword in line_lower and line.strip():
                        if keyword not in found_info:
                            found_info[keyword] = []
                        found_info[keyword].append(line.strip()[:100])
                        if len(found_info[keyword]) >= 3:
                            break
            
            for key, values in found_info.items():
                print(f"  {key.upper()}: {values[:3]}")
            
    except Exception as e:
        print(f"❌ Error analyzing {filename}: {e}")

def main():
    # Analyze the example PDFs in detail
    example_files = [
        "Chase Example.pdf",
        "Huntington Example.pdf", 
        "US Bank Example.pdf"
    ]
    
    for filename in example_files:
        filepath = os.path.join(samples_dir, filename)
        if os.path.exists(filepath):
            analyze_detailed(filepath, filename)
        else:
            print(f"⚠️  File not found: {filename}")
    
    # Quick check on one of the check images
    print(f"\n{'='*80}")
    print("📄 Quick Check: 1139.pdf (Huntington Check)")
    print(f"{'='*80}\n")
    
    check_file = os.path.join(samples_dir, "1139.pdf")
    if os.path.exists(check_file):
        try:
            with pdfplumber.open(check_file) as pdf:
                first_page = pdf.pages[0]
                text = first_page.extract_text()
                print("Extracted Text:")
                print(text)
                print("\n⚠️  This appears to be an image-based check (scanned document)")
                print("    Will need OCR (pytesseract) for proper extraction")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == '__main__':
    main()

