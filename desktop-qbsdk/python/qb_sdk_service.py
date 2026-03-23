"""
QuickBooks SDK Service
Handles direct connection to QuickBooks Desktop using COM SDK
"""

import sys
import os
import logging
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Windows-only
if sys.platform != 'win32':
    raise RuntimeError("QuickBooks SDK only works on Windows")


class QBSDKService:
    """Service for connecting to QuickBooks Desktop via SDK"""
    
    def __init__(self):
        self.qb = None
        self.connection_ticket = None
        self.session_ticket = None
        self.company_file = None
        self._connection_opened = False  # True after first successful OpenConnection (ticket may be None)
        self._initialize_com()
    
    def _initialize_com(self):
        """Initialize COM object for QuickBooks"""
        try:
            import win32com.client
            # Try different COM object versions (QBXMLRP2 = SDK 3.0+; QBXMLRP = older)
            com_objects = [
                "QBXMLRP2.RequestProcessor.2",
                "QBXMLRP2.RequestProcessor",
                "QBXMLRP.RequestProcessor",
            ]
            last_error = None
            for com_obj in com_objects:
                try:
                    self.qb = win32com.client.Dispatch(com_obj)
                    logger.info(f"Successfully initialized COM object: {com_obj}")
                    return
                except Exception as e:
                    last_error = e
                    logger.info(f"COM {com_obj} failed: {e}")
                    continue
            
            err_msg = str(last_error) if last_error else "Unknown"
            raise RuntimeError(
                "Could not create QuickBooks COM object. "
                "QuickBooks Desktop must be installed and running. "
                "If you see 'Class not registered' or '80040154', install the QuickBooks Desktop SDK from Intuit (it registers QBXMLRP2). "
                "Details: %s" % err_msg
            )
        except ImportError:
            raise RuntimeError("pywin32 is required. Install with: pip install pywin32")
    
    def is_quickbooks_running(self) -> bool:
        """Check if QuickBooks Desktop is running"""
        try:
            import psutil
            for proc in psutil.process_iter(['pid', 'name']):
                name = proc.info['name'].lower()
                if 'qbw' in name or 'quickbooks' in name:
                    return True
            return False
        except ImportError:
            logger.warning("psutil not available, cannot check if QB is running")
            return True  # Assume running if we can't check
    
    def open_connection(self, app_name: str = "QB Accounting SDK") -> str:
        """
        Open connection to QuickBooks
        
        Args:
            app_name: Application name for QuickBooks
            
        Returns:
            Connection ticket
        """
        if not self.is_quickbooks_running():
            raise RuntimeError("QuickBooks Desktop must be running. Please open QuickBooks Desktop and your company file.")
        
        # SDK allows only one OpenConnection per COM instance; calling again raises.
        if self._connection_opened:
            logger.info("Connection already open, reusing (ticket: %s)", self.connection_ticket)
            return self.connection_ticket
        
        try:
            self.connection_ticket = self.qb.OpenConnection("", app_name)
            self._connection_opened = True
            logger.info(f"Opened connection to QuickBooks (ticket: {self.connection_ticket})")
            return self.connection_ticket
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to open connection: {error_msg}")
            raise RuntimeError(f"Failed to open QuickBooks connection: {error_msg}")
    
    def begin_session(self, company_file: str, open_mode: int = 0) -> str:
        """
        Begin session with QuickBooks company file

        Args:
            company_file: Path to .QBW file
            open_mode: 0 = Single user, 1 = Multi-user

        Returns:
            Session ticket
        """
        if not self._connection_opened:
            self.open_connection()

        if not os.path.exists(company_file):
            raise FileNotFoundError(f"Company file not found: {company_file}")

        # Normalize path: absolute, real path, Windows backslashes (QB can be sensitive to path format)
        company_file = os.path.normpath(os.path.abspath(company_file))
        logger.info(f"BeginSession path: {company_file}")

        try:
            self.session_ticket = self.qb.BeginSession(company_file, open_mode)
            self.company_file = company_file
            logger.info(f"Started session with {company_file} (session ticket: {self.session_ticket})")
            return self.session_ticket
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to begin session: {error_msg}")
            if "Could not start QuickBooks" in error_msg or "-2147220472" in error_msg or "0x80040408" in error_msg:
                raise RuntimeError(
                    "Could not start QuickBooks session (error 80040408). Try:\n"
                    "1. Open QuickBooks Desktop and open this company file: %s\n"
                    "2. Do NOT run QuickBooks or this app as Administrator (right-click -> Properties -> Compatibility -> uncheck Run as administrator).\n"
                    "3. Use the exact same path in Settings as shown in QuickBooks (File -> Open Previous).\n"
                    "4. QuickBooks is 32-bit: if you use 64-bit Python, install 32-bit Python and point the app to it so the SDK and QB match."
                    % company_file
                )
            raise RuntimeError(f"Failed to begin session: {error_msg}")
    
    def process_request(self, qbxml: str) -> str:
        """
        Send qbXML request to QuickBooks and get response
        
        Args:
            qbxml: qbXML request string
            
        Returns:
            qbXML response string
        """
        if not self.session_ticket:
            raise RuntimeError("No active session. Call begin_session() first.")
        
        log_dir = os.environ.get("LOG_DIR")
        try:
            from qb_request_logger import log_qb_request, log_qb_response
            log_qb_request(qbxml, log_dir=log_dir)
        except Exception as e:
            logger.debug("QB request logger: %s", e)
        
        # Validate QBXML before sending so parse errors surface locally with exact payload
        try:
            ET.fromstring(qbxml)
        except ET.ParseError as e:
            logger.error("QBXML is invalid (truncated or malformed). Parse error: %s", e)
            logger.error("QBXML length: %d chars. First 500 chars: %s", len(qbxml), qbxml[:500] if qbxml else "")
            raise RuntimeError(f"QBXML validation failed before sending to QuickBooks: {e}") from e
        
        try:
            logger.debug(f"Sending qbXML request (length: {len(qbxml)} chars)")
            response = self.qb.ProcessRequest(self.session_ticket, qbxml)
            logger.debug(f"Received qbXML response (length: {len(response)} chars)")
            try:
                from qb_request_logger import log_qb_response
                log_qb_response(response, log_dir=log_dir)
            except Exception as e:
                logger.debug("QB response logger: %s", e)
            return response
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to process request: {error_msg}")
            raise RuntimeError(f"QuickBooks request failed: {error_msg}")
    
    def end_session(self):
        """End current session"""
        if self.session_ticket:
            try:
                self.qb.EndSession(self.session_ticket)
                logger.info("Ended QuickBooks session")
                self.session_ticket = None
                self.company_file = None
            except Exception as e:
                logger.warning(f"Failed to end session: {e}")
    
    def close_connection(self):
        """Close connection to QuickBooks"""
        self.end_session()
        
        if self._connection_opened:
            try:
                if self.connection_ticket:
                    self.qb.CloseConnection("", self.connection_ticket)
                logger.info("Closed QuickBooks connection")
            except Exception as e:
                logger.warning(f"Failed to close connection: {e}")
            finally:
                self.connection_ticket = None
                self._connection_opened = False
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup"""
        self.close_connection()
    
    def is_connected(self) -> bool:
        """Check if currently connected to QuickBooks"""
        return self.session_ticket is not None and self.connection_ticket is not None
    
    def import_iif_file(self, iif_file_path: str) -> Dict[str, Any]:
        """
        Import an IIF file into QuickBooks Desktop
        
        This is a convenience method that uses the IIFImporter class.
        For more control, use IIFImporter directly.
        
        Args:
            iif_file_path: Path to the .iif file to import
            
        Returns:
            Dictionary with success status and message
        """
        from iif_importer import IIFImporter
        importer = IIFImporter(self)
        return importer.import_iif_file(iif_file_path)
    
    def import_iif_file(self, iif_file_path: str) -> Dict[str, Any]:
        """
        Import an IIF file into QuickBooks Desktop
        
        This is a convenience method that uses the IIFImporter class.
        For more control, use IIFImporter directly.
        
        Args:
            iif_file_path: Path to the .iif file to import
            
        Returns:
            Dictionary with success status and message
        """
        from iif_importer import IIFImporter
        importer = IIFImporter(self)
        return importer.import_iif_file(iif_file_path)

