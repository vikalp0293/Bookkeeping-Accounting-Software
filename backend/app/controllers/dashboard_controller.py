from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.db.base import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.dashboard import DashboardStats
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/stats", tags=["Dashboard"])


@router.get("/summary", response_model=DashboardStats)
async def get_dashboard_summary(
    workspace_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get dashboard statistics."""
    stats = DashboardService.get_stats(
        db=db,
        user_id=current_user.id,
        workspace_id=workspace_id
    )
    return stats

