"""
Sync Service
Polls backend API for queued transactions and syncs to QuickBooks via SDK
"""

import logging
import time
import requests
from typing import Optional, Dict, Any, List
from qb_sdk_service import QBSDKService
from qbxml_generator import QBXMLGenerator
from account_manager import AccountManager

logger = logging.getLogger(__name__)


class SyncService:
    """Service that syncs queued transactions to QuickBooks"""
    
    def __init__(
        self,
        backend_url: str,
        api_token: str,
        workspace_id: int,
        company_file: str,
        workspace_account_name: Optional[str] = None
    ):
        """
        Initialize sync service
        
        Args:
            backend_url: Backend API URL (e.g., "https://dev-sync-api.kylientlabs.com")
            api_token: JWT token for API authentication
            workspace_id: Workspace ID to sync
            company_file: Path to QuickBooks company file (.QBW)
            workspace_account_name: Optional account name from workspace settings
        """
        self.backend_url = backend_url.rstrip('/')
        self.api_token = api_token
        self.workspace_id = workspace_id
        self.company_file = company_file
        self.workspace_account_name = workspace_account_name
        self.qb_sdk = None
        self.account_manager = AccountManager()
        self.running = False
        self.poll_interval = 5  # seconds
        
    def start(self):
        """Start the sync service"""
        if self.running:
            logger.warning("Sync service already running")
            return
        
        logger.info("Starting sync service...")
        logger.info(f"Backend URL: {self.backend_url}")
        logger.info(f"Workspace ID: {self.workspace_id}")
        logger.info(f"Company File: {self.company_file}")
        
        # Initialize QuickBooks connection
        try:
            self.qb_sdk = QBSDKService()
            self.qb_sdk.open_connection()
            self.qb_sdk.begin_session(self.company_file)
            logger.info("Connected to QuickBooks Desktop")
            
            # Initialize account manager by querying accounts
            self._initialize_account_manager()
        except Exception as e:
            logger.error(f"Failed to connect to QuickBooks: {e}")
            raise
        
        self.running = True
        
        # Start polling loop
        try:
            while self.running:
                self._sync_cycle()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            logger.info("Sync service stopped by user")
        except Exception as e:
            logger.error(f"Sync service error: {e}", exc_info=True)
        finally:
            self.stop()
    
    def stop(self):
        """Stop the sync service"""
        logger.info("Stopping sync service...")
        self.running = False
        
        if self.qb_sdk:
            try:
                self.qb_sdk.close_connection()
            except Exception as e:
                logger.warning(f"Error closing QB connection: {e}")
    
    def _sync_cycle(self):
        """Single sync cycle - poll and process transactions"""
        try:
            # Get queued transactions
            queue_entries = self._get_queued_transactions()
            
            if not queue_entries:
                return
            
            logger.info(f"Found {len(queue_entries)} queued transactions")
            
            # Process each transaction
            for entry in queue_entries:
                try:
                    self._sync_transaction(entry)
                except Exception as e:
                    logger.error(f"Error syncing transaction {entry.get('id')}: {e}", exc_info=True)
                    # Mark as failed
                    self._update_transaction_status(entry['id'], 'failed', str(e))
        
        except Exception as e:
            logger.error(f"Error in sync cycle: {e}", exc_info=True)
    
    def _get_queued_transactions(self) -> List[Dict[str, Any]]:
        """Get queued transactions from backend API"""
        url = f"{self.backend_url}/api/v1/qb-queue/list"
        headers = {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json'
        }
        params = {
            'workspace_id': self.workspace_id,
            'status': 'queued',
            'limit': 10
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('transactions', [])
        except Exception as e:
            logger.error(f"Failed to get queued transactions: {e}")
            return []
    
    def _sync_transaction(self, entry: Dict[str, Any]):
        """Sync a single transaction to QuickBooks"""
        queue_id = entry['id']
        transaction_data = entry['transaction_data']
        
        logger.info(f"Syncing transaction {queue_id} (type: {transaction_data.get('transaction_type')})")
        
        # Mark as syncing
        self._update_transaction_status(queue_id, 'syncing')
        
        # Two-step flow: add Vendor/Customer first (separate XML), then CheckAdd/DepositAdd (separate XML)
        request_id = f"trans-{queue_id}"
        transaction_data['_queue_id'] = queue_id
        
        entity_xml = None
        transaction_xml = None
        try:
            # Step 1: Entity only (VendorAddRq or CustomerAddRq) - one request per envelope
            entity_xml = QBXMLGenerator.generate_entity_add_xml(
                transaction_data,
                request_id=request_id
            )
            entity_response_xml = self.qb_sdk.process_request(entity_xml)
            # 3100 "already in use" is OK; we proceed to add the transaction.
            # Use ListID for CheckAdd/DepositAdd (PayeeEntityRef/EntityRef) so QB resolves payee reliably.
            payee_list_id = QBXMLGenerator.parse_entity_add_response(entity_response_xml)
            if not payee_list_id:
                # Entity already existed (e.g. 3100) so we didn't get ListID from Add; query by name.
                payee_name = QBXMLGenerator.get_payee_name_for_entity(transaction_data)
                trans_type = (transaction_data.get('transaction_type') or '').upper()
                if trans_type in ['WITHDRAWAL', 'CHECK', 'FEE']:
                    query_xml = QBXMLGenerator.generate_vendor_query_xml(payee_name, request_id)
                elif trans_type == 'DEPOSIT':
                    query_xml = QBXMLGenerator.generate_customer_query_xml(payee_name, request_id)
                else:
                    query_xml = None
                if query_xml:
                    try:
                        query_response = self.qb_sdk.process_request(query_xml)
                        payee_list_id = QBXMLGenerator.parse_entity_query_response(query_response)
                    except Exception as e:
                        logger.warning(f"Entity query failed for payee {payee_name!r}: {e}; will use FullName")

            # Step 2: Transaction only (CheckAddRq or DepositAddRq).
            # CheckAdd: use ListID when we have it so payee shows in register.
            # DepositAdd: always use FullName for EntityRef (QB register does not show payee for deposits; ListID can break DepositAdd).
            trans_type = (transaction_data.get('transaction_type') or '').upper()
            payee_list_id_for_txn = payee_list_id if trans_type in ['WITHDRAWAL', 'CHECK', 'FEE'] else None
            transaction_xml = QBXMLGenerator.generate_transaction_only_xml(
                transaction_data,
                request_id=request_id,
                account_manager=self.account_manager,
                workspace_account_name=self.workspace_account_name,
                payee_list_id=payee_list_id_for_txn
            )
            response_xml = self.qb_sdk.process_request(transaction_xml)

            parsed = QBXMLGenerator.parse_response(response_xml)

            if parsed['success']:
                # Extract transaction ID from response if available
                qb_transaction_id = None
                if parsed.get('results'):
                    try:
                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(response_xml)
                        for tag in ('CheckRet', 'DepositRet', 'SalesReceiptRet'):
                            ret = root.find(f'.//{tag}')
                            if ret is not None:
                                txn_id_el = ret.find('TxnID')
                                if txn_id_el is not None and txn_id_el.text:
                                    qb_transaction_id = txn_id_el.text
                                    break
                    except Exception:
                        pass
                
                # Mark as synced
                self._update_transaction_status(
                    queue_id,
                    'synced',
                    response_xml=response_xml,
                    qb_transaction_id=qb_transaction_id
                )
                logger.info(f"Transaction {queue_id} synced successfully")
            else:
                # Mark as failed
                error_msg = parsed.get('results', [{}])[0].get('statusMessage', 'Unknown error')
                self._update_transaction_status(queue_id, 'failed', error_message=error_msg)
                logger.error(f"Transaction {queue_id} failed: {error_msg}")
                if transaction_xml:
                    logger.error("QB transaction XML sent (transaction %s):\n%s", queue_id, transaction_xml)
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error processing transaction {queue_id}: {error_msg}")
            if entity_xml:
                logger.error("QB entity XML sent (transaction %s):\n%s", queue_id, entity_xml)
            if transaction_xml:
                logger.error("QB transaction XML sent (transaction %s):\n%s", queue_id, transaction_xml)
            self._update_transaction_status(queue_id, 'failed', error_message=error_msg)
            raise
    
    def _initialize_account_manager(self):
        """Initialize account manager by querying QuickBooks for accounts"""
        try:
            logger.info("Initializing account manager...")
            account_query_xml = QBXMLGenerator.generate_account_query()
            response_xml = self.qb_sdk.process_request(account_query_xml)
            self.account_manager.update_from_account_query_response(response_xml)
            logger.info(f"Account manager initialized with {len(self.account_manager.known_accounts)} accounts")
        except Exception as e:
            logger.warning(f"Failed to initialize account manager: {e}")
            logger.warning("Account resolution may be less accurate")
    
    def _update_transaction_status(
        self,
        queue_id: int,
        status: str,
        error_message: Optional[str] = None,
        response_xml: Optional[str] = None,
        qb_transaction_id: Optional[str] = None
    ):
        """Update transaction status via backend API"""
        url = f"{self.backend_url}/api/v1/qb-queue/update-status"
        headers = {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json'
        }
        params = {
            'workspace_id': self.workspace_id
        }
        data = {
            'queue_id': queue_id,
            'status': status,
        }
        
        if error_message:
            data['error_message'] = error_message
        if response_xml:
            data['response_xml'] = response_xml
        if qb_transaction_id:
            data['qb_transaction_id'] = qb_transaction_id
        
        try:
            response = requests.post(url, headers=headers, params=params, json=data, timeout=10)
            if response.status_code == 404:
                # Endpoint doesn't exist yet - log and continue
                logger.warning(f"Status update endpoint not available. Transaction {queue_id} status: {status}")
                return
            response.raise_for_status()
            logger.debug(f"Updated transaction {queue_id} status to {status}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to update transaction status: {e}")
            # Don't fail the sync if status update fails

