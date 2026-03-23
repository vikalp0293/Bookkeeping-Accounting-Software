#!/usr/bin/env python3
"""Manually trigger extraction for file ID 3."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.base import SessionLocal
from app.models.file import File, FileStatus
from app.models.extracted_data import ExtractedData
from app.services.pdf_extractor import PDFExtractor
import time

db = SessionLocal()
try:
    file = db.query(File).filter(File.id == 3).first()
    if not file:
        print("File not found")
        sys.exit(1)
    
    print(f"Processing file: {file.original_filename}")
    print(f"File path: {file.file_path}")
    print(f"File exists: {os.path.exists(file.file_path)}")
    
    if not os.path.exists(file.file_path):
        print("ERROR: File not found on disk")
        sys.exit(1)
    
    extracted_data = db.query(ExtractedData).filter(ExtractedData.file_id == 3).first()
    if not extracted_data:
        print("Creating extraction record...")
        extracted_data = ExtractedData(
            file_id=3,
            extraction_status="pending",
            raw_data={},
            processed_data={}
        )
        db.add(extracted_data)
        db.commit()
    
    print("\nStarting extraction...")
    start_time = time.time()
    
    # Extract PDF
    extracted_result = PDFExtractor.extract_from_pdf(file.file_path)
    
    elapsed = time.time() - start_time
    print(f"Extraction completed in {elapsed:.2f} seconds")
    
    if "error" in extracted_result:
        print(f"ERROR: {extracted_result['error']}")
        extracted_data.extraction_status = "failed"
        extracted_data.error_message = extracted_result["error"]
        file.status = FileStatus.FAILED
    else:
        print(f"Extracted {len(extracted_result.get('transactions', []))} transactions")
        extracted_data.raw_data = extracted_result
        extracted_data.processed_data = extracted_result
        extracted_data.extraction_status = "completed"
        file.status = FileStatus.COMPLETED
        print("✓ Extraction successful")
    
    db.commit()
    print("\nDatabase updated successfully")
    
finally:
    db.close()

