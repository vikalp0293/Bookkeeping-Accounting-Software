from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.db.base import Base


class ReviewPriority(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class ReviewReason(str, enum.Enum):
    LOW_CONFIDENCE = "low_confidence"
    MISSING_FIELDS = "missing_fields"
    NON_ENGLISH = "non_english"
    NO_PAYEE_MATCH = "no_payee_match"
    USER_FLAGGED = "user_flagged"
    PAYEE_CORRECTION = "payee_correction"
    OTHER = "other"


class ReviewQueue(Base):
    __tablename__ = "review_queue"
    
    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    transaction_id = Column(String, nullable=True)  # Transaction identifier from extracted data
    review_reason = Column(SQLEnum(ReviewReason), nullable=False)
    priority = Column(SQLEnum(ReviewPriority), default=ReviewPriority.MEDIUM)
    status = Column(SQLEnum(ReviewStatus), default=ReviewStatus.PENDING)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)  # Reviewer notes
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    file = relationship("File", back_populates="review_items")
    reviewer = relationship("User", foreign_keys=[assigned_to], back_populates="assigned_reviews")

