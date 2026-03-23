"""
User Activity Log Controller
API endpoints for viewing user activity logs.
"""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
from app.db.base import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services.activity_log_service import ActivityLogService
from app.models.user_activity_log import UserActivityLog, ActivityActionType
from app.services.workspace_access_service import require_workspace_access

router = APIRouter(prefix="/activity-logs", tags=["Activity Logs"])


class ActivityLogResponse(BaseModel):
    id: int
    user_id: int
    workspace_id: Optional[int]
    action_type: str
    resource_type: Optional[str]
    resource_id: Optional[int]
    details: Optional[dict]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class ActivityStatsResponse(BaseModel):
    total_activities: int
    period_days: int
    action_counts: dict


@router.get("", response_model=List[ActivityLogResponse])
async def get_activity_logs(
    workspace_id: Optional[int] = Query(None, description="Filter by workspace ID"),
    action_type: Optional[str] = Query(None, description="Filter by action type"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get activity logs with optional filters.
    Users can only see their own logs unless they are superuser.
    """
    # Parse dates
    start_datetime = None
    end_datetime = None
    if start_date:
        try:
            start_datetime = datetime.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format. Use YYYY-MM-DD"
            )
    if end_date:
        try:
            end_datetime = datetime.fromisoformat(end_date)
            # Set to end of day
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid end_date format. Use YYYY-MM-DD"
            )
    
    # Filter by user_id unless superuser
    filter_user_id = None if current_user.is_superuser else current_user.id
    
    # If workspace_id is provided, filter by it; otherwise show all logs for the user
    # (including logs without workspace_id like login actions)
    filter_workspace_id = workspace_id
    
    logs = ActivityLogService.get_activity_logs(
        db=db,
        user_id=filter_user_id,
        workspace_id=filter_workspace_id,  # None means don't filter by workspace
        action_type=action_type,
        resource_type=resource_type,
        start_date=start_datetime,
        end_date=end_datetime,
        limit=limit,
        offset=offset
    )
    
    return logs


@router.get("/stats", response_model=ActivityStatsResponse)
async def get_activity_stats(
    workspace_id: Optional[int] = Query(None, description="Filter by workspace ID"),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get activity statistics."""
    # If not superuser, only show stats for current user's workspaces
    filter_workspace_id = workspace_id
    if not current_user.is_superuser and workspace_id:
        require_workspace_access(db, current_user, workspace_id)
    
    stats = ActivityLogService.get_activity_stats(
        db=db,
        workspace_id=filter_workspace_id,
        days=days
    )
    
    return stats
