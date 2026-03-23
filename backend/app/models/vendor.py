from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class Vendor(Base):
    __tablename__ = "vendors"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    subcategory = Column(String, nullable=True)
    common_payee_patterns = Column(JSON, nullable=True)  # List of patterns to match payees
    quickbooks_vendor_id = Column(String, nullable=True)  # QB vendor ID if synced
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    category = relationship("Category", back_populates="vendors")
    payees = relationship("Payee", back_populates="vendor")


class Category(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    parent_category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    quickbooks_account = Column(String, nullable=True)  # QB account name for sync
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    parent = relationship("Category", remote_side=[id], backref="children")
    vendors = relationship("Vendor", back_populates="category")
    payees = relationship("Payee", back_populates="category")

