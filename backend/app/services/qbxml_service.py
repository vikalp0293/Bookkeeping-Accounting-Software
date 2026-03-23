"""
QuickBooks qbXML Generation Service
Generates qbXML requests for syncing transactions to QuickBooks Desktop
"""

import xml.etree.ElementTree as ET
from xml.dom import minidom
from xml.sax.saxutils import escape as xml_escape
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import html
import re

logger = logging.getLogger(__name__)

# QuickBooks entity name (Vendor/Customer) max length
QB_ENTITY_NAME_MAX_LEN = 41
QB_ENTITY_NAME_BAD_CHARS = re.compile(r'[\\:|*?"<>\[\]]')


def _sanitize_entity_name(name: str, fallback: str = "Unknown") -> str:
    """Sanitize name for QuickBooks Vendor/Customer (strip, remove bad chars, truncate)."""
    if not name or not str(name).strip():
        return fallback
    s = str(name).strip()
    s = QB_ENTITY_NAME_BAD_CHARS.sub(' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:QB_ENTITY_NAME_MAX_LEN] if s else fallback


def _xml_safe(s: str) -> str:
    """Escape dynamic text for XML so QB parser never sees raw & < > \" ' (avoids truncation/parse errors)."""
    if not s:
        return ''
    return xml_escape(str(s), {"'": "&apos;", '"': "&quot;"})


class QBXMLService:
    """Service for generating qbXML requests for QuickBooks Desktop"""
    
    QBXML_VERSION = "13.0"  # QB 2018 uses qbXML 13.0
    # CRITICAL: QuickBooks Desktop REQUIRES qbXML sent TO QuickBooks to start with BOTH:
    # 1. XML declaration: <?xml version="1.0"?>
    # 2. qbXML processing instruction: <?qbxml version="13.0"?>
    #
    # CORRECT format (REQUIRED):
    #   <?xml version="1.0"?><?qbxml version="13.0"?><QBXML>...
    
    @staticmethod
    def generate_customer_add(customer_name: str, request_id: str = "1") -> str:
        """
        Generate qbXML to create a new customer in QuickBooks.
        
        Args:
            customer_name: Name of the customer to create
            request_id: Unique request ID
            
        Returns:
            qbXML string for CustomerAdd request
        """
        qbxml = ET.Element('QBXML')
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'stopOnError')
        
        # Add CustomerAdd request
        customer_add_rq = ET.SubElement(msgs_rq, 'CustomerAddRq')
        customer_add_rq.set('requestID', request_id)
        
        customer_add = ET.SubElement(customer_add_rq, 'CustomerAdd')
        ET.SubElement(customer_add, 'Name').text = customer_name
        
        # Convert to string
        xml_str = ET.tostring(qbxml, encoding='unicode', xml_declaration=False)
        # CRITICAL: QuickBooks Desktop XML declaration rules for Add/Mod requests:
        # - Add/Mod requests (CustomerAddRq, ItemNonInventoryAddRq, AccountAddRq): XML declaration is REJECTED (causes 0x80040400)
        # - Only queries (AccountQueryRq, CustomerQueryRq, etc.): XML declaration is allowed
        # Therefore, Add/Mod requests must start with <?qbxml> ONLY, no XML declaration
        qbxml_declaration = f'<?qbxml version="{QBXMLService.QBXML_VERSION}"?>'
        result = f'{qbxml_declaration}{xml_str}'
        return result
    
    @staticmethod
    def generate_vendor_add(vendor_name: str, request_id: str = "1") -> str:
        """
        Generate qbXML to create a new vendor in QuickBooks.
        
        Args:
            vendor_name: Name of the vendor to create
            request_id: Unique request ID
            
        Returns:
            qbXML string for VendorAdd request
        """
        qbxml = ET.Element('QBXML')
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'stopOnError')
        
        # Add VendorAdd request
        vendor_add_rq = ET.SubElement(msgs_rq, 'VendorAddRq')
        vendor_add_rq.set('requestID', request_id)
        
        vendor_add = ET.SubElement(vendor_add_rq, 'VendorAdd')
        ET.SubElement(vendor_add, 'Name').text = vendor_name
        
        # Convert to string
        xml_str = ET.tostring(qbxml, encoding='unicode', xml_declaration=False)
        # CRITICAL: QuickBooks Desktop XML declaration rules for Add/Mod requests:
        # - Add/Mod requests (VendorAddRq, CustomerAddRq, ItemNonInventoryAddRq, AccountAddRq): XML declaration is REJECTED (causes 0x80040400)
        # - Only queries (AccountQueryRq, CustomerQueryRq, etc.): XML declaration is allowed
        # Therefore, Add/Mod requests must start with <?qbxml> ONLY, no XML declaration
        qbxml_declaration = f'<?qbxml version="{QBXMLService.QBXML_VERSION}"?>'
        result = f'{qbxml_declaration}{xml_str}'
        return result
    
    @staticmethod
    def generate_item_non_inventory_add(item_name: str, account_name: str, request_id: str = "1") -> str:
        """
        Generate qbXML to create a new non-inventory item in QuickBooks.
        Non-inventory items are used for services or items that map to income accounts.
        
        CRITICAL: QuickBooks Desktop REQUIRES either <SalesPrice> or <PurchaseCost> in SalesOrPurchase.
        Missing this causes schema-level parser error → 0x80040400.
        We use SalesPrice=0.00 as a safe default for service items.
        
        Args:
            item_name: Name of the item to create (e.g., "Bank Deposits", "Bank Interest")
            account_name: Name of the income account this item maps to (e.g., "Sales", "Interest Income")
            request_id: Unique request ID
            
        Returns:
            qbXML string for ItemNonInventoryAdd request
        """
        qbxml = ET.Element('QBXML')
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'stopOnError')
        
        # Add ItemNonInventoryAdd request
        item_add_rq = ET.SubElement(msgs_rq, 'ItemNonInventoryAddRq')
        item_add_rq.set('requestID', request_id)
        
        item_add = ET.SubElement(item_add_rq, 'ItemNonInventoryAdd')
        ET.SubElement(item_add, 'Name').text = item_name
        
        # SalesOrPurchase - maps the item to an income account
        # CRITICAL: QuickBooks Desktop REQUIRES either <SalesPrice> or <PurchaseCost> in SalesOrPurchase
        # CRITICAL: QuickBooks Desktop ALSO REQUIRES either <SalesDesc> or <Desc> in SalesOrPurchase
        # Missing either causes schema-level parser error → 0x80040400
        # Using SalesPrice=0.00 is a common pattern for service items that map to accounts
        sales_or_purchase = ET.SubElement(item_add, 'SalesOrPurchase')
        # CRITICAL: SalesDesc is REQUIRED - QuickBooks Desktop parser rejects without it
        ET.SubElement(sales_or_purchase, 'SalesDesc').text = item_name
        ET.SubElement(sales_or_purchase, 'SalesPrice').text = '0.00'
        account_ref = ET.SubElement(sales_or_purchase, 'AccountRef')
        ET.SubElement(account_ref, 'FullName').text = account_name
        
        # Convert to string
        xml_str = ET.tostring(qbxml, encoding='unicode', xml_declaration=False)
        
        # CRITICAL: Verify XML is complete (not truncated)
        # ElementTree should always produce complete XML, but log for debugging
        if not xml_str or not xml_str.strip():
            logger.error(f"ItemNonInventoryAdd XML generation produced empty string for item '{item_name}'")
            raise ValueError(f"ItemNonInventoryAdd XML generation failed for item '{item_name}'")
        
        # Verify all required elements are present (sanity check)
        required_elements = ['<AccountRef>', '<SalesPrice>', '<SalesDesc>', '<Name>', '<ItemNonInventoryAdd>']
        for element in required_elements:
            if element not in xml_str:
                logger.error(f"ItemNonInventoryAdd XML missing required element '{element}' for item '{item_name}'")
                logger.error(f"Generated XML (first 500 chars): {xml_str[:500]}")
                raise ValueError(f"ItemNonInventoryAdd XML missing required element '{element}' for item '{item_name}'")
        
        # CRITICAL: QuickBooks Desktop XML declaration rules for Add/Mod requests:
        # - Add/Mod requests (CustomerAddRq, ItemNonInventoryAddRq, AccountAddRq): XML declaration is REJECTED (causes 0x80040400)
        # - Only queries (AccountQueryRq, CustomerQueryRq, etc.): XML declaration is allowed
        # Therefore, Add/Mod requests must start with <?qbxml> ONLY, no XML declaration
        qbxml_declaration = f'<?qbxml version="{QBXMLService.QBXML_VERSION}"?>'
        result = f'{qbxml_declaration}{xml_str}'
        
        # Log XML info for debugging (truncated to avoid log spam)
        logger.debug(f"Generated ItemNonInventoryAdd XML for '{item_name}' (length: {len(result)} chars)")
        if len(result) < 200:
            logger.warning(f"ItemNonInventoryAdd XML seems short (length: {len(result)} chars) - full XML: {result}")
        
        return result
    
    @staticmethod
    def generate_account_add(account_name: str, account_type: str = "Bank", description: Optional[str] = None, request_id: str = "1") -> str:
        """
        Generate qbXML to create a new account in QuickBooks.
        
        Args:
            account_name: Name of the account to create
            account_type: Type of account (Bank, Income, Expense, OtherCurrentAsset, etc.)
            description: Optional description for the account
            request_id: Unique request ID
            
        Returns:
            qbXML string for AccountAdd request
        """
        qbxml = ET.Element('QBXML')
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'stopOnError')
        
        # Add AccountAdd request
        account_add_rq = ET.SubElement(msgs_rq, 'AccountAddRq')
        account_add_rq.set('requestID', request_id)
        
        account_add = ET.SubElement(account_add_rq, 'AccountAdd')
        ET.SubElement(account_add, 'Name').text = account_name
        ET.SubElement(account_add, 'AccountType').text = account_type
        
        if description:
            ET.SubElement(account_add, 'Desc').text = description[:4095]  # QB limit
        
        # Convert to string
        xml_str = ET.tostring(qbxml, encoding='unicode', xml_declaration=False)
        # CRITICAL: QuickBooks Desktop XML declaration rules for Add/Mod requests:
        # - Add/Mod requests (CustomerAddRq, ItemNonInventoryAddRq, AccountAddRq): XML declaration is REJECTED (causes 0x80040400)
        # - Only queries (AccountQueryRq, CustomerQueryRq, etc.): XML declaration is allowed
        # Therefore, Add/Mod requests must start with <?qbxml> ONLY, no XML declaration
        qbxml_declaration = f'<?qbxml version="{QBXMLService.QBXML_VERSION}"?>'
        result = f'{qbxml_declaration}{xml_str}'
        return result
    
    @staticmethod
    def generate_host_query(request_id: str = "1") -> str:
        """
        Generate qbXML for HostQuery request (required first step in QBWC handshake).
        QuickBooks Desktop requires this before any business queries.
        
        Args:
            request_id: Unique request ID
            
        Returns:
            qbXML string for HostQuery request
        """
        qbxml = ET.Element('QBXML')
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'stopOnError')
        
        # Add HostQuery request
        host_query_rq = ET.SubElement(msgs_rq, 'HostQueryRq')
        host_query_rq.set('requestID', request_id)
        
        # Convert to string
        xml_str = ET.tostring(qbxml, encoding='unicode', xml_declaration=False)
        # CRITICAL: QuickBooks Desktop REQUIRES both XML declaration and qbXML processing instruction
        xml_decl = '<?xml version="1.0"?>'
        qbxml_declaration = f'<?qbxml version="{QBXMLService.QBXML_VERSION}"?>'
        result = f'{xml_decl}{qbxml_declaration}{xml_str}'
        return result
    
    @staticmethod
    def generate_company_query(request_id: str = "1") -> str:
        """
        Generate qbXML for CompanyQuery request (required second step in QBWC handshake).
        Must be sent after HostQueryRs is received.
        
        Args:
            request_id: Unique request ID
            
        Returns:
            qbXML string for CompanyQuery request
        """
        qbxml = ET.Element('QBXML')
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'stopOnError')
        
        # Add CompanyQuery request
        company_query_rq = ET.SubElement(msgs_rq, 'CompanyQueryRq')
        company_query_rq.set('requestID', request_id)
        
        # Convert to string
        xml_str = ET.tostring(qbxml, encoding='unicode', xml_declaration=False)
        # CRITICAL: QuickBooks Desktop REQUIRES both XML declaration and qbXML processing instruction
        xml_decl = '<?xml version="1.0"?>'
        qbxml_declaration = f'<?qbxml version="{QBXMLService.QBXML_VERSION}"?>'
        result = f'{xml_decl}{qbxml_declaration}{xml_str}'
        return result
    
    @staticmethod
    def generate_customer_query(request_id: str = "1") -> str:
        """
        Generate qbXML for CustomerQuery request to get list of customers.
        
        Args:
            request_id: Unique request ID
            
        Returns:
            qbXML string for CustomerQuery request
        """
        qbxml = ET.Element('QBXML')
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'stopOnError')
        
        customer_query_rq = ET.SubElement(msgs_rq, 'CustomerQueryRq')
        customer_query_rq.set('requestID', request_id)
        # Request only Name to minimize response size
        ET.SubElement(customer_query_rq, 'IncludeRetElement').text = 'Name'
        
        # Convert to string
        xml_str = ET.tostring(qbxml, encoding='unicode', xml_declaration=False)
        xml_str = QBXMLService._convert_self_closing_to_explicit(xml_str)
        # CRITICAL: QuickBooks Desktop REQUIRES both XML declaration and qbXML processing instruction
        xml_decl = '<?xml version="1.0"?>'
        qbxml_declaration = f'<?qbxml version="{QBXMLService.QBXML_VERSION}"?>'
        result = f'{xml_decl}{qbxml_declaration}{xml_str}'
        return result
    
    @staticmethod
    def generate_vendor_query(request_id: str = "1") -> str:
        """
        Generate qbXML for VendorQuery request to get list of vendors.
        
        Args:
            request_id: Unique request ID
            
        Returns:
            qbXML string for VendorQuery request
        """
        qbxml = ET.Element('QBXML')
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'stopOnError')
        
        vendor_query_rq = ET.SubElement(msgs_rq, 'VendorQueryRq')
        vendor_query_rq.set('requestID', request_id)
        # Request only Name to minimize response size
        ET.SubElement(vendor_query_rq, 'IncludeRetElement').text = 'Name'
        
        # Convert to string
        xml_str = ET.tostring(qbxml, encoding='unicode', xml_declaration=False)
        xml_str = QBXMLService._convert_self_closing_to_explicit(xml_str)
        # CRITICAL: QuickBooks Desktop REQUIRES both XML declaration and qbXML processing instruction
        xml_decl = '<?xml version="1.0"?>'
        qbxml_declaration = f'<?qbxml version="{QBXMLService.QBXML_VERSION}"?>'
        result = f'{xml_decl}{qbxml_declaration}{xml_str}'
        return result
    
    @staticmethod
    def generate_item_query(request_id: str = "1") -> str:
        """
        Generate qbXML for ItemQuery request to get list of items.
        
        Args:
            request_id: Unique request ID
            
        Returns:
            qbXML string for ItemQuery request
        """
        qbxml = ET.Element('QBXML')
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'stopOnError')
        
        item_query_rq = ET.SubElement(msgs_rq, 'ItemQueryRq')
        item_query_rq.set('requestID', request_id)
        # Request only Name to minimize response size
        ET.SubElement(item_query_rq, 'IncludeRetElement').text = 'Name'
        
        # Convert to string
        xml_str = ET.tostring(qbxml, encoding='unicode', xml_declaration=False)
        xml_str = QBXMLService._convert_self_closing_to_explicit(xml_str)
        # CRITICAL: QuickBooks Desktop REQUIRES both XML declaration and qbXML processing instruction
        xml_decl = '<?xml version="1.0"?>'
        qbxml_declaration = f'<?qbxml version="{QBXMLService.QBXML_VERSION}"?>'
        result = f'{xml_decl}{qbxml_declaration}{xml_str}'
        return result
    
    @staticmethod
    def generate_account_query(request_id: str = "1", account_type: Optional[str] = None) -> str:
        """
        Generate qbXML query to get list of accounts from QuickBooks.
        This can be used to verify account names exist and get exact names.
        
        Args:
            request_id: Unique request ID
            account_type: Optional filter for account type (e.g., "Bank", "Income", "Expense")
            
        Returns:
            qbXML string for AccountQuery request
        """
        qbxml = ET.Element('QBXML')
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'stopOnError')
        
        # Add AccountQuery request
        account_query_rq = ET.SubElement(msgs_rq, 'AccountQueryRq')
        account_query_rq.set('requestID', request_id)
        
        # CRITICAL: QuickBooks Desktop may reject empty AccountQueryRq elements (0x80040400 error)
        # Add IncludeRetElement to make the element non-empty and specify which fields to return
        # We need Name and AccountType for account resolution
        ET.SubElement(account_query_rq, 'IncludeRetElement').text = 'Name'
        ET.SubElement(account_query_rq, 'IncludeRetElement').text = 'AccountType'
        
        # If account_type is specified, filter by type
        # Common types: Bank, Income, Expense, OtherCurrentAsset (for Undeposited Funds)
        if account_type:
            account_type_filter = ET.SubElement(account_query_rq, 'AccountTypeFilter')
            ET.SubElement(account_type_filter, 'AccountType').text = account_type
        
        # Convert to string
        xml_str = ET.tostring(qbxml, encoding='unicode', xml_declaration=False)
        # CRITICAL: All qbXML request (*Rq) elements MUST be rendered with explicit open and close tags.
        xml_str = QBXMLService._convert_self_closing_to_explicit(xml_str)
        # CRITICAL: QuickBooks Desktop REQUIRES both XML declaration and qbXML processing instruction
        xml_decl = '<?xml version="1.0"?>'
        qbxml_declaration = f'<?qbxml version="{QBXMLService.QBXML_VERSION}"?>'
        result = f'{xml_decl}{qbxml_declaration}{xml_str}'
        return result
    
    @staticmethod
    def generate_qbxml_for_single_transaction(
        transaction: Dict[str, Any],
        request_id: str = "1",
        account_manager = None,
        workspace_account_name: Optional[str] = None
    ) -> str:
        """
        Generate qbXML request for a SINGLE transaction.
        
        Note: QuickBooks Desktop supports multiple requests per QBXMLMsgsRq,
        but Web Connector best practice is to send one transaction per request
        for better error handling and transaction tracking.
        This method generates qbXML for exactly ONE transaction.
        
        Args:
            transaction: Single transaction dictionary
            request_id: Unique request ID for this transaction
            account_manager: Optional QBAccountManager instance for account resolution
            
        Returns:
            qbXML string ready to send to QuickBooks (ONE transaction only)
        """
        # Create root QBXML element
        # Note: The version is specified in the <?qbxml version="13.0"?> processing instruction,
        # NOT as an attribute on the QBXML element
        qbxml = ET.Element('QBXML')
        
        # Create QBXMLMsgsRq element
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        # continueOnError so VendorAdd/CustomerAdd "already in use" does not fail the batch (per sample)
        msgs_rq.set('onError', 'continueOnError')
        
        # Add the single transaction
        trans_type = transaction.get('transaction_type', '').upper()
        
        if trans_type in ['WITHDRAWAL', 'CHECK', 'FEE']:
            QBXMLService._add_check_transaction(msgs_rq, transaction, request_id, account_manager, workspace_account_name)
        elif trans_type == 'DEPOSIT':
            # Use Pattern B: Direct DepositAdd with AccountRef (no SalesReceiptAdd, no Undeposited Funds)
            # This avoids relationship/linking issues and works as standalone transactions
            # Interest deposits use "Interest Income" account, regular deposits use "Sales" account
            QBXMLService._add_direct_deposit_transaction(msgs_rq, transaction, request_id, account_manager, workspace_account_name)
        else:
            logger.warning(f"Unknown transaction type: {trans_type}, cannot generate qbXML")
            raise ValueError(f"Unknown transaction type: {trans_type}")
        
        # Convert to ASCII bytes (QuickBooks Desktop 2018 requires ASCII, not Unicode)
        xml_bytes = ET.tostring(qbxml, encoding='ascii', xml_declaration=False)
        # Decode to string for processing
        xml_str = xml_bytes.decode('ascii')
        # CRITICAL: All qbXML request (*Rq) elements MUST be rendered with explicit open and close tags.
        # Self-closing request tags cause 0x80040400 errors in QuickBooks Desktop.
        xml_before_conversion = xml_str
        xml_str = QBXMLService._convert_self_closing_to_explicit(xml_str)
        
        # Debug logging: Check if conversion changed anything
        if xml_before_conversion != xml_str:
            import re
            pattern = r'<(\w+)([^/>]*?)\s*/>'
            before_matches = re.findall(pattern, xml_before_conversion)
            after_matches = re.findall(pattern, xml_str)
            self_closing_before = [m for m in before_matches if not m[0].startswith('?')]
            self_closing_after = [m for m in after_matches if not m[0].startswith('?')]
            if self_closing_before:
                logger.debug(f"Converted {len(self_closing_before)} self-closing tags to explicit in transaction XML")
        
        # CRITICAL: QuickBooks Desktop XML declaration rules:
        # - ALL transactional requests (SalesReceiptAdd, DepositAdd, CheckAdd, etc.) MUST include BOTH:
        #   1. <?xml version="1.0" ?> (with space before ?> per QuickBooks samples)
        #   2. <?qbxml version="13.0"?> (qbxml declaration format)
        # - Without the XML declaration, QuickBooks Desktop's strict MSXML parser throws 0x80040400
        # - This is a QuickBooks Desktop quirk - the parser does not assume XML 1.0
        # CRITICAL: Use ASCII bytes only, no encoding attributes
        # CRITICAL: Match QuickBooks sample XML format exactly - spaces around = in attributes
        xml_declaration = '<?xml version="1.0" ?>'  # Space before ?> per QuickBooks samples
        qbxml_declaration = f'<?qbxml version="{QBXMLService.QBXML_VERSION}"?>'
        
        # Post-process XML to add spaces around = in attributes (matches QuickBooks sample format)
        # QuickBooks samples show: onError = "stopOnError" and requestID = "0"
        # ElementTree generates: onError="stopOnError" (no spaces)
        # This difference can cause 0x80040400 parsing errors
        xml_str = QBXMLService._add_attribute_spacing(xml_str)
        
        # Format XML with proper indentation to match QuickBooks sample XML files
        # Test XML files use 2-space indentation, which may be required by QuickBooks Desktop
        xml_str = QBXMLService._format_xml_with_indentation(xml_str, indent="  ")
        
        # CRITICAL: QuickBooks Desktop requires XML declarations on separate lines
        # Test XML files show: <?xml version="1.0" ?> on one line, then <?qbxml version="13.0"?> on next line
        # This format matches the QuickBooks sample XML files exactly
        result = f'{xml_declaration}\n{qbxml_declaration}\n{xml_str}'
        return result
    
    @staticmethod
    def generate_qbxml_for_transactions(transactions: List[Dict[str, Any]], request_id: str = "1") -> str:
        """
        Generate qbXML request for multiple transactions.
        
        WARNING: QuickBooks Desktop does NOT support batching multiple requests!
        This method should only be used for QuickBooks Online or other compatible systems.
        For QuickBooks Desktop, use generate_qbxml_for_single_transaction() instead.
        
        Args:
            transactions: List of transaction dictionaries
            request_id: Unique request ID for this batch
            
        Returns:
            qbXML string ready to send to QuickBooks
        """
        # Create root QBXML element
        # Note: The version is specified in the <?qbxml version="13.0"?> processing instruction,
        # NOT as an attribute on the QBXML element
        qbxml = ET.Element('QBXML')
        
        # Create QBXMLMsgsRq element
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'stopOnError')
        
        # Add each transaction
        for idx, trans in enumerate(transactions):
            trans_type = trans.get('transaction_type', '').upper()
            
            if trans_type in ['WITHDRAWAL', 'CHECK', 'FEE']:
                QBXMLService._add_check_transaction(msgs_rq, trans, f"{request_id}-{idx}", None)
            elif trans_type == 'DEPOSIT':
                QBXMLService._add_deposit_transaction(msgs_rq, trans, f"{request_id}-{idx}")
            else:
                logger.warning(f"Unknown transaction type: {trans_type}, skipping transaction")
                continue
        
        # Convert to string
        xml_str = ET.tostring(qbxml, encoding='unicode', xml_declaration=False)
        # CRITICAL: QuickBooks Desktop REQUIRES both XML declaration and qbXML processing instruction
        xml_decl = '<?xml version="1.0"?>'
        qbxml_declaration = f'<?qbxml version="{QBXMLService.QBXML_VERSION}"?>'
        result = f'{xml_decl}{qbxml_declaration}{xml_str}'
        return result
    
    @staticmethod
    def _add_attribute_spacing(xml_str: str) -> str:
        """
        Add spaces around = in XML attributes to match QuickBooks sample format.
        
        QuickBooks Desktop sample XML files show attributes with spaces:
        - onError = "stopOnError" (not onError="stopOnError")
        - requestID = "0" (not requestID="0")
        
        ElementTree generates attributes without spaces, which can cause
        0x80040400 parsing errors in QuickBooks Desktop 2018.
        
        Args:
            xml_str: XML string from ElementTree
            
        Returns:
            XML string with spaces around = in attributes
        """
        import re
        # Pattern to match attribute="value" or attribute='value' within tag attributes
        # Match: <tag attr="value"> or <tag attr='value' />
        # Replace: <tag attr = "value"> or <tag attr = 'value' />
        def add_spaces_to_attributes(match):
            tag_content = match.group(1)  # Content between < and >
            # Pattern to match attribute="value" or attribute='value'
            attr_pattern = r'(\w+)=("|\')([^"\']*)("|\')'
            
            def add_spaces(attr_match):
                attr_name = attr_match.group(1)
                quote1 = attr_match.group(2)
                value = attr_match.group(3)
                quote2 = attr_match.group(4)
                return f'{attr_name} = {quote1}{value}{quote2}'
            
            # Replace all attribute=value patterns with attribute = value
            modified_content = re.sub(attr_pattern, add_spaces, tag_content)
            return f'<{modified_content}>'
        
        # Match tags: <tag attributes> or <tag attributes />
        # Process only the attributes part, not the tag name or content
        result = re.sub(r'<([^>]+)>', add_spaces_to_attributes, xml_str)
        
        return result
    
    @staticmethod
    def _format_xml_with_indentation(xml_str: str, indent: str = "  ") -> str:
        """
        Format XML string with proper indentation to match QuickBooks sample XML files.
        
        QuickBooks Desktop sample XML files use 2-space indentation. ElementTree's
        tostring() outputs everything on one line, which may cause parsing issues.
        
        Args:
            xml_str: XML string (without declarations, already has attribute spacing)
            indent: Indentation string (default: 2 spaces)
            
        Returns:
            Formatted XML string with proper indentation
        """
        try:
            # Parse the XML string (attribute spacing is already applied)
            root = ET.fromstring(xml_str)
            
            # Recursively format XML element with indentation
            def format_element(elem, level=0):
                """Recursively format XML element with indentation."""
                indent_str = indent * level
                next_indent = indent * (level + 1)
                
                # Build start tag - preserve attribute spacing from input
                # We need to reconstruct the tag with attributes as they appear in xml_str
                # For simplicity, we'll format attributes with spacing
                tag_name = elem.tag
                if elem.attrib:
                    # Format attributes with spacing (already applied, but we format them)
                    attrs = ' '.join([f'{k} = "{v}"' for k, v in elem.attrib.items()])
                    start_tag = f'{indent_str}<{tag_name} {attrs}>'
                else:
                    start_tag = f'{indent_str}<{tag_name}>'
                
                # Handle text content and children
                if len(elem) == 0:
                    # Leaf element - text must be on same line as tags (QuickBooks requirement)
                    if elem.text and elem.text.strip():
                        return f'{start_tag}{elem.text.strip()}</{tag_name}>'
                    else:
                        return f'{start_tag}</{tag_name}>'
                
                # Has children
                parts = [start_tag]
                
                for child in elem:
                    parts.append(format_element(child, level + 1))
                
                parts.append(f'{indent_str}</{tag_name}>')
                return '\n'.join(parts)
            
            formatted = format_element(root, level=0)
            return formatted
        except ET.ParseError as e:
            logger.warning(f"Failed to format XML with indentation: {e}. Returning original XML.")
            return xml_str
    
    @staticmethod
    def _convert_self_closing_to_explicit(xml_str: str) -> str:
        """
        Convert self-closing tags to explicit open/close tags.
        QuickBooks Desktop REQUIRES all qbXML request (*Rq) elements to use explicit tags.
        Self-closing request tags cause 0x80040400 errors in QuickBooks Desktop.
        
        Args:
            xml_str: XML string that may contain self-closing tags
            
        Returns:
            XML string with self-closing tags converted to explicit tags
        """
        # Pattern to match self-closing tags: <TagName attribute="value" />
        # We need to be careful to only match actual self-closing tags, not processing instructions
        pattern = r'<(\w+)([^/>]*?)\s*/>'
        
        def replace_tag(match):
            tag_name = match.group(1)
            attributes = match.group(2)
            # Skip processing instructions (<?xml, <?qbxml)
            if tag_name.startswith('?'):
                return match.group(0)
            return f'<{tag_name}{attributes}></{tag_name}>'
        
        return re.sub(pattern, replace_tag, xml_str)
    
    @staticmethod
    def _validate_qbxml_format(qbxml: str) -> None:
        """
        Validate qbXML format.
        QuickBooks Desktop REQUIRES qbXML to start with both XML declaration and qbXML processing instruction.
        
        Args:
            qbxml: qbXML string to validate
            
        Note:
            This is a placeholder for future validation if needed.
            Currently, all qbXML generation methods ensure correct format.
        """
        # Validation is now handled by ensuring correct format in generation methods
        pass
    
    @staticmethod
    def _add_check_transaction(parent: ET.Element, trans: Dict[str, Any], request_id: str, account_manager = None, workspace_account_name: Optional[str] = None):
        """Add a Check transaction to qbXML. Per sample_check_add_consolidated: VendorAddRq first, then CheckAddRq."""
        payee_name = _sanitize_entity_name(trans.get('payee') or '', 'Bank Charges')
        vendor_add_rq = ET.SubElement(parent, 'VendorAddRq')
        vendor_add_rq.set('requestID', f'{request_id}-vendor')
        vendor_add = ET.SubElement(vendor_add_rq, 'VendorAdd')
        ET.SubElement(vendor_add, 'Name').text = _xml_safe(payee_name)
        logger.debug(f"VendorAddRq for payee: '{payee_name}'")

        check_add_rq = ET.SubElement(parent, 'CheckAddRq')
        check_add_rq.set('requestID', request_id)
        
        check_add = ET.SubElement(check_add_rq, 'CheckAdd')
        
        # Bank Account (the bank account the check is written from)
        # CRITICAL: Use workspace account name if provided (user-specified account)
        # Account names are whitespace-sensitive and case-sensitive
        # NOTE: qbXML 13.0 CheckAdd uses AccountRef (not BankAccountRef) for the bank account
        account_ref = ET.SubElement(check_add, 'AccountRef')
        account_name = None

        # CRITICAL: Always use workspace account name (user-specified)
        # All transactions must go to the same account, regardless of transaction data
        if not workspace_account_name or not workspace_account_name.strip():
            error_msg = "Workspace account name is required but not provided. All transactions must use the workspace account."
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        account_name = workspace_account_name.strip()
        logger.info(f"Using workspace account name for CheckAddRq AccountRef: '{account_name}' (all transactions use this account)")
        
        ET.SubElement(account_ref, 'FullName').text = _xml_safe(account_name)
        logger.debug(f"Check transaction using bank account: '{account_name}'")
        
        # PayeeEntityRef - use payee as Vendor (created above if not in QBD)
        payee_entity_ref = ET.SubElement(check_add, 'PayeeEntityRef')
        ET.SubElement(payee_entity_ref, 'FullName').text = _xml_safe(payee_name)
        logger.debug(f"CheckAdd using PayeeEntityRef: '{payee_name}'")
        
        # Reference number - CRITICAL: QuickBooks REQUIRES at least ONE of:
        # - PayeeEntityRef, OR - RefNumber
        # Element order per working sample: AccountRef, PayeeEntityRef, RefNumber, TxnDate, ExpenseLineAdd
        ref_number = trans.get('reference_number')
        if ref_number:
            queue_id = trans.get('_queue_id', '')
            unique_ref = f"SYNC-{queue_id}-{ref_number}" if queue_id else f"SYNC-{ref_number}"
        else:
            queue_id = trans.get('_queue_id', '')
            unique_ref = f"SYNC-CHECK-{queue_id}" if queue_id else f"SYNC-CHECK-{request_id.replace('trans-', '') if request_id else str(int(datetime.now().timestamp()))}"
        ET.SubElement(check_add, 'RefNumber').text = _xml_safe(unique_ref)
        logger.debug(f"CheckAdd RefNumber: '{unique_ref}'")
        
        # Date (required) - use YYYY-MM-DD for CheckAdd (QB rejects MM/DD/YYYY with statusCode 3020)
        trans_date = QBXMLService._format_date_iso(trans.get('date'))
        if not trans_date:
            logger.warning(f"Transaction missing date, using today's date: {trans}")
            trans_date = datetime.now().strftime('%Y-%m-%d')
        ET.SubElement(check_add, 'TxnDate').text = trans_date
        
        # Amount (always positive for checks)
        # IMPORTANT: qbXML CheckAdd does NOT support a top-level <Amount> node.
        amount = abs(float(trans.get('amount', 0)))
        
        # Get memo text for later use (will be added AFTER ExpenseLineAdd per SDK requirements)
        memo = trans.get('description', trans.get('memo', ''))
        
        # Expense line (required for checks) - MUST come BEFORE Memo per QuickBooks SDK
        # QB requires ExpenseLineAdd AccountRef to be an Expense or CostOfGoodsSold account, NOT Bank.
        # Use payee-mapped account name from transaction if set (e.g. Rent Expense, Utilities); else fall back to Miscellaneous Expense.
        expense_line = ET.SubElement(check_add, 'ExpenseLineAdd')
        
        preferred_account_name = trans.get('expense_account') or 'Miscellaneous Expense'
        expense_account = None
        if account_manager and account_manager.is_initialized():
            expense_account = account_manager.resolve_account(preferred_account_name, 'Expense')
            if not expense_account:
                expense_account = account_manager.get_first_account_of_type('Expense')
            if not expense_account:
                expense_account = account_manager.get_first_account_of_type('CostOfGoodsSold')
            if not expense_account:
                expense_account = account_manager.get_first_account_of_type('Equity')
        if not expense_account:
            raise ValueError(
                "No Expense, CostOfGoodsSold, or Equity account found in QuickBooks. "
                "Add at least one such account (e.g. Miscellaneous Expense) in Chart of Accounts to sync payments."
            )
        logger.info(f"Check expense line AccountRef: '{expense_account}' (WITHDRAWAL → Payment)")
        
        expense_account_ref = ET.SubElement(expense_line, 'AccountRef')
        ET.SubElement(expense_account_ref, 'FullName').text = _xml_safe(expense_account)
        logger.debug(f"Check expense line using account: '{expense_account}'")
        
        # Amount (required, always positive for checks) - MUST come AFTER AccountRef
        ET.SubElement(expense_line, 'Amount').text = f"{amount:.2f}"
        
        if memo:
            memo_safe = _xml_safe(memo[:4095])
            ET.SubElement(expense_line, 'Memo').text = memo_safe
        # CRITICAL: Memo at CheckAdd level MUST come AFTER ExpenseLineAdd per QuickBooks SDK
        if memo:
            ET.SubElement(check_add, 'Memo').text = memo_safe  # QB limit
    
    @staticmethod
    def _add_direct_deposit_transaction(parent: ET.Element, trans: Dict[str, Any], request_id: str, account_manager = None, workspace_account_name: Optional[str] = None):
        """
        Add a Direct Deposit transaction to qbXML (Pattern B - Direct deposit, no relationships).
        
        CRITICAL: This uses DepositAdd with AccountRef directly - no SalesReceiptAdd, no Undeposited Funds.
        This avoids relationship/linking issues and works as standalone transactions.
        
        - Interest deposits use AccountRef = "Interest Income"
        - Regular deposits use AccountRef = "Sales"
        
        CRITICAL REQUIREMENTS (matching web example structure):
        - DepositToAccountRef is REQUIRED - MUST be FIRST element
        - TxnDate is REQUIRED - MUST come AFTER DepositToAccountRef
        - Memo is OPTIONAL - can be added at DepositAdd level (after TxnDate)
        - DepositLineAdd MUST use AccountRef (Income/OtherIncome account, NOT Bank) - MUST come AFTER TxnDate/Memo
        - Element order: DepositToAccountRef → TxnDate → Memo (optional) → DepositLineAdd
        - QuickBooks SDK requires strict element ordering - incorrect order causes 0x80040400 errors
        
        Args:
            parent: Parent XML element (QBXMLMsgsRq)
            trans: Transaction dictionary
            request_id: Unique request ID
            account_manager: Optional QBAccountManager instance for account resolution
            workspace_account_name: Optional workspace account name (user-specified)
        """
        customer_name = _sanitize_entity_name(trans.get('payee') or '', 'Bank Deposits')
        customer_add_rq = ET.SubElement(parent, 'CustomerAddRq')
        customer_add_rq.set('requestID', f'{request_id}-customer')
        customer_add = ET.SubElement(customer_add_rq, 'CustomerAdd')
        ET.SubElement(customer_add, 'Name').text = _xml_safe(customer_name)
        logger.debug(f"CustomerAddRq for payee: '{customer_name}'")

        deposit_add_rq = ET.SubElement(parent, 'DepositAddRq')
        deposit_add_rq.set('requestID', request_id)  # Required for request/response matching
        
        deposit_add = ET.SubElement(deposit_add_rq, 'DepositAdd')
        
        # EXACT STRUCTURE MATCHING sample_deposit_add_consolidated:
        # 1. TxnDate (FIRST)
        # 2. DepositToAccountRef (SECOND)
        # 3. DepositLineAdd (EntityRef, AccountRef, Memo, Amount)
        
        # 1. TxnDate (REQUIRED) - FIRST per sample
        trans_date = QBXMLService._format_date_iso(trans.get('date'))
        if not trans_date:
            logger.warning(f"Transaction missing date, using today's date: {trans}")
            trans_date = datetime.now().strftime('%Y-%m-%d')
        ET.SubElement(deposit_add, 'TxnDate').text = trans_date
        
        # 2. DepositToAccountRef (REQUIRED) - SECOND per sample
        deposit_to_account_ref = ET.SubElement(deposit_add, 'DepositToAccountRef')
        if not workspace_account_name or not workspace_account_name.strip():
            error_msg = "Workspace account name is required but not provided. All transactions must use the workspace account."
            logger.error(error_msg)
            raise ValueError(error_msg)
        account_name = workspace_account_name.strip()
        logger.info(f"Using workspace account name for DepositAdd DepositToAccountRef: '{account_name}' (all transactions use this account)")
        ET.SubElement(deposit_to_account_ref, 'FullName').text = _xml_safe(account_name)
        logger.debug(f"Deposit transaction using DepositToAccountRef: '{account_name}'")
        
        # 4. DepositLineAdd (REQUIRED) - EntityRef (customer), AccountRef, Memo, Amount per sample
        deposit_line = ET.SubElement(deposit_add, 'DepositLineAdd')
        entity_ref = ET.SubElement(deposit_line, 'EntityRef')
        ET.SubElement(entity_ref, 'FullName').text = _xml_safe(customer_name)
        
        # Determine which account to use based on transaction description
        description = trans.get('description', trans.get('memo', '')).lower()
        is_interest = (
            'interest' in description or
            'int income' in description or
            'bank interest' in description
        )
        
        # Account for deposit line - use subaccount notation for interest, "Sales" for regular deposits
        # CRITICAL: Bank accounts cannot be used in DepositLineAdd → AccountRef (causes 0x80040400)
        # Per user's structure: "Other Income: Interest Income" (subaccount notation with colon)
        if is_interest:
            # Use subaccount notation: "Other Income: Interest Income"
            deposit_account = 'Other Income: Interest Income'
            account_type = 'OtherIncome'
        else:
            deposit_account = 'Sales'
            account_type = 'Income'
        
        if account_manager and account_manager.is_initialized():
            resolved_account = account_manager.resolve_account(
                preferred=deposit_account,
                fallback_type=account_type
            )
            if resolved_account:
                deposit_account = resolved_account
                logger.debug(f"Resolved deposit line account: '{deposit_account}'")
            else:
                # IIF-style: use any existing Income/OtherIncome/Equity account; no validation.
                fallback = (
                    account_manager.get_first_account_of_type('Income')
                    or account_manager.get_first_account_of_type('OtherIncome')
                    or account_manager.get_first_account_of_type('Equity')
                )
                if fallback:
                    deposit_account = fallback
                    logger.debug(f"Using first available Income/OtherIncome/Equity account: '{deposit_account}'")
                else:
                    raise ValueError(
                        "No Income, OtherIncome, or Equity account found in QuickBooks. "
                        "Add at least one such account (e.g. Sales or Interest Income) in Chart of Accounts to sync deposits."
                    )
        
        account_ref = ET.SubElement(deposit_line, 'AccountRef')
        ET.SubElement(account_ref, 'FullName').text = _xml_safe(deposit_account)
        logger.info(f"Direct deposit using AccountRef: '{deposit_account}' (DEPOSIT → Deposit)")
        
        # Memo then Amount per sample_deposit_add_consolidated (EntityRef, AccountRef, Memo, Amount)
        line_memo = trans.get('description', trans.get('memo', ''))
        if line_memo:
            ET.SubElement(deposit_line, 'Memo').text = _xml_safe(line_memo[:4095])  # QB limit
        
        amount = abs(float(trans.get('amount', 0)))
        if amount <= 0:
            error_msg = f"Deposit amount must be greater than zero, got: {trans.get('amount', 0)}"
            logger.error(f"Invalid deposit amount: {trans}")
            raise ValueError(error_msg)
        ET.SubElement(deposit_line, 'Amount').text = f"{amount:.2f}"
        
        # Element order per sample: TxnDate → DepositToAccountRef → DepositLineAdd (EntityRef, AccountRef, Memo, Amount)
    
    @staticmethod
    def _add_interest_deposit_transaction(parent: ET.Element, trans: Dict[str, Any], request_id: str, account_manager = None, workspace_account_name: Optional[str] = None):
        """
        Legacy method - redirects to _add_direct_deposit_transaction for backward compatibility.
        """
        logger.debug("_add_interest_deposit_transaction called - redirecting to _add_direct_deposit_transaction")
        QBXMLService._add_direct_deposit_transaction(parent, trans, request_id, account_manager, workspace_account_name)
    
    @staticmethod
    def generate_deposit_add_with_txn_id(
        sales_receipt_txn_id: str,
        sales_receipt_txn_line_id: str,
        amount: float,
        trans_date: str,
        ref_number: Optional[str] = None,
        workspace_account_name: Optional[str] = None,
        request_id: str = "dep-1"
    ) -> str:
        """
        Generate DepositAdd XML (Pattern A, Step 2) using TxnID/TxnLineID/TxnType pattern.
        
        CRITICAL: This is Step 2 of Pattern A - moves money from Undeposited Funds to Bank account.
        Must be called AFTER SalesReceiptAdd succeeds and we have the TxnID and TxnLineID from SalesReceiptAddRs.
        
        CRITICAL REQUIREMENTS:
        - TxnDate is REQUIRED
        - RefNumber MUST NOT be included for Pattern A (TxnID/TxnLineID/TxnType)
          Including RefNumber causes QuickBooks to switch to "manual deposit parsing mode"
          which conflicts with Pattern A structure and causes 0x80040400
        - DepositToAccountRef is REQUIRED - MUST come AFTER TxnDate, BEFORE DepositLineAdd
        - DepositLineAdd MUST use TxnID, TxnLineID, TxnType ONLY (Pattern A - clears existing transaction)
        - CRITICAL: Within DepositLineAdd, element order MUST be: TxnID → TxnLineID → TxnType
          (NOT TxnType → TxnID → TxnLineID - wrong order causes 0x80040400 even with valid XML)
        - TxnLineID MUST be the actual value from SalesReceiptLineRet, NOT -1 (using -1 causes 0x80040400)
        - Amount MUST NOT be included in DepositLineAdd - QB Desktop derives it automatically from SalesReceiptLineRet
        - Including Amount with TxnID/TxnLineID/TxnType violates QB schema and causes 0x80040400
        - Element order: TxnDate → DepositToAccountRef → DepositLineAdd (NO RefNumber for Pattern A)
        - QuickBooks SDK requires strict element ordering - incorrect order causes 0x80040400 errors
        
        Args:
            sales_receipt_txn_id: TxnID from SalesReceiptAddRs response
            sales_receipt_txn_line_id: TxnLineID from SalesReceiptLineRet (CRITICAL: must be actual value, not -1)
            amount: Transaction amount (used for validation/logging only, NOT included in XML)
            trans_date: Transaction date in ISO format (YYYY-MM-DD)
            ref_number: Optional reference number
            workspace_account_name: Workspace account name (bank account to deposit to)
            request_id: Unique request ID
            
        Returns:
            qbXML string for DepositAdd request
        """
        # Create root QBXML element
        qbxml = ET.Element('QBXML')
        
        # Create QBXMLMsgsRq element
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'stopOnError')
        
        deposit_add_rq = ET.SubElement(msgs_rq, 'DepositAddRq')
        deposit_add_rq.set('requestID', request_id)
        
        deposit_add = ET.SubElement(deposit_add_rq, 'DepositAdd')
        
        # TxnDate (required)
        ET.SubElement(deposit_add, 'TxnDate').text = trans_date
        
        # CRITICAL: RefNumber MUST NOT be included for Pattern A (TxnID/TxnLineID/TxnType)
        # Including RefNumber causes QuickBooks Desktop to switch to "manual deposit parsing mode"
        # which conflicts with the Pattern A structure and causes 0x80040400 "error when parsing XML"
        # RefNumber is kept in logs for traceability but NOT sent to QuickBooks
        if ref_number:
            logger.debug(f"DepositAdd RefNumber (for logging only, NOT included in XML): '{ref_number}'")
        
        # DepositToAccountRef (required) - bank account to deposit to
        deposit_to_account_ref = ET.SubElement(deposit_add, 'DepositToAccountRef')
        # CRITICAL: Always use workspace account name (user-specified)
        # All transactions must go to the same account, regardless of transaction data
        if not workspace_account_name or not workspace_account_name.strip():
            error_msg = "Workspace account name is required but not provided. All transactions must use the workspace account."
            logger.error(error_msg)
            raise ValueError(error_msg)
        account_name = workspace_account_name.strip()
        ET.SubElement(deposit_to_account_ref, 'FullName').text = account_name
        logger.info(f"DepositAdd using DepositToAccountRef: '{account_name}' (Pattern A, Step 2)")
        
        # DepositLineAdd (required) - uses TxnType, TxnID, TxnLineID (Pattern A - clears existing transaction)
        # CRITICAL: This pattern references the existing SalesReceipt in Undeposited Funds and clears it
        # TxnLineID MUST be the actual value from SalesReceiptLineRet, NOT -1
        # 
        # IMPORTANT:
        # When clearing Undeposited Funds using TxnType/TxnID/TxnLineID (Pattern A),
        # QuickBooks Desktop derives the amount automatically from the referenced
        # SalesReceiptLineRet.
        #
        # Including <Amount> here violates the QB Desktop schema and causes:
        #   0x80040400 - "error when parsing the provided XML text stream"
        #
        # Therefore, Amount MUST NOT be included in DepositLineAdd for txn-based deposits.
        # The amount parameter is kept for validation/logging purposes only.
        deposit_line = ET.SubElement(deposit_add, 'DepositLineAdd')
        # CRITICAL: QuickBooks Desktop requires EXACT element order within DepositLineAdd:
        # TxnID → TxnLineID → TxnType (NOT TxnType → TxnID → TxnLineID)
        # Wrong order causes 0x80040400 "error when parsing the provided XML text stream"
        # even though the XML is well-formed and all accounts exist.
        ET.SubElement(deposit_line, 'TxnID').text = sales_receipt_txn_id
        ET.SubElement(deposit_line, 'TxnLineID').text = sales_receipt_txn_line_id
        ET.SubElement(deposit_line, 'TxnType').text = 'SalesReceipt'
        # NOTE: Amount is NOT included - QB Desktop derives it from SalesReceiptLineRet automatically
        logger.debug(f"DepositAdd using TxnID/TxnLineID/TxnType pattern (TxnID: '{sales_receipt_txn_id}', TxnLineID: '{sales_receipt_txn_line_id}', Expected Amount: {amount:.2f} - derived automatically by QB)")
        
        # Convert to ASCII bytes
        xml_bytes = ET.tostring(qbxml, encoding='ascii', xml_declaration=False)
        xml_str = xml_bytes.decode('ascii')
        
        # Convert self-closing tags to explicit tags
        xml_str = QBXMLService._convert_self_closing_to_explicit(xml_str)
        
        # CRITICAL: ALL transactional requests MUST include BOTH XML declaration and qbXML declaration
        # QuickBooks Desktop's strict MSXML parser requires <?xml version="1.0"?> for transactional XML
        xml_declaration = '<?xml version="1.0"?>'
        qbxml_declaration = f'<?qbxml version="{QBXMLService.QBXML_VERSION}"?>'
        result = f'{xml_declaration}\n{qbxml_declaration}\n{xml_str}'
        
        return result
    
    # NOTE: _escape_xml_text() was removed - ElementTree handles XML escaping automatically
    # Using it would cause double-escaping issues
    
    @staticmethod
    def _add_sales_receipt_to_undeposited_funds(parent: ET.Element, trans: Dict[str, Any], request_id: str, account_manager = None):
        """
        Add a Sales Receipt transaction to qbXML for regular deposits (Pattern A, Step 1).
        
        CRITICAL: This is Step 1 of Pattern A - creates SalesReceiptAdd to Undeposited Funds.
        Step 2 (DepositAdd with TxnID) will be handled in a follow-up request after we get TxnID from response.
        
        CRITICAL REQUIREMENTS:
        - CustomerRef is REQUIRED (QuickBooks Desktop rejects without it)
        - RefNumber is OPTIONAL but recommended - MUST come AFTER TxnDate, BEFORE DepositToAccountRef
        - DepositToAccountRef MUST be "Undeposited Funds" (REQUIRED when UF is enabled)
        - DepositToAccountRef MUST come AFTER TxnDate and RefNumber, BEFORE SalesReceiptLineAdd
        - SalesReceiptLineAdd must use ItemRef (NOT AccountRef) - MUST come AFTER DepositToAccountRef
        - Element order: CustomerRef → TxnDate → RefNumber → DepositToAccountRef → SalesReceiptLineAdd
        - QuickBooks SDK requires strict element ordering - incorrect order causes 0x80040400 errors
        - NOTE: DepositToAccountRef MUST appear before any SalesReceiptLineAdd elements - this is non-negotiable
        
        Args:
            parent: Parent XML element (QBXMLMsgsRq)
            trans: Transaction dictionary
            request_id: Unique request ID
            account_manager: Optional QBAccountManager instance for account resolution
        """
        sales_receipt_add_rq = ET.SubElement(parent, 'SalesReceiptAddRq')
        sales_receipt_add_rq.set('requestID', request_id)
        
        sales_receipt_add = ET.SubElement(sales_receipt_add_rq, 'SalesReceiptAdd')
        
        # CRITICAL: CustomerRef is REQUIRED - QuickBooks Desktop rejects SalesReceiptAddRq without it
        # Use "Bank Deposits" as the generic customer for all bank statement deposits
        customer_ref = ET.SubElement(sales_receipt_add, 'CustomerRef')
        customer_name = 'Bank Deposits'  # Standard customer name for bank deposits
        ET.SubElement(customer_ref, 'FullName').text = customer_name
        logger.debug(f"SalesReceipt using CustomerRef: '{customer_name}'")
        
        # Date (required) - MUST use ISO format (YYYY-MM-DD) for QuickBooks
        trans_date = QBXMLService._format_date_iso(trans.get('date'))
        if not trans_date:
            logger.warning(f"Transaction missing date, using today's date: {trans}")
            trans_date = datetime.now().strftime('%Y-%m-%d')
        ET.SubElement(sales_receipt_add, 'TxnDate').text = trans_date
        
        # RefNumber (REQUIRED) - MUST come AFTER TxnDate, BEFORE DepositToAccountRef
        # Use unique value to avoid duplicate transaction errors
        # QuickBooks enforces idempotency on RefNumber
        ref_number = trans.get('reference_number')
        if ref_number:
            # Make it unique by prefixing with SYNC- and queue ID if available
            queue_id = trans.get('_queue_id', '')
            if queue_id:
                unique_ref = f"SYNC-{queue_id}-{ref_number}"
            else:
                unique_ref = f"SYNC-{ref_number}"
        else:
            # Generate unique RefNumber from request_id (contains queue_id + timestamp)
            queue_id = trans.get('_queue_id', '')
            if queue_id:
                unique_ref = f"SYNC-SR-{queue_id}"
            else:
                # Fallback: use request_id without "trans-" prefix
                req_id_clean = request_id.replace('trans-', '') if request_id else str(int(datetime.now().timestamp()))
                unique_ref = f"SYNC-SR-{req_id_clean}"
        
        ET.SubElement(sales_receipt_add, 'RefNumber').text = unique_ref
        logger.debug(f"SalesReceipt RefNumber: '{unique_ref}'")
        
        # DepositToAccountRef (REQUIRED) - MUST come AFTER TxnDate and RefNumber, BEFORE SalesReceiptLineAdd per QuickBooks SDK
        # CRITICAL: For Pattern A (Undeposited Funds flow), DepositToAccountRef MUST be "Undeposited Funds"
        # This is Step 1 - the SalesReceipt goes to Undeposited Funds, then DepositAdd (Step 2) moves it to bank
        # Account names are whitespace-sensitive and case-sensitive
        deposit_to_account_ref = ET.SubElement(sales_receipt_add, 'DepositToAccountRef')
        account_name = 'Undeposited Funds'  # REQUIRED for Pattern A when UF is enabled
        
        # Try to resolve exact account name from account manager if available
        if account_manager and account_manager.is_initialized():
            resolved_account = account_manager.resolve_account(
                preferred='Undeposited Funds',
                fallback_type='OtherCurrentAsset'
            )
            if resolved_account:
                account_name = resolved_account
                logger.debug(f"Resolved Undeposited Funds account from account manager: '{account_name}'")
        
        ET.SubElement(deposit_to_account_ref, 'FullName').text = account_name
        logger.info(f"SalesReceipt transaction using DepositToAccountRef: '{account_name}' (Pattern A, Step 1)")
        
        # SalesReceiptLineAdd (REQUIRED) - MUST come AFTER DepositToAccountRef per QuickBooks SDK
        # CRITICAL: Must use ItemRef, NOT AccountRef
        # Items map to accounts - we use "Bank Deposits" or "Bank Interest" items (NOT Account names!)
        sales_receipt_line = ET.SubElement(sales_receipt_add, 'SalesReceiptLineAdd')
        
        # Item mapping: Detect Interest Income vs default to Sales
        # CRITICAL: Items are NOT Accounts! "Sales" is an Account, NOT an Item.
        # We must use Item names like "Bank Deposits" (maps to Sales account) or "Bank Interest" (maps to Interest Income account)
        # Rule: If description contains interest keywords → Bank Interest item, else → Bank Deposits item
        description = trans.get('description', trans.get('memo', '')).lower()
        is_interest = (
            'interest' in description or
            'int income' in description or
            'bank interest' in description
        )
        
        if is_interest:
            # Use "Bank Interest" item (which maps to Interest Income account)
            item_name = 'Bank Interest'
            logger.debug(f"SalesReceipt line ItemRef (Bank Interest → Interest Income account): '{item_name}'")
        else:
            # Default to "Bank Deposits" item (which maps to Sales account)
            item_name = 'Bank Deposits'
            logger.debug(f"SalesReceipt line ItemRef (Bank Deposits → Sales account): '{item_name}'")
        
        # ItemRef (REQUIRED) - MUST come BEFORE Amount
        # CRITICAL: SalesReceiptLineAdd requires ItemRef, NOT AccountRef
        # The Item ("Bank Deposits" or "Bank Interest") maps to the corresponding Income account internally
        item_ref = ET.SubElement(sales_receipt_line, 'ItemRef')
        ET.SubElement(item_ref, 'FullName').text = item_name
        
        # Amount (required, always positive for deposits) - MUST come AFTER ItemRef
        amount = abs(float(trans.get('amount', 0)))
        if amount <= 0:
            error_msg = f"Deposit amount must be greater than zero, got: {trans.get('amount', 0)}"
            logger.error(f"Invalid deposit amount: {trans}")
            raise ValueError(error_msg)
        ET.SubElement(sales_receipt_line, 'Amount').text = f"{amount:.2f}"
        
        # Element order: CustomerRef → TxnDate → RefNumber → DepositToAccountRef → SalesReceiptLineAdd
    
    @staticmethod
    def _format_date(date_str: Optional[str]) -> Optional[str]:
        """
        Convert date string to QuickBooks format (MM/DD/YYYY)
        
        Args:
            date_str: Date in various formats (YYYY-MM-DD, MM/DD/YYYY, etc.)
            
        Returns:
            Date string in MM/DD/YYYY format or None
        """
        if not date_str:
            return None
        
        try:
            # Try parsing different formats
            formats = [
                '%Y-%m-%d',      # 2025-01-15
                '%m/%d/%Y',      # 01/15/2025
                '%m-%d-%Y',      # 01-15-2025
                '%Y/%m/%d',      # 2025/01/15
            ]
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime('%m/%d/%Y')
                except ValueError:
                    continue
            
            logger.warning(f"Could not parse date: {date_str}")
            return None
        except Exception as e:
            logger.error(f"Error formatting date {date_str}: {e}")
            return None
    
    @staticmethod
    def _format_date_qb(date_str: Optional[str]) -> Optional[str]:
        """
        Convert date string to QuickBooks format (MM/DD/YYYY with slashes)
        QuickBooks Desktop requires MM/DD/YYYY format (with slashes, not dashes)
        
        Args:
            date_str: Date in various formats (YYYY-MM-DD, MM/DD/YYYY, MM-DD-YYYY, etc.)
            
        Returns:
            Date string in MM/DD/YYYY format (with slashes) or None
        """
        if not date_str:
            return None
        
        try:
            # Try parsing different formats
            formats = [
                '%Y-%m-%d',      # 2026-01-11
                '%m/%d/%Y',      # 01/11/2026
                '%m-%d-%Y',      # 01-11-2026
                '%Y/%m/%d',      # 2026/01/11
            ]
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime('%m/%d/%Y')  # MM/DD/YYYY with slashes (QB Desktop standard)
                except ValueError:
                    continue
            
            logger.warning(f"Could not parse date: {date_str}")
            return None
        except Exception as e:
            logger.error(f"Error formatting date {date_str}: {e}")
            return None
    
    @staticmethod
    def _format_date_iso(date_str: Optional[str]) -> Optional[str]:
        """
        Convert date string to ISO format (YYYY-MM-DD) for QuickBooks qbXML requests
        
        Args:
            date_str: Date in various formats (YYYY-MM-DD, MM/DD/YYYY, etc.)
            
        Returns:
            Date string in YYYY-MM-DD format or None
        """
        if not date_str:
            return None
        
        try:
            # Try parsing different formats
            formats = [
                '%Y-%m-%d',      # 2025-01-15
                '%m/%d/%Y',      # 01/15/2025
                '%m-%d-%Y',      # 01-15-2025
                '%Y/%m/%d',      # 2025/01/15
            ]
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime('%Y-%m-%d')  # ISO format
                except ValueError:
                    continue
            
            logger.warning(f"Could not parse date: {date_str}")
            return None
        except Exception as e:
            logger.error(f"Error formatting date {date_str}: {e}")
            return None
    
    @staticmethod
    def parse_qbxml_response(response_xml: str) -> Dict[str, Any]:
        """
        Parse qbXML response from QuickBooks
        
        Args:
            response_xml: qbXML response string
            
        Returns:
            Dictionary with parsed response data
        """
        try:
            root = ET.fromstring(response_xml)
            
            # Find status codes
            results = []
            
            # Check for errors
            # QuickBooks Desktop does NOT use namespaces in qbXML responses
            # CRITICAL: Only check TRANSACTION response types (*AddRs) for sync success
            # DO NOT include query responses (*QueryRs) - they should not mark transactions as synced
            # DO NOT include setup operations (AccountAddRs, CustomerAddRs, ItemNonInventoryAddRs) - they are prerequisites, not transactions
            # Query responses (AccountQueryRs, HostQueryRs, CompanyQueryRs) are for handshake/account discovery only
            # Setup operations (AccountAddRs, CustomerAddRs, ItemNonInventoryAddRs) must succeed before transactions can proceed, but don't mark transactions as synced
            status_rs = (
                root.findall('.//CheckAddRs') +
                root.findall('.//DepositAddRs') +
                root.findall('.//SalesReceiptAddRs')
                # Explicitly EXCLUDE:
                # - Query responses: AccountQueryRs, HostQueryRs, CompanyQueryRs, CustomerQueryRs, ItemQueryRs
                # - Setup operations: AccountAddRs, CustomerAddRs, ItemNonInventoryAddRs
                # Only actual transaction responses (CheckAddRs, DepositAddRs, SalesReceiptAddRs) mark transactions as synced
            )
            for rs in status_rs:
                status_code = rs.get('statusCode', '0')
                status_message = rs.get('statusMessage', '')
                request_id = rs.get('requestID', '')
                
                # Extract TxnID and TxnLineID for successful SalesReceiptAddRs (needed for Pattern A, Step 2)
                txn_id = None
                txn_line_id = None
                if rs.tag == 'SalesReceiptAddRs' and status_code == '0':
                    # TxnID is in SalesReceiptRet -> TxnID
                    # TxnLineID is in SalesReceiptRet -> SalesReceiptLineRet -> TxnLineID
                    sales_receipt_ret = rs.find('.//SalesReceiptRet')
                    if sales_receipt_ret is not None:
                        txn_id_elem = sales_receipt_ret.find('TxnID')
                        if txn_id_elem is not None:
                            txn_id = txn_id_elem.text
                            logger.info(f"Extracted TxnID from SalesReceiptAddRs: {txn_id} (requestID: {request_id})")
                        
                        # Extract TxnLineID from SalesReceiptLineRet (CRITICAL: must use actual TxnLineID, not -1)
                        sales_receipt_line_ret = sales_receipt_ret.find('.//SalesReceiptLineRet')
                        if sales_receipt_line_ret is not None:
                            txn_line_id_elem = sales_receipt_line_ret.find('TxnLineID')
                            if txn_line_id_elem is not None:
                                txn_line_id = txn_line_id_elem.text
                                logger.info(f"Extracted TxnLineID from SalesReceiptAddRs: {txn_line_id} (requestID: {request_id})")
                
                # User-friendly remediation for known QB error codes (e.g. 3140 = payee not found)
                remediation = None
                if status_code == '3140' and rs.tag == 'CheckAddRs':
                    remediation = (
                        "Create the vendor 'Bank Charges' in QuickBooks (Vendors → Add Vendor → Name: Bank Charges), "
                        "or run sample_vendor_add.xml in SDK Test Plus 3, then retry."
                    )
                results.append({
                    'requestID': request_id,
                    'statusCode': status_code,
                    'statusMessage': status_message,
                    'success': status_code == '0',
                    'txnID': txn_id,
                    'txnLineID': txn_line_id,  # CRITICAL: Required for DepositAdd Pattern A
                    'responseType': rs.tag,  # 'SalesReceiptAddRs', 'DepositAddRs', 'CheckAddRs'
                    'remediation': remediation,
                })
            
            return {
                'success': all(r['success'] for r in results),
                'results': results
            }
        except Exception as e:
            logger.error(f"Error parsing qbXML response: {e}")
            return {
                'success': False,
                'error': str(e),
                'results': []
            }

