#!/usr/bin/env python3
"""
Script to retry extraction for specific file IDs.
Usage: python retry_extraction.py <file_id1> <file_id2> ...
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db.base import SessionLocal
from app.services.extraction_service import ExtractionService
from fastapi import BackgroundTasks

def retry_extraction(file_id: int):
    """Retry extraction for a file."""
    db = SessionLocal()
    try:
        print(f"\n{'='*60}")
        print(f"Retrying extraction for file ID: {file_id}")
        print(f"{'='*60}")
        
        # Get file info first
        from app.models.file import File, FileStatus
        from app.models.extracted_data import ExtractedData
        import threading
        
        file = db.query(File).filter(File.id == file_id).first()
        if not file:
            print(f"❌ File {file_id} not found")
            return False
        
        print(f"📄 File: {file.original_filename}")
        print(f"📊 Status: {file.status}")
        print(f"📅 Created: {file.created_at}")
        
        # Force re-extraction (even if completed)
        # Get or create extraction record
        extracted_data = db.query(ExtractedData).filter(ExtractedData.file_id == file_id).first()
        
        if extracted_data:
            # Reset extraction data
            extracted_data.extraction_status = "pending"
            extracted_data.error_message = None
            extracted_data.raw_data = {}
            extracted_data.processed_data = {}
        else:
            # Create new extraction record
            extracted_data = ExtractedData(
                file_id=file_id,
                extraction_status="pending",
                raw_data={},
                processed_data={}
            )
            db.add(extracted_data)
        
        # Reset file status to processing
        file.status = FileStatus.PROCESSING
        db.commit()
        db.refresh(extracted_data)
        
        # Process extraction in background thread
        def run_extraction():
            ExtractionService._process_extraction(file_id)
        
        extraction_thread = threading.Thread(target=run_extraction, daemon=True)
        extraction_thread.start()
        
        print(f"✅ Extraction retry initiated")
        print(f"📊 Extraction Status: {extracted_data.extraction_status}")
        print(f"⏳ Processing will continue in background...")
        return True
        
    except Exception as e:
        print(f"❌ Error retrying extraction for file {file_id}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python retry_extraction.py <file_id1> <file_id2> ...")
        print("Example: python retry_extraction.py 66 68")
        sys.exit(1)
    
    file_ids = [int(arg) for arg in sys.argv[1:]]
    print(f"🔄 Retrying extraction for {len(file_ids)} file(s)...")
    
    for file_id in file_ids:
        retry_extraction(file_id)
    
    print(f"\n✅ Retry requests completed for all files")
    print("💡 Check the extraction status in the UI or wait a few minutes for processing to complete")

