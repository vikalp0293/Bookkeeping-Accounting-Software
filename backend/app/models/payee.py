from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class Payee(Base):
    __tablename__ = "payees"
    
    id = Column(Integer, primary_key=True, index=True)
    normalized_name = Column(String, nullable=False, index=True)  # Lowercase, normalized for matching
    display_name = Column(String, nullable=False)  # Original/corrected display name
    aliases = Column(JSON, nullable=True)  # List of alternative names
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)  # Optional vendor link
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)  # Suggested category
    qb_expense_account_name = Column(String, nullable=True)  # QuickBooks expense account for this payee (e.g. Rent Expense, Utilities)
    usage_count = Column(Integer, default=0)  # How many times this payee has been used
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    workspace = relationship("Workspace", back_populates="payees")
    vendor = relationship("Vendor", back_populates="payees")
    category = relationship("Category", back_populates="payees")
    corrections = relationship("PayeeCorrection", back_populates="payee", cascade="all, delete-orphan")


class PayeeCorrection(Base):
    __tablename__ = "payee_corrections"
    
    id = Column(Integer, primary_key=True, index=True)
    payee_id = Column(Integer, ForeignKey("payees.id"), nullable=False)
    original_payee = Column(String, nullable=False)  # Original extracted payee name
    corrected_payee = Column(String, nullable=False)  # Corrected payee name
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=True)
    transaction_id = Column(String, nullable=True)  # Transaction identifier from extracted data
    correction_reason = Column(String, nullable=True)  # Why correction was made
    similarity_score = Column(Float, nullable=True)  # Similarity score if auto-matched
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    payee = relationship("Payee", back_populates="corrections")
    user = relationship("User", back_populates="payee_corrections")
    file = relationship("File", back_populates="payee_corrections")

