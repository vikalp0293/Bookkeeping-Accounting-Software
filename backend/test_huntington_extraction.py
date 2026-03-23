#!/usr/bin/env python3
"""Test Huntington extraction on uploaded PDF."""
import json
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.pdf_extractor import PDFExtractor

PDF_PATH = "/Users/apple/.cursor/projects/Users-apple-projects-sync-software/uploads/Huntington_Checking_X4497_202506.pdf"

def main():
    if not os.path.exists(PDF_PATH):
        print(f"PDF not found: {PDF_PATH}")
        return 1
    print("Extracting Huntington statement...")
    result = PDFExtractor.extract_huntington_statement(PDF_PATH)
    if "error" in result:
        print("Error:", result["error"])
        return 1
    txns = result.get("transactions", [])
    print(f"\n=== Summary ===")
    print(f"Bank: {result.get('bank_name')}")
    print(f"Statement period: {result.get('statement_period_start')} to {result.get('statement_period_end')}")
    print(f"Total transactions: {len(txns)}")
    print(f"Beginning balance: {result.get('beginning_balance')}")
    print(f"Ending balance: {result.get('ending_balance')}")
    deposits = [t for t in txns if t.get("transaction_type") == "DEPOSIT"]
    withdrawals = [t for t in txns if t.get("transaction_type") in ("WITHDRAWAL", "FEE")]
    print(f"Deposits: {len(deposits)}, Withdrawals/Fees: {len(withdrawals)}")
    print(f"\n=== Sample transactions (first 5) ===")
    for i, t in enumerate(txns[:5]):
        print(f"  {i+1}. {t.get('date')} | {t.get('transaction_type')} | {t.get('payee')} | {t.get('amount')} | {t.get('description', '')[:50]}")
    print(f"\n=== Sample transactions (last 5) ===")
    for i, t in enumerate(txns[-5:]):
        print(f"  {len(txns)-4+i}. {t.get('date')} | {t.get('transaction_type')} | {t.get('payee')} | {t.get('amount')} | {t.get('description', '')[:50]}")
    print(f"\n=== All unique dates ===")
    dates = sorted(set(t.get("date") for t in txns))
    print(dates)
    print(f"\n=== Withdrawal payees (sample) ===")
    for t in withdrawals[:15]:
        print(f"  {t.get('payee')} | {t.get('description', '')[:60]}")
    out_path = os.path.join(os.path.dirname(PDF_PATH), "huntington_extraction_result.json")
    with open(out_path, "w") as f:
        json.dump({k: v for k, v in result.items() if k != "transactions"}, f, indent=2)
    with open(out_path.replace(".json", "_transactions.json"), "w") as f:
        json.dump(txns, f, indent=2)
    print(f"\nFull result (no txns) saved to {out_path}")
    print(f"Transactions saved to {out_path.replace('.json', '_transactions.json')}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
