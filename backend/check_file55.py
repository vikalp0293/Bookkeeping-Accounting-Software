#!/usr/bin/env python3
"""
Script to check file 55 extraction data and review queue status.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.base import SessionLocal
from app.models.file import File
from app.models.extracted_data import ExtractedData
from app.models.review_queue import ReviewQueue
import json

def check_file55():
    db = SessionLocal()
    try:
        # Get file 55
        file = db.query(File).filter(File.id == 55).first()
        
        if not file:
            print("❌ File 55 not found in database")
            return
        
        print(f"📄 File 55: {file.original_filename}")
        print(f"   Status: {file.status}")
        print(f"   Type: {file.file_type}")
        print(f"   Created: {file.created_at}")
        print()
        
        # Get extraction data
        extracted_data = db.query(ExtractedData).filter(ExtractedData.file_id == 55).first()
        
        if not extracted_data:
            print("❌ No extraction data found for file 55")
            return
        
        print(f"📊 Extraction Status: {extracted_data.extraction_status}")
        print(f"   Created: {extracted_data.created_at}")
        print(f"   Updated: {extracted_data.updated_at}")
        if extracted_data.error_message:
            print(f"   Error: {extracted_data.error_message}")
        print()
        
        # Check processed_data for flags
        if extracted_data.processed_data:
            processed = extracted_data.processed_data
            print("🔍 Processed Data Analysis:")
            
            flags = processed.get("flags", [])
            if flags:
                print(f"   ⚠️  Flags: {flags}")
            else:
                print("   ✅ No flags (no issues detected)")
            
            missing_fields = processed.get("missing_fields", [])
            if missing_fields:
                print(f"   ⚠️  Missing Fields: {missing_fields}")
            else:
                print("   ✅ No missing fields")
            
            language = processed.get("language_detection", {})
            if language:
                is_english = language.get("is_english", True)
                lang = language.get("language", "unknown")
                print(f"   Language: {lang}, Is English: {is_english}")
                if not is_english:
                    print("   ⚠️  Non-English content detected")
            
            confidence = processed.get("confidence") or extracted_data.raw_data.get("confidence") if extracted_data.raw_data else None
            if confidence is not None:
                print(f"   Confidence: {confidence}%")
                if confidence < 70:
                    print("   ⚠️  Low confidence detected")
            
            review_queued = processed.get("review_queued", False)
            print(f"   Review Queued: {review_queued}")
            
            # Check for transactions
            if "transactions" in processed or (extracted_data.raw_data and "transactions" in extracted_data.raw_data):
                transactions = processed.get("transactions") or extracted_data.raw_data.get("transactions", [])
                print(f"   Transactions: {len(transactions)} found")
                if transactions:
                    # Check first transaction for missing fields
                    first_trans = transactions[0] if isinstance(transactions, list) else transactions
                    print(f"   First transaction fields: {list(first_trans.keys()) if isinstance(first_trans, dict) else 'N/A'}")
        else:
            print("⚠️  No processed_data found")
            if extracted_data.raw_data:
                print("   Raw data exists but not processed")
        
        print()
        
        # Check review queue
        review_items = db.query(ReviewQueue).filter(ReviewQueue.file_id == 55).all()
        
        if review_items:
            print(f"📋 Review Queue Items: {len(review_items)} found")
            for item in review_items:
                print(f"   - ID: {item.id}")
                print(f"     Reason: {item.review_reason}")
                print(f"     Priority: {item.priority}")
                print(f"     Status: {item.status}")
                print(f"     Notes: {item.notes}")
                print(f"     Created: {item.created_at}")
        else:
            print("❌ No review queue items found for file 55")
            print()
            print("🔍 Analysis: Why wasn't it added?")
            
            if not extracted_data.processed_data:
                print("   ⚠️  No processed_data - post-processing may not have run")
            else:
                processed = extracted_data.processed_data
                needs_review = False
                
                # Check all conditions
                flags = processed.get("flags", [])
                if flags:
                    print(f"   ⚠️  Flags present: {flags} - should trigger review")
                    needs_review = True
                else:
                    print("   ✅ No flags - extraction passed all checks")
                
                missing_fields = processed.get("missing_fields", [])
                if missing_fields:
                    print(f"   ⚠️  Missing fields: {missing_fields} - should trigger review")
                    needs_review = True
                
                language = processed.get("language_detection", {})
                if language and not language.get("is_english", True):
                    print(f"   ⚠️  Non-English detected - should trigger review")
                    needs_review = True
                
                confidence = processed.get("confidence") or (extracted_data.raw_data.get("confidence") if extracted_data.raw_data else None)
                if confidence is not None and confidence < 70:
                    print(f"   ⚠️  Low confidence ({confidence}%) - should trigger review")
                    needs_review = True
                
                if needs_review:
                    print()
                    print("   ❌ ISSUE: File should have been added to review queue but wasn't!")
                    print("   Possible reasons:")
                    print("   1. Post-processing completed but add_to_queue() failed silently")
                    print("   2. needs_review flag was False despite having issues")
                    print("   3. Exception occurred in review queue addition")
                else:
                    print()
                    print("   ✅ File passed all checks - correctly not added to review queue")
        
        # Show raw data summary
        if extracted_data.raw_data:
            print("📄 Raw Data Summary:")
            raw = extracted_data.raw_data
            if "transactions" in raw:
                transactions = raw["transactions"]
                print(f"   Transactions found: {len(transactions)}")
                if transactions and len(transactions) > 0:
                    first_trans = transactions[0]
                    print(f"   First transaction keys: {list(first_trans.keys()) if isinstance(first_trans, dict) else 'N/A'}")
            elif "document_type" in raw:
                print(f"   Document type: {raw.get('document_type')}")
            else:
                print(f"   Raw data keys: {list(raw.keys())[:10]}")
            print()
        
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_file55()

