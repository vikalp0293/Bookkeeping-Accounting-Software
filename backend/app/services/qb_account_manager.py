"""
QuickBooks Account Manager Service
Manages account existence checks and automatic account creation
"""

import xml.etree.ElementTree as ET
from typing import Dict, Set, Optional, List
import logging

from app.services.qbxml_service import QBXMLService

logger = logging.getLogger(__name__)


class QBAccountManager:
    """
    Manages QuickBooks accounts, customers, and items - tracks which exist and creates missing ones.
    """
    
    def __init__(self):
        # Cache of accounts that exist in QuickBooks (name -> type)
        self.known_accounts: Dict[str, str] = {}
        # Accounts that we've requested to create (pending creation) - maps request_id to account_name
        self.pending_accounts: Dict[str, str] = {}  # request_id -> account_name
        # Accounts that failed to create (to avoid retrying)
        self.failed_accounts: Set[str] = set()
        
        # Cache of customers that exist in QuickBooks (just names for now)
        self.known_customers: Set[str] = set()
        # Customers that we've requested to create (pending creation) - maps request_id to customer_name
        self.pending_customers: Dict[str, str] = {}  # request_id -> customer_name
        # Customers that failed to create (to avoid retrying)
        self.failed_customers: Set[str] = set()
        
        # Cache of items that exist in QuickBooks (just names for now)
        self.known_items: Set[str] = set()
        # Items that we've requested to create (pending creation) - maps request_id to item_name
        self.pending_items: Dict[str, str] = {}  # request_id -> item_name
        # Items that failed to create (to avoid retrying)
        self.failed_items: Set[str] = set()
        
        # Cache of vendors that exist in QuickBooks (just names for now)
        self.known_vendors: Set[str] = set()
        # Vendors that we've requested to create (pending creation) - maps request_id to vendor_name
        self.pending_vendors: Dict[str, str] = {}  # request_id -> vendor_name
        # Vendors that failed to create (to avoid retrying)
        self.failed_vendors: Set[str] = set()
        
        # Track query completion status (to handle empty query results)
        self.customer_query_completed: bool = False
        self.item_query_completed: bool = False
        self.vendor_query_completed: bool = False
    
    def update_from_account_query_response(self, response_xml: str) -> None:
        """
        Update known accounts from AccountQuery response.
        
        Args:
            response_xml: qbXML response from AccountQuery
        """
        try:
            root = ET.fromstring(response_xml)
            account_ret_list = root.findall('.//AccountRet')
            
            for account in account_ret_list:
                name_elem = account.find('Name')
                type_elem = account.find('AccountType')
                if name_elem is not None and type_elem is not None:
                    account_name = name_elem.text
                    account_type = type_elem.text
                    self.known_accounts[account_name] = account_type
                    logger.info(f"Known account: '{account_name}' (type: {account_type})")
            
            logger.info(f"Updated account cache: {len(self.known_accounts)} accounts known")
        except Exception as e:
            logger.error(f"Error parsing account query response: {e}", exc_info=True)
    
    def update_from_account_add_response(self, response_xml: str, request_id: Optional[str] = None) -> bool:
        """
        Update account cache after creating an account.
        
        Args:
            response_xml: qbXML response from AccountAdd
            request_id: Request ID used to create the account (to identify which account)
            
        Returns:
            True if account was successfully created, False otherwise
        """
        # Find account name from request_id
        account_name = None
        if request_id and request_id in self.pending_accounts:
            account_name = self.pending_accounts[request_id]
        elif self.pending_accounts:
            # Fallback: use first pending account
            account_name = list(self.pending_accounts.values())[0]
            request_id = list(self.pending_accounts.keys())[0]
        
        if not account_name:
            logger.warning("Could not identify which account was created from response")
            return False
        
        try:
            root = ET.fromstring(response_xml)
            
            # CRITICAL: statusCode is an ATTRIBUTE on AccountAddRs, not a child element
            account_add_rs = root.find('.//AccountAddRs')
            if account_add_rs is not None:
                status_code = account_add_rs.get('statusCode', '')
                status_message = account_add_rs.get('statusMessage', '')
                
                if status_code == "0":  # Success
                    # Get account type from response
                    account_ret = root.find('.//AccountRet')
                    if account_ret is not None:
                        type_elem = account_ret.find('AccountType')
                        account_type = type_elem.text if type_elem is not None else "Bank"
                        self.known_accounts[account_name] = account_type
                        if request_id:
                            self.pending_accounts.pop(request_id, None)
                        logger.info(f"✓ Account '{account_name}' successfully created (type: {account_type})")
                        return True
                    else:
                        # Success but couldn't parse type - assume Bank
                        self.known_accounts[account_name] = "Bank"
                        if request_id:
                            self.pending_accounts.pop(request_id, None)
                        logger.info(f"✓ Account '{account_name}' successfully created (assuming Bank type)")
                        return True
                else:
                    # Check if it's a duplicate (account already exists)
                    if "already exists" in status_message.lower() or status_code == "3100":
                        # Account already exists - add to known accounts
                        self.known_accounts[account_name] = "Bank"  # Assume Bank type
                        if request_id:
                            self.pending_accounts.pop(request_id, None)
                        logger.info(f"Account '{account_name}' already exists (duplicate creation attempt)")
                        return True
                    else:
                        # Real failure
                        self.failed_accounts.add(account_name)
                        if request_id:
                            self.pending_accounts.pop(request_id, None)
                        logger.error(f"✗ Failed to create account '{account_name}': {status_message} (statusCode: {status_code})")
                        return False
            else:
                # No AccountAddRs element - assume failure
                self.failed_accounts.add(account_name)
                if request_id:
                    self.pending_accounts.pop(request_id, None)
                logger.error(f"✗ Failed to create account '{account_name}': No AccountAddRs element in response")
                return False
        except Exception as e:
            logger.error(f"Error parsing account add response: {e}", exc_info=True)
            self.failed_accounts.add(account_name)
            if request_id:
                self.pending_accounts.pop(request_id, None)
            return False
    
    def is_initialized(self) -> bool:
        """
        Check if account manager has been initialized with AccountQuery results.
        
        Returns:
            True if AccountQuery has been run and cache is populated, False otherwise
        """
        return len(self.known_accounts) > 0
    
    def account_exists(self, account_name: str) -> bool:
        """
        Check if an account exists in QuickBooks.
        
        Args:
            account_name: Name of the account to check
            
        Returns:
            True if account exists, False otherwise
        """
        return account_name in self.known_accounts
    
    def resolve_account(self, preferred: str, fallback_type: str = "OtherCurrentAsset") -> Optional[str]:
        """
        Resolve account name by matching against known accounts.
        Account names are whitespace-sensitive and case-insensitive.
        
        Args:
            preferred: Preferred account name (e.g., "Undeposited Funds")
            fallback_type: Account type to search for if preferred name not found
            
        Returns:
            Exact account name from QuickBooks, or None if not found
        """
        # Normalize preferred name (lowercase, strip whitespace)
        preferred_normalized = preferred.strip().lower()
        
        # First, try exact match (case-insensitive)
        for account_name in self.known_accounts:
            if account_name.strip().lower() == preferred_normalized:
                logger.debug(f"Resolved account '{preferred}' to '{account_name}' (exact match)")
                return account_name
        
        # If not found and we have a fallback type, search by type
        if fallback_type:
            for account_name, account_type in self.known_accounts.items():
                if account_type == fallback_type:
                    logger.debug(f"Resolved account '{preferred}' to '{account_name}' (type match: {fallback_type})")
                    return account_name
        
        logger.warning(f"Could not resolve account '{preferred}' (type: {fallback_type}) - not found in known accounts")
        return None
    
    def get_first_account_of_type(self, account_type: str) -> Optional[str]:
        """
        Return the first account name of the given type from known_accounts.
        Used when we need any valid account of a type (e.g. Expense for Check line).
        """
        for account_name, atype in self.known_accounts.items():
            if atype == account_type:
                return account_name
        return None
    
    def generate_account_query_request(self) -> str:
        """
        Generate AccountQuery request to populate account cache.
        
        Returns:
            qbXML string for AccountQuery request
        """
        # Use simple requestID format (no hyphens) to avoid potential parsing issues
        return QBXMLService.generate_account_query(request_id="1")
    
    def get_accounts_needed_for_transaction(self, transaction: Dict) -> List[tuple]:
        """
        Get list of (account_name, account_type) pairs that MUST exist for a transaction.
        Only the workspace bank account is required; we do not require creating
        expense/income accounts (we use resolve_account to pick an existing one at build time).
        """
        accounts_needed = []
        
        trans_type = transaction.get('transaction_type', '').upper()
        
        # Only require the bank account (workspace account). No validation of expense/misc/sales.
        main_account = transaction.get('account', 'Checking')
        if main_account:
            accounts_needed.append((main_account.strip(), 'Bank'))
        
        # Do NOT add Miscellaneous Expense, Sales, or Interest Income - we use existing
        # accounts via resolve_account when building XML (IIF-style: log to one bank only).
        
        seen = set()
        unique_accounts = []
        for account_name, account_type in accounts_needed:
            if account_name not in seen:
                seen.add(account_name)
                unique_accounts.append((account_name, account_type))
        
        return unique_accounts
    
    def get_missing_accounts(self, transaction: Dict) -> List[tuple]:
        """
        Get list of accounts that need to be created for a transaction.
        
        Args:
            transaction: Transaction dictionary
            
        Returns:
            List of (account_name, account_type) tuples that need to be created
        """
        accounts_needed = self.get_accounts_needed_for_transaction(transaction)
        missing = []
        
        for account_name, account_type in accounts_needed:
            # If cache is empty, assume account doesn't exist and try to create it
            # (QuickBooks will return an error if it already exists, which we handle)
            if len(self.known_accounts) == 0:
                # Cache is empty - assume account doesn't exist and try to create
                is_pending = account_name in self.pending_accounts.values()
                is_failed = account_name in self.failed_accounts
                if not is_pending and not is_failed:
                    missing.append((account_name, account_type))
                    logger.info(f"Account manager cache is empty - will attempt to create '{account_name}'")
            elif not self.account_exists(account_name):
                # Cache is populated - check if account exists
                # Check if it's pending or failed
                is_pending = account_name in self.pending_accounts.values()
                is_failed = account_name in self.failed_accounts
                if not is_pending and not is_failed:
                    missing.append((account_name, account_type))
        
        return missing
    
    def generate_account_create_request(self, account_name: str, account_type: str = "Bank") -> Optional[str]:
        """
        Generate qbXML to create an account.
        
        Args:
            account_name: Name of account to create
            account_type: Type of account (Bank, Income, etc.)
            
        Returns:
            qbXML string for AccountAdd request, or None if account creation should be skipped
        """
        # Skip if already failed
        if account_name in self.failed_accounts:
            logger.warning(f"Skipping account creation for '{account_name}' - previous attempt failed")
            return None
        
        # Generate request ID
        request_id = f"account-add-{account_name}-{id(self)}"  # Include object ID for uniqueness
        
        # Mark as pending (map request_id to account_name)
        self.pending_accounts[request_id] = account_name
        
        # Generate account creation request
        description = f"Auto-created by Sync Accounting for transaction sync"
        return QBXMLService.generate_account_add(
            account_name=account_name,
            account_type=account_type,
            description=description,
            request_id=request_id
        )
    
    # ========================================================================
    # Customer Management Methods
    # ========================================================================
    
    def update_from_customer_query_response(self, response_xml: str) -> None:
        """
        Update known customers from CustomerQuery response.
        Also marks query as completed, even if no customers were found.
        
        Args:
            response_xml: qbXML response from CustomerQuery
        """
        try:
            root = ET.fromstring(response_xml)
            
            # Check if this is a CustomerQueryRs response (regardless of results)
            customer_query_rs = root.find('.//CustomerQueryRs')
            if customer_query_rs is not None:
                # Query completed - mark as done (even if empty result)
                self.customer_query_completed = True
                logger.info("CustomerQuery completed (query finished, may have 0 results)")
            
            customer_ret_list = root.findall('.//CustomerRet')
            
            for customer in customer_ret_list:
                name_elem = customer.find('Name')
                if name_elem is not None:
                    customer_name = name_elem.text
                    self.known_customers.add(customer_name)
                    logger.info(f"Known customer: '{customer_name}'")
            
            logger.info(f"Updated customer cache: {len(self.known_customers)} customers known")
        except Exception as e:
            logger.error(f"Error parsing customer query response: {e}", exc_info=True)
    
    def customer_exists(self, customer_name: str) -> bool:
        """Check if a customer exists in QuickBooks."""
        return customer_name in self.known_customers
    
    def generate_customer_query_request(self) -> str:
        """Generate CustomerQuery request to populate customer cache."""
        return QBXMLService.generate_customer_query(request_id="1")
    
    def generate_customer_create_request(self, customer_name: str) -> Optional[str]:
        """
        Generate qbXML to create a customer.
        
        Args:
            customer_name: Name of customer to create
            
        Returns:
            qbXML string for CustomerAdd request, or None if creation should be skipped
        """
        if customer_name in self.failed_customers:
            logger.warning(f"Skipping customer creation for '{customer_name}' - previous attempt failed")
            return None
        
        request_id = f"customer-add-{customer_name}-{id(self)}"
        self.pending_customers[request_id] = customer_name
        
        return QBXMLService.generate_customer_add(
            customer_name=customer_name,
            request_id=request_id
        )
    
    def update_from_customer_add_response(self, response_xml: str, request_id: Optional[str] = None) -> bool:
        """
        Update customer cache after creating a customer.
        
        Args:
            response_xml: qbXML response from CustomerAdd
            request_id: Request ID used to create the customer
            
        Returns:
            True if customer was successfully created, False otherwise
        """
        customer_name = None
        if request_id and request_id in self.pending_customers:
            customer_name = self.pending_customers[request_id]
        elif self.pending_customers:
            customer_name = list(self.pending_customers.values())[0]
            request_id = list(self.pending_customers.keys())[0]
        
        if not customer_name:
            logger.warning("Could not identify which customer was created from response")
            return False
        
        try:
            root = ET.fromstring(response_xml)
            # CRITICAL: statusCode is an ATTRIBUTE on CustomerAddRs, not a child element
            customer_add_rs = root.find('.//CustomerAddRs')
            if customer_add_rs is not None:
                status_code = customer_add_rs.get('statusCode', '')
                status_message = customer_add_rs.get('statusMessage', '')
                
                if status_code == "0":  # Success
                    self.known_customers.add(customer_name)
                    if request_id:
                        self.pending_customers.pop(request_id, None)
                    logger.info(f"✓ Customer '{customer_name}' successfully created")
                    return True
                else:
                    # Check if it's a duplicate (customer already exists)
                    if "already exists" in status_message.lower() or status_code == "3100":
                        self.known_customers.add(customer_name)
                        if request_id:
                            self.pending_customers.pop(request_id, None)
                        logger.info(f"Customer '{customer_name}' already exists")
                        return True
                    else:
                        self.failed_customers.add(customer_name)
                        if request_id:
                            self.pending_customers.pop(request_id, None)
                        logger.error(f"✗ Failed to create customer '{customer_name}': {status_message} (statusCode: {status_code})")
                        return False
            else:
                self.failed_customers.add(customer_name)
                if request_id:
                    self.pending_customers.pop(request_id, None)
                logger.error(f"✗ Failed to create customer '{customer_name}': No CustomerAddRs element in response")
                return False
        except Exception as e:
            logger.error(f"Error parsing customer add response: {e}", exc_info=True)
            self.failed_customers.add(customer_name)
            if request_id:
                self.pending_customers.pop(request_id, None)
            return False
    
    # ========================================================================
    # Item Management Methods
    # ========================================================================
    
    def update_from_item_query_response(self, response_xml: str) -> None:
        """
        Update known items from ItemQuery response.
        Also marks query as completed, even if no items were found.
        
        Args:
            response_xml: qbXML response from ItemQuery
        """
        try:
            root = ET.fromstring(response_xml)
            
            # Check if this is an ItemQueryRs response (regardless of results)
            item_query_rs = root.find('.//ItemQueryRs')
            if item_query_rs is not None:
                # Query completed - mark as done (even if empty result)
                self.item_query_completed = True
                logger.info("ItemQuery completed (query finished, may have 0 results)")
            
            # ItemQuery returns different item types - check all
            item_ret_list = root.findall('.//ItemServiceRet')
            item_ret_list += root.findall('.//ItemNonInventoryRet')
            item_ret_list += root.findall('.//ItemInventoryRet')
            
            for item in item_ret_list:
                name_elem = item.find('Name')
                if name_elem is not None:
                    item_name = name_elem.text
                    self.known_items.add(item_name)
                    logger.info(f"Known item: '{item_name}'")
            
            logger.info(f"Updated item cache: {len(self.known_items)} items known")
        except Exception as e:
            logger.error(f"Error parsing item query response: {e}", exc_info=True)
    
    def item_exists(self, item_name: str) -> bool:
        """Check if an item exists in QuickBooks."""
        return item_name in self.known_items
    
    def generate_item_query_request(self) -> str:
        """Generate ItemQuery request to populate item cache."""
        return QBXMLService.generate_item_query(request_id="1")
    
    def generate_item_create_request(self, item_name: str, account_name: str) -> Optional[str]:
        """
        Generate qbXML to create a non-inventory item.
        
        Args:
            item_name: Name of item to create (e.g., "Sales", "Interest Income")
            account_name: Name of income account this item maps to
            
        Returns:
            qbXML string for ItemNonInventoryAdd request, or None if creation should be skipped
        """
        if item_name in self.failed_items:
            logger.warning(f"Skipping item creation for '{item_name}' - previous attempt failed")
            return None
        
        request_id = f"item-add-{item_name}-{id(self)}"
        self.pending_items[request_id] = item_name
        
        return QBXMLService.generate_item_non_inventory_add(
            item_name=item_name,
            account_name=account_name,
            request_id=request_id
        )
    
    def update_from_item_add_response(self, response_xml: str, request_id: Optional[str] = None) -> bool:
        """
        Update item cache after creating an item.
        
        Args:
            response_xml: qbXML response from ItemNonInventoryAdd
            request_id: Request ID used to create the item
            
        Returns:
            True if item was successfully created, False otherwise
        """
        item_name = None
        if request_id and request_id in self.pending_items:
            item_name = self.pending_items[request_id]
        elif self.pending_items:
            item_name = list(self.pending_items.values())[0]
            request_id = list(self.pending_items.keys())[0]
        
        if not item_name:
            logger.warning("Could not identify which item was created from response")
            return False
        
        try:
            root = ET.fromstring(response_xml)
            # CRITICAL: statusCode is an ATTRIBUTE on ItemNonInventoryAddRs, not a child element
            item_add_rs = root.find('.//ItemNonInventoryAddRs')
            if item_add_rs is not None:
                status_code = item_add_rs.get('statusCode', '')
                status_message = item_add_rs.get('statusMessage', '')
                
                if status_code == "0":  # Success
                    self.known_items.add(item_name)
                    if request_id:
                        self.pending_items.pop(request_id, None)
                    logger.info(f"✓ Item '{item_name}' successfully created")
                    return True
                else:
                    # Check if it's a duplicate (item already exists)
                    if "already exists" in status_message.lower() or status_code == "3100":
                        self.known_items.add(item_name)
                        if request_id:
                            self.pending_items.pop(request_id, None)
                        logger.info(f"Item '{item_name}' already exists")
                        return True
                    else:
                        self.failed_items.add(item_name)
                        if request_id:
                            self.pending_items.pop(request_id, None)
                        logger.error(f"✗ Failed to create item '{item_name}': {status_message} (statusCode: {status_code})")
                        return False
            else:
                self.failed_items.add(item_name)
                if request_id:
                    self.pending_items.pop(request_id, None)
                logger.error(f"✗ Failed to create item '{item_name}': No ItemNonInventoryAddRs element in response")
                return False
        except Exception as e:
            logger.error(f"Error parsing item add response: {e}", exc_info=True)
            self.failed_items.add(item_name)
            if request_id:
                self.pending_items.pop(request_id, None)
            return False
    
    def get_required_customer_for_deposit(self) -> str:
        """Get the required customer name for deposit transactions (SalesReceiptAddRq)."""
        return "Bank Deposits"
    
    def get_required_items_for_deposit(self, transaction: Dict) -> List[str]:
        """
        Get list of item names required for a deposit transaction.
        
        CRITICAL: Items are NOT Accounts!
        - "Sales" is an Account, NOT an Item
        - "Interest Income" is an Account, NOT an Item
        - We use Item names: "Bank Deposits" (maps to Sales account) and "Bank Interest" (maps to Interest Income account)
        
        Args:
            transaction: Transaction dictionary
            
        Returns:
            List of item names needed (e.g., ["Bank Deposits"] or ["Bank Interest"])
        """
        description = transaction.get('description', transaction.get('memo', '')).lower()
        is_interest = (
            'interest' in description or
            'int income' in description or
            'bank interest' in description
        )
        
        if is_interest:
            return ['Bank Interest']  # Item name (maps to Interest Income account)
        else:
            return ['Bank Deposits']  # Item name (maps to Sales account)
    
    # ========================================================================
    # Vendor Management Methods
    # ========================================================================
    
    def update_from_vendor_query_response(self, response_xml: str) -> None:
        """
        Update known vendors from VendorQuery response.
        Also marks query as completed, even if no vendors were found.
        
        Args:
            response_xml: qbXML response from VendorQuery
        """
        try:
            root = ET.fromstring(response_xml)
            
            # Check if this is a VendorQueryRs response (regardless of results)
            vendor_query_rs = root.find('.//VendorQueryRs')
            if vendor_query_rs is not None:
                # Query completed - mark as done (even if empty result)
                self.vendor_query_completed = True
                logger.info("VendorQuery completed (query finished, may have 0 results)")
            
            # Parse vendor names from response
            vendor_ret_list = root.findall('.//VendorRet')
            for vendor in vendor_ret_list:
                name_elem = vendor.find('Name')
                if name_elem is not None:
                    vendor_name = name_elem.text
                    self.known_vendors.add(vendor_name)
                    logger.info(f"Known vendor: '{vendor_name}'")
            
            logger.info(f"Updated vendor cache: {len(self.known_vendors)} vendors known")
        except Exception as e:
            logger.error(f"Error parsing vendor query response: {e}", exc_info=True)
    
    def vendor_exists(self, vendor_name: str) -> bool:
        """Check if a vendor exists in QuickBooks."""
        return vendor_name in self.known_vendors
    
    def generate_vendor_query_request(self) -> str:
        """Generate VendorQuery request to populate vendor cache."""
        return QBXMLService.generate_vendor_query(request_id="1")
    
    def generate_vendor_create_request(self, vendor_name: str) -> Optional[str]:
        """
        Generate qbXML to create a vendor.
        
        Args:
            vendor_name: Name of vendor to create (e.g., "Bank Charges")
            
        Returns:
            qbXML string for VendorAdd request, or None if creation should be skipped
        """
        if vendor_name in self.failed_vendors:
            logger.warning(f"Skipping vendor creation for '{vendor_name}' - previous attempt failed")
            return None
        
        request_id = f"vendor-add-{vendor_name}-{id(self)}"
        self.pending_vendors[request_id] = vendor_name
        
        return QBXMLService.generate_vendor_add(
            vendor_name=vendor_name,
            request_id=request_id
        )
    
    def update_from_vendor_add_response(self, response_xml: str, request_id: Optional[str] = None) -> bool:
        """
        Update vendor cache after creating a vendor.
        
        Args:
            response_xml: qbXML response from VendorAdd
            request_id: Request ID used to create the vendor
            
        Returns:
            True if vendor was successfully created, False otherwise
        """
        vendor_name = None
        if request_id and request_id in self.pending_vendors:
            vendor_name = self.pending_vendors[request_id]
        elif self.pending_vendors:
            vendor_name = list(self.pending_vendors.values())[0]
            request_id = list(self.pending_vendors.keys())[0]
        
        if not vendor_name:
            logger.warning("Could not identify which vendor was created from response")
            return False
        
        try:
            root = ET.fromstring(response_xml)
            # CRITICAL: statusCode is an ATTRIBUTE on VendorAddRs, not a child element
            vendor_add_rs = root.find('.//VendorAddRs')
            if vendor_add_rs is not None:
                status_code = vendor_add_rs.get('statusCode', '')
                status_message = vendor_add_rs.get('statusMessage', '')
                
                if status_code == "0":  # Success
                    self.known_vendors.add(vendor_name)
                    if request_id:
                        self.pending_vendors.pop(request_id, None)
                    logger.info(f"✓ Vendor '{vendor_name}' successfully created")
                    return True
                else:
                    # Check if it's a duplicate (vendor already exists)
                    if "already exists" in status_message.lower() or status_code == "3100":
                        self.known_vendors.add(vendor_name)
                        if request_id:
                            self.pending_vendors.pop(request_id, None)
                        logger.info(f"Vendor '{vendor_name}' already exists")
                        return True
                    else:
                        self.failed_vendors.add(vendor_name)
                        if request_id:
                            self.pending_vendors.pop(request_id, None)
                        logger.error(f"✗ Failed to create vendor '{vendor_name}': {status_message} (statusCode: {status_code})")
                        return False
            else:
                self.failed_vendors.add(vendor_name)
                if request_id:
                    self.pending_vendors.pop(request_id, None)
                logger.error(f"✗ Failed to create vendor '{vendor_name}': No VendorAddRs element in response")
                return False
        except Exception as e:
            logger.error(f"Error parsing vendor add response: {e}", exc_info=True)
            self.failed_vendors.add(vendor_name)
            if request_id:
                self.pending_vendors.pop(request_id, None)
            return False
    
    def get_required_vendor_for_check(self) -> str:
        """Get the required vendor name for check transactions (CheckAddRq)."""
        return "Bank Charges"
    
    def is_setup_complete_for_deposits(self) -> bool:
        """
        Check if setup is complete for processing DEPOSIT transactions.
        
        Setup is complete when:
        - AccountQuery has been run (account manager initialized)
        - CustomerQuery has been completed (even if empty result)
        - ItemQuery has been completed (even if empty result)
        - Required customer ("Bank Deposits") exists or was just created
        - Required items ("Sales", "Interest Income") exist or were just created
        
        Returns:
            True if setup is complete and ready to process deposits, False otherwise
        """
        # AccountQuery must be complete
        if not self.is_initialized():
            return False
        
        # CustomerQuery must be complete
        if not self.customer_query_completed:
            return False
        
        # ItemQuery must be complete
        if not self.item_query_completed:
            return False
        
        # Required customer must exist (or be pending/just created)
        required_customer = self.get_required_customer_for_deposit()
        if not self.customer_exists(required_customer):
            # Check if it's pending creation (might have been created but response not yet processed)
            is_pending = required_customer in self.pending_customers.values()
            is_failed = required_customer in self.failed_customers
            if not is_pending and not is_failed:
                # Not in cache, not pending, not failed = needs to be created
                return False
        
        # CRITICAL: Check for SPECIFIC required items, not just "any items exist"
        # Required items: "Bank Deposits" and "Bank Interest"
        # These are Item names (NOT Account names) that map to income accounts
        required_items = {'Bank Deposits', 'Bank Interest'}
        
        for required_item in required_items:
            # Item must exist (known), be pending (in creation), or have failed (which blocks setup)
            if required_item not in self.known_items:
                is_pending = required_item in self.pending_items.values()
                is_failed = required_item in self.failed_items
                
                if is_failed:
                    # Item creation failed - setup is NOT complete
                    logger.warning(f"Required item '{required_item}' failed creation - setup not complete for deposits")
                    return False
                
                if not is_pending:
                    # Item doesn't exist, not pending, not failed = needs to be created
                    logger.info(f"Required item '{required_item}' not found - setup not complete for deposits")
                    return False
        
        # All required items exist or are pending successfully
        return True


# Global account manager instance (per workspace/session)
_account_managers: Dict[int, QBAccountManager] = {}


def get_account_manager(workspace_id: int) -> QBAccountManager:
    """
    Get or create account manager for a workspace.
    
    Args:
        workspace_id: Workspace ID
        
    Returns:
        QBAccountManager instance for this workspace
    """
    if workspace_id not in _account_managers:
        _account_managers[workspace_id] = QBAccountManager()
    return _account_managers[workspace_id]

