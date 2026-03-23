from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.db.base import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.review_queue import ReviewQueue, ReviewStatus, ReviewPriority, ReviewReason
from app.services.review_queue_service import ReviewQueueService
from pydantic import BaseModel, field_serializer

router = APIRouter(prefix="/review-queue", tags=["Review Queue"])


class ReviewQueueResponse(BaseModel):
    id: int
    file_id: int
    transaction_id: Optional[str]
    review_reason: str
    priority: str
    status: str
    assigned_to: Optional[int]
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    
    @field_serializer('created_at', 'updated_at', 'reviewed_at')
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        if dt is None:
            return None
        return dt.isoformat()
    
    class Config:
        from_attributes = True


class ReviewStatsResponse(BaseModel):
    total: int
    pending: int
    in_review: int
    completed: int


class UpdateReviewRequest(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


@router.get("", response_model=List[ReviewQueueResponse])
async def get_review_queue(
    workspace_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    priority: Optional[str] = Query(None),
    assigned_to: Optional[int] = Query(None),
    limit: Optional[int] = Query(100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get review queue items."""
    status_enum = None
    if status_filter:
        try:
            # Handle case-insensitive status conversion
            status_upper = status_filter.upper()
            # Map common variations
            status_map = {
                "PENDING": ReviewStatus.PENDING,
                "IN_REVIEW": ReviewStatus.IN_REVIEW,
                "APPROVED": ReviewStatus.APPROVED,
                "REJECTED": ReviewStatus.REJECTED,
                "COMPLETED": ReviewStatus.COMPLETED,
                "SKIPPED": ReviewStatus.SKIPPED
            }
            status_enum = status_map.get(status_upper)
            if not status_enum:
                status_enum = ReviewStatus(status_filter)
        except (ValueError, KeyError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}"
            )
    
    priority_enum = None
    if priority:
        try:
            priority_enum = ReviewPriority(priority)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid priority: {priority}"
            )
    
    # Default to PENDING if no status filter is provided
    if not status_enum:
        status_enum = ReviewStatus.PENDING
    
    items = ReviewQueueService.get_queue_items(
        db=db,
        workspace_id=workspace_id,
        status=status_enum,
        priority=priority_enum,
        assigned_to=assigned_to,
        limit=limit
    )
    
    return items


@router.get("/stats", response_model=ReviewStatsResponse)
async def get_review_stats(
    workspace_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get review queue statistics."""
    stats = ReviewQueueService.get_review_stats(
        db=db,
        workspace_id=workspace_id
    )
    return stats


@router.post("/{review_id}/assign")
async def assign_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Assign a review item to current user."""
    try:
        review_item = ReviewQueueService.assign_review(
            db=db,
            review_id=review_id,
            user_id=current_user.id
        )
        return review_item
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.patch("/{review_id}", response_model=ReviewQueueResponse)
async def update_review(
    review_id: int,
    request: UpdateReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update review item status."""
    status_enum = None
    if request.status:
        try:
            status_enum = ReviewStatus(request.status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {request.status}"
            )
    
    if not status_enum:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status is required"
        )
    
    try:
        review_item = ReviewQueueService.update_review_status(
            db=db,
            review_id=review_id,
            status=status_enum,
            notes=request.notes
        )
        return review_item
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

