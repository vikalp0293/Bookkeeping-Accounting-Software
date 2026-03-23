"""
Test IIF Auto-Sync
Tests automatic download and import of IIF files from backend API
"""

import sys
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_auto_sync():
    """Test automatic IIF sync from backend"""
    if sys.platform != 'win32':
        logger.error("This test requires Windows")
        return False
    
    try:
        from qb_sdk_service import QBSDKService
        from iif_auto_sync import IIFAutoSync
        
        logger.info("=" * 60)
        logger.info("Testing IIF Auto-Sync from Backend API")
        logger.info("=" * 60)
        
        # Get configuration
        backend_url = input("\nEnter backend URL (e.g., https://dev-sync-api.kylientlabs.com): ").strip()
        if not backend_url:
            backend_url = "https://dev-sync-api.kylientlabs.com"
        
        api_token = input("\nEnter API token (JWT): ").strip()
        if not api_token:
            logger.error("API token is required")
            return False
        
        workspace_id = input("\nEnter workspace ID: ").strip()
        if not workspace_id:
            logger.error("Workspace ID is required")
            return False
        workspace_id = int(workspace_id)
        
        company_file = input("\nEnter path to QuickBooks company file (.QBW): ").strip()
        if not os.path.exists(company_file):
            logger.error(f"Company file not found: {company_file}")
            return False
        
        file_id = input("\nEnter file ID to sync (or press Enter for all files): ").strip()
        file_id = int(file_id) if file_id else None
        
        # Connect to QuickBooks
        logger.info("\nConnecting to QuickBooks Desktop...")
        qb_sdk = QBSDKService()
        qb_sdk.open_connection()
        qb_sdk.begin_session(company_file)
        logger.info("✓ Connected to QuickBooks Desktop")
        
        try:
            # Create auto-sync service
            auto_sync = IIFAutoSync(
                backend_url=backend_url,
                api_token=api_token,
                workspace_id=workspace_id,
                company_file=company_file,
                qb_sdk_service=qb_sdk
            )
            
            # Perform sync
            logger.info(f"\nStarting auto-sync (file_id: {file_id or 'all files'})...")
            result = auto_sync.sync_file(file_id=file_id)
            
            if result['success']:
                logger.info("=" * 60)
                logger.info("✅ IIF Auto-Sync SUCCESSFUL")
                logger.info("=" * 60)
                logger.info(f"Message: {result.get('message', 'N/A')}")
                return True
            else:
                logger.error("=" * 60)
                logger.error("❌ IIF Auto-Sync FAILED")
                logger.error("=" * 60)
                logger.error(f"Error: {result.get('message', 'Unknown error')}")
                if 'errors' in result:
                    for error in result['errors']:
                        logger.error(f"  - {error}")
                return False
                
        finally:
            qb_sdk.close_connection()
            
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return False

if __name__ == '__main__':
    success = test_auto_sync()
    sys.exit(0 if success else 1)
