"""
User Activity Log Model
Tracks user actions for audit and history purposes.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
import enum


class ActivityActionType(str, enum.Enum):
    """Types of user actions"""
    FILE_UPLOAD = "file_upload"
    FILE_DELETE = "file_delete"
    EXTRACTION_START = "extraction_start"
    EXTRACTION_RETRY = "extraction_retry"
    PAYEE_CORRECT = "payee_correct"
    PAYEE_CREATE = "payee_create"
    TRANSACTION_SYNC = "transaction_sync"
    SETTINGS_UPDATE = "settings_update"
    LOGIN = "login"
    LOGOUT = "logout"
    EXPORT_DATA = "export_data"
    REVIEW_APPROVE = "review_approve"
    REVIEW_REJECT = "review_reject"
    OTHER = "other"


class UserActivityLog(Base):
    """Log of user activities for audit trail"""
    __tablename__ = "user_activity_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True, index=True)
    
    # Action details
    action_type = Column(String, nullable=False, index=True)  # ActivityActionType
    resource_type = Column(String, nullable=True)  # file, transaction, payee, settings, etc.
    resource_id = Column(Integer, nullable=True)  # ID of the resource acted upon
    
    # Additional details
    details = Column(JSON, nullable=True)  # Additional context (filename, amounts, etc.)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationships
    user = relationship("User", back_populates="activity_logs")
    workspace = relationship("Workspace", back_populates="activity_logs")
