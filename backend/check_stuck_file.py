#!/usr/bin/env python3
"""
Script to check and fix stuck processing files.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db.base import SessionLocal
from app.models.file import File, FileStatus
from app.models.extracted_data import ExtractedData
from datetime import datetime, timedelta

def check_stuck_files():
    """Check for files stuck in processing state for more than 10 minutes."""
    db = SessionLocal()
    try:
        # Find files in processing state
        processing_files = db.query(File).filter(File.status == FileStatus.PROCESSING).all()
        
        print(f"Found {len(processing_files)} file(s) in processing state:")
        
        for file in processing_files:
            # Check how long it's been processing
            if file.updated_at:
                time_diff = datetime.now(file.updated_at.tzinfo) - file.updated_at
            else:
                time_diff = datetime.now(file.created_at.tzinfo) - file.created_at
            
            minutes_stuck = time_diff.total_seconds() / 60
            
            print(f"\nFile ID: {file.id}")
            print(f"  Filename: {file.original_filename}")
            print(f"  Status: {file.status}")
            print(f"  Created: {file.created_at}")
            print(f"  Updated: {file.updated_at}")
            print(f"  Stuck for: {minutes_stuck:.1f} minutes")
            
            # Check if file exists on disk
            if os.path.exists(file.file_path):
                print(f"  File exists on disk: ✓")
            else:
                print(f"  File exists on disk: ✗ (NOT FOUND)")
            
            # Check extraction status
            extraction = db.query(ExtractedData).filter(ExtractedData.file_id == file.id).first()
            if extraction:
                print(f"  Extraction status: {extraction.extraction_status}")
                if extraction.error_message:
                    print(f"  Error message: {extraction.error_message}")
            
            # If stuck for more than 10 minutes, mark as failed
            if minutes_stuck > 10:
                print(f"  ⚠️  File has been stuck for {minutes_stuck:.1f} minutes (>10 min)")
                response = input(f"  Mark file {file.id} as failed? (y/n): ")
                if response.lower() == 'y':
                    file.status = FileStatus.FAILED
                    if extraction:
                        extraction.extraction_status = "failed"
                        extraction.error_message = f"Processing timeout - stuck for {minutes_stuck:.1f} minutes"
                    db.commit()
                    print(f"  ✓ Marked file {file.id} as failed")
        
    finally:
        db.close()

if __name__ == "__main__":
    check_stuck_files()

