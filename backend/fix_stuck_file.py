#!/usr/bin/env python3
"""
Script to fix a specific stuck file.
Usage: python3 fix_stuck_file.py <file_id>
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db.base import SessionLocal
from app.models.file import File, FileStatus
from app.models.extracted_data import ExtractedData

def fix_stuck_file(file_id: int):
    """Mark a stuck file as failed."""
    db = SessionLocal()
    try:
        file = db.query(File).filter(File.id == file_id).first()
        if not file:
            print(f"File {file_id} not found")
            return False
        
        if file.status != FileStatus.PROCESSING:
            print(f"File {file_id} is not in processing state (current: {file.status})")
            return False
        
        print(f"Fixing stuck file ID: {file_id}")
        print(f"  Filename: {file.original_filename}")
        
        # Mark as failed
        file.status = FileStatus.FAILED
        
        # Update extraction status
        extraction = db.query(ExtractedData).filter(ExtractedData.file_id == file_id).first()
        if extraction:
            extraction.extraction_status = "failed"
            extraction.error_message = "Processing timeout - extraction was stuck and manually cancelled"
        
        db.commit()
        print(f"✓ Successfully marked file {file_id} as failed")
        return True
        
    except Exception as e:
        print(f"Error fixing file {file_id}: {e}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 fix_stuck_file.py <file_id>")
        sys.exit(1)
    
    file_id = int(sys.argv[1])
    fix_stuck_file(file_id)

