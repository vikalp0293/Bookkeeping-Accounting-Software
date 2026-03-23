"""
IIF Auto-Sync Service
Automatically downloads and imports IIF files from backend API
"""

import sys
import os
import logging
import time
import tempfile
import requests
from typing import Optional, Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if sys.platform != 'win32':
    raise RuntimeError("IIF Auto-Sync only works on Windows")


class IIFAutoSync:
    """Service that automatically downloads and imports IIF files from backend"""
    
    def __init__(
        self,
        backend_url: str,
        api_token: str,
        workspace_id: int,
        company_file: str,
        qb_sdk_service
    ):
        """
        Initialize IIF auto-sync service
        
        Args:
            backend_url: Backend API URL (e.g., "https://dev-sync-api.kylientlabs.com")
            api_token: JWT token for API authentication
            workspace_id: Workspace ID to sync
            company_file: Path to QuickBooks company file (.QBW)
            qb_sdk_service: Connected QBSDKService instance
        """
        self.backend_url = backend_url.rstrip('/')
        self.api_token = api_token
        self.workspace_id = workspace_id
        self.company_file = company_file
        self.qb_sdk = qb_sdk_service
        self.running = False
        
        # Import IIF importer
        from iif_importer import IIFImporter
        self.iif_importer = IIFImporter(self.qb_sdk)
    
    def sync_file(self, file_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Download and import IIF file for a specific file or all files in workspace
        
        Args:
            file_id: Optional file ID to export. If None, exports all files in workspace
            
        Returns:
            Dictionary with sync result
        """
        try:
            # Step 1: Download IIF file from backend
            logger.info(f"Downloading IIF file from backend (workspace_id: {self.workspace_id}, file_id: {file_id})")
            
            url = f"{self.backend_url}/api/v1/export/quickbooks/queued/{self.workspace_id}"
            params = {'limit': 1000}
            if file_id:
                params['file_id'] = file_id
            
            headers = {
                'Authorization': f'Bearer {self.api_token}',
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=60)
            response.raise_for_status()
            
            # Save to temp file
            temp_dir = tempfile.gettempdir()
            timestamp = int(time.time())
            temp_file = os.path.join(temp_dir, f"qb_import_{self.workspace_id}_{timestamp}.iif")
            
            with open(temp_file, 'wb') as f:
                f.write(response.content)
            
            file_size = os.path.getsize(temp_file)
            logger.info(f"Downloaded IIF file ({file_size} bytes) to: {temp_file}")
            
            # Step 2: Import into QuickBooks
            logger.info("Importing IIF file into QuickBooks Desktop...")
            import_result = self.iif_importer.import_iif_file(temp_file)
            
            # Clean up temp file
            try:
                os.remove(temp_file)
                logger.debug(f"Cleaned up temp file: {temp_file}")
            except:
                pass
            
            if import_result['success']:
                logger.info("=" * 60)
                logger.info("✅ IIF Auto-Sync SUCCESSFUL")
                logger.info("=" * 60)
                return {
                    'success': True,
                    'message': 'IIF file downloaded and imported successfully',
                    'import_result': import_result
                }
            else:
                logger.error("=" * 60)
                logger.error("❌ IIF Auto-Sync FAILED")
                logger.error("=" * 60)
                logger.error(f"Import error: {import_result.get('message', 'Unknown error')}")
                return {
                    'success': False,
                    'message': f"IIF file downloaded but import failed: {import_result.get('message', 'Unknown error')}",
                    'import_result': import_result
                }
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to download IIF file from backend: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg,
                'errors': [str(e)]
            }
        except Exception as e:
            error_msg = f"IIF auto-sync error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'message': error_msg,
                'errors': [str(e)]
            }
    
    def sync_all_files(self) -> Dict[str, Any]:
        """Sync all files in workspace (no file_id filter)"""
        return self.sync_file(file_id=None)
