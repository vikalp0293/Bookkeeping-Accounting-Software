from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.schemas.auth import UserLogin, Token, TokenRefresh, UserResponse
from app.services.auth_service import AuthService
from app.services.activity_log_service import ActivityLogService
from app.models.user_activity_log import ActivityActionType
from app.dependencies.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])



@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, request: Request, db: Session = Depends(get_db)):
    """Login and get access token."""
    user = AuthService.authenticate_user(
        db=db,
        email=credentials.email,
        password=credentials.password
    )
    tokens = AuthService.create_session(db=db, user=user)
    
    # Log activity
    ActivityLogService.log_activity_from_request(
        db=db,
        user_id=user.id,
        action_type=ActivityActionType.LOGIN.value,
        request=request,
        resource_type="user",
        resource_id=user.id,
        details={"email": user.email}
    )
    
    return tokens


@router.post("/refresh", response_model=dict)
async def refresh_token(token_data: TokenRefresh, db: Session = Depends(get_db)):
    """Refresh access token."""
    tokens = AuthService.refresh_access_token(
        db=db,
        refresh_token=token_data.refresh_token
    )
    return tokens


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return current_user

