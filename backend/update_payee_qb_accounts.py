#!/usr/bin/env python3
"""
One-off script: set qb_expense_account_name on all payees to a random choice from:
  Utilities, Repairs and Maintenance, Rent Expense, Cost of Goods Sold

Run from backend dir with venv active: python update_payee_qb_accounts.py
"""
import sys
import os
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.base import SessionLocal
from app.models.payee import Payee

QB_ACCOUNTS = [
    "Utilities",
    "Repairs and Maintenance",
    "Rent Expense",
    "Cost of Goods Sold",
]


def main():
    db = SessionLocal()
    try:
        payees = db.query(Payee).all()
        if not payees:
            print("No payees found.")
            return
        for payee in payees:
            payee.qb_expense_account_name = random.choice(QB_ACCOUNTS)
        db.commit()
        print(f"Updated qb_expense_account_name for {len(payees)} payee(s) (random from: {QB_ACCOUNTS}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
