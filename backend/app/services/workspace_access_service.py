from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.models.user import User
from app.models.workspace import Workspace


def get_accessible_workspace_id(current_user: User) -> Optional[int]:
    """
    Returns the single workspace id the user is allowed to operate on (non-superuser),
    or None if not set / not applicable.
    """
    if current_user.is_superuser or (current_user.role or "").lower() == "superuser":
        return None
    if current_user.workspace_id:
        return int(current_user.workspace_id)
    return None


def require_workspace_access(db: Session, current_user: User, workspace_id: int) -> Workspace:
    """
    Superuser: can access any workspace.
    Admin/Reviewer/Accountant: can access only their assigned workspace_id.
    """
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    if current_user.is_superuser or (current_user.role or "").lower() == "superuser":
        return workspace

    if current_user.workspace_id and int(current_user.workspace_id) == int(workspace_id):
        return workspace

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this workspace")

