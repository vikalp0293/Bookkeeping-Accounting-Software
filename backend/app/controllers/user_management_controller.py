from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.base import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.workspace import Workspace
from app.core.security import get_password_hash


router = APIRouter(prefix="/users", tags=["User Management"])


class CreateAdminRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str] = None
    workspace_name: Optional[str] = None


class CreateWorkspaceUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str] = None
    role: str  # reviewer/accountant


class UserListItem(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    is_active: bool
    is_superuser: bool
    role: str
    workspace_id: Optional[int] = None

    class Config:
        from_attributes = True


def _require_superuser(current_user: User) -> None:
    if not (current_user.is_superuser or (current_user.role or "").lower() == "superuser"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser only")


def _require_admin(current_user: User) -> None:
    if (current_user.role or "").lower() != "admin" and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")


@router.get("", response_model=List[UserListItem])
async def list_users(
    role: Optional[str] = None,
    workspace_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Superuser: list all users (optionally filter by role/workspace).
    Admin: list users in their workspace.
    """
    q = db.query(User)

    if current_user.is_superuser or (current_user.role or "").lower() == "superuser":
        if role:
            q = q.filter(User.role == role)
        if workspace_id is not None:
            q = q.filter(User.workspace_id == workspace_id)
        return q.order_by(User.id.asc()).all()

    _require_admin(current_user)
    if not current_user.workspace_id:
        return []
    q = q.filter(User.workspace_id == current_user.workspace_id)
    if role:
        q = q.filter(User.role == role)
    return q.order_by(User.id.asc()).all()


@router.post("/admin", response_model=UserListItem, status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    payload: CreateAdminRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Superuser-only: creates an Admin user and a workspace for that Admin.
    """
    _require_superuser(current_user)

    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

    admin_user = User(
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        is_active=True,
        is_superuser=False,
        role="admin",
    )
    db.add(admin_user)
    db.flush()  # assign admin_user.id

    ws = Workspace(
        name=payload.workspace_name or f"{admin_user.full_name or admin_user.email}'s Workspace",
        owner_id=admin_user.id,
    )
    db.add(ws)
    db.flush()

    admin_user.workspace_id = ws.id

    db.commit()
    db.refresh(admin_user)
    return admin_user


@router.post("/workspace-user", response_model=UserListItem, status_code=status.HTTP_201_CREATED)
async def create_workspace_user(
    payload: CreateWorkspaceUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Admin-only: creates a Reviewer or Accountant user in the Admin's workspace.
    """
    _require_admin(current_user)
    if not current_user.workspace_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin workspace not set")

    role = (payload.role or "").lower().strip()
    if role not in {"reviewer", "accountant"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role must be reviewer or accountant")

    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

    user = User(
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        is_active=True,
        is_superuser=False,
        role=role,
        workspace_id=current_user.workspace_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

