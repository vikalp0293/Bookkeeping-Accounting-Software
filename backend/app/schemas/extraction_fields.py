"""
Schema definitions for extraction fields and QuickBooks mapping.
This defines all the keys/fields needed for data extraction and QuickBooks export.
"""
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime


# ============================================================================
# EXTRACTION FIELDS - What we extract from bank statements/checks
# ============================================================================

class Transaction(BaseModel):
    """Individual transaction from bank statement."""
    date: str  # Format: YYYY-MM-DD or MM/DD/YYYY
    amount: float  # Positive for deposits, negative for withdrawals
    description: str  # Transaction description/memo
    payee: Optional[str] = None  # Vendor/payee name
    transaction_type: Optional[str] = None  # "DEPOSIT", "WITHDRAWAL", "CHECK", "FEE", "INTEREST"
    reference_number: Optional[str] = None  # Check number, transaction ID, etc.
    category: Optional[str] = None  # For future categorization
    account: Optional[str] = None  # Account name/number if multiple accounts


class BankStatementData(BaseModel):
    """Complete extracted data from a bank statement."""
    # Account Information
    account_number: Optional[str] = None
    account_name: Optional[str] = None  # e.g., "Chase Business Complete Checking"
    bank_name: Optional[str] = None  # e.g., "Chase", "Huntington", "US Bank"
    
    # Statement Period
    statement_period_start: Optional[str] = None  # Format: YYYY-MM-DD
    statement_period_end: Optional[str] = None  # Format: YYYY-MM-DD
    statement_date: Optional[str] = None  # When statement was generated
    
    # Balances
    beginning_balance: Optional[float] = None
    ending_balance: Optional[float] = None
    available_balance: Optional[float] = None
    average_ledger_balance: Optional[float] = None
    average_collected_balance: Optional[float] = None
    
    # Summary Totals
    total_deposits: Optional[float] = None
    total_withdrawals: Optional[float] = None
    total_checks_paid: Optional[float] = None
    total_service_charges: Optional[float] = None
    total_interest_earned: Optional[float] = None
    
    # Transactions
    transactions: List[Transaction] = []
    
    # Metadata
    number_of_transactions: Optional[int] = None
    number_of_checks: Optional[int] = None
    number_of_deposits: Optional[int] = None


class CheckData(BaseModel):
    """Extracted data from a check (scanned/image)."""
    check_number: Optional[str] = None
    date: Optional[str] = None  # Check date
    payee: Optional[str] = None  # Who the check is made out to
    amount: Optional[float] = None  # Check amount
    memo: Optional[str] = None  # Memo line on check
    account_number: Optional[str] = None  # Bank account number
    routing_number: Optional[str] = None  # Bank routing number
    bank_name: Optional[str] = None


# ============================================================================
# QUICKBOOKS FIELDS - What we need for QuickBooks export
# ============================================================================

class QuickBooksTransaction(BaseModel):
    """Transaction formatted for QuickBooks .IIF export."""
    trnstype: str  # "DEPOSIT", "CHECK", "TRANSFER", "GENERAL JOURNAL"
    date: str  # Format: MM/DD/YYYY
    accnt: str  # Account name in QuickBooks (e.g., "Checking", "Savings")
    name: str  # Payee/Vendor name
    amount: float  # Always positive in QuickBooks
    memo: str  # Transaction description
    
    # Optional QuickBooks fields
    cleared: Optional[str] = None  # "Y" or "N"
    toprint: Optional[str] = None  # "Y" or "N"
    addr1: Optional[str] = None
    addr2: Optional[str] = None
    class_field: Optional[str] = None  # Class (if using classes)
    customer: Optional[str] = None  # Customer name
    vendor: Optional[str] = None  # Vendor name
    employee: Optional[str] = None  # Employee name


class QuickBooksExportData(BaseModel):
    """Complete data structure for QuickBooks export."""
    transactions: List[QuickBooksTransaction]
    account_name: str  # Default account name for transactions
    export_date: Optional[str] = None


# ============================================================================
# FIELD MAPPING - How extraction fields map to QuickBooks
# ============================================================================

EXTRACTION_TO_QUICKBOOKS_MAPPING = {
    # Transaction fields
    "date": "date",  # Convert format: YYYY-MM-DD -> MM/DD/YYYY
    "amount": "amount",  # Convert: negative -> positive for checks
    "description": "memo",
    "payee": "name",
    "transaction_type": "trnstype",  # Map: "DEPOSIT" -> "DEPOSIT", "WITHDRAWAL" -> "CHECK"
    "reference_number": None,  # Can go in memo
    "category": None,  # Can map to QuickBooks account or class
    
    # Account fields
    "account_name": "accnt",
    "account_number": None,  # Not used in QuickBooks directly
}

# Transaction type mapping
TRANSACTION_TYPE_MAPPING = {
    "DEPOSIT": "DEPOSIT",
    "deposit": "DEPOSIT",
    "WITHDRAWAL": "CHECK",
    "withdrawal": "CHECK",
    "CHECK": "CHECK",
    "check": "CHECK",
    "FEE": "CHECK",
    "fee": "CHECK",
    "SERVICE CHARGE": "CHECK",
    "INTEREST": "DEPOSIT",
    "interest": "DEPOSIT",
}

