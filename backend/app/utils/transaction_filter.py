"""
Utility functions for filtering invalid transactions (e.g., balance activity entries).
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import re


def is_balance_activity_entry(trans: Dict[str, Any], statement_period_start: Optional[str] = None, 
                               statement_period_end: Optional[str] = None) -> bool:
    """
    Check if a transaction is actually a balance activity entry (not a real transaction).
    
    Balance activity entries are running balances shown in bank statements, not actual transactions.
    They typically have:
    - Very large amounts (> $100,000)
    - Payee names that look like balance values (e.g., "182,119.83 185,309.43")
    - Memos that contain date patterns followed by balance values
    - Dates outside the statement period
    
    Args:
        trans: Transaction dictionary with date, amount, payee, description/memo
        statement_period_start: Optional statement period start date (YYYY-MM-DD)
        statement_period_end: Optional statement period end date (YYYY-MM-DD)
    
    Returns:
        True if this appears to be a balance activity entry, False otherwise
    """
    # Get transaction fields
    trans_amount_raw = trans.get('amount')
    trans_date = trans.get('date')
    trans_payee = trans.get('payee', trans.get('vendor', ''))
    trans_memo = trans.get('description', trans.get('memo', ''))
    
    # Skip if missing essential data
    if not trans_amount_raw or not trans_date:
        return False
    
    try:
        trans_amount = float(trans_amount_raw)
    except (ValueError, TypeError):
        return False
    
    # 1. Skip transactions with very large amounts (likely balance entries)
    # Typical transactions are < $100,000. Balances are usually much larger.
    if abs(trans_amount) > 100000:
        return True
    
    # 2. Check if payee name looks like a balance value
    # Balance values typically contain commas and multiple numbers (e.g., "182,119.83 185,309.43")
    payee_str = str(trans_payee) if trans_payee else ''
    if payee_str and ',' in payee_str:
        # Pattern: numbers with commas separated by spaces (e.g., "182,119.83 185,309.43")
        balance_pattern = r'\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s+\d{1,3}(?:,\d{3})*(?:\.\d{2})?'
        if re.search(balance_pattern, payee_str):
            return True
        # Also check if payee is just a large number with commas (single balance value)
        if re.match(r'^\d{1,3}(?:,\d{3})*(?:\.\d{2})?$', payee_str.strip()) and abs(trans_amount) > 10000:
            return True
    
    # 3. Check if memo/description looks like balance activity
    # Balance activity memos typically contain date patterns followed by balance values
    # Pattern: "MM/DD balance_value" or "MM/DD balance_value MM/DD balance_value"
    memo_str = str(trans_memo) if trans_memo else ''
    if memo_str:
        balance_memo_pattern = r'\d{1,2}/\d{1,2}\s+\d{1,3}(?:,\d{3})*(?:\.\d{2})?'
        # If memo contains balance pattern and is relatively short, it's likely balance activity
        if re.search(balance_memo_pattern, memo_str) and len(memo_str) < 100:
            return True
    
    # 4. Check if date is outside statement period (if provided)
    # Do NOT filter out check transactions (Check #xxx) for date-only reasons - they are real transactions
    ref = trans.get("reference_number")
    desc = (trans.get("description") or trans.get("memo") or "")
    is_check_transaction = (
        (ref is not None and str(ref).strip() and 3 <= len(re.sub(r"\D", "", str(ref))) <= 6)
        or bool(re.search(r"Check\s*#?\s*\d{3,6}\b", str(desc), re.IGNORECASE))
    )
    if not is_check_transaction and statement_period_start and statement_period_end and trans_date:
        try:
            trans_dt = datetime.strptime(trans_date, '%Y-%m-%d')
            start_dt = datetime.strptime(statement_period_start, '%Y-%m-%d')
            end_dt = datetime.strptime(statement_period_end, '%Y-%m-%d')
            if trans_dt < start_dt or trans_dt > end_dt:
                return True
        except Exception:
            pass  # If date parsing fails, don't filter based on date

    return False


def filter_transactions(
    transactions: List[Dict[str, Any]], 
    statement_period_start: Optional[str] = None,
    statement_period_end: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Filter out invalid transactions (balance activity entries, etc.) from a list of transactions.
    
    Args:
        transactions: List of transaction dictionaries
        statement_period_start: Optional statement period start date (YYYY-MM-DD)
        statement_period_end: Optional statement period end date (YYYY-MM-DD)
    
    Returns:
        Filtered list of valid transactions
    """
    if not transactions:
        return []
    
    filtered = []
    for trans in transactions:
        # Skip balance activity entries
        if is_balance_activity_entry(trans, statement_period_start, statement_period_end):
            continue
        
        # Also skip transactions with zero or missing amounts
        trans_amount_raw = trans.get('amount')
        if trans_amount_raw is None:
            continue
        try:
            if float(trans_amount_raw) == 0:
                continue
        except (ValueError, TypeError):
            continue
        
        # Skip if missing essential data
        if not trans.get('date'):
            continue
        
        filtered.append(trans)
    
    return filtered
