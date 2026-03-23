"""
QuickBooks Web Connector Controller

Provides SOAP endpoints for QuickBooks Web Connector integration.
QB Web Connector polls these endpoints to sync transactions to QuickBooks Desktop.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import PlainTextResponse
import xml.etree.ElementTree as ET
import logging
import html
import json
from datetime import datetime
from pathlib import Path
import os
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.db.base import get_db
from app.services.qb_queue_service import QBQueueService
from app.services.qbxml_service import QBXMLService
from app.models.qb_transaction_queue import QBTransactionStatus
from app.models.workspace import Workspace

# Setup logging
logger = logging.getLogger(__name__)

# Determine log directory - try multiple locations
# 1. Check if LOG_DIR environment variable is set
# 2. Try relative to current working directory
# 3. Try relative to this file's location (backend/app/controllers)
LOG_DIR = None
if os.getenv("LOG_DIR"):
    LOG_DIR = Path(os.getenv("LOG_DIR"))
elif Path("logs").exists():
    LOG_DIR = Path("logs").resolve()
else:
    # Try relative to backend directory
    backend_dir = Path(__file__).parent.parent.parent
    LOG_DIR = backend_dir / "logs"

# Ensure log directory exists
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Create file handler for QB Web Connector logs
qbwc_log_file = LOG_DIR / "qb_web_connector.log"
file_handler = logging.FileHandler(str(qbwc_log_file), encoding='utf-8')
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.setLevel(logging.INFO)

# Log initial message to verify logging works
logger.info("=" * 60)
logger.info("QB Web Connector Service Started")
logger.info(f"Log file: {qbwc_log_file}")
logger.info(f"Log directory: {LOG_DIR}")
logger.info(f"Current working directory: {os.getcwd()}")
logger.info("=" * 60)

router = APIRouter(tags=["QuickBooks Web Connector"])

# Session state tracking for QBWC handshake
# States: "HOST_QUERY_PENDING", "COMPANY_QUERY_PENDING", "READY_FOR_WORK"
_qbwc_session_states: dict[str, str] = {}

# CRITICAL: Track if a SalesReceiptAdd was created in the current session
# QuickBooks Desktop cannot reference a TxnID created in the same session
# This flag prevents processing pending_deposit transactions in the same session
_sales_receipt_created_this_session: dict[str, bool] = {}


def get_session_state(ticket: str) -> str:
    """Get current session state for a ticket. Defaults to HOST_QUERY_PENDING."""
    return _qbwc_session_states.get(ticket, "HOST_QUERY_PENDING")


def set_session_state(ticket: str, state: str) -> None:
    """Set session state for a ticket."""
    _qbwc_session_states[ticket] = state
    logger.info(f"Session state updated - Ticket: {ticket}, State: {state}")


def mark_sales_receipt_created(ticket: str) -> None:
    """Mark that a SalesReceiptAdd was created in this session for the given ticket."""
    _sales_receipt_created_this_session[ticket] = True
    logger.info(f"Marked SalesReceiptAdd created in current session - Ticket: {ticket}")


def has_sales_receipt_created_this_session(ticket: str) -> bool:
    """Check if a SalesReceiptAdd was created in the current session."""
    return _sales_receipt_created_this_session.get(ticket, False)


def clear_sales_receipt_flag(ticket: str) -> None:
    """Clear the SalesReceiptAdd flag for a ticket (called when session ends or new session starts)."""
    was_set = ticket in _sales_receipt_created_this_session
    _sales_receipt_created_this_session.pop(ticket, None)
    if was_set:
        logger.info(f"Cleared SalesReceiptAdd flag for ticket: {ticket} (was previously set)")
    else:
        logger.debug(f"Cleared SalesReceiptAdd flag for ticket: {ticket} (was not set)")


@router.post("")
async def qbwc_endpoint(request: Request, db: Session = Depends(get_db)):
    """Main QB Web Connector SOAP endpoint"""
    body = await request.body()
    content_type = request.headers.get("content-type", "")
    client_ip = request.client.host if request.client else "unknown"
    
    logger.info(f"=== QB Web Connector Request ===")
    logger.info(f"IP: {client_ip}")
    logger.info(f"Content-Type: {content_type}")
    logger.info(f"Request Body Length: {len(body)} bytes")
    
    if "text/xml" in content_type or "application/soap+xml" in content_type:
        # Log first 500 chars of request
        try:
            body_preview = body.decode('utf-8')[:500]
            logger.info(f"Request Preview:\n{body_preview}")
        except:
            logger.info("Request body (binary or non-UTF8)")
        
        response = await handle_soap_request(body, db)
        
        # Log response preview
        if hasattr(response, 'body'):
            try:
                response_preview = response.body.decode('utf-8')[:500] if isinstance(response.body, bytes) else str(response.body)[:500]
                logger.info(f"Response Preview:\n{response_preview}")
            except:
                pass
        
        logger.info(f"=== End Request ===\n")
        return response
    else:
        logger.info("Non-SOAP request received")
        return PlainTextResponse("QB Web Connector Service", status_code=200)


@router.get("")
async def qbwc_get(request: Request):
    """WSDL endpoint - QB Web Connector fetches this to validate the service"""
    client_ip = request.client.host if request.client else "unknown"
    
    # Check if WSDL is requested
    if "wsdl" in str(request.url.query).lower():
        logger.info(f"WSDL requested from IP: {client_ip}")
        logger.info(f"WSDL request URL: {request.url}")
        
        # Try to serve static WSDL file first
        static_wsdl_path = Path(__file__).parent.parent / "static" / "qbwc.wsdl"
        if static_wsdl_path.exists():
            logger.info(f"Serving static WSDL file: {static_wsdl_path}")
            with open(static_wsdl_path, 'r', encoding='utf-8') as f:
                wsdl_content = f.read()
            return PlainTextResponse(wsdl_content, media_type="text/xml")
        else:
            # Fallback to generated WSDL
            logger.info("Static WSDL not found, using generated WSDL")
            return PlainTextResponse(get_wsdl(), media_type="text/xml")
    
    logger.info(f"Health check from IP: {client_ip}")
    logger.info(f"Health check URL: {request.url}")
    return PlainTextResponse("QB Web Connector Service is running")


async def handle_soap_request(body: bytes, db: Session) -> PlainTextResponse:
    """Handle SOAP requests from QB Web Connector"""
    try:
        xml_str = body.decode('utf-8')
        root = ET.fromstring(xml_str)
        
        # Find SOAP body
        body_elem = root.find('.//{http://schemas.xmlsoap.org/soap/envelope/}Body')
        if body_elem is None:
            logger.error("Invalid SOAP request - no Body element found")
            return soap_fault("Invalid SOAP request")
        
        # Handle different QBWC methods
        for child in body_elem:
            method_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            logger.info(f"Processing method: {method_name}")
            
            if method_name == "authenticate":
                return handle_authenticate(child, db)
            elif method_name == "sendRequestXML":
                return handle_send_request(child, db)
            elif method_name == "receiveResponseXML":
                return handle_receive_response(child, db)
            elif method_name == "connectionError":
                return handle_connection_error(child)
            elif method_name == "getLastError":
                return handle_get_last_error()
            elif method_name == "closeConnection":
                return handle_close_connection()
            elif method_name == "serverVersion":
                return handle_server_version()
            elif method_name == "clientVersion":
                return handle_client_version(child)
        
        logger.warning(f"Unknown method: {method_name}")
        return soap_fault("Unknown method")
    except Exception as e:
        logger.error(f"Error handling SOAP request: {e}", exc_info=True)
        return soap_fault(str(e))


def handle_authenticate(element, db: Session) -> PlainTextResponse:
    """Handle authentication request"""
    username = ""
    password = ""
    
    for child in element:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if tag == "strUserName":
            username = child.text or ""
        elif tag == "strPassword":
            password = child.text or ""
    
    logger.info(f"=== Authentication attempt ===")
    logger.info(f"Username: '{username}' (length: {len(username)})")
    logger.info(f"Password provided: {'Yes' if password else 'No'} (length: {len(password) if password else 0})")
    
    # Simple authentication (implement proper auth in production)
    # For now, username format: "workspace_id:username" or just "username"
    # Password: "admin" (or implement proper password check)
    
    workspace_id = None
    if ':' in username:
        # Format: "workspace_id:username"
        parts = username.split(':', 1)
        try:
            workspace_id = int(parts[0])
            username = parts[1]
        except ValueError:
            pass
    
    # If no workspace_id in username, get default workspace
    if workspace_id is None:
        # Get first workspace (or implement user-based lookup)
        workspace = db.query(Workspace).first()
        if workspace:
            workspace_id = workspace.id
            logger.info(f"Using default workspace: {workspace_id}")
        else:
            logger.error("No workspace found in database")
            workspace_id = None
    
    # Validate authentication
    from app.core.config import settings
    
    # Get configured credentials (can be overridden via environment variables)
    qbwc_username = os.getenv('QBWC_USERNAME', settings.QBWC_USERNAME)
    qbwc_password = os.getenv('QBWC_PASSWORD', settings.QBWC_PASSWORD)
    
    logger.info(f"Validating - Username: {username}, Password length: {len(password)}")
    logger.info(f"Expected username: {qbwc_username}, Expected password length: {len(qbwc_password)}")
    
    # Accept configured username/password or "admin"/"admin" for backward compatibility
    if (username == qbwc_username and password == qbwc_password) or (username == "admin" and password == "admin"):
        if workspace_id:
            # Create ticket with workspace_id
            ticket = f"sync-accounting-{workspace_id}"
            logger.info(f"✓ Authentication successful - Ticket: {ticket}, Workspace: {workspace_id}")
            
            # CRITICAL: Clear SalesReceiptAdd flag for new session
            # This ensures DepositAdd can be processed in this new session
            clear_sales_receipt_flag(ticket)
            logger.info(f"✓ Cleared SalesReceiptAdd flag for new session - Ticket: {ticket}")
            
            # CRITICAL: Clear account manager cache for new session
            # Account names must be fetched fresh from QuickBooks via AccountQuery
            # This ensures we use exact account names (case/whitespace sensitive)
            from app.services.qb_account_manager import get_account_manager
            account_manager = get_account_manager(workspace_id)
            account_manager.known_accounts.clear()
            account_manager.pending_accounts.clear()
            account_manager.failed_accounts.clear()
            logger.info(f"Cleared account manager cache for workspace {workspace_id} - will run AccountQuery first")
            # Return ticket and empty string for company file (empty string = no specific company file required, but still allow sync)
            # Returning empty string instead of "none" to ensure QBWC calls sendRequestXML
            response = f"""<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<authenticateResponse xmlns="http://developer.intuit.com/">
<authenticateResult>
<string>{ticket}</string>
<string></string>
</authenticateResult>
</authenticateResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
        else:
            logger.error("Authentication failed: No workspace available")
            response = """<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<authenticateResponse xmlns="http://developer.intuit.com/">
<authenticateResult>
<string>nvu</string>
<string>No workspace available</string>
</authenticateResult>
</authenticateResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    else:
        logger.warning(f"✗ Authentication failed for username: {username}")
        response = """<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<authenticateResponse xmlns="http://developer.intuit.com/">
<authenticateResult>
<string>nvu</string>
<string>Invalid username or password</string>
</authenticateResult>
</authenticateResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    
    return PlainTextResponse(response, media_type="text/xml")


def handle_send_request(element, db: Session) -> PlainTextResponse:
    """Handle sendRequestXML - return QBXML request to process"""
    logger.info("=" * 60)
    logger.info("=== sendRequestXML CALLED ===")
    logger.info("=" * 60)
    
    ticket = ""
    company_file = ""
    hcp_response = ""
    
    for child in element:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if tag == "ticket":
            ticket = child.text or ""
        elif tag == "strCompanyFileName":
            company_file = child.text or ""
        elif tag == "strHCPResponse":
            hcp_response = child.text or ""
    
    logger.info(f"sendRequestXML called - Ticket: {ticket}, Company File: {company_file}")
    
    # CRITICAL: Parse strHCPResponse to detect handshake responses and update state
    # QuickBooks sends previous response in strHCPResponse (HTML-encoded XML)
    if hcp_response:
        try:
            # Decode HTML entities (e.g., &lt; becomes <)
            decoded_response = html.unescape(hcp_response)
            root = ET.fromstring(decoded_response)
            
            # Check for HostQueryRs → update state to COMPANY_QUERY_PENDING
            host_query_rs = root.find('.//HostQueryRs')
            if host_query_rs is not None:
                logger.info("=" * 60)
                logger.info("=== DETECTED HostQueryRs in strHCPResponse - UPDATING STATE TO COMPANY_QUERY_PENDING ===")
                logger.info("=" * 60)
                set_session_state(ticket, "COMPANY_QUERY_PENDING")
            
            # Check for CompanyQueryRs → update state to READY_FOR_WORK
            company_query_rs = root.find('.//CompanyQueryRs')
            if company_query_rs is not None:
                logger.info("=" * 60)
                logger.info("=== DETECTED CompanyQueryRs in strHCPResponse - UPDATING STATE TO READY_FOR_WORK ===")
                logger.info("=" * 60)
                set_session_state(ticket, "READY_FOR_WORK")
        except Exception as parse_error:
            logger.warning(f"Could not parse strHCPResponse: {parse_error}")
            logger.debug(f"strHCPResponse content (first 500 chars): {hcp_response[:500]}")
    
    # Extract workspace_id from ticket (format: "sync-accounting-{workspace_id}")
    workspace_id = None
    if ticket.startswith("sync-accounting-"):
        try:
            workspace_id = int(ticket.split("-")[-1])
        except ValueError:
            logger.error(f"Invalid ticket format: {ticket}")
            workspace_id = None
    
    if not workspace_id:
        logger.warning("No workspace_id in ticket, returning empty response")
        response = """<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
        return PlainTextResponse(response, media_type="text/xml")
    
    # Get queued transactions for this workspace
    logger.info(f"=== sendRequestXML: Looking for queued transactions - workspace_id: {workspace_id} ===")
    
    # Debug: Check total count of queued transactions using raw SQL to avoid any ORM issues
    from app.models.qb_transaction_queue import QBTransactionQueue
    from sqlalchemy import text
    
    # Try direct SQL query to see what's actually in the database
    raw_count = db.execute(
        text("SELECT COUNT(*) FROM qb_transaction_queue WHERE workspace_id = :workspace_id AND status = :status"),
        {"workspace_id": workspace_id, "status": "queued"}
    ).scalar()
    logger.info(f"Raw SQL count for workspace {workspace_id} with status 'queued': {raw_count}")
    
    # Also try ORM query
    total_queued = db.query(QBTransactionQueue).filter(
        and_(
            QBTransactionQueue.workspace_id == workspace_id,
            QBTransactionQueue.status == 'queued'
        )
    ).count()
    logger.info(f"ORM count for workspace {workspace_id} with status 'queued': {total_queued}")
    
    # Check all statuses for debugging
    all_statuses = db.query(
        QBTransactionQueue.status,
        func.count(QBTransactionQueue.id).label('count')
    ).filter(
        QBTransactionQueue.workspace_id == workspace_id
    ).group_by(QBTransactionQueue.status).all()
    
    logger.info(f"Transaction status breakdown for workspace {workspace_id}:")
    for status, count in all_statuses:
        logger.info(f"  - Status '{status}' (type: {type(status).__name__}): {count} records")
    
    # Try to get a sample record to see what the actual status value is
    sample_record = db.query(QBTransactionQueue).filter(
        QBTransactionQueue.workspace_id == workspace_id
    ).first()
    if sample_record:
        logger.info(f"Sample record - ID: {sample_record.id}, Status: '{sample_record.status}' (type: {type(sample_record.status).__name__}), Workspace: {sample_record.workspace_id}")
    
    # CRITICAL: QuickBooks Desktop Web Connector REQUIRES strict handshake sequence:
    # 1. First sendRequestXML → HostQueryRq
    # 2. After HostQueryRs → CompanyQueryRq  
    # 3. After CompanyQueryRs → Business queries (AccountQuery, Deposits, etc.)
    # Skipping this sequence causes 0x80040400 errors!
    
    session_state = get_session_state(ticket)
    logger.info(f"Session state for ticket {ticket}: {session_state}")
    
    # Step 1: Send HostQueryRq (first sendRequestXML call)
    if session_state == "HOST_QUERY_PENDING":
        logger.info("=== QBWC Handshake Step 1: Sending HostQueryRq ===")
        host_query_xml = QBXMLService.generate_host_query(request_id="1")
        logger.info(f"HostQuery first 120 chars (repr): {repr(host_query_xml[:120])}")
        
        response = f"""<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult><![CDATA[{host_query_xml}]]></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
        return PlainTextResponse(response, media_type="text/xml")
    
    # Step 2: Send CompanyQueryRq (after HostQueryRs received)
    if session_state == "COMPANY_QUERY_PENDING":
        logger.info("=== QBWC Handshake Step 2: Sending CompanyQueryRq ===")
        company_query_xml = QBXMLService.generate_company_query(request_id="1")
        logger.info(f"CompanyQuery first 120 chars (repr): {repr(company_query_xml[:120])}")
        
        response = f"""<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult><![CDATA[{company_query_xml}]]></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
        return PlainTextResponse(response, media_type="text/xml")
    
    # Step 3: Now we can send business queries (AccountQuery, transactions, etc.)
    if session_state == "READY_FOR_WORK":
        from app.services.qb_account_manager import get_account_manager
        account_manager = get_account_manager(workspace_id)
        
        # First, check if we need to initialize account manager with AccountQuery
        if not account_manager.is_initialized():
            logger.info("=== Account manager not initialized - running AccountQuery ===")
            account_query_xml = account_manager.generate_account_query_request()
            logger.info(f"AccountQuery first 120 chars (repr): {repr(account_query_xml[:120])}")
            
            response = f"""<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult><![CDATA[{account_query_xml}]]></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
            return PlainTextResponse(response, media_type="text/xml")
        
        # After AccountQuery, check if we need to query/create Customer and Items for DEPOSIT transactions
        # Check if there are any DEPOSIT transactions queued
        has_deposit_transactions = False
        queue_entries_sample = QBQueueService.get_queued_transactions(db, workspace_id, limit=1)
        if queue_entries_sample:
            queue_entry = queue_entries_sample[0]
            if queue_entry.transaction_data.get('transaction_type', '').upper() == 'DEPOSIT':
                has_deposit_transactions = True
        
        # CRITICAL: Check if setup is complete for deposits
        # If setup is complete, skip all query/create checks and proceed directly to transaction processing
        if has_deposit_transactions and account_manager.is_setup_complete_for_deposits():
            logger.info("=== Setup complete for DEPOSIT transactions - proceeding to transaction processing ===")
            # Fall through to transaction processing (lines below)
        elif has_deposit_transactions:
            # Setup not complete - run queries/creations
            # Check if we need to query customers (only if query hasn't completed yet)
            if not account_manager.customer_query_completed:
                logger.info("=== Querying customers for DEPOSIT transactions ===")
                customer_query_xml = account_manager.generate_customer_query_request()
                response = f"""<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult><![CDATA[{customer_query_xml}]]></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
                return PlainTextResponse(response, media_type="text/xml")
            
            # Check if we need to query items (only if query hasn't completed yet)
            if not account_manager.item_query_completed:
                logger.info("=== Querying items for DEPOSIT transactions ===")
                item_query_xml = account_manager.generate_item_query_request()
                response = f"""<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult><![CDATA[{item_query_xml}]]></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
                return PlainTextResponse(response, media_type="text/xml")
        
        # Pattern B: All deposits now use direct DepositAdd (no pending_deposit handling needed)
        # Deposits are processed directly as regular queued transactions - no relationships required
        
        # After AccountQuery (or if already initialized), process transactions
        queue_entries = QBQueueService.get_queued_transactions(db, workspace_id, limit=1)
        logger.info(f"QBQueueService.get_queued_transactions returned {len(queue_entries)} entries (limit=1 for QB Desktop compatibility)")
        
        if not queue_entries:
            logger.warning(f"=== No queued transactions found for workspace {workspace_id} ===")
            logger.warning(f"Raw SQL count was: {raw_count}, ORM count was: {total_queued}")
            logger.warning(f"This means sendRequestXML will return empty, causing 'No data exchange required' message")
            response = """<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
            return PlainTextResponse(response, media_type="text/xml")
        
        # Process only the first transaction (we only fetch 1 anyway)
        queue_entry = queue_entries[0]
        
        logger.info(f"Processing single transaction: ID={queue_entry.id}, Type={queue_entry.transaction_data.get('transaction_type', 'UNKNOWN')}, Status={queue_entry.status}")
        
        # Get account manager for this workspace
        from app.services.qb_account_manager import get_account_manager
        account_manager = get_account_manager(workspace_id)
        
        # CRITICAL: Only process transactions with status='queued'
        if queue_entry.status != 'queued':
            logger.error(f"Transaction ID={queue_entry.id} has unexpected status '{queue_entry.status}' - expected 'queued'")
            logger.error(f"This transaction should not be processed here - skipping")
            response = """<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
            return PlainTextResponse(response, media_type="text/xml")
        
        # If account manager cache is empty, we should query accounts first
        # But if we have transactions queued, we'll try to create accounts on-demand
        # For DEPOSIT transactions, check/create Customer and Items first
        if queue_entry.transaction_data.get('transaction_type', '').upper() == 'DEPOSIT':
            # Check if "Bank Deposits" customer exists
            required_customer = account_manager.get_required_customer_for_deposit()
            if not account_manager.customer_exists(required_customer):
                # Check if already pending or failed
                is_pending = required_customer in account_manager.pending_customers.values()
                is_failed = required_customer in account_manager.failed_customers
                
                if not is_pending and not is_failed:
                    logger.info(f"=== Missing customer detected - will create '{required_customer}' ===")
                    customer_create_xml = account_manager.generate_customer_create_request(required_customer)
                    if customer_create_xml:
                        logger.info(f"Generated CustomerAdd request for '{required_customer}'")
                        response = f"""<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult><![CDATA[{customer_create_xml}]]></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
                        return PlainTextResponse(response, media_type="text/xml")
                    else:
                        logger.warning(f"Could not generate customer creation request for '{required_customer}' - proceeding anyway")
            
            # Check if required items exist
            required_items = account_manager.get_required_items_for_deposit(queue_entry.transaction_data)
            for item_name in required_items:
                if not account_manager.item_exists(item_name):
                    # Check if already pending or failed
                    is_pending = item_name in account_manager.pending_items.values()
                    is_failed = item_name in account_manager.failed_items
                    
                    if not is_pending and not is_failed:
                        logger.info(f"=== Missing item detected - will create '{item_name}' ===")
                        # Determine which account this item should map to
                        # CRITICAL: Items are NOT Accounts!
                        # "Bank Deposits" item maps to "Sales" account
                        # "Bank Interest" item maps to "Interest Income" account
                        if item_name == 'Bank Interest':
                            account_name = 'Interest Income'  # Account name (not item name)
                        else:
                            account_name = 'Sales'  # Account name (not item name)
                        
                        item_create_xml = account_manager.generate_item_create_request(item_name, account_name)
                        if item_create_xml:
                            # Log full XML for debugging (first 500 chars)
                            logger.info(f"Generated ItemNonInventoryAdd request for '{item_name}' (maps to '{account_name}')")
                            logger.debug(f"ItemNonInventoryAdd XML (first 500 chars): {item_create_xml[:500]}")
                            logger.debug(f"ItemNonInventoryAdd XML (full length: {len(item_create_xml)} chars)")
                            
                            # Verify XML is complete (not truncated)
                            if len(item_create_xml) < 100:
                                logger.error(f"ItemNonInventoryAdd XML appears truncated (length: {len(item_create_xml)} chars)")
                                logger.error(f"Full XML: {item_create_xml}")
                            
                            response = f"""<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult><![CDATA[{item_create_xml}]]></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
                            return PlainTextResponse(response, media_type="text/xml")
                        else:
                            logger.warning(f"Could not generate item creation request for '{item_name}' - proceeding anyway")
                    elif is_pending:
                        # Item creation is in progress - wait for it to complete
                        logger.info(f"Item '{item_name}' creation is pending - waiting for ItemNonInventoryAddRs before proceeding")
                        # Return empty response to wait for Item creation to complete
                        response = """<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
                        return PlainTextResponse(response, media_type="text/xml")
                    elif is_failed:
                        # Item creation failed - cannot proceed with SalesReceiptAddRq
                        logger.error(f"Item '{item_name}' creation failed - cannot proceed with SalesReceiptAddRq (Item doesn't exist)")
                        # Return empty response and mark transaction as failed
                        QBQueueService.mark_failed(db, queue_entry.id, f"Required item '{item_name}' creation failed - item doesn't exist in QuickBooks")
                        response = """<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
                        return PlainTextResponse(response, media_type="text/xml")
            
            # CRITICAL: Verify all required items exist before proceeding
            # Double-check after the loop to ensure we don't proceed if items are still missing
            for item_name in required_items:
                if not account_manager.item_exists(item_name):
                    logger.error(f"Required item '{item_name}' does not exist and cannot be created - blocking transaction")
                    QBQueueService.mark_failed(db, queue_entry.id, f"Required item '{item_name}' does not exist in QuickBooks")
                    response = """<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
                    return PlainTextResponse(response, media_type="text/xml")
        
        # For CHECK/WITHDRAWAL/FEE transactions, check/create Vendor first
        trans_type = queue_entry.transaction_data.get('transaction_type', '').upper()
        if trans_type in ['WITHDRAWAL', 'CHECK', 'FEE']:
            # Check if vendor query has been completed
            if not account_manager.vendor_query_completed:
                logger.info("=== Querying vendors for CHECK transactions ===")
                vendor_query_xml = account_manager.generate_vendor_query_request()
                response = f"""<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult><![CDATA[{vendor_query_xml}]]></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
                return PlainTextResponse(response, media_type="text/xml")
            
            # Check if "Bank Charges" vendor exists
            required_vendor = account_manager.get_required_vendor_for_check()
            if not account_manager.vendor_exists(required_vendor):
                # Check if already pending or failed
                is_pending = required_vendor in account_manager.pending_vendors.values()
                is_failed = required_vendor in account_manager.failed_vendors
                
                if is_pending:
                    logger.info(f"Vendor '{required_vendor}' creation is pending. Returning empty request to wait.")
                    response = """<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
                    return PlainTextResponse(response, media_type="text/xml")
                
                if is_failed:
                    logger.error(f"Vendor '{required_vendor}' failed creation previously. Marking transaction {queue_entry.id} as failed.")
                    QBQueueService.mark_failed(db, queue_entry.id, f"Required vendor '{required_vendor}' failed to create.")
                    response = """<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
                    return PlainTextResponse(response, media_type="text/xml")
                
                if not is_pending and not is_failed:
                    logger.info(f"=== Missing vendor detected - will create '{required_vendor}' ===")
                    vendor_create_xml = account_manager.generate_vendor_create_request(required_vendor)
                    if vendor_create_xml:
                        logger.info(f"Generated VendorAdd request for '{required_vendor}'")
                        response = f"""<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult><![CDATA[{vendor_create_xml}]]></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
                        return PlainTextResponse(response, media_type="text/xml")
                    else:
                        logger.warning(f"Could not generate vendor creation request for '{required_vendor}' - proceeding anyway")
        
        # Check if any accounts need to be created
        missing_accounts = account_manager.get_missing_accounts(queue_entry.transaction_data)
        
        if missing_accounts:
            logger.info(f"=== Missing accounts detected - will create them first ===")
            for account_name, account_type in missing_accounts:
                logger.info(f"  Need to create: '{account_name}' (type: {account_type})")
            
            # Create the first missing account (one at a time, per QB Desktop limitation)
            account_name, account_type = missing_accounts[0]
            logger.info(f"Creating account: '{account_name}' (type: {account_type})")
            
            account_create_xml = account_manager.generate_account_create_request(account_name, account_type)
            if account_create_xml:
                logger.info(f"Generated AccountAdd request for '{account_name}'")
                response = f"""<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult><![CDATA[{account_create_xml}]]></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
                return PlainTextResponse(response, media_type="text/xml")
            else:
                logger.warning(f"Could not generate account creation request for '{account_name}' - proceeding with transaction anyway")
        else:
            # No missing accounts - check if account manager cache is populated
            if len(account_manager.known_accounts) == 0:
                logger.warning("Account manager cache is empty - accounts may not exist in QuickBooks")
                logger.warning("This could cause transaction failures. Consider querying accounts first.")
        
        # Mark transaction as syncing
        QBQueueService.mark_syncing(db, queue_entry.id)
        
        # Get workspace account name: multi-company (company_file + company_account_map) or single workspace default
        workspace_account_name = None
        try:
            workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
            if workspace:
                if queue_entry.company_file and getattr(workspace, 'company_account_map', None) and isinstance(workspace.company_account_map, dict):
                    workspace_account_name = workspace.company_account_map.get(queue_entry.company_file)
                    if workspace_account_name:
                        logger.info(f"Using per-company account for '{queue_entry.company_file[:50]}...': '{workspace_account_name}'")
                if not workspace_account_name and workspace.quickbooks_account_name:
                    workspace_account_name = workspace.quickbooks_account_name
                    logger.info(f"Using workspace account name: '{workspace_account_name}'")
                if not workspace_account_name:
                    logger.warning(f"Workspace {workspace_id} has no quickbooks_account_name and no company_account_map for this company - will use fallback")
        except Exception as e:
            logger.warning(f"Failed to get workspace account name: {e}")
        
        # Generate qbXML for single transaction (pass account_manager and workspace_account_name)
        try:
            qbxml = QBQueueService.generate_qbxml_for_single_transaction(
                queue_entry, 
                account_manager,
                workspace_account_name=workspace_account_name
            )
            logger.info(f"Transaction qbXML first 120 chars (repr): {repr(qbxml[:120])}")
            
            # Validate qbXML is not empty
            if not qbxml or not qbxml.strip():
                logger.error("Generated qbXML is empty or None!")
                # Mark transaction as failed
                QBQueueService.mark_failed(db, queue_entry.id, "Generated qbXML was empty")
                # Return empty response with proper namespace
                response = """<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
                return PlainTextResponse(response, media_type="text/xml")
            
            # Store qbXML in queue entry
            queue_entry.qbxml_request = qbxml
            db.commit()
            
            logger.info(f"Generated qbXML for transaction ID={queue_entry.id}")
            logger.info(f"qbXML length: {len(qbxml)} characters")
            # Log full qbXML for debugging (this is critical for troubleshooting)
            logger.info(f"=== FULL qbXML BEING SENT TO QUICKBOOKS ===")
            logger.info(qbxml)
            logger.info(f"=== END qbXML ===")
            
            # CDATA section should not escape the content, but we need to ensure the CDATA itself is properly formatted
            # The qbXML should be wrapped in CDATA to avoid XML escaping issues
            # However, if CDATA contains "]]>", we need to split it (unlikely but possible)
            if "]]>" in qbxml:
                logger.warning("qbXML contains ']]>' which will break CDATA section - this should not happen")
                # Replace with a safe alternative or split CDATA sections
                qbxml = qbxml.replace("]]>", "]]]]><![CDATA[>")
            
            # Ensure qbXML is a string and not None
            qbxml_str = str(qbxml) if qbxml else ""
            
            response = f"""<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult><![CDATA[{qbxml_str}]]></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
            
            # Validate response is not empty
            if not response or not response.strip():
                logger.error("Response XML is empty!")
                raise ValueError("Response XML is empty")
            
            return PlainTextResponse(response, media_type="text/xml")
        except Exception as e:
            logger.error(f"Error generating qbXML: {e}", exc_info=True)
            # Mark transaction as failed
            QBQueueService.mark_failed(db, queue_entry.id, f"Error generating qbXML: {str(e)}")
            
            response = """<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse xmlns="http://developer.intuit.com/">
<sendRequestXMLResult></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
            return PlainTextResponse(response, media_type="text/xml")


def handle_receive_response(element, db: Session) -> PlainTextResponse:
    """Handle receiveResponseXML - process QB response"""
    ticket = ""
    response_xml = ""
    hresult = ""
    message = ""
    
    for child in element:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if tag == "ticket":
            ticket = child.text or ""
        elif tag == "response":
            response_xml = child.text or ""
        elif tag == "hresult":
            hresult = child.text or ""
        elif tag == "message":
            message = child.text or ""
    
    logger.info(f"=== Received QB Response ===")
    logger.info(f"Ticket: {ticket}")
    logger.info(f"HResult: {hresult}")
    logger.info(f"Message: {message}")
    logger.info(f"Response XML Length: {len(response_xml)} bytes")
    
    # Extract workspace_id from ticket
    workspace_id = None
    if ticket.startswith("sync-accounting-"):
        try:
            workspace_id = int(ticket.split("-")[-1])
        except ValueError:
            logger.error(f"Invalid ticket format: {ticket}")
    
    # Get transactions that are currently syncing for this workspace
    syncing_entries = []
    if workspace_id:
        from app.models.qb_transaction_queue import QBTransactionQueue
        syncing_entries = db.query(QBTransactionQueue).filter(
            and_(
                QBTransactionQueue.workspace_id == workspace_id,
                QBTransactionQueue.status == 'syncing'
            )
        ).order_by(QBTransactionQueue.last_sync_attempt.desc()).limit(10).all()
    
    # CRITICAL: Check for handshake responses FIRST, before any other processing
    # This MUST happen even if response_xml parsing fails, to update session state
    if response_xml:
        try:
            root = ET.fromstring(response_xml)
            
            # CRITICAL: Check for handshake responses and update session state IMMEDIATELY
            # HostQueryRs → move to COMPANY_QUERY_PENDING
            host_query_rs = root.find('.//HostQueryRs')
            if host_query_rs is not None:
                logger.info("=" * 60)
                logger.info("=== RECEIVED HostQueryRs - UPDATING STATE TO COMPANY_QUERY_PENDING ===")
                logger.info("=" * 60)
                set_session_state(ticket, "COMPANY_QUERY_PENDING")
                logger.info(f"Session state updated successfully for ticket {ticket}")
            
            # CompanyQueryRs → move to READY_FOR_WORK
            company_query_rs = root.find('.//CompanyQueryRs')
            if company_query_rs is not None:
                logger.info("=" * 60)
                logger.info("=== RECEIVED CompanyQueryRs - UPDATING STATE TO READY_FOR_WORK ===")
                logger.info("=" * 60)
                set_session_state(ticket, "READY_FOR_WORK")
                logger.info(f"Session state updated successfully for ticket {ticket}")
        except Exception as parse_error:
            logger.error(f"Error parsing response XML for handshake detection: {parse_error}")
            logger.error(f"Response XML (first 500 chars): {response_xml[:500]}")
    
    if response_xml:
        # Parse response for transaction processing
        parsed_response = QBXMLService.parse_qbxml_response(response_xml)
        
        # Try to parse and log key information
        try:
            root = ET.fromstring(response_xml)
            
            # Check if this is a CustomerQuery response - if so, update account manager
            # IMPORTANT: Check for CustomerQueryRs (not just CustomerRet) to handle empty results
            customer_query_rs = root.find('.//CustomerQueryRs')
            if customer_query_rs is not None and workspace_id:
                logger.info("=" * 60)
                logger.info("=== CUSTOMER QUERY RESPONSE - Available Customers in QuickBooks ===")
                logger.info("=" * 60)
                
                from app.services.qb_account_manager import get_account_manager
                account_manager = get_account_manager(workspace_id)
                account_manager.update_from_customer_query_response(response_xml)
            
            # Check if this is an ItemQuery response - if so, update account manager
            # IMPORTANT: Check for ItemQueryRs (not just item ret elements) to handle empty results
            item_query_rs = root.find('.//ItemQueryRs')
            if item_query_rs is not None and workspace_id:
                logger.info("=" * 60)
                logger.info("=== ITEM QUERY RESPONSE - Available Items in QuickBooks ===")
                logger.info("=" * 60)
                
                from app.services.qb_account_manager import get_account_manager
                account_manager = get_account_manager(workspace_id)
                account_manager.update_from_item_query_response(response_xml)
            
            # Check if this is a VendorQuery response - if so, update account manager
            # IMPORTANT: Check for VendorQueryRs (not just VendorRet) to handle empty results
            vendor_query_rs = root.find('.//VendorQueryRs')
            if vendor_query_rs is not None and workspace_id:
                logger.info("=" * 60)
                logger.info("=== VENDOR QUERY RESPONSE - Available Vendors in QuickBooks ===")
                logger.info("=" * 60)
                
                from app.services.qb_account_manager import get_account_manager
                account_manager = get_account_manager(workspace_id)
                account_manager.update_from_vendor_query_response(response_xml)
            
            # Check if this is an AccountQuery response - if so, update account manager
            account_ret_list = root.findall('.//AccountRet')
            if account_ret_list:
                logger.info("=" * 60)
                logger.info("=== ACCOUNT QUERY RESPONSE - Available Accounts in QuickBooks ===")
                logger.info("=" * 60)
                
                # Update account manager with known accounts
                if workspace_id:
                    from app.services.qb_account_manager import get_account_manager
                    account_manager = get_account_manager(workspace_id)
                    account_manager.update_from_account_query_response(response_xml)
                
                bank_accounts = []
                income_accounts = []
                other_accounts = []
                for account in account_ret_list:
                    name_elem = account.find('Name')
                    type_elem = account.find('AccountType')
                    if name_elem is not None and type_elem is not None:
                        account_name = name_elem.text
                        account_type = type_elem.text
                        if account_type == 'Bank':
                            bank_accounts.append(account_name)
                            logger.info(f"  ✓ Bank Account: '{account_name}'")
                        elif account_type == 'Income':
                            income_accounts.append(account_name)
                            logger.info(f"  ✓ Income Account: '{account_name}'")
                        else:
                            other_accounts.append((account_name, account_type))
                            logger.info(f"  ✓ {account_type} Account: '{account_name}'")
                
                logger.info("=" * 60)
                logger.info(f"SUMMARY: Found {len(bank_accounts)} Bank Account(s), {len(income_accounts)} Income Account(s)")
                logger.info("=" * 60)
            
            # Check if this is a CustomerAdd response - update account manager
            customer_add_rs = root.find('.//CustomerAddRs')
            if customer_add_rs is not None and workspace_id:
                request_id_attr = customer_add_rs.get('requestID')
                logger.info(f"=== CustomerAdd Response - RequestID: {request_id_attr} ===")
                
                from app.services.qb_account_manager import get_account_manager
                account_manager = get_account_manager(workspace_id)
                
                success = account_manager.update_from_customer_add_response(response_xml, request_id_attr)
                if success:
                    customer_name = None
                    if request_id_attr and request_id_attr in account_manager.pending_customers:
                        customer_name = account_manager.pending_customers.get(request_id_attr)
                    elif account_manager.pending_customers:
                        customer_name = list(account_manager.pending_customers.values())[0]
                    
                    if customer_name:
                        logger.info(f"✓ Customer '{customer_name}' is now available - transactions can proceed")
                else:
                    logger.error(f"✗ Failed to create customer - check QuickBooks permissions and customer name")
            
            # Check if this is an ItemNonInventoryAdd response - update account manager
            item_add_rs = root.find('.//ItemNonInventoryAddRs')
            if item_add_rs is not None and workspace_id:
                request_id_attr = item_add_rs.get('requestID')
                logger.info(f"=== ItemNonInventoryAdd Response - RequestID: {request_id_attr} ===")
                
                from app.services.qb_account_manager import get_account_manager
                account_manager = get_account_manager(workspace_id)
                
                success = account_manager.update_from_item_add_response(response_xml, request_id_attr)
                if success:
                    item_name = None
                    if request_id_attr and request_id_attr in account_manager.pending_items:
                        item_name = account_manager.pending_items.get(request_id_attr)
                    elif account_manager.pending_items:
                        item_name = list(account_manager.pending_items.values())[0]
                    
                    if item_name:
                        logger.info(f"✓ Item '{item_name}' is now available - transactions can proceed")
                else:
                    logger.error(f"✗ Failed to create item - check QuickBooks permissions and item name")
            
            # Check if this is a VendorAdd response - update account manager
            vendor_add_rs = root.find('.//VendorAddRs')
            if vendor_add_rs is not None and workspace_id:
                request_id_attr = vendor_add_rs.get('requestID')
                logger.info(f"=== VendorAdd Response - RequestID: {request_id_attr} ===")
                
                from app.services.qb_account_manager import get_account_manager
                account_manager = get_account_manager(workspace_id)
                
                success = account_manager.update_from_vendor_add_response(response_xml, request_id_attr)
                if success:
                    vendor_name = None
                    if request_id_attr and request_id_attr in account_manager.pending_vendors:
                        vendor_name = account_manager.pending_vendors.get(request_id_attr)
                    elif account_manager.pending_vendors:
                        vendor_name = list(account_manager.pending_vendors.values())[0]
                    
                    if vendor_name:
                        logger.info(f"✓ Vendor '{vendor_name}' is now available - transactions can proceed")
                else:
                    logger.error(f"✗ Failed to create vendor - check QuickBooks permissions and vendor name")
            
            # Check if this is an AccountAdd response - update account manager
            account_add_rs = root.find('.//AccountAddRs')
            if account_add_rs is not None and workspace_id:
                # Get requestID from the response to identify which account was created
                request_id_attr = account_add_rs.get('requestID')
                
                logger.info(f"=== AccountAdd Response - RequestID: {request_id_attr} ===")
                
                from app.services.qb_account_manager import get_account_manager
                account_manager = get_account_manager(workspace_id)
                
                # Update account manager with the response
                success = account_manager.update_from_account_add_response(response_xml, request_id_attr)
                if success:
                    # Find which account was created
                    account_name = None
                    if request_id_attr and request_id_attr in account_manager.pending_accounts:
                        account_name = account_manager.pending_accounts.get(request_id_attr)
                    elif account_manager.pending_accounts:
                        account_name = list(account_manager.pending_accounts.values())[0]
                    
                    if account_name:
                        logger.info(f"✓ Account '{account_name}' is now available - transactions can proceed")
                else:
                    logger.error(f"✗ Failed to create account - check QuickBooks permissions and account name")
            
            # Log status codes if present
            status_codes = root.findall('.//statusCode')
            status_messages = root.findall('.//statusMessage')
            
            if status_codes:
                for sc in status_codes:
                    logger.info(f"Status Code: {sc.text}")
            if status_messages:
                for sm in status_messages:
                    logger.info(f"Status Message: {sm.text}")
            
            # Log first 2000 chars of response (increased for account query responses)
            logger.info(f"Response Preview:\n{response_xml[:2000]}")
        except Exception as e:
            logger.warning(f"Could not parse response XML: {e}")
            logger.info(f"Raw Response (first 500 chars):\n{response_xml[:500]}")
        
        # Update transaction status based on response
        if syncing_entries:
            results = parsed_response.get('results', [])
            
            for idx, entry in enumerate(syncing_entries):
                if idx < len(results):
                    result = results[idx]
                    response_type = result.get('responseType', '')
                    txn_id = result.get('txnID')
                    
                    if result.get('success'):
                        # Pattern B: All transactions (including DepositAddRs) are fully synced directly
                        # No pending_deposit handling needed - deposits use direct DepositAdd with AccountRef
                        QBQueueService.mark_synced(db, entry.id, response_xml, txn_id)
                        logger.info(f"Transaction fully synced: {entry.id} (Pattern B - direct deposit, no relationships)")
                    else:
                        error_msg = result.get('statusMessage', 'Unknown error')
                        QBQueueService.mark_failed(db, entry.id, error_msg)
                        logger.error(f"Transaction failed: {entry.id} - {error_msg}")
                else:
                    # No result for this entry, mark as failed
                    QBQueueService.mark_failed(db, entry.id, "No response received")
                    logger.warning(f"No response received for transaction: {entry.id}")
            
            if parsed_response.get('success'):
                logger.info(f"All transactions processed successfully")
            else:
                failed_count = len([r for r in results if not r.get('success')])
                logger.warning(f"Some transactions failed: {failed_count}")
        else:
            logger.warning("No syncing transactions found to update")
    
    # Check for errors
    if hresult and hresult != "0":
        error_details = f"QB Error - HResult: {hresult}, Message: {message}"
        logger.error(f"=== QuickBooks Error ===")
        logger.error(error_details)
        
        # CRITICAL: Handle 0x80040400 errors for setup operations (ItemAdd, VendorAdd, CustomerAdd)
        # When 0x80040400 occurs, response_xml is often empty, so we can't parse ItemNonInventoryAddRs/VendorAddRs/CustomerAddRs
        # We need to mark pending setup entities as FAILED to prevent infinite waiting
        if hresult == "0x80040400" and workspace_id and not syncing_entries:
            logger.error("0x80040400 error detected with no syncing transactions - likely setup operation failure")
            
            from app.services.qb_account_manager import get_account_manager
            account_manager = get_account_manager(workspace_id)
            
            # Mark all pending items/vendors/customers as FAILED
            # This prevents the system from waiting forever for a response that will never come
            failed_setup_entities = []
            
            # Check pending items
            if account_manager.pending_items:
                for request_id, item_name in list(account_manager.pending_items.items()):
                    account_manager.failed_items.add(item_name)
                    account_manager.pending_items.pop(request_id, None)
                    failed_setup_entities.append(f"Item '{item_name}'")
                    logger.error(f"✗ Marked pending item '{item_name}' as FAILED due to 0x80040400 error")
            
            # Check pending vendors
            if account_manager.pending_vendors:
                for request_id, vendor_name in list(account_manager.pending_vendors.items()):
                    account_manager.failed_vendors.add(vendor_name)
                    account_manager.pending_vendors.pop(request_id, None)
                    failed_setup_entities.append(f"Vendor '{vendor_name}'")
                    logger.error(f"✗ Marked pending vendor '{vendor_name}' as FAILED due to 0x80040400 error")
            
            # Check pending customers
            if account_manager.pending_customers:
                for request_id, customer_name in list(account_manager.pending_customers.items()):
                    account_manager.failed_customers.add(customer_name)
                    account_manager.pending_customers.pop(request_id, None)
                    failed_setup_entities.append(f"Customer '{customer_name}'")
                    logger.error(f"✗ Marked pending customer '{customer_name}' as FAILED due to 0x80040400 error")
            
            if failed_setup_entities:
                logger.error(f"FATAL SETUP ERROR: The following setup operations failed with 0x80040400 (XML parsing error):")
                for entity in failed_setup_entities:
                    logger.error(f"  - {entity}")
                logger.error("STOPPING transaction processing until setup XML is fixed.")
                logger.error("Please check the XML generation code for these entities and verify:")
                logger.error("  1. All XML tags are properly closed")
                logger.error("  2. No XML declaration (<?xml version='1.0'?>) for Add/Mod requests")
                logger.error("  3. All required elements are present")
                logger.error("  4. Element order matches QuickBooks SDK requirements")
            
            # Return success to continue, but setup is now marked as failed
            response = """<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<receiveResponseXMLResponse xmlns="http://developer.intuit.com/">
<receiveResponseXMLResult>0</receiveResponseXMLResult>
</receiveResponseXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
            return PlainTextResponse(response, media_type="text/xml")
        
        # If AccountQuery fails, log error but don't mark transactions as failed
        # AccountQuery errors should be handled separately
        if not syncing_entries:
            # No syncing transactions - might be AccountQuery error
            logger.error("Error occurred but no syncing transactions - might be AccountQuery failure")
            logger.error("AccountQuery is required for proper account resolution - transactions may fail with 3120 errors")
            # Return success to continue, but log the error
            response = """<?xml version="1.0" encoding="utf-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<receiveResponseXMLResponse xmlns="http://developer.intuit.com/">
<receiveResponseXMLResult>0</receiveResponseXMLResult>
</receiveResponseXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
            return PlainTextResponse(response, media_type="text/xml")
        
        # Log the full response XML for debugging
        if response_xml:
            logger.error(f"Full QB Response XML:\n{response_xml}")
            
            # Try to extract more detailed error information from response
            try:
                # ET is already imported at the top of the file
                root = ET.fromstring(response_xml)
                
                # Look for statusCode and statusMessage in the response
                for status_code in root.findall('.//statusCode'):
                    logger.error(f"QB Status Code: {status_code.text}")
                for status_msg in root.findall('.//statusMessage'):
                    logger.error(f"QB Status Message: {status_msg.text}")
                for detail in root.findall('.//statusDetail'):
                    logger.error(f"QB Status Detail: {detail.text}")
                    
            except Exception as e:
                logger.warning(f"Could not parse error details from response: {e}")
        
        # Mark syncing transactions as failed with detailed error
        for entry in syncing_entries:
            # Include transaction-specific troubleshooting information
            trans_data = entry.transaction_data
            trans_type = trans_data.get('transaction_type', '').upper()
            # Get account name from transaction data or use a generic placeholder
            account_name = trans_data.get('account') or trans_data.get('workspace_account_name') or 'bank account'
            
            detailed_error = f"{error_details}\nAccount: '{account_name}'"
            
            # Transaction-type specific error messages
            if trans_type in ['WITHDRAWAL', 'CHECK', 'FEE']:
                # Check-specific troubleshooting
                expense_account = trans_data.get('expense_account', 'Miscellaneous Expense')
                detailed_error += f", Expense Account: '{expense_account}'"
                detailed_error += "\n\nTROUBLESHOOTING FOR CHECK:"
                detailed_error += "\n1. Verify bank account name exists in QuickBooks (Lists > Chart of Accounts)"
                detailed_error += "\n2. Verify expense account name exists in QuickBooks"
                detailed_error += "\n3. Verify vendor 'Bank Charges' exists (Vendors > Vendor List)"
                detailed_error += "\n4. Account and vendor names must match EXACTLY (case-sensitive)"
            elif trans_type == 'DEPOSIT':
                # Deposit-specific troubleshooting
                # Pattern B: Direct deposit - no Undeposited Funds involved
                # Get workspace account name from the transaction entry if available
                workspace_account = trans_data.get('workspace_account_name') or trans_data.get('account', 'workspace account')
                detailed_error += f", Deposit To Account: '{workspace_account}'"
                detailed_error += "\n\nTROUBLESHOOTING FOR DEPOSIT:"
                detailed_error += "\n1. Verify bank account name exists in QuickBooks (Lists > Chart of Accounts)"
                detailed_error += "\n2. Verify 'Sales' account exists (Income account for DepositLineAdd)"
                detailed_error += "\n3. Verify 'Undeposited Funds' is DISABLED in Preferences > Payments > Company Preferences"
                detailed_error += "\n4. Account names must match EXACTLY (case-sensitive)"
            
            QBQueueService.mark_failed(db, entry.id, detailed_error)
            logger.error(f"Transaction {entry.id} failed: {detailed_error}")
    
    logger.info(f"=== End QB Response ===\n")
    
    response = """<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<receiveResponseXMLResponse>
<receiveResponseXMLResult>0</receiveResponseXMLResult>
</receiveResponseXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return PlainTextResponse(response, media_type="text/xml")


def handle_connection_error(element) -> PlainTextResponse:
    """Handle connection errors from QuickBooks"""
    ticket = ""
    hresult = ""
    message = ""
    
    for child in element:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if tag == "ticket":
            ticket = child.text or ""
        elif tag == "hresult":
            hresult = child.text or ""
        elif tag == "message":
            message = child.text or ""
    
    logger.error("=" * 60)
    logger.error("=== QuickBooks Connection Error ===")
    logger.error(f"Ticket: {ticket}")
    logger.error(f"HResult: {hresult}")
    logger.error(f"Message: {message}")
    logger.error("=" * 60)
    
    # Common connection errors:
    # 0x80040408 = "Could not start QuickBooks"
    # This usually means:
    # 1. QuickBooks Desktop is not running
    # 2. Company file is not open
    # 3. QuickBooks needs to be restarted
    
    if hresult == "0x80040408" or "Could not start QuickBooks" in message:
        logger.error("TROUBLESHOOTING:")
        logger.error("1. Ensure QuickBooks Desktop is running")
        logger.error("2. Open your company file in QuickBooks")
        logger.error("3. Try restarting QuickBooks Desktop")
        logger.error("4. Check if QuickBooks is in single-user mode")
    
    logger.error("=" * 60)
    error_msg = ""
    for child in element:
        if "error" in child.tag.lower():
            error_msg = child.text or ""
    
    logger.error(f"=== QB Connection Error ===")
    logger.error(f"Error: {error_msg}")
    logger.error(f"=== End Connection Error ===\n")
    
    response = """<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<connectionErrorResponse>
<connectionErrorResult>done</connectionErrorResult>
</connectionErrorResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return PlainTextResponse(response, media_type="text/xml")


def handle_get_last_error() -> PlainTextResponse:
    """Handle getLastError request"""
    logger.info("getLastError called - no errors to report")
    response = """<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<getLastErrorResponse>
<getLastErrorResult></getLastErrorResult>
</getLastErrorResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return PlainTextResponse(response, media_type="text/xml")


def handle_close_connection() -> PlainTextResponse:
    """Handle closeConnection"""
    logger.info("closeConnection called - connection closed")
    
    # CRITICAL: Defensive cleanup - clear all SalesReceiptAdd flags on session close
    # This ensures no flag leakage between sessions
    if _sales_receipt_created_this_session:
        cleared_count = len(_sales_receipt_created_this_session)
        _sales_receipt_created_this_session.clear()
        logger.info(f"Cleared {cleared_count} SalesReceiptAdd flag(s) on session close (defensive cleanup)")
    response = """<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<closeConnectionResponse>
<closeConnectionResult>OK</closeConnectionResult>
</closeConnectionResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return PlainTextResponse(response, media_type="text/xml")


def handle_server_version() -> PlainTextResponse:
    """Handle serverVersion - optional method to report server version"""
    logger.info("serverVersion called - returning version")
    # Return empty string to indicate we don't support versioning (optional method)
    response = """<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<serverVersionResponse xmlns="http://developer.intuit.com/">
<serverVersionResult></serverVersionResult>
</serverVersionResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return PlainTextResponse(response, media_type="text/xml")


def handle_client_version(element) -> PlainTextResponse:
    """Handle clientVersion - optional method to receive QBWC version"""
    client_version = ""
    for child in element:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if tag == "strVersion":
            client_version = child.text or ""
    
    logger.info(f"clientVersion called - QBWC Version: {client_version}")
    # Return empty string to indicate we don't support versioning (optional method)
    response = """<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<clientVersionResponse xmlns="http://developer.intuit.com/">
<clientVersionResult></clientVersionResult>
</clientVersionResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return PlainTextResponse(response, media_type="text/xml")


def soap_fault(message: str) -> PlainTextResponse:
    """Return SOAP fault"""
    response = f"""<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<SOAP-ENV:Fault>
<faultcode>SOAP-ENV:Server</faultcode>
<faultstring>{message}</faultstring>
</SOAP-ENV:Fault>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return PlainTextResponse(response, media_type="text/xml", status_code=500)


def get_wsdl() -> str:
    """Return WSDL description with AppDesc - this is what QB Web Connector validates"""
    # Complete WSDL with all QBWC methods and AppDesc in correct location
    # AppDesc must be in <appinfo> within <annotation> under <definitions>
    # Reference: https://static.developer.intuit.com/resources/QBWC_proguide.pdf
    wsdl = '''<?xml version="1.0" encoding="utf-8"?>
<definitions xmlns="http://schemas.xmlsoap.org/wsdl/" 
             xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/" 
             xmlns:tns="http://developer.intuit.com/" 
             xmlns:xsd="http://www.w3.org/2001/XMLSchema"
             targetNamespace="http://developer.intuit.com/">
    <annotation>
        <appinfo>
            <AppDesc>Sync Accounting - Automated bank statement and check data sync to QuickBooks Desktop</AppDesc>
        </appinfo>
    </annotation>
    <types>
        <xsd:schema targetNamespace="http://developer.intuit.com/">
            <xsd:element name="authenticate">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="strUserName" type="xsd:string"/>
                        <xsd:element name="strPassword" type="xsd:string"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
            <xsd:element name="authenticateResponse">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="authenticateResult" type="xsd:string"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
            <xsd:element name="sendRequestXML">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="ticket" type="xsd:string"/>
                        <xsd:element name="strHCPResponse" type="xsd:string"/>
                        <xsd:element name="strCompanyFileName" type="xsd:string"/>
                        <xsd:element name="qbXMLCountry" type="xsd:string"/>
                        <xsd:element name="qbXMLMajorVers" type="xsd:int"/>
                        <xsd:element name="qbXMLMinorVers" type="xsd:int"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
            <xsd:element name="sendRequestXMLResponse">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="sendRequestXMLResult" type="xsd:string"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
            <xsd:element name="receiveResponseXML">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="ticket" type="xsd:string"/>
                        <xsd:element name="response" type="xsd:string"/>
                        <xsd:element name="hresult" type="xsd:string"/>
                        <xsd:element name="message" type="xsd:string"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
            <xsd:element name="receiveResponseXMLResponse">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="receiveResponseXMLResult" type="xsd:int"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
            <xsd:element name="connectionError">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="ticket" type="xsd:string"/>
                        <xsd:element name="hresult" type="xsd:string"/>
                        <xsd:element name="message" type="xsd:string"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
            <xsd:element name="connectionErrorResponse">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="connectionErrorResult" type="xsd:string"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
            <xsd:element name="getLastError">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="ticket" type="xsd:string"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
            <xsd:element name="getLastErrorResponse">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="getLastErrorResult" type="xsd:string"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
            <xsd:element name="closeConnection">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="ticket" type="xsd:string"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
            <xsd:element name="closeConnectionResponse">
                <xsd:complexType>
                    <xsd:sequence>
                        <xsd:element name="closeConnectionResult" type="xsd:string"/>
                    </xsd:sequence>
                </xsd:complexType>
            </xsd:element>
        </xsd:schema>
    </types>
    <message name="authenticateRequest">
        <part name="parameters" element="tns:authenticate"/>
    </message>
    <message name="authenticateResponse">
        <part name="parameters" element="tns:authenticateResponse"/>
    </message>
    <message name="sendRequestXMLRequest">
        <part name="parameters" element="tns:sendRequestXML"/>
    </message>
    <message name="sendRequestXMLResponse">
        <part name="parameters" element="tns:sendRequestXMLResponse"/>
    </message>
    <message name="receiveResponseXMLRequest">
        <part name="parameters" element="tns:receiveResponseXML"/>
    </message>
    <message name="receiveResponseXMLResponse">
        <part name="parameters" element="tns:receiveResponseXMLResponse"/>
    </message>
    <message name="connectionErrorRequest">
        <part name="parameters" element="tns:connectionError"/>
    </message>
    <message name="connectionErrorResponse">
        <part name="parameters" element="tns:connectionErrorResponse"/>
    </message>
    <message name="getLastErrorRequest">
        <part name="parameters" element="tns:getLastError"/>
    </message>
    <message name="getLastErrorResponse">
        <part name="parameters" element="tns:getLastErrorResponse"/>
    </message>
    <message name="closeConnectionRequest">
        <part name="parameters" element="tns:closeConnection"/>
    </message>
    <message name="closeConnectionResponse">
        <part name="parameters" element="tns:closeConnectionResponse"/>
    </message>
    <portType name="QBWebConnectorSvcSoap">
        <operation name="authenticate">
            <input message="tns:authenticateRequest"/>
            <output message="tns:authenticateResponse"/>
        </operation>
        <operation name="sendRequestXML">
            <input message="tns:sendRequestXMLRequest"/>
            <output message="tns:sendRequestXMLResponse"/>
        </operation>
        <operation name="receiveResponseXML">
            <input message="tns:receiveResponseXMLRequest"/>
            <output message="tns:receiveResponseXMLResponse"/>
        </operation>
        <operation name="connectionError">
            <input message="tns:connectionErrorRequest"/>
            <output message="tns:connectionErrorResponse"/>
        </operation>
        <operation name="getLastError">
            <input message="tns:getLastErrorRequest"/>
            <output message="tns:getLastErrorResponse"/>
        </operation>
        <operation name="closeConnection">
            <input message="tns:closeConnectionRequest"/>
            <output message="tns:closeConnectionResponse"/>
        </operation>
    </portType>
    <binding name="QBWebConnectorSvcSoap" type="tns:QBWebConnectorSvcSoap">
        <soap:binding transport="http://schemas.xmlsoap.org/soap/http" style="document"/>
        <operation name="authenticate">
            <soap:operation soapAction="http://developer.intuit.com/authenticate"/>
            <input><soap:body use="literal"/></input>
            <output><soap:body use="literal"/></output>
        </operation>
        <operation name="sendRequestXML">
            <soap:operation soapAction="http://developer.intuit.com/sendRequestXML"/>
            <input><soap:body use="literal"/></input>
            <output><soap:body use="literal"/></output>
        </operation>
        <operation name="receiveResponseXML">
            <soap:operation soapAction="http://developer.intuit.com/receiveResponseXML"/>
            <input><soap:body use="literal"/></input>
            <output><soap:body use="literal"/></output>
        </operation>
        <operation name="connectionError">
            <soap:operation soapAction="http://developer.intuit.com/connectionError"/>
            <input><soap:body use="literal"/></input>
            <output><soap:body use="literal"/></output>
        </operation>
        <operation name="getLastError">
            <soap:operation soapAction="http://developer.intuit.com/getLastError"/>
            <input><soap:body use="literal"/></input>
            <output><soap:body use="literal"/></output>
        </operation>
        <operation name="closeConnection">
            <soap:operation soapAction="http://developer.intuit.com/closeConnection"/>
            <input><soap:body use="literal"/></input>
            <output><soap:body use="literal"/></output>
        </operation>
    </binding>
    <service name="QBWebConnectorSvc">
        <port name="QBWebConnectorSvcSoap" binding="tns:QBWebConnectorSvcSoap">
            <soap:address location="https://dev-sync-api.kylientlabs.com/qbwc"/>
        </port>
    </service>
</definitions>'''
    return wsdl

