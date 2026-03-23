"""
QuickBooks qbXML generator for SDK / desktop sync.

Generates qbXML for CheckAdd and DepositAdd with the same format as the working
sample XMLs (desktop/qb-agent/sample_xml/). Use this in the SDK app (e.g. qb_sdk_service.py)
so sync XML matches the backend and passes QuickBooks validation.

CRITICAL (matching sample XMLs):
- TxnDate: YYYY-MM-DD (QB rejects MM/DD/YYYY with statusCode 3020)
- CheckAdd: AccountRef for bank (not BankAccountRef); order: AccountRef, PayeeEntityRef, RefNumber, TxnDate, ExpenseLineAdd
- DepositAdd: DepositToAccountRef, TxnDate (YYYY-MM-DD), DepositLineAdd
- XML: <?xml version="1.0" ?> + <?qbxml version="13.0"?>
"""

import xml.etree.ElementTree as ET
import re
from typing import Dict, Any, Optional
from datetime import datetime

QBXML_VERSION = "13.0"


def _format_date_iso(date_str: Optional[str]) -> Optional[str]:
    """Return date as YYYY-MM-DD for qbXML (CheckAdd/DepositAdd require this format)."""
    if not date_str:
        return None
    try:
        for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%Y/%m/%d'):
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue
    except Exception:
        pass
    return None


def _convert_self_closing_to_explicit(xml_str: str) -> str:
    """Convert self-closing tags to explicit open/close (QB Desktop requirement)."""
    pattern = r'<(\w+)([^/>]*?)\s*/>'
    def replace_tag(match):
        tag_name, attrs = match.group(1), match.group(2)
        if tag_name.startswith('?'):
            return match.group(0)
        return f'<{tag_name}{attrs}></{tag_name}>'
    return re.sub(pattern, replace_tag, xml_str)


def _add_attribute_spacing(xml_str: str) -> str:
    """Add spaces around = in attributes to match QuickBooks sample format."""
    attr_pattern = r'(\w+)=("|\')([^"\']*)("|\')'
    def add_spaces(m):
        return f'{m.group(1)} = {m.group(2)}{m.group(3)}{m.group(4)}'
    def on_tag(match):
        content = re.sub(attr_pattern, add_spaces, match.group(1))
        return f'<{content}>'
    return re.sub(r'<([^>]+)>', on_tag, xml_str)


def _format_xml_with_indentation(xml_str: str, indent: str = "  ") -> str:
    """Format XML with 2-space indentation (matches sample XMLs)."""
    try:
        root = ET.fromstring(xml_str)
        def format_el(elem, level=0):
            ind = indent * level
            tag = elem.tag
            attrs = ' '.join([f'{k} = "{v}"' for k, v in elem.attrib.items()]) if elem.attrib else ''
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


def _add_check_transaction(
    parent: ET.Element,
    trans: Dict[str, Any],
    request_id: str,
    workspace_account_name: str,
    payee_name: str = "Bank Charges",
    expense_account_name: str = "Miscellaneous Expense",
) -> None:
    """
    Add CheckAdd to parent. Order: AccountRef, PayeeEntityRef, RefNumber, TxnDate, ExpenseLineAdd.
    TxnDate must be YYYY-MM-DD.
    """
    if not workspace_account_name or not workspace_account_name.strip():
        raise ValueError("workspace_account_name is required for CheckAdd")
    account_name = workspace_account_name.strip()

    check_add_rq = ET.SubElement(parent, 'CheckAddRq')
    check_add_rq.set('requestID', request_id)
    check_add = ET.SubElement(check_add_rq, 'CheckAdd')

    # AccountRef (qbXML 13.0 uses AccountRef for bank, not BankAccountRef)
    account_ref = ET.SubElement(check_add, 'AccountRef')
    ET.SubElement(account_ref, 'FullName').text = account_name

    payee_entity_ref = ET.SubElement(check_add, 'PayeeEntityRef')
    ET.SubElement(payee_entity_ref, 'FullName').text = payee_name

    ref_number = trans.get('reference_number')
    queue_id = trans.get('_queue_id', '')
    if ref_number:
        unique_ref = f"SYNC-{queue_id}-{ref_number}" if queue_id else f"SYNC-{ref_number}"
    else:
        unique_ref = f"SYNC-CHECK-{queue_id}" if queue_id else f"SYNC-CHECK-{request_id.replace('trans-', '') or str(int(datetime.now().timestamp()))}"
    ET.SubElement(check_add, 'RefNumber').text = unique_ref

    trans_date = _format_date_iso(trans.get('date'))
    if not trans_date:
        trans_date = datetime.now().strftime('%Y-%m-%d')
    ET.SubElement(check_add, 'TxnDate').text = trans_date

    amount = abs(float(trans.get('amount', 0)))
    memo = trans.get('description', trans.get('memo', ''))

    expense_line = ET.SubElement(check_add, 'ExpenseLineAdd')
    expense_account_ref = ET.SubElement(expense_line, 'AccountRef')
    ET.SubElement(expense_account_ref, 'FullName').text = expense_account_name
    ET.SubElement(expense_line, 'Amount').text = f"{amount:.2f}"
    if memo:
        ET.SubElement(expense_line, 'Memo').text = memo[:4095]
    if memo:
        ET.SubElement(check_add, 'Memo').text = memo[:4095]


def _add_direct_deposit_transaction(
    parent: ET.Element,
    trans: Dict[str, Any],
    request_id: str,
    workspace_account_name: str,
    deposit_account_sales: str = "Sales",
    deposit_account_interest: str = "Other Income: Interest Income",
) -> None:
    """
    Add DepositAdd to parent. Order: DepositToAccountRef, TxnDate, DepositLineAdd.
    TxnDate must be YYYY-MM-DD.
    """
    if not workspace_account_name or not workspace_account_name.strip():
        raise ValueError("workspace_account_name is required for DepositAdd")
    account_name = workspace_account_name.strip()

    deposit_add_rq = ET.SubElement(parent, 'DepositAddRq')
    deposit_add_rq.set('requestID', request_id)
    deposit_add = ET.SubElement(deposit_add_rq, 'DepositAdd')

    deposit_to_account_ref = ET.SubElement(deposit_add, 'DepositToAccountRef')
    ET.SubElement(deposit_to_account_ref, 'FullName').text = account_name

    trans_date = _format_date_iso(trans.get('date'))
    if not trans_date:
        trans_date = datetime.now().strftime('%Y-%m-%d')
    ET.SubElement(deposit_add, 'TxnDate').text = trans_date

    description = (trans.get('description') or trans.get('memo') or '').lower()
    is_interest = any(x in description for x in ('interest', 'int income', 'bank interest'))
    deposit_account = deposit_account_interest if is_interest else deposit_account_sales

    deposit_line = ET.SubElement(deposit_add, 'DepositLineAdd')
    account_ref = ET.SubElement(deposit_line, 'AccountRef')
    ET.SubElement(account_ref, 'FullName').text = deposit_account
    amount = abs(float(trans.get('amount', 0)))
    if amount <= 0:
        raise ValueError("Deposit amount must be greater than zero")
    ET.SubElement(deposit_line, 'Amount').text = f"{amount:.2f}"
    line_memo = trans.get('description', trans.get('memo', ''))
    if line_memo:
        ET.SubElement(deposit_line, 'Memo').text = line_memo[:4095]


def generate_qbxml_for_single_transaction(
    transaction: Dict[str, Any],
    request_id: str = "1",
    workspace_account_name: Optional[str] = None,
    *,
    payee_name: str = "Bank Charges",
    expense_account_name: str = "Miscellaneous Expense",
    deposit_account_sales: str = "Sales",
    deposit_account_interest: str = "Other Income: Interest Income",
) -> str:
    """
    Generate qbXML for a single transaction (CheckAdd or DepositAdd).

    Args:
        transaction: Dict with transaction_type, date, amount, description/memo, reference_number, _queue_id (optional).
        request_id: Request ID for the qbXML request.
        workspace_account_name: QuickBooks bank account name (e.g. "kylient"). Required.
        payee_name: Vendor name for CheckAdd (default "Bank Charges").
        expense_account_name: Expense account for CheckAdd (default "Miscellaneous Expense").
        deposit_account_sales: Income account for non-interest deposits (default "Sales").
        deposit_account_interest: Income account for interest deposits (default "Other Income: Interest Income").

    Returns:
        Full qbXML string with <?xml ?> and <?qbxml version="13.0"?>, ready to send to QuickBooks.
    """
    if not workspace_account_name:
        raise ValueError("workspace_account_name is required")

    qbxml = ET.Element('QBXML')
    msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
    msgs_rq.set('onError', 'stopOnError')

    trans_type = (transaction.get('transaction_type') or '').upper()
    if trans_type in ('WITHDRAWAL', 'CHECK', 'FEE'):
        _add_check_transaction(
            msgs_rq, transaction, request_id, workspace_account_name,
            payee_name=payee_name, expense_account_name=expense_account_name,
        )
    elif trans_type == 'DEPOSIT':
        _add_direct_deposit_transaction(
            msgs_rq, transaction, request_id, workspace_account_name,
            deposit_account_sales=deposit_account_sales,
            deposit_account_interest=deposit_account_interest,
        )
    else:
        raise ValueError(f"Unknown transaction type: {trans_type}")

    xml_bytes = ET.tostring(qbxml, encoding='ascii', xml_declaration=False)
    xml_str = xml_bytes.decode('ascii')
    xml_str = _convert_self_closing_to_explicit(xml_str)
    xml_str = _add_attribute_spacing(xml_str)
    xml_str = _format_xml_with_indentation(xml_str, indent="  ")

    xml_declaration = '<?xml version="1.0" ?>'
    qbxml_declaration = f'<?qbxml version="{QBXML_VERSION}"?>'
    return f'{xml_declaration}\n{qbxml_declaration}\n{xml_str}'
