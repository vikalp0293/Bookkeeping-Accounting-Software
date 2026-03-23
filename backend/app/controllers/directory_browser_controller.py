from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services.directory_browser_service import DirectoryBrowserService
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/directory-browser", tags=["Directory Browser"])


class DirectoryListResponse(BaseModel):
    current_path: Optional[str]
    parent_path: Optional[str]
    items: list


class DirectoryValidationResponse(BaseModel):
    valid: bool
    resolved_path: Optional[str] = None
    error: Optional[str] = None


@router.get("/list", response_model=DirectoryListResponse)
async def list_directory(
    path: Optional[str] = Query(None, description="Directory path to list. If not provided, returns base paths."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List contents of a directory on the server."""
    try:
        result = DirectoryBrowserService.list_directory(path)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing directory: {str(e)}"
        )


@router.get("/validate", response_model=DirectoryValidationResponse)
async def validate_directory(
    path: str = Query(..., description="Directory path to validate"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Validate that a directory exists and is accessible."""
    result = DirectoryBrowserService.validate_directory(path)
    return result

