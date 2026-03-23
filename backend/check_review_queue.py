#!/usr/bin/env python3
"""
Script to check review queue items and stats.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.base import SessionLocal
from app.models.review_queue import ReviewQueue, ReviewStatus
from app.models.file import File

def check_review_queue():
    db = SessionLocal()
    try:
        # Get all review queue items
        all_items = db.query(ReviewQueue).all()
        print(f"📋 Total Review Queue Items: {len(all_items)}")
        print()
        
        for item in all_items:
            print(f"Item ID: {item.id}")
            print(f"  File ID: {item.file_id}")
            print(f"  Status: {item.status}")
            print(f"  Priority: {item.priority}")
            print(f"  Reason: {item.review_reason}")
            print(f"  Created: {item.created_at}")
            
            # Get file info
            file = db.query(File).filter(File.id == item.file_id).first()
            if file:
                print(f"  File: {file.original_filename}")
                print(f"  Workspace ID: {file.workspace_id}")
            print()
        
        # Check by status
        pending_items = db.query(ReviewQueue).filter(ReviewQueue.status == ReviewStatus.PENDING).all()
        print(f"📊 Pending Items: {len(pending_items)}")
        
        # Check stats calculation
        total = db.query(ReviewQueue).count()
        pending = db.query(ReviewQueue).filter(ReviewQueue.status == ReviewStatus.PENDING).count()
        in_review = db.query(ReviewQueue).filter(ReviewQueue.status == ReviewStatus.IN_REVIEW).count()
        completed = db.query(ReviewQueue).filter(ReviewQueue.status == ReviewStatus.COMPLETED).count()
        
        print(f"   Total: {total}")
        print(f"   Pending: {pending}")
        print(f"   In Review: {in_review}")
        print(f"   Completed: {completed}")
        print()
        
        # Check if items are filtered by workspace
        if pending_items:
            print("🔍 Checking workspace filtering:")
            for item in pending_items:
                file = db.query(File).filter(File.id == item.file_id).first()
                if file:
                    print(f"   Item {item.id} - File {item.file_id} ({file.original_filename}) - Workspace: {file.workspace_id}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_review_queue()

