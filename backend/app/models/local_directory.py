from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class LocalDirectory(Base):
    __tablename__ = "local_directories"
    
    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, unique=True)
    directory_path = Column(String, nullable=False)  # Encrypted or plain path
    is_active = Column(Boolean, default=True)  # Enable/disable auto-scan
    scan_interval_minutes = Column(Integer, default=60)  # How often to scan (in minutes)
    last_scan_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    workspace = relationship("Workspace", back_populates="local_directory")

