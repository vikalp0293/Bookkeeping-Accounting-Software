#!/usr/bin/env python3
"""
Test AI-enhanced extraction on checks with ground truth data (batch processing).
Tests in smaller batches to avoid timeouts.
"""
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from app.services.check_extractor import CheckExtractor

def load_ground_truth_mapping() -> List[Dict]:
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
    
    # Payee (fuzzy match)
    extracted_payee = str(extracted.get('payee', '')).strip().upper()
    truth_payee = str(ground_truth.get('payee', '')).strip().upper()
    # Remove common suffixes
    extracted_payee_clean = extracted_payee.replace(' INC', '').replace(' LLC', '').replace(' CORP', '').replace(' LTD', '')
    truth_payee_clean = truth_payee.replace(' INC', '').replace(' LLC', '').replace(' CORP', '').replace(' LTD', '')
    results['payee'] = extracted_payee_clean == truth_payee_clean or extracted_payee == truth_payee
    
    # Amount (allow $0.01 difference)
    extracted_amount = float(extracted.get('amount', 0) or 0)
    truth_amount = float(ground_truth.get('amount', 0) or 0)
    results['amount'] = abs(extracted_amount - truth_amount) < 0.02
    
    return results

def test_checks_batch(start_idx: int = 0, batch_size: int = 10):
    """Test extraction on a batch of checks."""
    print("🧪 AI-Enhanced Check Extraction - Batch Test")
    print("="*80)
    
    # Load ground truth
    ground_truth_list = load_ground_truth_mapping()
    if not ground_truth_list:
        return
    
    total_checks = len(ground_truth_list)
    end_idx = min(start_idx + batch_size, total_checks)
    batch = ground_truth_list[start_idx:end_idx]
    
    print(f"\n📋 Testing batch: {start_idx+1}-{end_idx} of {total_checks} total checks")
    print("="*80)
    
    results = []
    total_time = 0
    
    for i, truth in enumerate(batch, start_idx+1):
        filename = truth.get('filename', '')
        directory = truth.get('directory', '')
        
        print(f"\n[{i}/{total_checks}] {filename}")
        print(f"  Expected: Check #{truth.get('check_number', 'N/A')}, ${truth.get('amount', 0):,.2f}")
        
        # Find check file
        check_path = find_check_file(directory, filename)
        if not check_path:
            print(f"  ⚠️  File not found")
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
            
            status = "✅" if accuracy == 100 else "⚠️" if accuracy >= 50 else "❌"
            print(f"  {status} {correct_count}/{total_fields} fields correct ({accuracy:.0f}%) - {elapsed:.1f}s")
            
            # Show incorrect fields
            if not comparison['check_number']:
                print(f"     ❌ Check #: got '{extracted.get('check_number')}', expected '{truth.get('check_number')}'")
            if not comparison['date']:
                print(f"     ❌ Date: got '{extracted.get('date')}', expected '{truth.get('date')}'")
            if not comparison['payee']:
                print(f"     ❌ Payee: got '{extracted.get('payee', '')[:40]}', expected '{truth.get('payee', '')[:40]}'")
            if not comparison['amount']:
                print(f"     ❌ Amount: got ${extracted.get('amount', 0):,.2f}, expected ${truth.get('amount', 0):,.2f}")
            
            results.append({
                'filename': filename,
                'directory': directory,
                'found': True,
                'extracted': {
                    'check_number': extracted.get('check_number'),
                    'date': extracted.get('date'),
                    'payee': extracted.get('payee'),
                    'amount': extracted.get('amount'),
                },
                'ground_truth': {
                    'check_number': truth.get('check_number'),
                    'date': truth.get('date'),
                    'payee': truth.get('payee'),
                    'amount': truth.get('amount'),
                },
                'comparison': comparison,
                'accuracy': accuracy,
                'time': elapsed
            })
            
        except Exception as e:
            print(f"  ❌ Error: {str(e)[:100]}")
            results.append({
                'filename': filename,
                'directory': directory,
                'found': True,
                'error': str(e)
            })
    
    # Generate summary
    print("\n" + "="*80)
    print("📊 BATCH SUMMARY")
    print("="*80)
    
    successful = [r for r in results if r.get('found') and 'error' not in r]
    failed = [r for r in results if not r.get('found') or 'error' in r]
    
    print(f"\n✅ Successfully extracted: {len(successful)}/{len(results)}")
    print(f"❌ Failed/Not found: {len(failed)}/{len(results)}")
    print(f"⏱️  Total time: {total_time:.2f}s")
    if successful:
        print(f"⏱️  Average time: {total_time/len(successful):.2f}s per check")
    
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
        
        # Save results
        results_file = Path(__file__).parent / f'extraction_results_batch_{start_idx}_{end_idx}.json'
        with open(results_file, 'w') as f:
            json.dump({
                'batch': f'{start_idx+1}-{end_idx}',
                'total_checks': total_checks,
                'timestamp': datetime.now().isoformat(),
                'field_accuracies': field_accuracies,
                'overall_accuracy': overall_accuracy,
                'results': results
            }, f, indent=2)
        
        print(f"\n💾 Results saved to: {results_file}")
    
    print(f"\n💡 To test next batch: python3 test_checks_batch.py {end_idx} {batch_size}")
    print("="*80)

if __name__ == "__main__":
    import sys
    start_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    batch_size = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    test_checks_batch(start_idx, batch_size)

