#!/usr/bin/env python3
"""Check file and extraction status."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.base import SessionLocal
from app.models.file import File
from app.models.extracted_data import ExtractedData

db = SessionLocal()
try:
    file = db.query(File).filter(File.id == 3).first()
    if file:
        print(f"File ID: {file.id}")
        print(f"Filename: {file.original_filename}")
        print(f"Status: {file.status}")
        print(f"File Path: {file.file_path}")
        print(f"File exists: {os.path.exists(file.file_path)}")
        print(f"Created: {file.created_at}")
        print(f"Updated: {file.updated_at}")
        
        extraction = db.query(ExtractedData).filter(ExtractedData.file_id == 3).first()
        if extraction:
            print(f"\nExtraction Status: {extraction.extraction_status}")
            print(f"Error: {extraction.error_message}")
            print(f"Has raw_data: {extraction.raw_data is not None}")
            print(f"Has processed_data: {extraction.processed_data is not None}")
        else:
            print("\nNo extraction record found")
    else:
        print("File ID 3 not found")
finally:
    db.close()

