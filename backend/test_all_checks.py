#!/usr/bin/env python3
"""
Test AI-enhanced extraction on all checks with ground truth data.
Generates comprehensive accuracy report.
"""
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

sys.path.insert(0, str(Path(__file__).parent))

from app.services.check_extractor import CheckExtractor

def load_ground_truth_mapping() -> List[Dict]:
    """Load ground truth data with file mappings."""
    mapping_file = Path(__file__).parent / 'check_ground_truth_mapping.json'
    if not mapping_file.exists():
        print("❌ Ground truth mapping file not found. Run the mapping script first.")
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
        # Try common formats
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
    
    # Payee (fuzzy match - case insensitive, allow minor differences)
    extracted_payee = str(extracted.get('payee', '')).strip().upper()
    truth_payee = str(ground_truth.get('payee', '')).strip().upper()
    # Remove common suffixes for comparison
    extracted_payee_clean = extracted_payee.replace(' INC', '').replace(' LLC', '').replace(' CORP', '')
    truth_payee_clean = truth_payee.replace(' INC', '').replace(' LLC', '').replace(' CORP', '')
    results['payee'] = extracted_payee_clean == truth_payee_clean or extracted_payee == truth_payee
    
    # Amount (allow small difference due to cents)
    extracted_amount = float(extracted.get('amount', 0) or 0)
    truth_amount = float(ground_truth.get('amount', 0) or 0)
    # Allow $0.01 difference
    results['amount'] = abs(extracted_amount - truth_amount) < 0.02
    
    return results

def test_all_checks():
    """Test extraction on all checks with ground truth data."""
    print("🧪 AI-Enhanced Check Extraction - Comprehensive Test")
    print("="*80)
    
    # Load ground truth
    ground_truth_list = load_ground_truth_mapping()
    if not ground_truth_list:
        return
    
    print(f"\n📋 Found {len(ground_truth_list)} checks with ground truth data")
    print("="*80)
    
    results = []
    total_time = 0
    
    for i, truth in enumerate(ground_truth_list, 1):
        filename = truth.get('filename', '')
        directory = truth.get('directory', '')
        
        print(f"\n[{i}/{len(ground_truth_list)}] Testing: {filename}")
        print(f"  Directory: {directory}")
        print(f"  Expected Check #: {truth.get('check_number', 'N/A')}")
        
        # Find check file
        check_path = find_check_file(directory, filename)
        if not check_path:
            print(f"  ⚠️  Check file not found: {filename}")
            results.append({
                'filename': filename,
                'directory': directory,
                'found': False,
                'error': 'File not found'
            })
            continue
        
        # Extract data
        start_time = time.time()
        try:
            extracted = CheckExtractor.extract_check_data(check_path)
            elapsed = time.time() - start_time
            total_time += elapsed
            
            # Compare with ground truth
            comparison = compare_fields(extracted, truth)
            
            # Count correct fields
            correct_count = sum(comparison.values())
            total_fields = len(comparison)
            accuracy = (correct_count / total_fields * 100) if total_fields > 0 else 0
            
            print(f"  ✅ Extraction completed in {elapsed:.2f}s")
            print(f"  📊 Accuracy: {correct_count}/{total_fields} fields ({accuracy:.1f}%)")
            
            # Show field-by-field comparison
            print(f"  📋 Field Comparison:")
            print(f"     Check #: {extracted.get('check_number', 'N/A')} (expected: {truth.get('check_number', 'N/A')}) {'✅' if comparison['check_number'] else '❌'}")
            print(f"     Date: {extracted.get('date', 'N/A')} (expected: {truth.get('date', 'N/A')}) {'✅' if comparison['date'] else '❌'}")
            print(f"     Payee: {extracted.get('payee', 'N/A')[:40]} (expected: {truth.get('payee', 'N/A')[:40]}) {'✅' if comparison['payee'] else '❌'}")
            print(f"     Amount: ${extracted.get('amount', 0):,.2f} (expected: ${truth.get('amount', 0):,.2f}) {'✅' if comparison['amount'] else '❌'}")
            
            results.append({
                'filename': filename,
                'directory': directory,
                'found': True,
                'extracted': extracted,
                'ground_truth': truth,
                'comparison': comparison,
                'accuracy': accuracy,
                'time': elapsed
            })
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results.append({
                'filename': filename,
                'directory': directory,
                'found': True,
                'error': str(e)
            })
    
    # Generate summary
    print("\n" + "="*80)
    print("📊 SUMMARY REPORT")
    print("="*80)
    
    successful = [r for r in results if r.get('found') and 'error' not in r]
    failed = [r for r in results if not r.get('found') or 'error' in r]
    
    print(f"\n✅ Successfully extracted: {len(successful)}/{len(results)}")
    print(f"❌ Failed/Not found: {len(failed)}/{len(results)}")
    print(f"⏱️  Total time: {total_time:.2f}s")
    print(f"⏱️  Average time per check: {total_time/len(successful):.2f}s" if successful else "")
    
    if successful:
        # Field-level accuracy
        field_accuracies = {
            'check_number': sum(1 for r in successful if r.get('comparison', {}).get('check_number', False)) / len(successful) * 100,
            'date': sum(1 for r in successful if r.get('comparison', {}).get('date', False)) / len(successful) * 100,
            'payee': sum(1 for r in successful if r.get('comparison', {}).get('payee', False)) / len(successful) * 100,
            'amount': sum(1 for r in successful if r.get('comparison', {}).get('amount', False)) / len(successful) * 100,
        }
        
        print(f"\n📈 Field-Level Accuracy:")
        for field, accuracy in field_accuracies.items():
            print(f"   {field.replace('_', ' ').title()}: {accuracy:.1f}%")
        
        # Overall accuracy
        overall_accuracy = sum(r.get('accuracy', 0) for r in successful) / len(successful)
        print(f"\n🎯 Overall Accuracy: {overall_accuracy:.1f}%")
        
        # Save detailed results
        results_file = Path(__file__).parent / 'extraction_test_results.json'
        with open(results_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'total_tested': len(results),
                'successful': len(successful),
                'failed': len(failed),
                'field_accuracies': field_accuracies,
                'overall_accuracy': overall_accuracy,
                'results': results
            }, f, indent=2)
        
        print(f"\n💾 Detailed results saved to: {results_file}")
    
    print("\n" + "="*80)
    print("✅ Test Complete!")

if __name__ == "__main__":
    test_all_checks()

