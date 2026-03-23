#!/usr/bin/env python3
"""Run US Bank extraction on stat.pdf and print transaction/check counts."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.pdf_extractor import PDFExtractor

def main():
    # Default to uploaded stat.pdf; override with first arg
    path = sys.argv[1] if len(sys.argv) > 1 else "/Users/apple/.cursor/projects/Users-apple-projects-sync-software/uploads/stat.pdf"
    if not os.path.isfile(path):
        print(f"File not found: {path}")
        sys.exit(1)

    result = PDFExtractor.extract_from_pdf(path)
    if "error" in result:
        print("Error:", result["error"])
        sys.exit(1)

    txns = result.get("transactions", [])
    by_type = {}
    for t in txns:
        typ = t.get("transaction_type", "OTHER")
        by_type[typ] = by_type.get(typ, 0) + 1

    print("Total transactions:", len(txns))
    print("By type:", by_type)

    checks = [t for t in txns if "Check" in (t.get("description") or "")]
    print("Check-like (description contains 'Check'):", len(checks))
    for t in checks[:30]:
        print(" ", t.get("date"), t.get("amount"), (t.get("description") or "")[:60])
    if len(checks) > 30:
        print(" ... and", len(checks) - 30, "more")

if __name__ == "__main__":
    main()
