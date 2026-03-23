"""
QuickBooks Transaction Queue Model
Stores transactions queued for syncing to QuickBooks Desktop via QB Web Connector
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
import enum


class QBTransactionStatus(str, enum.Enum):
    """Status of transaction in QB sync queue"""
    PENDING = "pending"      # Awaiting user approval
    QUEUED = "queued"        # Approved, queued for QB sync
    SYNCING = "syncing"      # Currently being synced by QB Web Connector
    PENDING_DEPOSIT_WAIT = "pending_deposit_wait"  # SalesReceiptAdd succeeded, waiting one sync cycle before DepositAdd
    PENDING_DEPOSIT = "pending_deposit"  # Ready for DepositAdd (Pattern A, Step 2) - after one sync cycle delay
    SYNCED = "synced"        # Successfully synced to QuickBooks
    FAILED = "failed"        # Sync failed


class QBTransactionQueue(Base):
    """Queue of transactions waiting to be synced to QuickBooks Desktop"""
    __tablename__ = "qb_transaction_queue"
    
    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    
    # Reference to the transaction in extracted_data
    # We store the file_id and transaction index/ID from processed_data
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False, index=True)
    transaction_index = Column(Integer, nullable=True)  # Index in transactions array
    transaction_id = Column(String, nullable=True)  # Unique transaction identifier if available
    
    # Multi-company: which QuickBooks company file this transaction is syncing to (desktop)
    company_file = Column(String, nullable=True)  # Full path to .qbw or company identifier
    
    # Transaction data (stored for reference and qbXML generation)
    transaction_data = Column(JSON, nullable=False)  # Full transaction data from extracted_data
    
    # Status tracking (using String instead of ENUM to avoid SQLAlchemy conversion issues)
    status = Column(String, default=QBTransactionStatus.PENDING.value, nullable=False, index=True)
    
    # QB Web Connector sync data
    qbxml_request = Column(Text, nullable=True)  # Generated qbXML request
    qbxml_response = Column(Text, nullable=True)  # Response from QuickBooks
    qb_transaction_id = Column(String, nullable=True)  # Transaction ID returned by QuickBooks
    
    # Error handling
    error_message = Column(Text, nullable=True)
    sync_attempts = Column(Integer, default=0)
    last_sync_attempt = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    workspace = relationship("Workspace", back_populates="qb_transactions")
    file = relationship("File", back_populates="qb_queue_entries")

