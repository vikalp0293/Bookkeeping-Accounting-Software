"""
Test QuickBooks SDK Connection
Run this to verify SDK connection works before using the sync service
"""

import sys
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_connection():
    """Test QuickBooks SDK connection"""
    if sys.platform != 'win32':
        logger.error("This test requires Windows")
        return False
    
    try:
        from qb_sdk_service import QBSDKService
        
        logger.info("Testing QuickBooks SDK connection...")
        
        # Get company file from user
        company_file = input("Enter path to QuickBooks company file (.QBW): ").strip()
        
        if not os.path.exists(company_file):
            logger.error(f"Company file not found: {company_file}")
            return False
        
        # Test connection
        with QBSDKService() as qb:
            logger.info("Opening connection...")
            qb.open_connection()
            
            logger.info("Starting session...")
            qb.begin_session(company_file)
            
            # Test query
            logger.info("Testing query...")
            test_xml = """<?xml version="1.0"?>
<?qbxml version="13.0"?>
<QBXML>
    <QBXMLMsgsRq onError="stopOnError">
        <CompanyQueryRq requestID="1">
        </CompanyQueryRq>
    </QBXMLMsgsRq>
</QBXML>"""
            
            response = qb.process_request(test_xml)
            logger.info(f"Query successful! Response length: {len(response)}")
            logger.info("=" * 60)
            logger.info("✅ SDK connection test PASSED")
            logger.info("=" * 60)
            return True
            
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return False

if __name__ == '__main__':
    success = test_connection()
    sys.exit(0 if success else 1)


