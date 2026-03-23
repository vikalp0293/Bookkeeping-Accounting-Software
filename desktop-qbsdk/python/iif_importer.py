"""
IIF File Importer for QuickBooks Desktop
Uses QuickBooks SDK to programmatically import IIF files
"""

import sys
import os
import logging
import time
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Windows-only
if sys.platform != 'win32':
    raise RuntimeError("IIF Importer only works on Windows")


class IIFImporter:
    """Service for importing IIF files into QuickBooks Desktop via SDK"""
    
    def __init__(self, qb_sdk_service):
        """
        Initialize IIF importer
        
        Args:
            qb_sdk_service: Instance of QBSDKService (already connected to QuickBooks)
        """
        self.qb_sdk = qb_sdk_service
        if not self.qb_sdk.is_connected():
            raise RuntimeError("QuickBooks SDK must be connected before importing IIF files")
    
    def import_iif_file(self, iif_file_path: str) -> Dict[str, Any]:
        """
        Import an IIF file into QuickBooks Desktop
        
        Args:
            iif_file_path: Path to the .iif file to import
            
        Returns:
            Dictionary with:
                - success: bool
                - message: str
                - imported_count: int (if available)
                - errors: list (if any)
        """
        if not os.path.exists(iif_file_path):
            raise FileNotFoundError(f"IIF file not found: {iif_file_path}")
        
        if not iif_file_path.lower().endswith('.iif'):
            raise ValueError(f"File must be a .iif file: {iif_file_path}")
        
        logger.info(f"Importing IIF file: {iif_file_path}")
        
        try:
            # Method 1: Try using QuickBooks SDK's ImportData method (if available)
            # Note: This method may not be available in all SDK versions
            result = self._import_via_sdk_method(iif_file_path)
            if result['success']:
                return result
            
            # Method 2: Fallback - Use qbXML DataExtDefAdd/Mod to trigger import
            # This is a workaround if ImportData is not available
            logger.warning("SDK ImportData method not available, trying alternative method...")
            result = self._import_via_qbxml(iif_file_path)
            if result['success']:
                return result
            
            # Method 3: Use Windows COM automation to trigger QuickBooks import dialog
            # This simulates File -> Utilities -> Import -> IIF Files
            logger.warning("qbXML import method not available, trying UI automation...")
            result = self._import_via_ui_automation(iif_file_path)
            return result
            
        except Exception as e:
            error_msg = f"Failed to import IIF file: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'message': error_msg,
                'errors': [str(e)]
            }
    
    def _import_via_sdk_method(self, iif_file_path: str) -> Dict[str, Any]:
        """
        Try to import using SDK's ImportData method (if available)
        This is the preferred method but may not be available in all SDK versions
        """
        try:
            # Check if the SDK has an ImportData method
            if hasattr(self.qb_sdk.qb, 'ImportData'):
                logger.info("Using SDK ImportData method...")
                # Convert to absolute path
                abs_path = os.path.abspath(iif_file_path)
                
                # ImportData typically takes: session_ticket, file_path, import_type
                # Import type: 0 = IIF, 1 = CSV, etc.
                result = self.qb_sdk.qb.ImportData(
                    self.qb_sdk.session_ticket,
                    abs_path,
                    0  # 0 = IIF format
                )
                
                logger.info(f"ImportData returned: {result}")
                return {
                    'success': True,
                    'message': 'IIF file imported successfully via SDK ImportData',
                    'result': result
                }
            else:
                return {'success': False, 'message': 'ImportData method not available in SDK'}
        except Exception as e:
            logger.debug(f"ImportData method failed: {e}")
            return {'success': False, 'message': f'ImportData method error: {str(e)}'}
    
    def _import_via_qbxml(self, iif_file_path: str) -> Dict[str, Any]:
        """
        Try to import using qbXML DataExtDef requests
        This is a workaround method
        """
        try:
            # Note: QuickBooks SDK doesn't have a direct qbXML method for IIF import
            # IIF import is typically done through the UI or ImportData method
            # This method is a placeholder for future implementation if needed
            
            logger.warning("qbXML import method not fully implemented - IIF import typically requires ImportData or UI automation")
            return {
                'success': False,
                'message': 'qbXML import method not available for IIF files'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'qbXML import error: {str(e)}'
            }
    
    def _import_via_ui_automation(self, iif_file_path: str) -> Dict[str, Any]:
        """
        Use Windows UI automation to trigger QuickBooks import dialog
        This simulates: File -> Utilities -> Import -> IIF Files
        """
        try:
            import win32com.client
            import time
            
            logger.info("Attempting UI automation for IIF import...")
            
            # Get QuickBooks application object
            # Try to get the running QuickBooks instance
            qb_app = None
            
            # Method 1: Try to get QuickBooks via COM
            try:
                # QuickBooks may expose an Application object
                qb_app = win32com.client.GetActiveObject("QB.Application")
                logger.info("Found QuickBooks application via GetActiveObject")
            except:
                # Method 2: Try to find QuickBooks window and send commands
                try:
                    import pywinauto
                    from pywinauto import Application
                    
                    # Connect to QuickBooks window
                    app = Application(backend="uia").connect(title_re=".*QuickBooks.*", timeout=5)
                    qb_window = app.top_window()
                    
                    logger.info("Found QuickBooks window via pywinauto")
                    
                    # Navigate menu: File -> Utilities -> Import -> IIF Files
                    # This is complex and fragile - better to use SDK if possible
                    logger.warning("UI automation for menu navigation is complex and may be unreliable")
                    logger.info("Recommendation: Use SDK ImportData method or manual import")
                    
                    return {
                        'success': False,
                        'message': 'UI automation not fully implemented - requires SDK ImportData or manual import',
                        'suggestion': 'Please use File -> Utilities -> Import -> IIF Files in QuickBooks manually, or ensure SDK ImportData method is available'
                    }
                except ImportError:
                    logger.warning("pywinauto not installed - cannot use UI automation")
                    return {
                        'success': False,
                        'message': 'UI automation requires pywinauto library',
                        'suggestion': 'Install with: pip install pywinauto'
                    }
                except Exception as e:
                    logger.warning(f"UI automation failed: {e}")
                    return {
                        'success': False,
                        'message': f'UI automation error: {str(e)}'
                    }
            
            # If we got here with qb_app, we could try to use it
            # But QuickBooks doesn't typically expose import methods via COM
            return {
                'success': False,
                'message': 'UI automation not fully implemented',
                'suggestion': 'Use SDK ImportData method or manual import via QuickBooks UI'
            }
            
        except ImportError as e:
            return {
                'success': False,
                'message': f'UI automation requires additional libraries: {str(e)}',
                'suggestion': 'Install required libraries or use SDK ImportData method'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'UI automation error: {str(e)}'
            }
    
    def import_iif_from_url(self, iif_url: str, save_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Download IIF file from URL and import it
        
        Args:
            iif_url: URL to download IIF file from
            save_path: Optional path to save the file (default: temp directory)
            
        Returns:
            Import result dictionary
        """
        import tempfile
        import requests
        import time
        
        if save_path is None:
            # Create temp file
            temp_dir = tempfile.gettempdir()
            timestamp = int(time.time())
            save_path = os.path.join(temp_dir, f"qb_import_{timestamp}.iif")
        
        try:
            logger.info(f"Downloading IIF file from: {iif_url}")
            
            # Download file
            response = requests.get(iif_url, timeout=30)
            response.raise_for_status()
            
            # Save to file
            with open(save_path, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"Downloaded IIF file to: {save_path}")
            
            # Import the file
            result = self.import_iif_file(save_path)
            
            # Clean up temp file if it was created
            if save_path.startswith(tempfile.gettempdir()):
                try:
                    os.remove(save_path)
                    logger.debug(f"Cleaned up temp file: {save_path}")
                except:
                    pass
            
            return result
            
        except Exception as e:
            error_msg = f"Failed to download/import IIF from URL: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'message': error_msg,
                'errors': [str(e)]
            }
