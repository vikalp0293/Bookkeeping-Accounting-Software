#!/usr/bin/env python3
"""
Script to test review queue API query with same parameters as frontend.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.base import SessionLocal
from app.models.review_queue import ReviewQueue, ReviewStatus, ReviewPriority
from app.models.file import File

def test_query():
    db = SessionLocal()
    try:
        # Simulate the frontend query: workspace_id=1, status="pending", priority="low"
        workspace_id = 1
        status_filter = "pending"  # lowercase as frontend sends
        priority_filter = "low"    # lowercase as frontend sends
        
        print(f"🔍 Testing query with:")
        print(f"   workspace_id: {workspace_id}")
        print(f"   status: {status_filter}")
        print(f"   priority: {priority_filter}")
        print()
        
        # Convert status
        try:
            status_enum = ReviewStatus(status_filter)
            print(f"✅ Status converted: {status_enum}")
        except ValueError as e:
            print(f"❌ Status conversion failed: {e}")
            return
        
        # Convert priority
        priority_enum = None
        if priority_filter:
            try:
                priority_enum = ReviewPriority(priority_filter)
                print(f"✅ Priority converted: {priority_enum}")
            except ValueError as e:
                print(f"❌ Priority conversion failed: {e}")
                return
        
        # Build query exactly as service does
        query = db.query(ReviewQueue)
        
        if workspace_id:
            query = query.join(File).filter(File.workspace_id == workspace_id)
            print(f"✅ Applied workspace filter: {workspace_id}")
        
        if status_enum:
            query = query.filter(ReviewQueue.status == status_enum)
            print(f"✅ Applied status filter: {status_enum}")
        
        if priority_enum:
            query = query.filter(ReviewQueue.priority == priority_enum)
            print(f"✅ Applied priority filter: {priority_enum}")
        
        # Order by priority and creation date
        query = query.order_by(
            ReviewQueue.priority.desc(),
            ReviewQueue.created_at.asc()
        )
        
        items = query.all()
        
        print()
        print(f"📋 Results: {len(items)} items found")
        for item in items:
            print(f"   - Item ID: {item.id}, File ID: {item.file_id}")
            print(f"     Status: {item.status}, Priority: {item.priority}")
            file = db.query(File).filter(File.id == item.file_id).first()
            if file:
                print(f"     File: {file.original_filename}, Workspace: {file.workspace_id}")
        
        # Also check without filters
        print()
        print("🔍 All review queue items (no filters):")
        all_items = db.query(ReviewQueue).all()
        for item in all_items:
            file = db.query(File).filter(File.id == item.file_id).first()
            print(f"   - Item {item.id}: File {item.file_id} ({file.original_filename if file else 'unknown'}), "
                  f"Status: {item.status}, Priority: {item.priority}, "
                  f"Workspace: {file.workspace_id if file else 'unknown'}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_query()

