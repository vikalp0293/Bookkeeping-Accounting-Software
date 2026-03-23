#!/usr/bin/env python3
"""
Test script for OCR service.
Tests OCR extraction on sample check files.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.services.ocr_service import OCRService
from app.services.check_extractor import CheckExtractor

def test_ocr_on_check(file_path):
    """Test OCR extraction on a check file."""
    print(f"\n{'='*60}")
    print(f"Testing OCR on: {file_path}")
    print(f"{'='*60}\n")
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return
    
    # Test OCR extraction
    print("1. Running OCR extraction...")
    ocr_result = OCRService.extract_text(file_path)
    
    if "error" in ocr_result:
        print(f"❌ OCR Error: {ocr_result['error']}")
        return
    
    print(f"✅ OCR Confidence: {ocr_result.get('confidence', 0):.1f}%")
    print(f"✅ Text Length: {ocr_result.get('char_count', 0)} characters")
    print(f"✅ Word Count: {ocr_result.get('word_count', 0)} words")
    
    # Test check extraction
    print("\n2. Extracting check data...")
    check_result = CheckExtractor.extract_check_data(file_path)
    
    if "error" in check_result:
        print(f"❌ Check Extraction Error: {check_result['error']}")
        return
    
    print("\n📋 Extracted Check Data:")
    print(f"   Check Number: {check_result.get('check_number', 'N/A')}")
    print(f"   Date: {check_result.get('date', 'N/A')}")
    print(f"   Payee: {check_result.get('payee', 'N/A')}")
    print(f"   Amount: ${check_result.get('amount', 0):,.2f}" if check_result.get('amount') else "   Amount: N/A")
    print(f"   Memo: {check_result.get('memo', 'N/A')}")
    print(f"   Bank: {check_result.get('bank_name', 'N/A')}")
    print(f"   Company: {check_result.get('company_name', 'N/A')}")
    print(f"   Account #: {check_result.get('account_number', 'N/A')}")
    print(f"   Routing #: {check_result.get('routing_number', 'N/A')}")
    print(f"   Confidence: {check_result.get('confidence', 0):.1f}%")
    
    # Show first 500 chars of raw OCR text
    raw_text = check_result.get('raw_text', '')
    if raw_text:
        print(f"\n📄 Raw OCR Text (first 500 chars):")
        print("-" * 60)
        print(raw_text[:500])
        print("-" * 60)

if __name__ == "__main__":
    # Test on sample check files
    sample_dir = "../samples"
    check_files = [
        "1139.pdf",
        "1140.pdf",
        "1141.pdf",
        "1142.pdf",
        "1144.pdf"
    ]
    
    print("🧪 OCR Service Test")
    print("=" * 60)
    
    for check_file in check_files:
        file_path = os.path.join(sample_dir, check_file)
        if os.path.exists(file_path):
            test_ocr_on_check(file_path)
        else:
            print(f"\n⚠️  Sample file not found: {file_path}")
    
    print(f"\n{'='*60}")
    print("✅ OCR Testing Complete!")
    print(f"{'='*60}\n")




# Test script