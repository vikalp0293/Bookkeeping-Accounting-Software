from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.db.base import Base


class FileStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class File(Base):
    __tablename__ = "files"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # pdf, image, excel
    file_size = Column(Integer, nullable=False)  # in bytes
    status = Column(Enum(FileStatus), default=FileStatus.UPLOADED)
    # Document classification: individual_check | bank_statement_only | bank_statement_with_checks | multi_check (set at upload for PDFs; updated after extraction)
    document_type = Column(String, nullable=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    workspace = relationship("Workspace", back_populates="files")
    extracted_data = relationship("ExtractedData", back_populates="file", cascade="all, delete-orphan", uselist=False)
    payee_corrections = relationship("PayeeCorrection", back_populates="file", cascade="all, delete-orphan")
    review_items = relationship("ReviewQueue", back_populates="file", cascade="all, delete-orphan")
    qb_queue_entries = relationship("QBTransactionQueue", back_populates="file", cascade="all, delete-orphan")

