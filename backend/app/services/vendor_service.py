"""
Vendor and category management service.
Handles vendor/category suggestions based on payee names.
"""
import logging
import re
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.vendor import Vendor, Category
from app.models.payee import Payee

logger = logging.getLogger(__name__)

# Try to import fuzzy matching library
try:
    from rapidfuzz import fuzz, process
    FUZZY_AVAILABLE = True
except ImportError:
    try:
        from fuzzywuzzy import fuzz, process
        FUZZY_AVAILABLE = True
    except ImportError:
        FUZZY_AVAILABLE = False
        logger.warning("Fuzzy matching library not available. Install rapidfuzz or fuzzywuzzy")


def normalize_payee_name(name: str) -> str:
    """Normalize payee name for matching (same as PayeeService)."""
    if not name:
        return ""
    normalized = name.lower().strip()
    normalized = re.sub(r'[.,;:!?\'"()\[\]{}]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    normalized = re.sub(r'\b(inc|llc|corp|ltd|co|company)\b', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


class VendorService:
    """Service for vendor and category management."""
    
    @staticmethod
    def get_all_vendors(db: Session, limit: Optional[int] = None) -> List[Vendor]:
        """Get all vendors."""
        query = db.query(Vendor)
        if limit:
            query = query.limit(limit)
        return query.all()
    
    @staticmethod
    def get_all_categories(db: Session, limit: Optional[int] = None) -> List[Category]:
        """Get all categories."""
        query = db.query(Category)
        if limit:
            query = query.limit(limit)
        return query.all()
    
    @staticmethod
    def create_vendor(
        db: Session,
        name: str,
        category_id: Optional[int] = None,
        subcategory: Optional[str] = None,
        common_payee_patterns: Optional[List[str]] = None
    ) -> Vendor:
        """Create a new vendor."""
        vendor = Vendor(
            name=name,
            category_id=category_id,
            subcategory=subcategory,
            common_payee_patterns=common_payee_patterns or []
        )
        db.add(vendor)
        db.commit()
        db.refresh(vendor)
        return vendor
    
    @staticmethod
    def create_category(
        db: Session,
        name: str,
        description: Optional[str] = None
    ) -> Category:
        """Create a new category."""
        category = Category(
            name=name,
            description=description
        )
        db.add(category)
        db.commit()
        db.refresh(category)
        return category
    
    @staticmethod
    def suggest_vendor_for_payee(
        db: Session,
        payee_name: str,
        threshold: int = 80
    ) -> Optional[Tuple[Vendor, float]]:
        """
        Suggest a vendor for a payee name based on:
        1. Common payee patterns in vendor records
        2. Fuzzy matching against vendor names
        3. Existing payee-vendor associations
        """
        if not payee_name or not payee_name.strip():
            return None
        
        payee_lower = payee_name.lower().strip()
        
        # 1. Check if any payee with this name already has a vendor
        existing_payee = db.query(Payee).filter(
            Payee.normalized_name == normalize_payee_name(payee_name)
        ).first()
        
        if existing_payee and existing_payee.vendor_id:
            vendor = db.query(Vendor).filter(Vendor.id == existing_payee.vendor_id).first()
            if vendor:
                return (vendor, 100.0)  # High confidence if payee already linked
        
        # 2. Check common payee patterns in vendors
        vendors = db.query(Vendor).all()
        best_match = None
        best_score = 0.0
        
        for vendor in vendors:
            if vendor.common_payee_patterns:
                for pattern in vendor.common_payee_patterns:
                    pattern_lower = pattern.lower().strip()
                    if FUZZY_AVAILABLE:
                        score = fuzz.ratio(payee_lower, pattern_lower)
                    else:
                        # Simple substring matching fallback
                        score = 100.0 if pattern_lower in payee_lower or payee_lower in pattern_lower else 0.0
                    
                    if score > best_score and score >= threshold:
                        best_score = score
                        best_match = vendor
        
        # 3. Fuzzy match against vendor names
        if FUZZY_AVAILABLE and vendors:
            vendor_names = [v.name for v in vendors]
            matches = process.extractOne(payee_name, vendor_names, scorer=fuzz.ratio)
            
            if matches and matches[1] >= threshold:
                matched_name, score = matches[0], matches[1]
                matched_vendor = next((v for v in vendors if v.name == matched_name), None)
                
                if matched_vendor and (not best_match or score > best_score):
                    best_match = matched_vendor
                    best_score = score
        
        if best_match and best_score >= threshold:
            return (best_match, best_score)
        
        return None
    
    @staticmethod
    def suggest_category_for_payee(
        db: Session,
        payee_name: str,
        vendor_id: Optional[int] = None
    ) -> Optional[Category]:
        """
        Suggest a category for a payee:
        1. Use vendor's category if vendor is known
        2. Use category from existing payee with same name
        3. Use most common category for similar payees
        """
        # 1. If vendor is provided, use vendor's category
        if vendor_id:
            vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
            if vendor and vendor.category_id:
                return db.query(Category).filter(Category.id == vendor.category_id).first()
        
        # 2. Check if any payee with this name has a category
        existing_payee = db.query(Payee).filter(
            Payee.normalized_name == normalize_payee_name(payee_name)
        ).first()
        
        if existing_payee:
            if existing_payee.category_id:
                return db.query(Category).filter(Category.id == existing_payee.category_id).first()
            
            # If payee has vendor, use vendor's category
            if existing_payee.vendor_id:
                vendor = db.query(Vendor).filter(Vendor.id == existing_payee.vendor_id).first()
                if vendor and vendor.category_id:
                    return db.query(Category).filter(Category.id == vendor.category_id).first()
        
        return None

