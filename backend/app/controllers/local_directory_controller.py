from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from app.db.base import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.workspace import Workspace
from app.services.local_directory_service import LocalDirectoryService
from app.services.workspace_access_service import require_workspace_access
from pydantic import BaseModel, field_serializer
from typing import Optional

router = APIRouter(prefix="/local-directory", tags=["Local Directory"])


class LocalDirectoryRequest(BaseModel):
    directory_path: str
    is_active: bool = True
    scan_interval_minutes: int = 60


class LocalDirectoryResponse(BaseModel):
    id: int
    workspace_id: int
    directory_path: str
    is_active: bool
    scan_interval_minutes: int
    last_scan_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    @field_serializer('created_at', 'updated_at', 'last_scan_at')
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        if dt is None:
            return None
        return dt.isoformat()
    
    class Config:
        from_attributes = True


class ScanResultResponse(BaseModel):
    success: bool
    new_files: list
    processed_files_count: int
    errors: list
    scan_time: Optional[str] = None
    error: Optional[str] = None


@router.get("", response_model=LocalDirectoryResponse)
async def get_local_directory(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get local directory configuration for workspace."""
    require_workspace_access(db, current_user, workspace_id)
    
    local_dir = LocalDirectoryService.get_directory(db, workspace_id)
    
    if not local_dir:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No local directory configured"
        )
    
    return local_dir


@router.post("", response_model=LocalDirectoryResponse, status_code=status.HTTP_201_CREATED)
async def set_local_directory(
    workspace_id: int,
    request: LocalDirectoryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Set or update local directory configuration."""
    require_workspace_access(db, current_user, workspace_id)
    
    try:
        local_dir = LocalDirectoryService.set_directory(
            db=db,
            workspace_id=workspace_id,
            directory_path=request.directory_path,
            is_active=request.is_active,
            scan_interval_minutes=request.scan_interval_minutes
        )
        return local_dir
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        error_msg = str(e)
        logger.error(f"Error setting local directory for workspace {workspace_id}: {error_msg}", exc_info=True)
        
        # Check if it's a database/table error
        if "does not exist" in error_msg.lower() or "no such table" in error_msg.lower() or "relation" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database migration required. Please run: alembic upgrade head"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving directory settings: {error_msg}"
        )


@router.post("/scan", response_model=ScanResultResponse)
async def scan_directory(
    workspace_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Scan directory for new files."""
    require_workspace_access(db, current_user, workspace_id)
    
    result = LocalDirectoryService.scan_directory(
        db=db,
        workspace_id=workspace_id,
        force_scan=force
    )
    
    return result


@router.patch("/toggle", response_model=LocalDirectoryResponse)
async def toggle_scanning(
    workspace_id: int,
    is_active: bool,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Enable or disable directory scanning."""
    require_workspace_access(db, current_user, workspace_id)
    
    try:
        local_dir = LocalDirectoryService.toggle_scanning(
            db=db,
            workspace_id=workspace_id,
            is_active=is_active
        )
        return local_dir
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

