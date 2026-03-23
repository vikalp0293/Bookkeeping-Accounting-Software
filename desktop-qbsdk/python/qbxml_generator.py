"""
QBXML Generator
Generates qbXML requests for QuickBooks Desktop.
Structure aligned with manual SDK samples in desktop/qb-agent/sample_xml/:
  sample_check_add.xml, sample_check_add_consolidated.xml,
  sample_deposit_add.xml, sample_deposit_add_consolidated.xml,
  sample_vendor_add.xml, sample_customer_add.xml.
"""

import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as xml_escape
from typing import Dict, Any, Optional
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)

QBXML_VERSION = "13.0"

# QuickBooks entity name (Vendor/Customer) max length; longer names are truncated
QB_ENTITY_NAME_MAX_LEN = 41
# RefNumber (check number) max length - QB returns status 3070 "too long" if exceeded (e.g. SYNC-CHECK-551)
QB_REF_NUMBER_MAX_LEN = 11
# Characters QB often rejects in entity names (including apostrophe and # which can break QB parser)
QB_ENTITY_NAME_BAD_CHARS = re.compile(r'[\\:|*?"<>\[\]\'#]')


def _to_ascii(s: str) -> str:
    """Force string to ASCII for QB Desktop COM (non-ASCII can cause 'parsing the provided XML' errors)."""
    if not s:
        return ''
    return s.encode('ascii', 'replace').decode('ascii')


def _xml_safe(s: str) -> str:
    """Escape dynamic text for XML so QB parser never sees raw & < > \" ' (avoids truncation/parse errors)."""
    if not s:
        return ''
    return xml_escape(str(s), {"'": "&apos;", '"': "&quot;"})


def _sanitize_entity_name(name: str, fallback: str = "Unknown") -> str:
    """Sanitize name for QuickBooks Vendor/Customer (strip, remove bad chars, ASCII-only, truncate)."""
    if not name or not str(name).strip():
        return fallback
    s = str(name).strip()
    s = QB_ENTITY_NAME_BAD_CHARS.sub(' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    s = _to_ascii(s)
    return s[:QB_ENTITY_NAME_MAX_LEN] if s else fallback


class QBXMLGenerator:
    """Generate qbXML requests for QuickBooks Desktop"""
    
    @staticmethod
    def generate_account_query(request_id: str = "1", account_type: Optional[str] = None) -> str:
        """Generate AccountQuery request. Structure per sample_account_query.xml."""
        qbxml = ET.Element('QBXML')
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'stopOnError')
        
        account_query_rq = ET.SubElement(msgs_rq, 'AccountQueryRq')
        account_query_rq.set('requestID', request_id)
        
        ET.SubElement(account_query_rq, 'IncludeRetElement').text = 'Name'
        ET.SubElement(account_query_rq, 'IncludeRetElement').text = 'AccountType'
        
        if account_type:
            account_type_filter = ET.SubElement(account_query_rq, 'AccountTypeFilter')
            ET.SubElement(account_type_filter, 'AccountType').text = account_type
        
        xml_str = ET.tostring(qbxml, encoding='unicode', xml_declaration=False)
        xml_str = QBXMLGenerator._convert_self_closing_to_explicit(xml_str)
        
        xml_decl = '<?xml version="1.0"?>'
        qbxml_declaration = f'<?qbxml version="{QBXML_VERSION}"?>'
        return f'{xml_decl}{qbxml_declaration}{xml_str}'
    
    @staticmethod
    def _serialize_qbxml(qbxml_el: ET.Element) -> str:
        """Serialize QBXML element to string (declaration + ASCII-safe formatting)."""
        xml_str = ET.tostring(qbxml_el, encoding='unicode', xml_declaration=False)
        xml_str = QBXMLGenerator._convert_self_closing_to_explicit(xml_str)
        xml_str = QBXMLGenerator._format_xml_with_indentation(xml_str, indent='  ')
        xml_str = _to_ascii(xml_str)
        xml_decl = '<?xml version="1.0"?>'
        qbxml_declaration = f'<?qbxml version="{QBXML_VERSION}"?>'
        return f'{xml_decl}\n{qbxml_declaration}\n{xml_str}'

    @staticmethod
    def get_payee_name_for_entity(transaction: Dict[str, Any]) -> str:
        """Return the sanitized payee name used for VendorAdd (checks) or CustomerAdd (deposits)."""
        trans_type = (transaction.get('transaction_type') or '').upper()
        if trans_type in ['WITHDRAWAL', 'CHECK', 'FEE']:
            return _sanitize_entity_name(transaction.get('payee') or '', 'Bank Charges')
        if trans_type == 'DEPOSIT':
            return _sanitize_entity_name(transaction.get('payee') or '', 'Bank Deposits')
        return _sanitize_entity_name(transaction.get('payee') or '', 'Unknown')

    @staticmethod
    def generate_vendor_query_xml(full_name: str, request_id: str = "1") -> str:
        """Generate VendorQueryRq by name to get ListID when vendor already exists (e.g. 3100 from VendorAdd)."""
        qbxml = ET.Element('QBXML')
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'stopOnError')
        vendor_query_rq = ET.SubElement(msgs_rq, 'VendorQueryRq')
        vendor_query_rq.set('requestID', f"{request_id}-vendor-query")
        name_filter = ET.SubElement(vendor_query_rq, 'NameFilter')
        name_filter.set('MatchCriterion', 'StartsWith')
        ET.SubElement(name_filter, 'Name').text = _xml_safe(_to_ascii(str(full_name).strip() or 'Bank Charges'))
        ET.SubElement(vendor_query_rq, 'IncludeRetElement').text = 'ListID'
        ET.SubElement(vendor_query_rq, 'IncludeRetElement').text = 'FullName'
        return QBXMLGenerator._serialize_qbxml(qbxml)

    @staticmethod
    def generate_customer_query_xml(full_name: str, request_id: str = "1") -> str:
        """Generate CustomerQueryRq by name to get ListID when customer already exists (e.g. 3100 from CustomerAdd)."""
        qbxml = ET.Element('QBXML')
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'stopOnError')
        customer_query_rq = ET.SubElement(msgs_rq, 'CustomerQueryRq')
        customer_query_rq.set('requestID', f"{request_id}-customer-query")
        name_filter = ET.SubElement(customer_query_rq, 'NameFilter')
        name_filter.set('MatchCriterion', 'StartsWith')
        ET.SubElement(name_filter, 'Name').text = _xml_safe(_to_ascii(str(full_name).strip() or 'Bank Deposits'))
        ET.SubElement(customer_query_rq, 'IncludeRetElement').text = 'ListID'
        ET.SubElement(customer_query_rq, 'IncludeRetElement').text = 'FullName'
        return QBXMLGenerator._serialize_qbxml(qbxml)

    @staticmethod
    def parse_entity_query_response(response_xml: str) -> Optional[str]:
        """Extract ListID from first VendorRet or CustomerRet in VendorQueryRs/CustomerQueryRs. Returns None if not found."""
        try:
            root = ET.fromstring(response_xml)
            for tag in ('VendorRet', 'CustomerRet'):
                ret = root.find(f'.//{tag}')
                if ret is not None:
                    list_id_el = ret.find('ListID')
                    if list_id_el is not None and list_id_el.text and list_id_el.text.strip():
                        return list_id_el.text.strip()
            return None
        except Exception:
            return None

    @staticmethod
    def generate_entity_add_xml(
        transaction: Dict[str, Any],
        request_id: str = "1",
    ) -> str:
        """Generate qbXML with ONLY VendorAddRq (checks/withdrawals/fees) or ONLY CustomerAddRq (deposits). Send this first.
        Structure per sample_vendor_add.xml and sample_customer_add.xml."""
        qbxml = ET.Element('QBXML')
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'continueOnError')
        trans_type = transaction.get('transaction_type', '').upper()
        if trans_type in ['WITHDRAWAL', 'CHECK', 'FEE']:
            QBXMLGenerator._add_vendor_only(msgs_rq, transaction, request_id)
        elif trans_type == 'DEPOSIT':
            QBXMLGenerator._add_customer_only(msgs_rq, transaction, request_id)
        else:
            raise ValueError(f"Unknown transaction type: {trans_type}")
        return QBXMLGenerator._serialize_qbxml(qbxml)

    @staticmethod
    def generate_transaction_only_xml(
        transaction: Dict[str, Any],
        request_id: str = "1",
        account_manager=None,
        workspace_account_name: Optional[str] = None,
        payee_list_id: Optional[str] = None
    ) -> str:
        """Generate qbXML with ONLY CheckAddRq or ONLY DepositAddRq. Send this after entity add.
        Vendor/Customer is passed by ListID (from step-1 response) when payee_list_id is set; otherwise by FullName (same name as step 1).
        CheckAdd: PayeeEntityRef with ListID or FullName. DepositAdd: EntityRef in DepositLineAdd with ListID or FullName."""
        qbxml = ET.Element('QBXML')
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'stopOnError')
        trans_type = transaction.get('transaction_type', '').upper()
        if trans_type in ['WITHDRAWAL', 'CHECK', 'FEE']:
            QBXMLGenerator._add_check_only(msgs_rq, transaction, request_id, account_manager, workspace_account_name, payee_list_id=payee_list_id)
        elif trans_type == 'DEPOSIT':
            QBXMLGenerator._add_deposit_only(msgs_rq, transaction, request_id, account_manager, workspace_account_name, payee_list_id=payee_list_id)
        else:
            raise ValueError(f"Unknown transaction type: {trans_type}")
        return QBXMLGenerator._serialize_qbxml(qbxml)

    @staticmethod
    def _add_vendor_only(parent: ET.Element, trans: Dict[str, Any], request_id: str) -> None:
        """Add only VendorAddRq to parent. Structure per sample_vendor_add.xml: VendorAddRq requestID, VendorAdd > Name."""
        payee_name = _sanitize_entity_name(trans.get('payee') or '', 'Bank Charges')
        vendor_add_rq = ET.SubElement(parent, 'VendorAddRq')
        vendor_add_rq.set('requestID', f"{request_id}-vendor")
        vendor_add = ET.SubElement(vendor_add_rq, 'VendorAdd')
        ET.SubElement(vendor_add, 'Name').text = _xml_safe(payee_name)

    @staticmethod
    def _add_customer_only(parent: ET.Element, trans: Dict[str, Any], request_id: str) -> None:
        """Add only CustomerAddRq to parent. Structure per sample_customer_add.xml: CustomerAddRq, CustomerAdd > Name."""
        customer_name = _sanitize_entity_name(trans.get('payee') or '', 'Bank Deposits')
        customer_add_rq = ET.SubElement(parent, 'CustomerAddRq')
        customer_add_rq.set('requestID', f"{request_id}-customer")
        customer_add = ET.SubElement(customer_add_rq, 'CustomerAdd')
        ET.SubElement(customer_add, 'Name').text = _xml_safe(customer_name)

    @staticmethod
    def _add_check_only(parent: ET.Element, trans: Dict[str, Any], request_id: str, account_manager=None, workspace_account_name: Optional[str] = None, payee_list_id: Optional[str] = None) -> None:
        """Add only CheckAddRq to parent. PayeeEntityRef: ListID from step-1 when payee_list_id set, else FullName (same name as VendorAdd)."""
        payee_name = _sanitize_entity_name(trans.get('payee') or '', 'Bank Charges')
        check_add_rq = ET.SubElement(parent, 'CheckAddRq')
        check_add_rq.set('requestID', request_id)
        check_add = ET.SubElement(check_add_rq, 'CheckAdd')
        
        # Bank Account - qbXML 13.0 CheckAdd uses AccountRef (not BankAccountRef)
        account_ref = ET.SubElement(check_add, 'AccountRef')
        account_name = (workspace_account_name or trans.get('account', 'Checking')).strip()
        if not account_name:
            raise ValueError("Workspace account name is required for CheckAdd.")
        ET.SubElement(account_ref, 'FullName').text = _xml_safe(account_name)
        
        # PayeeEntityRef - ListID from step-1 response when available (more reliable); else FullName
        payee_entity_ref = ET.SubElement(check_add, 'PayeeEntityRef')
        if payee_list_id and str(payee_list_id).strip():
            ET.SubElement(payee_entity_ref, 'ListID').text = _xml_safe(str(payee_list_id).strip())
        else:
            ET.SubElement(payee_entity_ref, 'FullName').text = _xml_safe(payee_name)
        
        # RefNumber - QB limits length (status 3070 if too long). Use short ref that fits QB_REF_NUMBER_MAX_LEN.
        ref_number = trans.get('reference_number')
        queue_id = trans.get('_queue_id', '')
        if queue_id:
            unique_ref = str(queue_id)
        else:
            # request_id is e.g. "trans-551" -> use numeric part or last 11 chars
            unique_ref = str(request_id).replace('trans-', '') or request_id
        unique_ref = _to_ascii(str(unique_ref))[:QB_REF_NUMBER_MAX_LEN]
        ET.SubElement(check_add, 'RefNumber').text = _xml_safe(unique_ref or '0')
        
        # Date - use YYYY-MM-DD (QB rejects MM/DD/YYYY with statusCode 3020 for check transaction date)
        trans_date = QBXMLGenerator._format_date_iso(trans.get('date'))
        if not trans_date:
            trans_date = datetime.now().strftime('%Y-%m-%d')
        ET.SubElement(check_add, 'TxnDate').text = trans_date
        
        # Amount
        amount = abs(float(trans.get('amount', 0)))
        
        # Expense line
        expense_line = ET.SubElement(check_add, 'ExpenseLineAdd')
        expense_account_ref = ET.SubElement(expense_line, 'AccountRef')
        expense_account = trans.get('expense_account', 'Miscellaneous Expense')
        if account_manager and account_manager.is_initialized():
            expense_account = account_manager.resolve_account(
                preferred=expense_account,
                fallback_type='Expense'
            ) or expense_account
        ET.SubElement(expense_account_ref, 'FullName').text = _xml_safe(expense_account.strip())
        ET.SubElement(expense_line, 'Amount').text = f"{amount:.2f}"
        
        # Memo only inside ExpenseLineAdd (per sample_check_add.xml - no Memo at CheckAdd level)
        memo = trans.get('description', trans.get('memo', ''))
        if memo:
            memo_safe = _xml_safe(_to_ascii(str(memo))[:4095])
            ET.SubElement(expense_line, 'Memo').text = memo_safe
        # Do not add Memo at CheckAdd level - working sample has only ExpenseLineAdd > Memo
    
    @staticmethod
    def _add_deposit_only(parent: ET.Element, trans: Dict[str, Any], request_id: str, account_manager=None, workspace_account_name: Optional[str] = None, payee_list_id: Optional[str] = None) -> None:
        """Add only DepositAddRq to parent. Structure per sample_deposit_add_consolidated.xml: TxnDate, DepositToAccountRef, DepositLineAdd (EntityRef, AccountRef, Memo, Amount)."""
        customer_name = _sanitize_entity_name(trans.get('payee') or '', 'Bank Deposits')
        deposit_add_rq = ET.SubElement(parent, 'DepositAddRq')
        deposit_add_rq.set('requestID', request_id)
        deposit_add = ET.SubElement(deposit_add_rq, 'DepositAdd')
        # 1. TxnDate first (per sample_deposit_add_consolidated)
        trans_date = QBXMLGenerator._format_date_iso(trans.get('date'))
        if not trans_date:
            trans_date = datetime.now().strftime('%Y-%m-%d')
        ET.SubElement(deposit_add, 'TxnDate').text = trans_date
        
        # 2. DepositToAccountRef
        deposit_to_account_ref = ET.SubElement(deposit_add, 'DepositToAccountRef')
        account_name = (workspace_account_name or trans.get('account', '')).strip()
        if not account_name:
            raise ValueError("Workspace account name is required for deposits.")
        ET.SubElement(deposit_to_account_ref, 'FullName').text = _xml_safe(account_name)
        
        # Deposit-level Memo with payee name so the bank register may show it in Payee column (QB uses Memo for deposit register in some versions)
        ET.SubElement(deposit_add, 'Memo').text = _xml_safe(customer_name)
        
        # 4. DepositLineAdd: EntityRef (customer) by ListID from step-1 when available, else FullName; then AccountRef, Memo, Amount
        deposit_line = ET.SubElement(deposit_add, 'DepositLineAdd')
        entity_ref = ET.SubElement(deposit_line, 'EntityRef')
        if payee_list_id and str(payee_list_id).strip():
            ET.SubElement(entity_ref, 'ListID').text = _xml_safe(str(payee_list_id).strip())
        else:
            ET.SubElement(entity_ref, 'FullName').text = _xml_safe(customer_name)

        description = (trans.get('description', '') or trans.get('memo', '') or '').lower()
        is_interest = 'interest' in description or 'int income' in description or 'bank interest' in description
        if is_interest:
            preferred = 'Interest Income'
            fallback_type = 'OtherIncome'
        else:
            preferred = 'Sales'
            fallback_type = 'Income'
        
        if account_manager and account_manager.is_initialized():
            deposit_account = account_manager.resolve_account(preferred=preferred, fallback_type=fallback_type)
            if not deposit_account:
                deposit_account = (
                    account_manager.get_first_account_of_type('Income')
                    or account_manager.get_first_account_of_type('OtherIncome')
                    or account_manager.get_first_account_of_type('Equity')
                )
            if not deposit_account:
                raise ValueError(
                    "No Income, OtherIncome, or Equity account found. Add one (e.g. Sales or Interest Income) in Chart of Accounts."
                )
        else:
            deposit_account = preferred if is_interest else 'Sales'
        
        account_ref = ET.SubElement(deposit_line, 'AccountRef')
        ET.SubElement(account_ref, 'FullName').text = _xml_safe(deposit_account.strip())
        memo = trans.get('description', trans.get('memo', ''))
        if memo:
            ET.SubElement(deposit_line, 'Memo').text = _xml_safe(_to_ascii(str(memo))[:4095])
        amount = abs(float(trans.get('amount', 0)))
        if amount <= 0:
            raise ValueError("Deposit amount must be greater than zero.")
        ET.SubElement(deposit_line, 'Amount').text = f"{amount:.2f}"
    
    @staticmethod
    def _format_date_iso(date_str: Optional[str]) -> Optional[str]:
        """Convert date to ISO format (YYYY-MM-DD)"""
        if not date_str:
            return None
        
        formats = ['%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%Y/%m/%d']
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue
        return None

    @staticmethod
    def _format_date_qb(date_str: Optional[str]) -> Optional[str]:
        """Convert date to MM/DD/YYYY. Not used for CheckAdd/DepositAdd (use _format_date_iso)."""
        if not date_str:
            return None
        formats = ['%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%Y/%m/%d']
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.strftime('%m/%d/%Y')
            except ValueError:
                continue
        return None
    
    @staticmethod
    def _convert_self_closing_to_explicit(xml_str: str) -> str:
        """Convert self-closing tags to explicit tags"""
        pattern = r'<(\w+)([^/>]*?)\s*/>'
        
        def replace_tag(match):
            tag_name = match.group(1)
            attributes = match.group(2)
            if tag_name.startswith('?'):
                return match.group(0)
            return f'<{tag_name}{attributes}></{tag_name}>'
        
        return re.sub(pattern, replace_tag, xml_str)
    
    @staticmethod
    def _add_attribute_spacing(xml_str: str) -> str:
        """Add spaces around = in attributes (QB Desktop sample format; avoids 0x80040400)."""
        attr_pattern = r'(\w+)=("|\')([^"\']*)("|\')'
        def add_spaces(m):
            return f'{m.group(1)} = {m.group(2)}{m.group(3)}{m.group(4)}'
        def on_tag(match):
            content = re.sub(attr_pattern, add_spaces, match.group(1))
            return f'<{content}>'
        return re.sub(r'<([^>]+)>', on_tag, xml_str)
    
    @staticmethod
    def _format_xml_with_indentation(xml_str: str, indent: str = '  ') -> str:
        """Format XML with 2-space indentation. Attributes without spaces (match working samples)."""
        try:
            root = ET.fromstring(xml_str)
            def format_el(elem, level=0):
                ind = indent * level
                tag = elem.tag
                attrs = ' '.join([f'{k}="{v}"' for k, v in elem.attrib.items()]) if elem.attrib else ''
                start = f'{ind}<{tag} {attrs}>'.replace(' >', '>') if attrs else f'{ind}<{tag}>'
                if len(elem) == 0:
                    text = (elem.text or '').strip()
                    return f'{start}{text}</{tag}>' if text else f'{start}</{tag}>'
                parts = [start]
                for child in elem:
                    parts.append(format_el(child, level + 1))
                parts.append(f'{ind}</{tag}>')
                return '\n'.join(parts)
            return format_el(root, 0)
        except ET.ParseError:
            return xml_str
    
    @staticmethod
    def parse_response(response_xml: str) -> Dict[str, Any]:
        """Parse qbXML response"""
        try:
            root = ET.fromstring(response_xml)
            results = []
            
            status_rs = (
                root.findall('.//CheckAddRs') +
                root.findall('.//DepositAddRs') +
                root.findall('.//SalesReceiptAddRs')
            )
            
            for rs in status_rs:
                status_code = rs.get('statusCode', '0')
                status_message = rs.get('statusMessage', '')
                request_id = rs.get('requestID', '')
                
                results.append({
                    'requestID': request_id,
                    'statusCode': status_code,
                    'statusMessage': status_message,
                    'success': status_code == '0'
                })
            
            return {
                'success': all(r['success'] for r in results) if results else False,
                'results': results
            }
        except Exception as e:
            logger.error(f"Error parsing qbXML response: {e}")
            return {
                'success': False,
                'error': str(e),
                'results': []
            }

    @staticmethod
    def parse_entity_add_response(response_xml: str) -> Optional[str]:
        """Extract ListID from VendorAddRs/VendorRet or CustomerAddRs/CustomerRet (step-1 response). Returns None if not found (e.g. 3100 already in use)."""
        try:
            root = ET.fromstring(response_xml)
            for tag in ('VendorRet', 'CustomerRet'):
                ret = root.find(f'.//{tag}')
                if ret is not None:
                    list_id_el = ret.find('ListID')
                    if list_id_el is not None and list_id_el.text and list_id_el.text.strip():
                        return list_id_el.text.strip()
            return None
        except Exception:
            return None


