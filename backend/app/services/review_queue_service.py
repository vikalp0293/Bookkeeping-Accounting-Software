"""
Review queue service for managing items that need manual review.
"""
import logging
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from app.models.review_queue import ReviewQueue, ReviewPriority, ReviewStatus, ReviewReason
from app.models.file import File
from app.models.user import User

logger = logging.getLogger(__name__)


class ReviewQueueService:
    """Service for managing review queue items."""
    
    @staticmethod
    def add_to_queue(
        db: Session,
        file_id: int,
        review_reason: ReviewReason,
        priority: ReviewPriority = ReviewPriority.MEDIUM,
        transaction_id: Optional[str] = None,
        notes: Optional[str] = None
    ) -> ReviewQueue:
        """Add an item to the review queue."""
        # Check if item already exists
        existing = db.query(ReviewQueue).filter(
            ReviewQueue.file_id == file_id,
            ReviewQueue.transaction_id == transaction_id,
            ReviewQueue.status == ReviewStatus.PENDING
        ).first()
        
        if existing:
            # Update existing item
            existing.review_reason = review_reason
            existing.priority = priority
            if notes:
                existing.notes = notes
            db.commit()
            db.refresh(existing)
            return existing
        
        # Create new review item
        review_item = ReviewQueue(
            file_id=file_id,
            transaction_id=transaction_id,
            review_reason=review_reason,
            priority=priority,
            status=ReviewStatus.PENDING,
            notes=notes
        )
        db.add(review_item)
        db.commit()
        db.refresh(review_item)
        
        return review_item
    
    @staticmethod
    def get_queue_items(
        db: Session,
        workspace_id: Optional[int] = None,
        status: Optional[ReviewStatus] = None,  # Changed default to None - let controller handle default
        priority: Optional[ReviewPriority] = None,
        assigned_to: Optional[int] = None,
        limit: Optional[int] = None
    ) -> List[ReviewQueue]:
        """Get review queue items with optional filters."""
        query = db.query(ReviewQueue)
        
        if workspace_id:
            # Filter by workspace through files
            query = query.join(File).filter(File.workspace_id == workspace_id)
        
        if status:
            query = query.filter(ReviewQueue.status == status)
        
        if priority:
            query = query.filter(ReviewQueue.priority == priority)
        
        if assigned_to:
            query = query.filter(ReviewQueue.assigned_to == assigned_to)
        
        # Order by priority and creation date
        query = query.order_by(
            ReviewQueue.priority.desc(),
            ReviewQueue.created_at.asc()
        )
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    @staticmethod
    def assign_review(
        db: Session,
        review_id: int,
        user_id: int
    ) -> ReviewQueue:
        """Assign a review item to a user."""
        review_item = db.query(ReviewQueue).filter(ReviewQueue.id == review_id).first()
        
        if not review_item:
            raise ValueError("Review item not found")
        
        review_item.assigned_to = user_id
        review_item.status = ReviewStatus.IN_REVIEW
        db.commit()
        db.refresh(review_item)
        
        return review_item
    
    @staticmethod
    def update_review_status(
        db: Session,
        review_id: int,
        status: ReviewStatus,
        notes: Optional[str] = None
    ) -> ReviewQueue:
        """Update review item status."""
        review_item = db.query(ReviewQueue).filter(ReviewQueue.id == review_id).first()
        
        if not review_item:
            raise ValueError("Review item not found")
        
        review_item.status = status
        if notes:
            review_item.notes = notes
        if status in [ReviewStatus.APPROVED, ReviewStatus.COMPLETED, ReviewStatus.REJECTED]:
            from datetime import datetime
            review_item.reviewed_at = datetime.utcnow()
        
        db.commit()
        db.refresh(review_item)
        
        return review_item
    
    @staticmethod
    def get_review_stats(
        db: Session,
        workspace_id: Optional[int] = None
    ) -> Dict[str, int]:
        """Get review queue statistics."""
        base_query = db.query(ReviewQueue)
        
        if workspace_id:
            # Filter by workspace through files
            base_query = base_query.join(File).filter(File.workspace_id == workspace_id)
        
        total = base_query.count()
        
        # Apply workspace filter to status queries too
        pending_query = base_query.filter(ReviewQueue.status == ReviewStatus.PENDING)
        in_review_query = base_query.filter(ReviewQueue.status == ReviewStatus.IN_REVIEW)
        completed_query = base_query.filter(ReviewQueue.status == ReviewStatus.COMPLETED)
        
        pending = pending_query.count()
        in_review = in_review_query.count()
        completed = completed_query.count()
        
        return {
            "total": total,
            "pending": pending,
            "in_review": in_review,
            "completed": completed
        }

