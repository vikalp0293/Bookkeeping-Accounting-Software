from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.db.base import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.vendor import Vendor, Category
from app.services.vendor_service import VendorService
from pydantic import BaseModel, field_serializer

router = APIRouter(prefix="/vendors", tags=["Vendors & Categories"])


class VendorResponse(BaseModel):
    id: int
    name: str
    category_id: Optional[int]
    subcategory: Optional[str]
    common_payee_patterns: Optional[List[str]]
    quickbooks_vendor_id: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    @field_serializer('created_at', 'updated_at')
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        if dt is None:
            return None
        return dt.isoformat()
    
    class Config:
        from_attributes = True


class CategoryResponse(BaseModel):
    id: int
    name: str
    parent_category_id: Optional[int]
    quickbooks_account: Optional[str]
    description: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    @field_serializer('created_at', 'updated_at')
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        if dt is None:
            return None
        return dt.isoformat()
    
    class Config:
        from_attributes = True


class VendorSuggestionResponse(BaseModel):
    vendor: Optional[VendorResponse]
    category: Optional[CategoryResponse]
    confidence: float


class CreateVendorRequest(BaseModel):
    name: str
    category_id: Optional[int] = None
    subcategory: Optional[str] = None
    common_payee_patterns: Optional[List[str]] = None


class CreateCategoryRequest(BaseModel):
    name: str
    description: Optional[str] = None
    parent_category_id: Optional[int] = None
    quickbooks_account: Optional[str] = None


@router.get("/vendors", response_model=List[VendorResponse])
async def get_vendors(
    limit: Optional[int] = Query(100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all vendors."""
    vendors = VendorService.get_all_vendors(db, limit=limit)
    return vendors


@router.get("/categories", response_model=List[CategoryResponse])
async def get_categories(
    limit: Optional[int] = Query(100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all categories."""
    categories = VendorService.get_all_categories(db, limit=limit)
    return categories


@router.post("/vendors", response_model=VendorResponse, status_code=status.HTTP_201_CREATED)
async def create_vendor(
    request: CreateVendorRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new vendor."""
    try:
        vendor = VendorService.create_vendor(
            db=db,
            name=request.name,
            category_id=request.category_id,
            subcategory=request.subcategory,
            common_payee_patterns=request.common_payee_patterns
        )
        return vendor
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    request: CreateCategoryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new category."""
    try:
        category = VendorService.create_category(
            db=db,
            name=request.name,
            description=request.description
        )
        return category
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/suggest", response_model=VendorSuggestionResponse)
async def suggest_vendor_category(
    payee_name: str = Query(..., description="Payee name to get suggestions for"),
    threshold: Optional[int] = Query(80, description="Similarity threshold (0-100)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get vendor and category suggestions for a payee name."""
    vendor_suggestion = VendorService.suggest_vendor_for_payee(
        db=db,
        payee_name=payee_name,
        threshold=threshold
    )
    
    vendor = None
    confidence = 0.0
    vendor_id_for_category = None
    
    if vendor_suggestion:
        vendor_obj, confidence = vendor_suggestion
        vendor = VendorResponse.model_validate(vendor_obj)
        vendor_id_for_category = vendor.id
    
    category_suggestion = VendorService.suggest_category_for_payee(
        db=db,
        payee_name=payee_name,
        vendor_id=vendor_id_for_category
    )
    
    category = None
    if category_suggestion:
        category = CategoryResponse.model_validate(category_suggestion)
    
    return VendorSuggestionResponse(
        vendor=vendor,
        category=category,
        confidence=confidence
    )

