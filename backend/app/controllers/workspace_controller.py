from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.db.base import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.workspace import Workspace
from pydantic import BaseModel, field_serializer

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


class WorkspaceResponse(BaseModel):
    id: int
    name: str
    owner_id: int
    quickbooks_account_name: Optional[str] = None
    company_account_map: Optional[Dict[str, str]] = None  # company file path -> account name
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    @field_serializer('created_at', 'updated_at')
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        if dt is None:
            return None
        return dt.isoformat()
    
    class Config:
        from_attributes = True


class WorkspaceUpdateRequest(BaseModel):
    name: Optional[str] = None
    quickbooks_account_name: Optional[str] = None
    company_account_map: Optional[Dict[str, str]] = None  # company file path -> account name


@router.get("", response_model=List[WorkspaceResponse])
async def get_user_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all workspaces for the current user."""
    if current_user.is_superuser or (current_user.role or "").lower() == "superuser":
        return db.query(Workspace).order_by(Workspace.id.asc()).all()

    # Admin/Reviewer/Accountant: exactly one workspace
    if current_user.workspace_id:
        ws = db.query(Workspace).filter(Workspace.id == current_user.workspace_id).all()
        return ws
    # Fallback: legacy admin users might only have owned workspaces
    return db.query(Workspace).filter(Workspace.owner_id == current_user.id).all()


@router.get("/default", response_model=WorkspaceResponse)
async def get_default_workspace(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the user's default workspace.

    Rules:
    - superuser: returns first owned workspace; creates one if none exists (legacy-safe).
    - admin: returns workspace_id if set; else first owned; creates if none exists.
    - reviewer/accountant: must already have workspace_id assigned (no auto-create).
    """
    try:
        role = (current_user.role or ("superuser" if current_user.is_superuser else "admin")).lower()

        # reviewer/accountant: must be assigned to an existing workspace
        if role in {"reviewer", "accountant"}:
            if not current_user.workspace_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Workspace not assigned to this user"
                )
            workspace = db.query(Workspace).filter(Workspace.id == current_user.workspace_id).first()
            if not workspace:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
            return workspace

        # admin/superuser: prefer explicit workspace_id membership if present
        if current_user.workspace_id:
            workspace = db.query(Workspace).filter(Workspace.id == current_user.workspace_id).first()
            if workspace:
                return workspace

        # legacy/admin: fall back to owned workspace
        workspace = db.query(Workspace).filter(Workspace.owner_id == current_user.id).first()
        if workspace:
            # keep membership in sync for legacy records
            if not current_user.workspace_id:
                current_user.workspace_id = workspace.id
                db.commit()
            return workspace

        # superuser/admin: create if none exists (legacy-safe; superuser may still need one)
        workspace = Workspace(
            name=f"{current_user.full_name or current_user.email}'s Workspace",
            owner_id=current_user.id
        )
        db.add(workspace)
        db.commit()
        db.refresh(workspace)

        current_user.workspace_id = workspace.id
        db.commit()
        return workspace
    except Exception as e:
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting/creating default workspace for user {current_user.id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading workspace: {str(e)}"
        )


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: int,
    request: WorkspaceUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update workspace settings (name and/or QuickBooks account name)."""
    workspace = db.query(Workspace).filter(
        Workspace.id == workspace_id,
        Workspace.owner_id == current_user.id
    ).first()
    
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found"
        )
    
    # Update fields if provided
    if request.name is not None:
        workspace.name = request.name
    if request.quickbooks_account_name is not None:
        workspace.quickbooks_account_name = request.quickbooks_account_name
    if request.company_account_map is not None:
        workspace.company_account_map = request.company_account_map
    
    db.commit()
    db.refresh(workspace)
    
    return workspace

