"""
Account Manager
Manages account resolution and caching for QuickBooks
Simplified version for SDK-based sync
"""

import logging
from typing import Optional, Set, Dict
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


class AccountManager:
    """Manages QuickBooks account resolution"""
    
    def __init__(self):
        self.known_accounts: Set[str] = set()
        self.account_types: Dict[str, str] = {}  # account_name -> account_type
        self.initialized = False
    
    def is_initialized(self) -> bool:
        """Check if account manager has been initialized"""
        return self.initialized and len(self.known_accounts) > 0
    
    def update_from_account_query_response(self, response_xml: str):
        """Update account cache from AccountQuery response"""
        try:
            root = ET.fromstring(response_xml)
            account_ret_list = root.findall('.//AccountRet')
            
            for account in account_ret_list:
                name_elem = account.find('Name')
                type_elem = account.find('AccountType')
                
                if name_elem is not None and type_elem is not None:
                    account_name = name_elem.text
                    account_type = type_elem.text
                    self.known_accounts.add(account_name)
                    self.account_types[account_name] = account_type
            
            self.initialized = True
            logger.info(f"Account manager initialized with {len(self.known_accounts)} accounts")
        except Exception as e:
            logger.error(f"Failed to parse account query response: {e}")
    
    def resolve_account(self, preferred: str, fallback_type: Optional[str] = None) -> Optional[str]:
        """
        Resolve account name, checking if it exists in cache
        
        Args:
            preferred: Preferred account name
            fallback_type: Fallback account type if preferred not found
            
        Returns:
            Resolved account name or None
        """
        preferred = preferred.strip()
        
        # Exact match
        if preferred in self.known_accounts:
            return preferred
        
        # Case-insensitive match
        for account in self.known_accounts:
            if account.lower() == preferred.lower():
                return account
        
        # If not found and we have accounts, return None (account doesn't exist)
        if self.initialized:
            logger.warning(f"Account '{preferred}' not found in QuickBooks")
            return None
        
        # Not initialized - return preferred as-is (will be validated by QuickBooks)
        return preferred

    def get_first_account_of_type(self, account_type: str) -> Optional[str]:
        """Return the first account name of the given type (e.g. Income, Expense, OtherIncome)."""
        if not self.initialized:
            return None
        for name, atype in self.account_types.items():
            if atype == account_type:
                return name
        return None
