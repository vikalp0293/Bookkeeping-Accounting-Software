from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    # RBAC
    role = Column(String, nullable=False, default="admin")  # superuser/admin/reviewer/accountant
    # Workspace membership (reviewer/accountant must have exactly one workspace)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    # Workspaces owned by this user (Admin/Superuser). Explicit foreign_keys to avoid ambiguity with users.workspace_id.
    workspaces = relationship(
        "Workspace",
        back_populates="owner",
        cascade="all, delete-orphan",
        foreign_keys="Workspace.owner_id",
    )
    # Single workspace membership for non-owner roles (reviewer/accountant/admin membership)
    workspace = relationship("Workspace", foreign_keys=[workspace_id])
    login_sessions = relationship("LoginSession", back_populates="user", cascade="all, delete-orphan")
    payee_corrections = relationship("PayeeCorrection", back_populates="user", cascade="all, delete-orphan")
    assigned_reviews = relationship("ReviewQueue", foreign_keys="ReviewQueue.assigned_to", back_populates="reviewer")
    activity_logs = relationship("UserActivityLog", back_populates="user", cascade="all, delete-orphan")

