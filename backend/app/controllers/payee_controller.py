from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi import Request
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.db.base import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.payee import Payee, PayeeCorrection
from app.services.payee_service import PayeeService
from app.services.activity_log_service import ActivityLogService
from app.models.user_activity_log import ActivityActionType
from pydantic import BaseModel, field_serializer

router = APIRouter(prefix="/payees", tags=["Payees"])


class PayeeResponse(BaseModel):
    id: int
    normalized_name: str
    display_name: str
    aliases: Optional[List[str]]
    workspace_id: int
    vendor_id: Optional[int]
    category_id: Optional[int]
    qb_expense_account_name: Optional[str] = None
    usage_count: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    @field_serializer('created_at', 'updated_at')
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        if dt is None:
            return None
        return dt.isoformat()
    
    class Config:
        from_attributes = True


class PayeeCorrectionResponse(BaseModel):
    id: int
    payee_id: int
    original_payee: str
    corrected_payee: str
    user_id: int
    file_id: Optional[int]
    transaction_id: Optional[str]
    correction_reason: Optional[str]
    similarity_score: Optional[float]
    created_at: datetime
    
    @field_serializer('created_at')
    def serialize_datetime(self, dt: datetime, _info) -> str:
        return dt.isoformat()
    
    class Config:
        from_attributes = True


class CreatePayeeRequest(BaseModel):
    payee_name: str
    auto_match: bool = True


class CorrectPayeeRequest(BaseModel):
    original_payee: str
    corrected_payee: str
    file_id: Optional[int] = None
    transaction_id: Optional[str] = None
    reason: Optional[str] = None


@router.get("", response_model=List[PayeeResponse])
async def get_payees(
    workspace_id: int,
    limit: Optional[int] = Query(50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get payees for workspace."""
    payees = PayeeService.get_suggested_payees(
        db=db,
        workspace_id=workspace_id,
        limit=limit or 50
    )
    return payees


@router.get("/suggestions", response_model=List[PayeeResponse])
async def get_payee_suggestions(
    workspace_id: int,
    limit: Optional[int] = Query(10),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get suggested payees (most frequently used)."""
    payees = PayeeService.get_suggested_payees(
        db=db,
        workspace_id=workspace_id,
        limit=limit or 10
    )
    return payees


@router.get("/recent", response_model=List[PayeeResponse])
async def get_recent_payees(
    workspace_id: int,
    limit: Optional[int] = Query(10),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get recently used payees."""
    payees = PayeeService.get_recent_payees(
        db=db,
        workspace_id=workspace_id,
        user_id=current_user.id,
        limit=limit or 10
    )
    return payees


@router.post("", response_model=PayeeResponse, status_code=status.HTTP_201_CREATED)
async def create_payee(
    workspace_id: int,
    request: CreatePayeeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create or get existing payee."""
    try:
        payee, is_new, similarity = PayeeService.create_or_get_payee(
            db=db,
            payee_name=request.payee_name,
            workspace_id=workspace_id,
            auto_match=request.auto_match
        )
        return payee
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/correct", response_model=PayeeCorrectionResponse, status_code=status.HTTP_201_CREATED)
async def correct_payee(
    http_request: Request,
    workspace_id: int,
    payee_id: int,
    request: CorrectPayeeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Record a payee correction."""
    # Find or create payee
    payee, _, similarity = PayeeService.create_or_get_payee(
        db=db,
        payee_name=request.corrected_payee,
        workspace_id=workspace_id,
        auto_match=False
    )
    
    # Record correction
    correction = PayeeService.record_correction(
        db=db,
        payee_id=payee.id,
        original_payee=request.original_payee,
        corrected_payee=request.corrected_payee,
        user_id=current_user.id,
        file_id=request.file_id,
        transaction_id=request.transaction_id,
        reason=request.reason,
        similarity_score=similarity
    )
    
    # Log activity
    ActivityLogService.log_activity_from_request(
        db=db,
        user_id=current_user.id,
        action_type=ActivityActionType.PAYEE_CORRECT.value,
        request=http_request,
        resource_type="payee",
        resource_id=payee.id,
        workspace_id=workspace_id,
        details={
            "original_payee": request.original_payee,
            "corrected_payee": request.corrected_payee,
            "file_id": request.file_id,
            "similarity_score": similarity
        }
    )
    
    return correction


@router.get("/match", response_model=dict)
async def match_payee(
    workspace_id: int,
    payee_name: str,
    threshold: Optional[int] = Query(85),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Find matching payee for a given name."""
    match_result = PayeeService.find_matching_payee(
        db=db,
        extracted_payee=payee_name,
        workspace_id=workspace_id,
        threshold=threshold
    )
    
    if match_result:
        payee, similarity = match_result
        return {
            "matched": True,
            "payee_id": payee.id,
            "display_name": payee.display_name,
            "similarity_score": similarity
        }
    else:
        return {
            "matched": False,
            "similarity_score": 0
        }


class UpdatePayeeRequest(BaseModel):
    display_name: Optional[str] = None
    aliases: Optional[List[str]] = None
    qb_expense_account_name: Optional[str] = None


@router.put("/{payee_id}", response_model=PayeeResponse)
async def update_payee(
    http_request: Request,
    payee_id: int,
    workspace_id: int,
    request: UpdatePayeeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update payee information."""
    payee = db.query(Payee).filter(
        Payee.id == payee_id,
        Payee.workspace_id == workspace_id
    ).first()
    
    if not payee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payee not found"
        )
    
    # Store old name before updating (for activity log and correction record)
    old_display_name = payee.display_name
    name_changed = False
    
    # Validate that display_name is not an amount
    if request.display_name:
        if PayeeService.is_amount(request.display_name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid payee name: '{request.display_name}' appears to be a monetary amount, not a payee name"
            )
        
        # Check if name actually changed
        if request.display_name.strip() != old_display_name.strip():
            name_changed = True
            # Automatically add old name as alias to preserve matching
            current_aliases = payee.aliases or []
            if old_display_name not in current_aliases:
                current_aliases.append(old_display_name)
                payee.aliases = current_aliases
            
            payee.display_name = request.display_name
            payee.normalized_name = PayeeService.normalize_payee_name(request.display_name)
    
    if request.aliases is not None:
        # Merge with existing aliases if name changed (to preserve old name)
        if name_changed and payee.aliases:
            # Ensure old name is in the new aliases list
            merged_aliases = list(set(request.aliases + [old_display_name]))
            payee.aliases = merged_aliases
        else:
            payee.aliases = request.aliases

    if request.qb_expense_account_name is not None:
        payee.qb_expense_account_name = request.qb_expense_account_name.strip() or None
    
    # Create correction record if name changed
    if name_changed:
        PayeeService.record_correction(
            db=db,
            payee_id=payee.id,
            original_payee=old_display_name,
            corrected_payee=request.display_name.strip(),
            user_id=current_user.id,
            file_id=None,  # Manual edit, not from file extraction
            transaction_id=None,
            reason="Manual edit from Payee Management",
            similarity_score=None
        )
    
    # Log activity
    ActivityLogService.log_activity_from_request(
        db=db,
        user_id=current_user.id,
        action_type=ActivityActionType.SETTINGS_UPDATE.value,
        request=http_request,
        resource_type="payee",
        resource_id=payee.id,
        workspace_id=workspace_id,
        details={
            "action": "payee_updated",
            "old_display_name": old_display_name,
            "new_display_name": request.display_name if request.display_name else old_display_name,
            "aliases_updated": request.aliases is not None,
            "correction_created": name_changed
        }
    )
    
    db.commit()
    db.refresh(payee)
    
    return payee


@router.delete("/{payee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payee(
    payee_id: int,
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a payee."""
    payee = db.query(Payee).filter(
        Payee.id == payee_id,
        Payee.workspace_id == workspace_id
    ).first()
    
    if not payee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payee not found"
        )
    
    db.delete(payee)
    db.commit()
    
    return None


@router.post("/merge", response_model=PayeeResponse)
async def merge_payees(
    workspace_id: int,
    source_payee_id: int,
    target_payee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Merge two payees (source into target)."""
    source_payee = db.query(Payee).filter(
        Payee.id == source_payee_id,
        Payee.workspace_id == workspace_id
    ).first()
    
    target_payee = db.query(Payee).filter(
        Payee.id == target_payee_id,
        Payee.workspace_id == workspace_id
    ).first()
    
    if not source_payee or not target_payee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or both payees not found"
        )
    
    # Merge aliases
    if source_payee.aliases:
        if target_payee.aliases:
            target_payee.aliases = list(set(target_payee.aliases + source_payee.aliases))
        else:
            target_payee.aliases = source_payee.aliases
    
    # Add source display name as alias if different
    if source_payee.display_name != target_payee.display_name:
        if not target_payee.aliases:
            target_payee.aliases = []
        if source_payee.display_name not in target_payee.aliases:
            target_payee.aliases.append(source_payee.display_name)
    
    # Update usage count
    target_payee.usage_count += source_payee.usage_count
    
    # Update corrections to point to target payee
    from app.models.payee import PayeeCorrection
    db.query(PayeeCorrection).filter(
        PayeeCorrection.payee_id == source_payee_id
    ).update({"payee_id": target_payee_id})
    
    # Delete source payee
    db.delete(source_payee)
    db.commit()
    db.refresh(target_payee)
    
    return target_payee


@router.get("/corrections", response_model=List[PayeeCorrectionResponse])
async def get_payee_corrections(
    workspace_id: int,
    payee_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get payee corrections."""
    query = db.query(PayeeCorrection).join(Payee).filter(
        Payee.workspace_id == workspace_id
    )
    
    if payee_id:
        query = query.filter(PayeeCorrection.payee_id == payee_id)
    
    corrections = query.order_by(PayeeCorrection.created_at.desc()).limit(100).all()
    
    return corrections

