"""
QuickBooks Transaction Queue Service
Manages the queue of transactions waiting to be synced to QuickBooks Desktop
"""

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import and_, or_
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import logging

from app.models.qb_transaction_queue import QBTransactionQueue, QBTransactionStatus
from app.models.extracted_data import ExtractedData
from app.models.file import File
from app.services.qbxml_service import QBXMLService
from app.services.payee_service import PayeeService

logger = logging.getLogger(__name__)

# Transaction types that require a payee → QB expense account mapping (withdrawals/checks)
WITHDRAWAL_TYPES = frozenset({'WITHDRAWAL', 'CHECK', 'FEE'})


class QBQueueService:
    """Service for managing QuickBooks transaction queue"""
    
    @staticmethod
    def queue_transaction(
        db: Session,
        workspace_id: int,
        file_id: int,
        transaction_data: Dict[str, Any],
        transaction_index: Optional[int] = None,
        transaction_id: Optional[str] = None,
        company_file: Optional[str] = None
    ) -> QBTransactionQueue:
        """
        Add a transaction to the queue.
        
        Args:
            db: Database session
            workspace_id: Workspace ID
            file_id: File ID containing the transaction
            transaction_data: Full transaction data dictionary
            transaction_index: Index in transactions array (optional)
            transaction_id: Unique transaction ID (optional)
            company_file: QuickBooks company file path for multi-company (optional)
            
        Returns:
            Created QBTransactionQueue entry
        """
        # Check if transaction already queued
        existing = db.query(QBTransactionQueue).filter(
            and_(
                QBTransactionQueue.workspace_id == workspace_id,
                QBTransactionQueue.file_id == file_id,
                QBTransactionQueue.transaction_index == transaction_index,
                QBTransactionQueue.status.in_(['pending', 'queued', 'syncing'])
            )
        ).first()
        
        if existing:
            logger.info(f"Transaction already in queue: {existing.id}")
            return existing
        
        # Create new queue entry
        queue_entry = QBTransactionQueue(
            workspace_id=workspace_id,
            file_id=file_id,
            transaction_index=transaction_index,
            transaction_id=transaction_id,
            transaction_data=transaction_data,
            status=QBTransactionStatus.PENDING.value,  # Use .value to get string
            company_file=company_file
        )
        
        db.add(queue_entry)
        db.commit()
        db.refresh(queue_entry)
        
        logger.info(f"Transaction queued: {queue_entry.id}")
        return queue_entry

    @staticmethod
    def _get_withdrawal_payees_from_transactions(transaction_list: List[Dict[str, Any]]) -> List[str]:
        """Return unique payee names from transactions that are withdrawal/check/fee types."""
        payees = []
        seen = set()
        for t in transaction_list:
            trans_type = (t.get('transaction_type') or '').upper()
            if trans_type not in WITHDRAWAL_TYPES:
                continue
            payee = (t.get('payee') or '').strip()
            if payee and payee not in seen:
                seen.add(payee)
                payees.append(payee)
        return payees

    @staticmethod
    def _get_missing_payee_transactions(transaction_list: List[Dict[str, Any]], file_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return withdrawal/check/fee transactions that have no payee name at all."""
        result = []
        for i, t in enumerate(transaction_list):
            trans_type = (t.get('transaction_type') or '').upper()
            if trans_type not in WITHDRAWAL_TYPES:
                continue
            payee = (t.get('payee') or '').strip()
            if not payee:
                result.append({
                    "description": t.get('description', ''),
                    "amount": t.get('amount', 0),
                    "transaction_index": t.get('_transaction_index', i),
                    "transaction_type": trans_type,
                    "file_id": t.get('_file_id') or file_id,
                })
        return result

    @staticmethod
    def get_unmapped_payees(
        db: Session,
        workspace_id: int,
        file_ids: Optional[List[int]] = None,
        transaction_list: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Get payees that are used in withdrawal/check/fee transactions but have no qb_expense_account_name,
        plus transactions that have no payee at all (e.g. checks on bank statements).

        Returns:
            Tuple of (unmapped_payees, missing_payee_transactions)
            - unmapped_payees: List of { payee_name, payee_id } for payees without expense accounts
            - missing_payee_transactions: List of { description, amount, transaction_index, transaction_type, file_id }
        """
        all_payee_names = []
        all_missing_payee_txns = []
        if file_ids:
            for file_id in file_ids:
                file = db.query(File).filter(File.id == file_id, File.workspace_id == workspace_id).first()
                if not file:
                    continue
                ext = db.query(ExtractedData).filter(ExtractedData.file_id == file_id).first()
                if not ext or not ext.processed_data:
                    continue
                transactions = (ext.processed_data or {}).get('transactions') or (ext.raw_data or {}).get('transactions') or []
                all_payee_names.extend(QBQueueService._get_withdrawal_payees_from_transactions(transactions))
                all_missing_payee_txns.extend(QBQueueService._get_missing_payee_transactions(transactions, file_id))
        if transaction_list:
            all_payee_names.extend(QBQueueService._get_withdrawal_payees_from_transactions(transaction_list))
            all_missing_payee_txns.extend(QBQueueService._get_missing_payee_transactions(transaction_list))
        # Unique payee names
        payee_names = list(dict.fromkeys(all_payee_names))
        unmapped = []
        for name in payee_names:
            match = PayeeService.find_matching_payee(db, name, workspace_id, threshold=80)
            if not match:
                unmapped.append({"payee_name": name, "payee_id": None})
                continue
            payee, _ = match
            if not (payee.qb_expense_account_name and payee.qb_expense_account_name.strip()):
                unmapped.append({"payee_name": payee.display_name, "payee_id": payee.id})
        return unmapped, all_missing_payee_txns

    @staticmethod
    def resolve_expense_account_for_transaction(
        db: Session,
        workspace_id: int,
        transaction_data: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        For withdrawal/check/fee transactions, resolve payee → expense account and set transaction_data['expense_account'].
        If payee has no mapping, return (original_data, error_message); else return (data_with_expense_account, None).
        Caller should not queue when error_message is set.
        """
        trans_type = (transaction_data.get('transaction_type') or '').upper()
        if trans_type not in WITHDRAWAL_TYPES:
            return (transaction_data, None)
        payee_name = (transaction_data.get('payee') or '').strip()
        if not payee_name:
            return (transaction_data, "Withdrawal transaction has no payee.")
        match = PayeeService.find_matching_payee(db, payee_name, workspace_id, threshold=80)
        if not match:
            return (transaction_data, f"Payee '{payee_name}' is not mapped. Add a payee and set its QuickBooks expense account.")
        payee, _ = match
        if not (payee.qb_expense_account_name and payee.qb_expense_account_name.strip()):
            return (transaction_data, f"Payee '{payee.display_name}' has no QuickBooks expense account. Map it in Payees before syncing.")
        data = dict(transaction_data)
        data['expense_account'] = payee.qb_expense_account_name.strip()
        return (data, None)

    @staticmethod
    def approve_transaction(db: Session, queue_id: int) -> QBTransactionQueue:
        """
        Approve a transaction for syncing (move to QUEUED status).
        
        Args:
            db: Database session
            queue_id: Queue entry ID
            
        Returns:
            Updated QBTransactionQueue entry
        """
        queue_entry = db.query(QBTransactionQueue).filter(
            QBTransactionQueue.id == queue_id
        ).first()
        
        if not queue_entry:
            raise ValueError(f"Queue entry not found: {queue_id}")
        
        if queue_entry.status != QBTransactionStatus.PENDING.value:
            raise ValueError(f"Transaction status is {queue_entry.status}, cannot approve")
        
        queue_entry.status = QBTransactionStatus.QUEUED.value
        db.commit()
        db.refresh(queue_entry)
        
        logger.info(f"Transaction approved: {queue_id}")
        return queue_entry
    
    @staticmethod
    def approve_transactions(db: Session, queue_ids: List[int]) -> List[QBTransactionQueue]:
        """
        Approve multiple transactions for syncing.
        
        Args:
            db: Database session
            queue_ids: List of queue entry IDs
            
        Returns:
            List of updated QBTransactionQueue entries
        """
        queue_entries = db.query(QBTransactionQueue).filter(
            and_(
                QBTransactionQueue.id.in_(queue_ids),
                QBTransactionQueue.status == 'pending'
            )
        ).all()
        
        for entry in queue_entries:
            entry.status = QBTransactionStatus.QUEUED.value
        
        db.commit()
        
        for entry in queue_entries:
            db.refresh(entry)
        
        logger.info(f"Approved {len(queue_entries)} transactions")
        return queue_entries
    
    @staticmethod
    def reject_transaction(db: Session, queue_id: int) -> None:
        """
        Reject a transaction (delete from queue).
        
        Args:
            db: Database session
            queue_id: Queue entry ID
        """
        queue_entry = db.query(QBTransactionQueue).filter(
            QBTransactionQueue.id == queue_id
        ).first()
        
        if queue_entry:
            db.delete(queue_entry)
            db.commit()
            logger.info(f"Transaction rejected: {queue_id}")
    
    @staticmethod
    def get_queued_transactions(
        db: Session,
        workspace_id: int,
        limit: int = 10
    ) -> List[QBTransactionQueue]:
        """
        Get transactions queued for sync (ready for QB Web Connector).
        
        Args:
            db: Database session
            workspace_id: Workspace ID
            limit: Maximum number of transactions to return
            
        Returns:
            List of QBTransactionQueue entries with status QUEUED
        """
        logger.info(f"get_queued_transactions called - workspace_id: {workspace_id}, limit: {limit}")
        
        # First, check total count with raw SQL to verify data exists
        from sqlalchemy import text
        count_result = db.execute(
            text("SELECT COUNT(*) FROM qb_transaction_queue WHERE workspace_id = :ws_id AND status = 'queued'"),
            {"ws_id": workspace_id}
        ).scalar()
        logger.info(f"Raw SQL count for workspace {workspace_id} with status 'queued': {count_result}")
        
        # Also check what statuses actually exist
        status_check = db.execute(
            text("SELECT DISTINCT status FROM qb_transaction_queue WHERE workspace_id = :ws_id"),
            {"ws_id": workspace_id}
        ).fetchall()
        logger.info(f"Distinct statuses in DB for workspace {workspace_id}: {[s[0] for s in status_check]}")
        
        query = db.query(QBTransactionQueue).filter(
            and_(
                QBTransactionQueue.workspace_id == workspace_id,
                QBTransactionQueue.status == 'queued'
            )
        ).order_by(QBTransactionQueue.created_at.asc()).limit(limit)
        
        # Try to get the SQL statement (may not work in all SQLAlchemy versions)
        try:
            logger.info(f"Query filter: workspace_id={workspace_id}, status='queued'")
        except:
            pass
        
        results = query.all()
        logger.info(f"Query returned {len(results)} queued transactions")
        
        if results:
            logger.info(f"First transaction ID: {results[0].id}, status: {results[0].status}, created: {results[0].created_at}")
        
        return results
    
    @staticmethod
    def mark_syncing(db: Session, queue_id: int) -> QBTransactionQueue:
        """
        Mark transaction as currently syncing.
        
        Args:
            db: Database session
            queue_id: Queue entry ID
            
        Returns:
            Updated QBTransactionQueue entry
        """
        queue_entry = db.query(QBTransactionQueue).filter(
            QBTransactionQueue.id == queue_id
        ).first()
        
        if queue_entry:
            queue_entry.status = QBTransactionStatus.SYNCING.value
            queue_entry.sync_attempts += 1
            queue_entry.last_sync_attempt = datetime.utcnow()
            db.commit()
            db.refresh(queue_entry)
        
        return queue_entry
    
    @staticmethod
    def mark_pending_deposit(
        db: Session,
        queue_id: int,
        sales_receipt_txn_id: str,
        sales_receipt_txn_line_id: str,
        qbxml_response: str
    ) -> QBTransactionQueue:
        """
        Mark transaction as pending deposit (Pattern A, Step 1 completed).
        
        This is called when SalesReceiptAdd succeeds. The TxnID and TxnLineID are stored
        and status is set to PENDING_DEPOSIT_WAIT. After one sync cycle delay, status
        transitions to PENDING_DEPOSIT, and then DepositAdd will be generated.
        
        CRITICAL: QuickBooks Desktop often needs one full sync cycle before a SalesReceipt
        can be referenced by DepositAdd, even across sessions. This two-stage delay ensures
        the transaction is fully committed and accessible.
        
        Args:
            db: Database session
            queue_id: Queue entry ID
            sales_receipt_txn_id: TxnID from SalesReceiptAddRs response
            sales_receipt_txn_line_id: TxnLineID from SalesReceiptLineRet (CRITICAL: must use actual value, not -1)
            qbxml_response: Response XML from QuickBooks
            
        Returns:
            Updated QBTransactionQueue entry
        """
        from app.models.qb_transaction_queue import QBTransactionStatus
        
        queue_entry = db.query(QBTransactionQueue).filter(
            QBTransactionQueue.id == queue_id
        ).first()
        
        if queue_entry:
            # CRITICAL: Set to PENDING_DEPOSIT_WAIT first (one sync cycle delay)
            # This ensures QuickBooks has fully committed the SalesReceipt before DepositAdd references it
            queue_entry.status = QBTransactionStatus.PENDING_DEPOSIT_WAIT.value
            queue_entry.qbxml_response = qbxml_response
            queue_entry.qb_transaction_id = sales_receipt_txn_id  # Store TxnID for Step 2
            
            # Store TxnLineID in transaction_data JSON (needed for DepositAdd)
            # CRITICAL: Use flag_modified() to ensure SQLAlchemy detects the JSON mutation
            if queue_entry.transaction_data:
                queue_entry.transaction_data['_txn_line_id'] = sales_receipt_txn_line_id
                flag_modified(queue_entry, 'transaction_data')
            else:
                queue_entry.transaction_data = {'_txn_line_id': sales_receipt_txn_line_id}
            
            db.commit()
            db.refresh(queue_entry)
            
            logger.info(f"Transaction marked as pending_deposit_wait (TxnID: {sales_receipt_txn_id}, TxnLineID: {sales_receipt_txn_line_id}): {queue_id}")
            logger.info(f"Status will transition to pending_deposit in the next sync cycle")
        
        return queue_entry
    
    @staticmethod
    def mark_synced(
        db: Session,
        queue_id: int,
        qbxml_response: str,
        qb_transaction_id: Optional[str] = None
    ) -> QBTransactionQueue:
        """
        Mark transaction as successfully synced.
        
        Args:
            db: Database session
            queue_id: Queue entry ID
            qbxml_response: Response XML from QuickBooks
            qb_transaction_id: Transaction ID returned by QuickBooks (optional)
            
        Returns:
            Updated QBTransactionQueue entry
        """
        queue_entry = db.query(QBTransactionQueue).filter(
            QBTransactionQueue.id == queue_id
        ).first()
        
        if queue_entry:
            queue_entry.status = QBTransactionStatus.SYNCED.value
            queue_entry.qbxml_response = qbxml_response
            queue_entry.qb_transaction_id = qb_transaction_id
            queue_entry.synced_at = datetime.utcnow()
            db.commit()
            db.refresh(queue_entry)
            
            logger.info(f"Transaction synced: {queue_id}")
        
        return queue_entry
    
    @staticmethod
    def mark_failed(
        db: Session,
        queue_id: int,
        error_message: str
    ) -> QBTransactionQueue:
        """
        Mark transaction sync as failed.
        
        Args:
            db: Database session
            queue_id: Queue entry ID
            error_message: Error message
            
        Returns:
            Updated QBTransactionQueue entry
        """
        queue_entry = db.query(QBTransactionQueue).filter(
            QBTransactionQueue.id == queue_id
        ).first()
        
        if queue_entry:
            queue_entry.status = QBTransactionStatus.FAILED.value
            queue_entry.error_message = error_message
            queue_entry.sync_attempts += 1
            queue_entry.last_sync_attempt = datetime.utcnow()
            db.commit()
            db.refresh(queue_entry)
            
            logger.error(f"Transaction sync failed: {queue_id} - {error_message}")
        
        return queue_entry
    
    @staticmethod
    def reset_failed_transactions(
        db: Session,
        workspace_id: int,
        max_retries: int = 3
    ) -> int:
        """
        Reset failed transactions back to queued status for retry.
        Only resets transactions that haven't exceeded max_retries.
        
        Args:
            db: Database session
            workspace_id: Workspace ID
            max_retries: Maximum number of retry attempts (default: 3)
            
        Returns:
            Number of transactions reset
        """
        failed_transactions = db.query(QBTransactionQueue).filter(
            and_(
                QBTransactionQueue.workspace_id == workspace_id,
                QBTransactionQueue.status == QBTransactionStatus.FAILED.value,
                QBTransactionQueue.sync_attempts < max_retries
            )
        ).all()
        
        reset_count = 0
        for entry in failed_transactions:
            entry.status = QBTransactionStatus.QUEUED.value
            # Clear error message so it can be retried
            entry.error_message = None
            reset_count += 1
        
        if reset_count > 0:
            db.commit()
            logger.info(f"Reset {reset_count} failed transactions back to queued status for workspace {workspace_id}")
        
        return reset_count
    
    @staticmethod
    def generate_qbxml_for_queue_entries(
        queue_entries: List[QBTransactionQueue]
    ) -> str:
        """
        Generate qbXML for a list of queue entries.
        
        NOTE: This method is deprecated for QuickBooks Desktop compatibility.
        QuickBooks Desktop does NOT support batching multiple requests.
        Use generate_qbxml_for_single_transaction() instead.
        
        Args:
            queue_entries: List of QBTransactionQueue entries
            
        Returns:
            qbXML string
        """
        transactions = []
        for entry in queue_entries:
            transactions.append(entry.transaction_data)
        
        return QBXMLService.generate_qbxml_for_transactions(
            transactions,
            request_id=f"batch-{datetime.utcnow().timestamp()}"
        )
    
    @staticmethod
    def generate_qbxml_for_single_transaction(
        queue_entry: QBTransactionQueue,
        account_manager = None,
        workspace_account_name: Optional[str] = None
    ) -> str:
        """
        Generate qbXML for a SINGLE queue entry.
        
        QuickBooks Desktop requires ONE transaction per sendRequestXML() call.
        This method generates qbXML for a single transaction.
        
        Args:
            queue_entry: Single QBTransactionQueue entry
            account_manager: Optional QBAccountManager instance for account resolution
            workspace_account_name: Optional workspace account name (user-specified)
            
        Returns:
            qbXML string with exactly ONE transaction request
        """
        # Add queue_id to transaction data for RefNumber uniqueness
        trans_data = queue_entry.transaction_data.copy()
        trans_data['_queue_id'] = queue_entry.id
        
        request_id = f"trans-{queue_entry.id}-{int(datetime.utcnow().timestamp())}"
        
        return QBXMLService.generate_qbxml_for_single_transaction(
            trans_data,
            request_id=request_id,
            account_manager=account_manager,
            workspace_account_name=workspace_account_name
        )
    
    @staticmethod
    def get_queue_stats(
        db: Session,
        workspace_id: int
    ) -> Dict[str, int]:
        """
        Get queue statistics for a workspace.
        
        Args:
            db: Database session
            workspace_id: Workspace ID
            
        Returns:
            Dictionary with counts for each status
        """
        stats = {}
        for status in QBTransactionStatus:
            count = db.query(QBTransactionQueue).filter(
                and_(
                    QBTransactionQueue.workspace_id == workspace_id,
                    QBTransactionQueue.status == status.value  # Compare with string value
                )
            ).count()
            stats[status.value] = count
        
        return stats

