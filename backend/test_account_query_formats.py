#!/usr/bin/env python3
"""
Test script to generate and compare different AccountQuery formats.
This helps identify the exact format that QuickBooks Desktop expects.
"""

import xml.etree.ElementTree as ET
from app.services.qbxml_service import QBXMLService

def generate_formats():
    """Generate different AccountQuery XML formats for testing"""
    
    print("=" * 80)
    print("AccountQuery XML Format Comparison")
    print("=" * 80)
    print()
    
    # Format 1: Current implementation (with explicit tags conversion)
    print("1. CURRENT FORMAT (with explicit tags conversion):")
    current = QBXMLService.generate_account_query(request_id="test-1")
    print(current)
    print()
    print(f"   First 120 chars: {repr(current[:120])}")
    print(f"   Length: {len(current)} chars")
    print(f"   Starts with <?qbxml: {current.lstrip().startswith('<?qbxml')}")
    print(f"   Starts with <?xml: {current.lstrip().startswith('<?xml')}")
    print(f"   Has explicit tags: {'</AccountQueryRq>' in current}")
    print()
    
    # Format 2: Manual construction (like CompanyQueryRq in test_qb_connection.py)
    print("2. MANUAL FORMAT (like CompanyQueryRq example):")
    qbxml = ET.Element('QBXML')
    msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
    msgs_rq.set('onError', 'stopOnError')
    account_query_rq = ET.SubElement(msgs_rq, 'AccountQueryRq')
    account_query_rq.set('requestID', 'test-2')
    
    manual_xml = ET.tostring(qbxml, encoding='unicode', xml_declaration=False)
    manual_result = f'<?qbxml version="13.0"?>{manual_xml}'
    print(manual_result)
    print()
    print(f"   First 120 chars: {repr(manual_result[:120])}")
    print(f"   Length: {len(manual_result)} chars")
    print(f"   Has self-closing tags: {'/>' in manual_xml}")
    print()
    
    # Format 3: With explicit tags manually
    print("3. MANUAL WITH EXPLICIT TAGS:")
    # Convert self-closing to explicit
    manual_explicit = QBXMLService._convert_self_closing_to_explicit(manual_xml)
    manual_explicit_result = f'<?qbxml version="13.0"?>{manual_explicit}'
    print(manual_explicit_result)
    print()
    print(f"   First 120 chars: {repr(manual_explicit_result[:120])}")
    print(f"   Length: {len(manual_explicit_result)} chars")
    print(f"   Has explicit tags: {'</AccountQueryRq>' in manual_explicit_result}")
    print()
    
    # Format 4: Compare with CompanyQueryRq format (which works in test_qb_connection.py)
    print("4. COMPANYQUERY FORMAT (from test_qb_connection.py - note: uses XML decl):")
    company_format = """<?xml version="1.0"?>
<?qbxml version="13.0"?>
<QBXML>
    <QBXMLMsgsRq onError="stopOnError">
        <CompanyQueryRq requestID="1">
        </CompanyQueryRq>
    </QBXMLMsgsRq>
</QBXML>"""
    print(company_format)
    print()
    print("   NOTE: This format works for DIRECT SDK, but Web Connector rejects XML declaration")
    print()
    
    print("=" * 80)
    print("RECOMMENDATIONS:")
    print("=" * 80)
    print("1. Use Format 1 (current) - it's correct for Web Connector")
    print("2. If still failing, the issue may be:")
    print("   - QuickBooks Desktop version compatibility")
    print("   - AccountQueryRq may require child elements (not empty)")
    print("   - Some other QuickBooks-specific requirement")
    print()
    print("Next steps:")
    print("- Check QuickBooks SDK OSR tool for exact format")
    print("- Try adding a filter to AccountQueryRq (make it non-empty)")
    print("- Check if CompanyQueryRq works (similar structure)")

if __name__ == "__main__":
    generate_formats()


