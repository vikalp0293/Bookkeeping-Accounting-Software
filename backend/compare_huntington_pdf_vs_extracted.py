#!/usr/bin/env python3
"""
Compare Huntington PDF transactions with extracted data (file_id=121).
Reports transactions that appear in the PDF but are missing from the extracted data.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pdfplumber
from app.db.base import SessionLocal
from app.models.extracted_data import ExtractedData


PDF_PATH = "/Users/apple/.cursor/projects/Users-apple-projects-sync-software/uploads/Huntington_Checking_X4497_202506.pdf"
FILE_ID = 121


def normalize_amount(a):
    try:
        return round(float(a), 2)
    except (TypeError, ValueError):
        return None


def description_key(desc, max_len=80):
    """Normalize description for matching (strip, upper, truncate)."""
    if not desc:
        return ""
    s = (desc or "").strip().upper().replace("\n", " ").replace("  ", " ")
    return s[:max_len] if len(s) > max_len else s


def extract_all_transactions_from_pdf_text(pdf_path: str):
    """Extract transactions using text regex (same as Huntington fallback). No tables in this PDF."""
    rows = []
    patterns = [
        re.compile(r"(\d{1,2}/\d{1,2})\s+([-]?[\d,]+\.\d{2})\s+([A-Za-z0-9\s,\-\.\*#]+?)(?=\n\s*\d{1,2}/\d{1,2}|\n\n|$)", re.MULTILINE),
        re.compile(r"(\d{1,2}/\d{1,2})\s+([-]?[\d,]+\.\d{2})\s+([^\n]+?)(?=\n\d{1,2}/\d{1,2}|\n\n|$)", re.MULTILINE),
    ]
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if "Other Credits (+)" not in page_text and "Other Debits (-)" not in page_text and "Credits (+)" not in page_text and "Debits (-)" not in page_text:
                if "Checks (-)" in page_text:
                    continue
            for pattern in patterns:
                matches = pattern.findall(page_text)
                if not matches:
                    continue
                for m in matches:
                    date_str, amount_str, desc = m[0], m[1], m[2].strip()
                    if not date_str or not amount_str:
                        continue
                    du = desc.upper()
                    if du.startswith("OTHER CREDITS") or du.startswith("OTHER DEBITS") or "CHECKS (-)" in du:
                        continue
                    if re.match(r"^\s*Check\s*#?\s*\d+\s*$", desc, re.I) or (re.match(r"^\s*Check\s*#?\s*\d+", desc, re.I) and len(desc) < 30):
                        continue
                    if re.match(r"^\s*\d{3,6}\s*$", desc):
                        continue
                    try:
                        amount = float(amount_str.replace(",", ""))
                        rows.append({"date": date_str, "amount": amount, "description": desc[:200], "section": None})
                    except ValueError:
                        pass
                break  # one pattern matched for this page
    return rows


def extract_all_transactions_from_pdf(pdf_path: str):
    """Extract every transaction row from PDF (Other Credits + Other Debits; skip Checks)."""
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            page_text = page.extract_text() or ""
            tables_found = page.find_tables()
            tables = [t.extract() for t in tables_found] if tables_found else page.extract_tables()
            table_bboxes = [t.bbox for t in tables_found] if tables_found else [None] * len(tables)
            current_section = None
            if "Other Credits (+)" in page_text or "Credits (+)" in page_text:
                current_section = "CREDITS"
            if "Other Debits (-)" in page_text or "Debits (-)" in page_text:
                current_section = "DEBITS"
            if "Checks (-)" in page_text:
                pass  # will set per-table

            for table_idx, table in enumerate(tables):
                if not table or len(table) < 2:
                    continue
                table_section = current_section
                if table_idx < len(table_bboxes) and table_bboxes[table_idx] is not None:
                    try:
                        bbox = table_bboxes[table_idx]
                        cropped = page.crop((0, 0, page.width, bbox[1]))
                        text_above = (cropped.extract_text() or "").strip()
                        if "Other Credits (+)" in text_above or "Credits (+)" in text_above:
                            table_section = "CREDITS"
                        elif "Other Debits (-)" in text_above or "Debits (-)" in text_above:
                            table_section = "DEBITS"
                        elif "Checks (-)" in text_above:
                            table_section = "CHECKS"
                    except Exception:
                        pass
                if table and table[0]:
                    first_row_text = " ".join(str(c or "") for c in table[0]).upper()
                    if "CHECKS (-)" in first_row_text:
                        table_section = "CHECKS"
                    elif "OTHER DEBITS (-)" in first_row_text or "DEBITS (-)" in first_row_text:
                        table_section = "DEBITS"
                    elif "OTHER CREDITS (+)" in first_row_text or "CREDITS (+)" in first_row_text:
                        table_section = "CREDITS"
                if table_section == "CHECKS":
                    continue
                header_row_idx = 0
                data_start_idx = 1
                if len(table) >= 3 and table[0]:
                    first_row_text = " ".join(str(c or "") for c in table[0]).upper()
                    second_has_header = any(
                        "date" in str(c).lower() or "amount" in str(c).lower()
                        for c in (table[1] if len(table) > 1 else []) if c
                    )
                    if (
                        "OTHER DEBITS" in first_row_text
                        or "OTHER CREDITS" in first_row_text
                        or "DEBITS (-)" in first_row_text
                        or "CREDITS (+)" in first_row_text
                    ) and second_has_header:
                        header_row_idx = 1
                        data_start_idx = 2
                data_rows = table[data_start_idx:] if data_start_idx < len(table) else table[1:]
                for row in data_rows:
                    if not row or len(row) < 2:
                        continue
                    row_text = " ".join(str(c or "") for c in row).upper()
                    if "OTHER DEBITS (-)" in row_text or "OTHER CREDITS (+)" in row_text or "CHECKS (-)" in row_text:
                        if "OTHER DEBITS" in row_text or "DEBITS (-)" in row_text:
                            table_section = "DEBITS"
                        elif "OTHER CREDITS" in row_text or "CREDITS (+)" in row_text:
                            table_section = "CREDITS"
                        elif "CHECKS (-)" in row_text:
                            table_section = "CHECKS"
                        continue
                    if table_section == "CHECKS":
                        continue
                    date_col_idx = amount_col_idx = desc_col_idx = None
                    for col_idx, cell in enumerate(row):
                        if cell and re.search(r"\d{1,2}/\d{1,2}", str(cell)):
                            date_col_idx = col_idx
                            break
                    for col_idx, cell in enumerate(row):
                        if cell and (
                            re.search(r"[\d,]+\.\d{2}", str(cell)) or "$" in str(cell)
                        ):
                            amount_col_idx = col_idx
                            break
                    for col_idx, cell in enumerate(row):
                        if cell and col_idx != date_col_idx and col_idx != amount_col_idx:
                            if len(str(cell).strip()) > 10:
                                desc_col_idx = col_idx
                                break
                    if date_col_idx is None:
                        date_col_idx = 0
                    if amount_col_idx is None:
                        amount_col_idx = 1 if len(row) > 1 else 0
                    if desc_col_idx is None:
                        desc_col_idx = 2 if len(row) > 2 else (1 if amount_col_idx != 1 else 0)
                    date_cell = str(row[date_col_idx]).strip() if date_col_idx < len(row) and row[date_col_idx] else ""
                    amount_cell = (
                        str(row[amount_col_idx]).strip()
                        if amount_col_idx < len(row) and row[amount_col_idx]
                        else ""
                    )
                    desc_cell = (
                        str(row[desc_col_idx]).strip()
                        if desc_col_idx < len(row) and row[desc_col_idx]
                        else ""
                    )
                    if not date_cell or not amount_cell:
                        continue
                    date_match = re.search(r"(\d{1,2}/\d{1,2}(?:/\d{2,4})?)", date_cell)
                    amount_match = re.search(r"([-]?[\d,]+\.\d{2})", amount_cell)
                    if not date_match or not amount_match:
                        continue
                    try:
                        amount = float(amount_match.group(1).replace(",", ""))
                        date_str = date_match.group(1)
                        desc = desc_cell or ""
                        rows.append(
                            {
                                "date": date_str,
                                "amount": amount,
                                "description": desc[:200],
                                "section": table_section,
                            }
                        )
                    except Exception:
                        continue
    return rows


def load_extracted_transactions(file_id: int):
    """Load transactions from extracted_data for file_id."""
    db = SessionLocal()
    try:
        rec = db.query(ExtractedData).filter(ExtractedData.file_id == file_id).first()
        if not rec or not rec.processed_data:
            return []
        return rec.processed_data.get("transactions", [])
    finally:
        db.close()


def main():
    if not os.path.exists(PDF_PATH):
        print(f"PDF not found: {PDF_PATH}")
        return 1
    print("Extracting all transactions from PDF (raw)...")
    pdf_txns = extract_all_transactions_from_pdf(PDF_PATH)
    if len(pdf_txns) == 0:
        print("  No tables found; using text-based extraction (same as extractor fallback)...")
        pdf_txns = extract_all_transactions_from_pdf_text(PDF_PATH)
    print(f"  PDF total rows (Credits + Debits, excl. Checks): {len(pdf_txns)}")

    print(f"Loading extracted data for file_id={FILE_ID}...")
    extracted = load_extracted_transactions(FILE_ID)
    print(f"  Extracted total: {len(extracted)}")

    # Build set of (amount, description_key) for extracted
    extracted_keys = set()
    for t in extracted:
        amt = normalize_amount(t.get("amount"))
        if amt is None:
            continue
        extracted_keys.add((amt, description_key(t.get("description") or "")))

    # Find missing: in PDF but no match in extracted
    # Match by (amount, description start) - extracted may truncate/normalize description
    def find_match(pdf_t):
        amt = normalize_amount(pdf_t["amount"])
        if amt is None:
            return True
        dk = description_key(pdf_t["description"])
        if (amt, dk) in extracted_keys:
            return True
        # Fuzzy: same amount and description overlap (either way)
        for e in extracted:
            ea = normalize_amount(e.get("amount"))
            if ea is None or abs(ea - amt) >= 0.01:
                continue
            ed = description_key(e.get("description") or "")
            if not dk or not ed:
                if dk == ed:
                    return True
                continue
            # Match if one description contains the other's first 30 chars
            if dk[:30] in ed or ed[:30] in dk:
                return True
        return False

    missing = [t for t in pdf_txns if not find_match(t)]

    # Dedupe missing by (amount, description_key) in case PDF has duplicates
    seen = set()
    unique_missing = []
    for m in missing:
        k = (normalize_amount(m["amount"]), description_key(m["description"]))
        if k not in seen:
            seen.add(k)
            unique_missing.append(m)

    print(f"\n=== MISSING TRANSACTIONS (in PDF but not in extracted data): {len(unique_missing)} ===\n")
    for i, t in enumerate(unique_missing, 1):
        sec = (t.get("section") or "?")[:8]
        desc = (t.get("description") or "")[:70]
        print(f"{i:3}. {t.get('date', ''):8}  ${t['amount']:>10,.2f}  [{sec:8}]  {desc}")

    if unique_missing:
        print(f"\nTotal missing: {len(unique_missing)}")
        out_path = os.path.join(os.path.dirname(PDF_PATH), "huntington_file_121_missing_transactions.txt")
        try:
            with open(out_path, "w") as f:
                f.write(f"Missing transactions: PDF vs extracted data (file_id={FILE_ID})\n")
                f.write(f"PDF total (text): {len(pdf_txns)}  Extracted: {len(extracted)}  Missing: {len(unique_missing)}\n\n")
                for i, t in enumerate(unique_missing, 1):
                    sec = (t.get("section") or "?")[:8]
                    desc = (t.get("description") or "")[:200]
                    f.write(f"{i:3}. {t.get('date', ''):8}  ${t['amount']:>10,.2f}  [{sec:8}]  {desc}\n")
            print(f"Saved to {out_path}")
        except Exception as e:
            print(f"Could not save file: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
