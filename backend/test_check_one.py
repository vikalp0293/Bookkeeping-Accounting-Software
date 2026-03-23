#!/usr/bin/env python3
"""
Test AI-enhanced extraction on one check at a time.
Shows detailed results for each check.
"""
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))

from app.services.check_extractor import CheckExtractor

def load_ground_truth_mapping() -> list:
    """Load ground truth data with file mappings."""
    mapping_file = Path(__file__).parent / 'check_ground_truth_mapping.json'
    if not mapping_file.exists():
        print("❌ Ground truth mapping file not found.")
        return []
    
    with open(mapping_file, 'r') as f:
        return json.load(f)

def find_check_file(directory: str, filename: str) -> Optional[str]:
    """Find the actual check PDF file."""
    base_path = Path(__file__).parent.parent / 'samples' / 'checks'
    
    # Try direct path
    direct_path = base_path / directory / filename
    if direct_path.exists():
        return str(direct_path)
    
    # Try in Checks subdirectory
    checks_path = base_path / directory / 'Checks' / filename
    if checks_path.exists():
        return str(checks_path)
    
    # Try in Bank Statement Checks subdirectory
    bank_checks_path = base_path / directory / 'Bank Statement Checks' / filename
    if bank_checks_path.exists():
        return str(bank_checks_path)
    
    # Try recursive search
    for pdf_file in (base_path / directory).rglob(filename):
        return str(pdf_file)
    
    return None

def normalize_date(date_str: str) -> str:
    """Normalize date to YYYY-MM-DD format."""
    if not date_str:
        return ""
    
    try:
        from datetime import datetime
        for fmt in ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y"]:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except:
                continue
    except:
        pass
    
    return date_str

def compare_fields(extracted: Dict, ground_truth: Dict) -> Dict[str, bool]:
    """Compare extracted fields with ground truth."""
    results = {}
    
    # Check number
    extracted_num = str(extracted.get('check_number', '')).strip()
    truth_num = str(ground_truth.get('check_number', '')).strip()
    results['check_number'] = extracted_num == truth_num
    
    # Date
    extracted_date = normalize_date(extracted.get('date', ''))
    truth_date = normalize_date(ground_truth.get('date', ''))
    results['date'] = extracted_date == truth_date
    
    # Payee (fuzzy match)
    extracted_payee = str(extracted.get('payee', '')).strip().upper()
    truth_payee = str(ground_truth.get('payee', '')).strip().upper()
    extracted_payee_clean = extracted_payee.replace(' INC', '').replace(' LLC', '').replace(' CORP', '').replace(' LTD', '')
    truth_payee_clean = truth_payee.replace(' INC', '').replace(' LLC', '').replace(' CORP', '').replace(' LTD', '')
    results['payee'] = extracted_payee_clean == truth_payee_clean or extracted_payee == truth_payee
    
    # Amount (allow $0.01 difference)
    extracted_amount = float(extracted.get('amount', 0) or 0)
    truth_amount = float(ground_truth.get('amount', 0) or 0)
    results['amount'] = abs(extracted_amount - truth_amount) < 0.02
    
    return results

def test_one_check(check_idx: int = 0):
    """Test extraction on one check."""
    ground_truth_list = load_ground_truth_mapping()
    if not ground_truth_list:
        print("❌ No ground truth data found")
        return
    
    if check_idx >= len(ground_truth_list):
        print(f"❌ Check index {check_idx} out of range (total: {len(ground_truth_list)})")
        return
    
    truth = ground_truth_list[check_idx]
    filename = truth.get('filename', '')
    directory = truth.get('directory', '')
    
    print("="*80)
    print(f"🧪 Testing Check #{check_idx + 1} of {len(ground_truth_list)}")
    print("="*80)
    print(f"📄 File: {filename}")
    print(f"📁 Directory: {directory}")
    print(f"\n📋 Expected (Ground Truth):")
    print(f"   Check Number: {truth.get('check_number', 'N/A')}")
    print(f"   Date: {truth.get('date', 'N/A')}")
    print(f"   Payee: {truth.get('payee', 'N/A')}")
    print(f"   Amount: ${truth.get('amount', 0):,.2f}")
    print(f"   Memo: {truth.get('memo', 'N/A')}")
    
    # Find check file
    check_path = find_check_file(directory, filename)
    if not check_path:
        print(f"\n❌ Check file not found: {filename}")
        print(f"   Searched in: samples/checks/{directory}/")
        return
    
    print(f"\n✅ Found file: {check_path}")
    print(f"\n🔄 Extracting data...")
    
    # Extract data
    start_time = time.time()
    try:
        extracted = CheckExtractor.extract_check_data(check_path)
        elapsed = time.time() - start_time
        
        print(f"\n✅ Extraction completed in {elapsed:.2f}s")
        print(f"\n📋 Extracted Data:")
        print(f"   Check Number: {extracted.get('check_number', 'N/A')}")
        print(f"   Date: {extracted.get('date', 'N/A')}")
        print(f"   Payee: {extracted.get('payee', 'N/A')}")
        print(f"   Amount: ${extracted.get('amount', 0):,.2f}" if extracted.get('amount') else "   Amount: N/A")
        print(f"   Memo: {extracted.get('memo', 'N/A')}")
        print(f"   Company: {extracted.get('company_name', 'N/A')}")
        print(f"   Bank: {extracted.get('bank_name', 'N/A')}")
        print(f"   Confidence: {extracted.get('confidence', 0):.1f}%")
        print(f"   Method: {extracted.get('extraction_method', 'N/A')}")
        
        # Compare with ground truth
        comparison = compare_fields(extracted, truth)
        
        # Count correct fields
        correct_count = sum(comparison.values())
        total_fields = len(comparison)
        accuracy = (correct_count / total_fields * 100) if total_fields > 0 else 0
        
        print(f"\n📊 Accuracy: {correct_count}/{total_fields} fields correct ({accuracy:.0f}%)")
        print(f"\n✅ Field Comparison:")
        print(f"   Check Number: {'✅ CORRECT' if comparison['check_number'] else '❌ WRONG'}")
        if not comparison['check_number']:
            print(f"      Got: '{extracted.get('check_number')}', Expected: '{truth.get('check_number')}'")
        
        print(f"   Date: {'✅ CORRECT' if comparison['date'] else '❌ WRONG'}")
        if not comparison['date']:
            print(f"      Got: '{extracted.get('date')}', Expected: '{truth.get('date')}'")
        
        print(f"   Payee: {'✅ CORRECT' if comparison['payee'] else '❌ WRONG'}")
        if not comparison['payee']:
            print(f"      Got: '{extracted.get('payee', '')[:50]}'")
            print(f"      Expected: '{truth.get('payee', '')[:50]}'")
        
        print(f"   Amount: {'✅ CORRECT' if comparison['amount'] else '❌ WRONG'}")
        if not comparison['amount']:
            print(f"      Got: ${extracted.get('amount', 0):,.2f}, Expected: ${truth.get('amount', 0):,.2f}")
            diff = abs(extracted.get('amount', 0) - truth.get('amount', 0))
            print(f"      Difference: ${diff:,.2f}")
        
        if accuracy == 100:
            print(f"\n🎉 PERFECT MATCH! All fields correct!")
        elif accuracy >= 75:
            print(f"\n✅ Good accuracy! Most fields correct.")
        elif accuracy >= 50:
            print(f"\n⚠️  Moderate accuracy. Some fields need improvement.")
        else:
            print(f"\n❌ Low accuracy. Multiple fields incorrect.")
        
    except Exception as e:
        print(f"\n❌ Error during extraction: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*80)
    print(f"💡 To test next check: python3 test_check_one.py {check_idx + 1}")
    print(f"💡 To test specific check: python3 test_check_one.py <index>")
    print("="*80)

if __name__ == "__main__":
    check_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    test_one_check(check_idx)

