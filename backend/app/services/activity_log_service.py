"""
User Activity Log Service
Handles logging and retrieval of user activities.
"""
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from fastapi import Request

from app.models.user_activity_log import UserActivityLog, ActivityActionType

logger = logging.getLogger(__name__)


class ActivityLogService:
    """Service for managing user activity logs"""
    
    @staticmethod
    def log_activity(
        db: Session,
        user_id: int,
        action_type: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> UserActivityLog:
        """
        Log a user activity.
        
        Args:
            db: Database session
            user_id: User ID performing the action
            action_type: Type of action (ActivityActionType)
            resource_type: Type of resource (file, transaction, payee, etc.)
            resource_id: ID of the resource
            workspace_id: Workspace ID (optional)
            details: Additional details as dictionary
            ip_address: IP address of the user
            user_agent: User agent string
            
        Returns:
            Created UserActivityLog entry
        """
        activity_log = UserActivityLog(
            user_id=user_id,
            workspace_id=workspace_id,
            action_type=action_type,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        db.add(activity_log)
        db.commit()
        db.refresh(activity_log)
        
        logger.debug(f"Activity logged: {action_type} by user {user_id}")
        return activity_log
    
    @staticmethod
    def log_activity_from_request(
        db: Session,
        user_id: int,
        action_type: str,
        request: Request,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> UserActivityLog:
        """
        Log activity with IP and user agent from request.
        
        Args:
            db: Database session
            user_id: User ID
            action_type: Type of action
            request: FastAPI Request object
            resource_type: Type of resource
            resource_id: ID of resource
            workspace_id: Workspace ID
            details: Additional details
            
        Returns:
            Created UserActivityLog entry
        """
        # Get IP address from request
        ip_address = request.client.host if request.client else None
        if request.headers.get("x-forwarded-for"):
            ip_address = request.headers.get("x-forwarded-for").split(",")[0].strip()
        
        # Get user agent
        user_agent = request.headers.get("user-agent")
        
        return ActivityLogService.log_activity(
            db=db,
            user_id=user_id,
            action_type=action_type,
            resource_type=resource_type,
            resource_id=resource_id,
            workspace_id=workspace_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    @staticmethod
    def get_activity_logs(
        db: Session,
        user_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
        action_type: Optional[str] = None,
        resource_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[UserActivityLog]:
        """
        Get activity logs with filters.
        
        Args:
            db: Database session
            user_id: Filter by user ID
            workspace_id: Filter by workspace ID
            action_type: Filter by action type
            resource_type: Filter by resource type
            start_date: Start date filter
            end_date: End date filter
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of UserActivityLog entries
        """
        query = db.query(UserActivityLog)
        
        # Apply filters
        if user_id:
            query = query.filter(UserActivityLog.user_id == user_id)
        if workspace_id:
            query = query.filter(UserActivityLog.workspace_id == workspace_id)
        if action_type:
            query = query.filter(UserActivityLog.action_type == action_type)
        if resource_type:
            query = query.filter(UserActivityLog.resource_type == resource_type)
        if start_date:
            query = query.filter(UserActivityLog.created_at >= start_date)
        if end_date:
            query = query.filter(UserActivityLog.created_at <= end_date)
        
        # Order by most recent first
        query = query.order_by(desc(UserActivityLog.created_at))
        
        # Apply pagination
        query = query.offset(offset).limit(limit)
        
        return query.all()
    
    @staticmethod
    def get_activity_stats(
        db: Session,
        workspace_id: Optional[int] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get activity statistics.
        
        Args:
            db: Database session
            workspace_id: Filter by workspace ID
            days: Number of days to look back
            
        Returns:
            Dictionary with statistics
        """
        start_date = datetime.utcnow() - timedelta(days=days)
        
        query = db.query(UserActivityLog)
        if workspace_id:
            query = query.filter(UserActivityLog.workspace_id == workspace_id)
        query = query.filter(UserActivityLog.created_at >= start_date)
        
        total_activities = query.count()
        
        # Count by action type
        action_counts = {}
        for action in ActivityActionType:
            count = query.filter(UserActivityLog.action_type == action.value).count()
            if count > 0:
                action_counts[action.value] = count
        
        return {
            "total_activities": total_activities,
            "period_days": days,
            "action_counts": action_counts
        }
