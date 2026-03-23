"""
QuickBooks integration service.
Supports:
1. Export to QuickBooks .IIF format
2. QuickBooks Online API integration (future)
"""
from typing import List, Dict, Any
from datetime import datetime


class QuickBooksService:
    """Service for QuickBooks integration and export."""
    
    @staticmethod
    def generate_iif_file(
        transactions: List[Dict[str, Any]], 
        bank_account_name: str = "Checking",
        income_account_name: str = "Sales"
    ) -> str:
        """
        Generate QuickBooks .IIF (Intuit Interchange Format) file content.
        
        CRITICAL: For deposits in IIF format:
        - TRNS line: Bank account (where money goes TO)
        - SPL line: Income account (where money comes FROM) - typically "Sales"
        - Both lines must have the same amount
        
        Args:
            transactions: List of transaction dictionaries with:
                - date: Transaction date (YYYY-MM-DD or MM/DD/YYYY)
                - amount: Transaction amount (positive for deposits, negative for withdrawals)
                - payee: Payee/vendor name (optional)
                - memo: Transaction description/memo
                - transaction_type: "DEPOSIT" or "WITHDRAWAL" (optional)
            bank_account_name: Bank account name (e.g., "Huntington X4497")
            income_account_name: Income account for deposits (e.g., "Sales")
        
        Returns:
            IIF file content as string
        """
        lines = []
        
        # IIF Header - CRITICAL: Headers must match exactly
        lines.append("!TRNS\tTRNSTYPE\tDATE\tACCNT\tNAME\tAMOUNT\tMEMO")
        lines.append("!SPL\tTRNSTYPE\tDATE\tACCNT\tNAME\tAMOUNT\tMEMO")
        lines.append("!ENDTRNS")
        
        # Process each transaction
        for trans in transactions:
            date = trans.get('date', datetime.now().strftime('%m/%d/%y'))
            amount = float(trans.get('amount', 0))
            payee = trans.get('payee', trans.get('vendor', 'Bank Deposits'))
            # Handle None values in payee
            if payee is None or payee == 'None' or str(payee).strip() == '':
                payee = 'Bank Deposits'
            memo = trans.get('memo', trans.get('description', ''))
            # Handle None values in memo
            if memo is None:
                memo = ''
            trans_type = trans.get('transaction_type', 'DEPOSIT' if amount >= 0 else 'WITHDRAWAL')
            
            # Format date (MM/DD/YY) - QuickBooks Desktop IIF requires 2-digit year format
            if isinstance(date, str):
                try:
                    # Try YYYY-MM-DD format first (most common from database)
                    dt = datetime.strptime(date, '%Y-%m-%d')
                    date = dt.strftime('%m/%d/%y')  # 2-digit year for IIF
                except:
                    try:
                        # Try MM/DD/YYYY format
                        dt = datetime.strptime(date, '%m/%d/%Y')
                        date = dt.strftime('%m/%d/%y')  # 2-digit year for IIF
                    except:
                        try:
                            # Try MM/DD/YY format (already correct)
                            dt = datetime.strptime(date, '%m/%d/%y')
                            date = dt.strftime('%m/%d/%y')
                        except:
                            try:
                                # Try MM/DD format (missing year) - intelligently determine year
                                dt = datetime.strptime(date, '%m/%d')
                                current_year = datetime.now().year
                                current_date = datetime.now()
                                
                                # Try current year first
                                dt_with_year = dt.replace(year=current_year)
                                
                                # If the date is in a future month (not just future days), it's probably from previous year
                                # (e.g., if today is Jan 2026 and date is March, it's likely March 2025)
                                # This handles bank statements where dates are often extracted without year
                                if dt_with_year > current_date:
                                    # Check if date is more than 60 days ahead OR in a different month that's ahead
                                    days_ahead = (dt_with_year - current_date).days
                                    months_ahead = (dt_with_year.year - current_date.year) * 12 + (dt_with_year.month - current_date.month)
                                    
                                    # If more than 60 days ahead OR in a future month (not current month), use previous year
                                    if days_ahead > 60 or (months_ahead > 0 and dt_with_year.month != current_date.month):
                                        dt_with_year = dt.replace(year=current_year - 1)
                                
                                date = dt_with_year.strftime('%m/%d/%y')
                            except:
                                # If all parsing fails, use today's date as fallback
                                date = datetime.now().strftime('%m/%d/%y')
            
            # Determine transaction type
            # CRITICAL: Check transaction_type FIRST, only use amount as fallback if type is missing
            trans_type_upper = trans_type.upper() if trans_type else ''
            
            # Handle FEE transactions - treat as CHECK/WITHDRAWAL in QuickBooks
            if trans_type_upper == 'FEE':
                trns_type = "CHECK"
                amount = abs(amount)  # Ensure positive
                
                # For fees/checks:
                # TRNS line: Bank account (where money comes from) - NEGATIVE amount
                # SPL line: Expense account (where money goes) - POSITIVE amount
                expense_account = trans.get('expense_account', 'Bank Service Charges')
                lines.append(f"TRNS\t{trns_type}\t{date}\t{bank_account_name}\t{payee}\t-{amount:.2f}\t{memo}")
                lines.append(f"SPL\t{trns_type}\t{date}\t{expense_account}\t{payee}\t{amount:.2f}\t{memo}")
                
            elif trans_type_upper == 'DEPOSIT':
                # Explicit DEPOSIT type
                trns_type = "DEPOSIT"
                amount = abs(amount)  # Ensure positive
                
                # For deposits in IIF format:
                # TRNS line: Bank account with POSITIVE amount (money coming in)
                # SPL line: Income account with NEGATIVE amount (credit to income)
                # The amounts must balance: TRNS positive + SPL negative = 0
                lines.append(f"TRNS\t{trns_type}\t{date}\t{bank_account_name}\t{payee}\t{amount:.2f}\t{memo}")
                lines.append(f"SPL\t{trns_type}\t{date}\t{income_account_name}\t{payee}\t-{amount:.2f}\t{memo}")
                
            elif trans_type_upper in ['WITHDRAWAL', 'CHECK']:
                # Explicit WITHDRAWAL/CHECK type
                trns_type = "CHECK"
                amount = abs(amount)  # Ensure positive
                
                # For checks/withdrawals:
                # TRNS line: Bank account (where money comes from) - NEGATIVE amount
                # SPL line: Expense account (where money goes) - POSITIVE amount
                expense_account = trans.get('expense_account', 'Expenses')
                lines.append(f"TRNS\t{trns_type}\t{date}\t{bank_account_name}\t{payee}\t-{amount:.2f}\t{memo}")
                lines.append(f"SPL\t{trns_type}\t{date}\t{expense_account}\t{payee}\t{amount:.2f}\t{memo}")
                
            else:
                # Fallback: Use amount sign if transaction_type is not provided or unknown
                if amount >= 0:
                    # Positive amount = DEPOSIT
                    trns_type = "DEPOSIT"
                    amount = abs(amount)
                    lines.append(f"TRNS\t{trns_type}\t{date}\t{bank_account_name}\t{payee}\t{amount:.2f}\t{memo}")
                    lines.append(f"SPL\t{trns_type}\t{date}\t{income_account_name}\t{payee}\t-{amount:.2f}\t{memo}")
                else:
                    # Negative amount = WITHDRAWAL/CHECK
                    trns_type = "CHECK"
                    amount = abs(amount)
                    expense_account = trans.get('expense_account', 'Expenses')
                    lines.append(f"TRNS\t{trns_type}\t{date}\t{bank_account_name}\t{payee}\t-{amount:.2f}\t{memo}")
                    lines.append(f"SPL\t{trns_type}\t{date}\t{expense_account}\t{payee}\t{amount:.2f}\t{memo}")
            
            lines.append("ENDTRNS")
        
        return "\n".join(lines)
    
    @staticmethod
    def convert_extracted_data_to_transactions(extracted_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Convert extracted data from bank statements/checks to QuickBooks transaction format.
        
        Args:
            extracted_data: Dictionary containing extracted transaction data
        
        Returns:
            List of transaction dictionaries ready for IIF export
        """
        transactions = []
        
        # Handle different data structures
        if 'transactions' in extracted_data:
            # If transactions are already in a list
            for trans in extracted_data['transactions']:
                transactions.append({
                    'date': trans.get('date'),
                    'amount': float(trans.get('amount', 0)),
                    'payee': trans.get('payee', trans.get('vendor', '')),
                    'memo': trans.get('description', trans.get('memo', '')),
                    'account': extracted_data.get('account_name', 'Checking')
                })
        elif 'raw_data' in extracted_data:
            # If it's a single transaction in raw_data
            raw = extracted_data.get('raw_data', {})
            transactions.append({
                'date': raw.get('date'),
                'amount': float(raw.get('amount', 0)),
                'payee': raw.get('payee', raw.get('vendor', '')),
                'memo': raw.get('description', raw.get('memo', '')),
                'account': extracted_data.get('account_name', 'Checking')
            })
        
        return transactions
    
    @staticmethod
    def export_to_iif_file(transactions: List[Dict[str, Any]], filename: str = None) -> str:
        """
        Export transactions to a QuickBooks .IIF file.
        
        Args:
            transactions: List of transaction dictionaries
            filename: Optional filename (without .iif extension)
        
        Returns:
            Path to the generated .IIF file
        """
        import os
        from app.core.config import settings
        
        # Generate IIF content
        iif_content = QuickBooksService.generate_iif_file(transactions)
        
        # Create export directory
        export_dir = os.path.join(settings.UPLOAD_DIR, 'exports')
        os.makedirs(export_dir, exist_ok=True)
        
        # Generate filename
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"quickbooks_export_{timestamp}"
        
        if not filename.endswith('.iif'):
            filename += '.iif'
        
        filepath = os.path.join(export_dir, filename)
        
        # Write file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(iif_content)
        
        return filepath

