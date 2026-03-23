from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSON
from app.db.base import Base


class Workspace(Base):
    __tablename__ = "workspaces"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    quickbooks_account_name = Column(String, nullable=True)  # QuickBooks account name for transaction sync
    # Multi-company: map company file path -> QuickBooks account name (desktop sync)
    company_account_map = Column(JSON, nullable=True)  # e.g. {"C:\\...\\Royal Ginger.qbw": "Checking"}
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    owner = relationship("User", back_populates="workspaces", foreign_keys=[owner_id])
    files = relationship("File", back_populates="workspace", cascade="all, delete-orphan")
    payees = relationship("Payee", back_populates="workspace", cascade="all, delete-orphan")
    local_directory = relationship("LocalDirectory", back_populates="workspace", uselist=False, cascade="all, delete-orphan")
    qb_transactions = relationship("QBTransactionQueue", back_populates="workspace", cascade="all, delete-orphan")
    activity_logs = relationship("UserActivityLog", back_populates="workspace", cascade="all, delete-orphan")

