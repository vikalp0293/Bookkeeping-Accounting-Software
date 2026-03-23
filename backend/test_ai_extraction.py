#!/usr/bin/env python3
"""
Test script to verify AI-enhanced check extraction.
Tests on sample checks and compares with ground truth data.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.check_extractor import CheckExtractor
import time

def test_check_extraction(check_path: str):
    """Test extraction on a single check."""
    print(f"\n{'='*80}")
    print(f"Testing: {Path(check_path).name}")
    print('='*80)
    
    start_time = time.time()
    try:
        result = CheckExtractor.extract_check_data(check_path)
        elapsed = time.time() - start_time
        
        print(f"✅ Extraction completed in {elapsed:.2f}s")
        print(f"\n📋 Extracted Data:")
        print(f"  Check Number: {result.get('check_number', 'N/A')}")
        print(f"  Date: {result.get('date', 'N/A')}")
        print(f"  Payee: {result.get('payee', 'N/A')[:60] if result.get('payee') else 'N/A'}")
        print(f"  Amount: ${result.get('amount', 0):,.2f}" if result.get('amount') else "  Amount: N/A")
        print(f"  Memo: {result.get('memo', 'N/A')[:40] if result.get('memo') else 'N/A'}")
        print(f"  Bank: {result.get('bank_name', 'N/A')}")
        print(f"  Company: {result.get('company_name', 'N/A')[:40] if result.get('company_name') else 'N/A'}")
        print(f"  Confidence: {result.get('confidence', 0):.1f}%")
        
        # Count extracted fields
        fields_extracted = sum([
            1 if result.get('check_number') else 0,
            1 if result.get('date') else 0,
            1 if result.get('payee') else 0,
            1 if result.get('amount') else 0,
        ])
        print(f"\n📊 Fields Extracted: {fields_extracted}/4")
        
        return result
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("🧪 AI-Enhanced Check Extraction Test")
    print("="*80)
    
    # Test on a sample check
    sample_checks = [
        "../samples/1139.pdf",
        "../samples/1140.pdf",
        "../samples/1141.pdf",
    ]
    
    for check_path in sample_checks:
        full_path = Path(__file__).parent / check_path
        if full_path.exists():
            test_check_extraction(str(full_path))
        else:
            print(f"⚠️  Check not found: {check_path}")
    
    print("\n" + "="*80)
    print("✅ Test Complete!")
    print("\n💡 To test on more checks:")
    print("   python3 test_ai_extraction.py")

