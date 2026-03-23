#!/usr/bin/env python3
"""
Debug WesBanco OCR: run OCR on a file (by file_id), print OCR snippet and parse result.
Usage: python debug_wesbanco_ocr.py <file_id>
Example: python debug_wesbanco_ocr.py 156
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db.base import SessionLocal
from app.models.file import File
from app.services.ocr_service import OCRService
from app.services.pdf_extractor import PDFExtractor


def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_wesbanco_ocr.py <file_id>")
        sys.exit(1)
    file_id = int(sys.argv[1])
    db = SessionLocal()
    try:
        file = db.query(File).filter(File.id == file_id).first()
        if not file:
            print(f"File {file_id} not found")
            sys.exit(1)
        path = file.file_path
        name = file.original_filename or path
        if not os.path.exists(path):
            print(f"File not on disk: {path}")
            sys.exit(1)
        print(f"File: {name}")
        print(f"Path: {path}")
        print("Running OCR (with fallback)...")
        ocr_result = OCRService.extract_text_from_pdf_image_with_fallback(
            path, page_limit=100, min_text_for_success=500, fallback_max_pages=25
        )
        ocr_text = (ocr_result or {}).get("text", "")
        ocr_len = len(ocr_text.strip())
        print(f"OCR length: {ocr_len} chars")
        if ocr_len > 0:
            snippet = ocr_text.strip()[:2500]
            print("\n--- OCR text (first 2500 chars) ---")
            print(snippet)
            print("--- end snippet ---\n")
        print("Parsing with extract_wesbanco_from_text...")
        parsed = PDFExtractor.extract_wesbanco_from_text(ocr_text)
        tx_count = len(parsed.get("transactions") or [])
        print(f"Parsed transactions: {tx_count}")
        if tx_count:
            for i, t in enumerate((parsed.get("transactions") or [])[:5]):
                print(f"  {i+1}. {t.get('date')} {t.get('transaction_type')} {t.get('amount')} {t.get('description', '')[:50]}")
        else:
            print("(No transactions parsed - check OCR snippet above for format)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
