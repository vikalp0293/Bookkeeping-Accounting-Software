from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class ExtractedData(Base):
    __tablename__ = "extracted_data"
    
    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id"), unique=True, nullable=False)
    raw_data = Column(JSON, nullable=True)  # Raw extracted data
    processed_data = Column(JSON, nullable=True)  # Processed/validated data
    extraction_status = Column(String, default="pending")  # pending, completed, failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    file = relationship("File", back_populates="extracted_data")

