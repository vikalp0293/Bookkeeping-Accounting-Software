"""
Test IIF File Import
Tests the IIF import functionality with QuickBooks Desktop
"""

import sys
import os
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_iif_import():
    """Test IIF file import into QuickBooks"""
    if sys.platform != 'win32':
        logger.error("This test requires Windows")
        return False
    
    try:
        from qb_sdk_service import QBSDKService
        
        logger.info("=" * 60)
        logger.info("Testing IIF File Import")
        logger.info("=" * 60)
        
        # Get company file from user
        company_file = input("\nEnter path to QuickBooks company file (.QBW): ").strip()
        
        if not os.path.exists(company_file):
            logger.error(f"Company file not found: {company_file}")
            return False
        
        # Get IIF file path
        iif_file = input("\nEnter path to IIF file to import (.iif): ").strip()
        
        if not os.path.exists(iif_file):
            logger.error(f"IIF file not found: {iif_file}")
            return False
        
        if not iif_file.lower().endswith('.iif'):
            logger.error(f"File must be a .iif file: {iif_file}")
            return False
        
        # Connect to QuickBooks
        logger.info("\nConnecting to QuickBooks Desktop...")
        with QBSDKService() as qb:
            logger.info("Opening connection...")
            qb.open_connection()
            
            logger.info("Starting session...")
            qb.begin_session(company_file)
            
            logger.info("✓ Connected to QuickBooks Desktop")
            
            # Test import
            logger.info(f"\nImporting IIF file: {iif_file}")
            logger.info("This may take a moment...")
            
            result = qb.import_iif_file(iif_file)
            
            if result['success']:
                logger.info("=" * 60)
                logger.info("✅ IIF Import SUCCESSFUL")
                logger.info("=" * 60)
                logger.info(f"Message: {result.get('message', 'N/A')}")
                if 'imported_count' in result:
                    logger.info(f"Imported transactions: {result['imported_count']}")
                return True
            else:
                logger.error("=" * 60)
                logger.error("❌ IIF Import FAILED")
                logger.error("=" * 60)
                logger.error(f"Error: {result.get('message', 'Unknown error')}")
                if 'errors' in result:
                    for error in result['errors']:
                        logger.error(f"  - {error}")
                if 'suggestion' in result:
                    logger.info(f"\nSuggestion: {result['suggestion']}")
                return False
            
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return False

if __name__ == '__main__':
    success = test_iif_import()
    sys.exit(0 if success else 1)
