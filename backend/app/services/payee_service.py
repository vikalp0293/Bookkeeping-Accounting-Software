"""
Payee matching and management service.
Handles payee normalization, similarity matching, and corrections.
"""
import re
import logging
from typing import Optional, Dict, List, Tuple
from sqlalchemy.orm import Session
from app.models.payee import Payee, PayeeCorrection
from app.models.workspace import Workspace

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


class PayeeService:
    """Service for payee matching and management."""
    
    # Similarity threshold for auto-matching (0-100)
    MATCH_THRESHOLD = 85
    
    @staticmethod
    def is_amount(value: str) -> bool:
        """
        Check if a string is actually a monetary amount, not a payee name.
        
        Args:
            value: String to check
            
        Returns:
            True if the value appears to be an amount, False otherwise
        """
        if not value or not isinstance(value, str):
            return False
        
        value_clean = value.strip()
        
        # Remove currency symbols and whitespace for checking
        value_test = re.sub(r'[\$,\s]', '', value_clean)
        
        # Check if it's primarily numeric (more than 50% digits)
        digit_count = sum(1 for c in value_test if c.isdigit())
        total_chars = len(value_test)
        
        if total_chars == 0:
            return False
        
        # If more than 50% are digits, it's likely an amount
        if digit_count / total_chars > 0.5:
            # Check for common amount patterns
            amount_patterns = [
                r'^\$?\s*[\d,]+\.?\d{0,2}\s*$',  # $1,234.56 or 1234.56
                r'^\$?\s*[\d,]+\.\d{2}\s*$',  # $1,234.56 (with cents)
                r'^\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s*$',  # 1,234.56 or 1234.56
                r'^\$?\s*\d+\.\d{2}\s*$',  # $1234.56
            ]
            
            for pattern in amount_patterns:
                if re.match(pattern, value_clean):
                    return True
            
            # Check if it's a number that could be an amount (between 0.01 and 1,000,000)
            try:
                # Remove $ and commas, try to parse as float
                num_str = re.sub(r'[\$,\s]', '', value_clean)
                if '.' in num_str:
                    num_value = float(num_str)
                else:
                    num_value = float(num_str)
                
                # If it's a reasonable amount range, it's likely an amount
                if 0.01 <= num_value <= 1000000:
                    return True
            except (ValueError, TypeError):
                pass
        
        return False
    
    @staticmethod
    def normalize_payee_name(name: str) -> str:
        """
        Normalize payee name for matching.
        - Convert to lowercase
        - Remove punctuation
        - Remove extra whitespace
        - Handle common variations
        """
        if not name:
            return ""
        
        # Convert to lowercase
        normalized = name.lower().strip()
        
        # Remove common punctuation
        normalized = re.sub(r'[.,;:!?\'"()\[\]{}]', '', normalized)
        
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # Handle common business suffixes
        normalized = re.sub(r'\b(inc|llc|corp|ltd|co|company)\b', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    @staticmethod
    def find_matching_payee(
        db: Session,
        extracted_payee: str,
        workspace_id: int,
        threshold: int = None
    ) -> Optional[Tuple[Payee, float]]:
        """
        Find matching payee in database using fuzzy matching.
        
        Returns:
            Tuple of (Payee object, similarity_score) or None if no match found
        """
        if not FUZZY_AVAILABLE:
            logger.warning("Fuzzy matching not available, skipping payee matching")
            return None
        
        if not extracted_payee or not extracted_payee.strip():
            return None
        
        threshold = threshold or PayeeService.MATCH_THRESHOLD
        normalized_extracted = PayeeService.normalize_payee_name(extracted_payee)
        
        if not normalized_extracted:
            return None
        
        # Get all payees for this workspace
        payees = db.query(Payee).filter(Payee.workspace_id == workspace_id).all()
        
        if not payees:
            return None
        
        # Create list of normalized names for matching (include display_name and aliases)
        payee_names = []
        payee_mapping = {}  # Map normalized name to payee object
        
        for payee in payees:
            # Add display name
            normalized_display = PayeeService.normalize_payee_name(payee.display_name)
            if normalized_display:
                payee_names.append(normalized_display)
                payee_mapping[normalized_display] = payee
            
            # Add aliases if they exist
            if payee.aliases:
                for alias in payee.aliases:
                    if alias:
                        normalized_alias = PayeeService.normalize_payee_name(alias)
                        if normalized_alias and normalized_alias not in payee_mapping:
                            payee_names.append(normalized_alias)
                            payee_mapping[normalized_alias] = payee
        
        # Find best match using fuzzy matching
        if FUZZY_AVAILABLE:
            try:
                # Use rapidfuzz or fuzzywuzzy process.extractOne
                result = process.extractOne(
                    normalized_extracted,
                    payee_names,
                    scorer=fuzz.ratio
                )
                
                if result and result[1] >= threshold:
                    matched_name = result[0]
                    # Get the payee from mapping
                    matched_payee = payee_mapping.get(matched_name)
                    if matched_payee:
                        return (matched_payee, result[1])
            except Exception as e:
                logger.error(f"Error in fuzzy matching: {e}")
        
        return None
    
    @staticmethod
    def create_or_get_payee(
        db: Session,
        payee_name: str,
        workspace_id: int,
        auto_match: bool = True,
        suggest_vendor_category: bool = True
    ) -> Tuple[Payee, bool, Optional[float]]:
        """
        Create a new payee or get existing one.
        
        Returns:
            Tuple of (Payee object, is_new, similarity_score)
        """
        if not payee_name or not payee_name.strip():
            raise ValueError("Payee name cannot be empty")
        
        # Validate that payee_name is not actually an amount
        if PayeeService.is_amount(payee_name):
            logger.warning(f"Rejected amount as payee name: '{payee_name}'. This appears to be a monetary amount, not a payee name.")
            raise ValueError(f"Invalid payee name: '{payee_name}' appears to be a monetary amount, not a payee name")
        
        normalized_name = PayeeService.normalize_payee_name(payee_name)
        
        # Check if payee already exists
        existing_payee = db.query(Payee).filter(
            Payee.workspace_id == workspace_id,
            Payee.normalized_name == normalized_name
        ).first()
        
        if existing_payee:
            # Update usage count
            existing_payee.usage_count += 1
            db.commit()
            return (existing_payee, False, 100.0)
        
        # Try to find similar payee if auto_match is enabled
        similarity_score = None
        if auto_match:
            match_result = PayeeService.find_matching_payee(
                db, payee_name, workspace_id
            )
            if match_result:
                matched_payee, similarity_score = match_result
                # Use the matched payee
                matched_payee.usage_count += 1
                db.commit()
                return (matched_payee, False, similarity_score)
        
        # Create new payee
        new_payee = Payee(
            normalized_name=normalized_name,
            display_name=payee_name.strip(),
            workspace_id=workspace_id,
            usage_count=1
        )
        
        # Suggest vendor and category if enabled
        if suggest_vendor_category:
            try:
                from app.services.vendor_service import VendorService
                
                # Suggest vendor
                vendor_suggestion = VendorService.suggest_vendor_for_payee(db, payee_name)
                if vendor_suggestion:
                    vendor, vendor_score = vendor_suggestion
                    new_payee.vendor_id = vendor.id
                    logger.info(f"Auto-assigned vendor '{vendor.name}' to payee '{payee_name}' (score: {vendor_score})")
                
                # Suggest category (use vendor's category if vendor was suggested)
                category_suggestion = VendorService.suggest_category_for_payee(
                    db, payee_name, new_payee.vendor_id
                )
                if category_suggestion:
                    new_payee.category_id = category_suggestion.id
                    logger.info(f"Auto-assigned category '{category_suggestion.name}' to payee '{payee_name}'")
            except Exception as e:
                logger.warning(f"Failed to suggest vendor/category for payee '{payee_name}': {e}")
        
        db.add(new_payee)
        db.commit()
        db.refresh(new_payee)
        
        return (new_payee, True, None)
    
    @staticmethod
    def record_correction(
        db: Session,
        payee_id: int,
        original_payee: str,
        corrected_payee: str,
        user_id: int,
        file_id: Optional[int] = None,
        transaction_id: Optional[str] = None,
        reason: Optional[str] = None,
        similarity_score: Optional[float] = None
    ) -> PayeeCorrection:
        """Record a payee correction."""
        correction = PayeeCorrection(
            payee_id=payee_id,
            original_payee=original_payee,
            corrected_payee=corrected_payee,
            user_id=user_id,
            file_id=file_id,
            transaction_id=transaction_id,
            correction_reason=reason,
            similarity_score=similarity_score
        )
        db.add(correction)
        db.commit()
        db.refresh(correction)
        
        # Update payee display name if correction is significant
        payee = db.query(Payee).filter(Payee.id == payee_id).first()
        if payee and corrected_payee != payee.display_name:
            # Update if the correction is more "standard" (longer, has proper capitalization)
            if len(corrected_payee) > len(payee.display_name) or corrected_payee[0].isupper():
                payee.display_name = corrected_payee
                payee.normalized_name = PayeeService.normalize_payee_name(corrected_payee)
                db.commit()
        
        return correction
    
    @staticmethod
    def get_suggested_payees(
        db: Session,
        workspace_id: int,
        limit: int = 10
    ) -> List[Payee]:
        """Get suggested payees (most frequently used)."""
        return db.query(Payee).filter(
            Payee.workspace_id == workspace_id
        ).order_by(
            Payee.usage_count.desc()
        ).limit(limit).all()
    
    @staticmethod
    def get_recent_payees(
        db: Session,
        workspace_id: int,
        user_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Payee]:
        """Get recently used payees."""
        query = db.query(Payee).filter(
            Payee.workspace_id == workspace_id
        )
        
        if user_id:
            # Get payees from user's recent corrections
            recent_corrections = db.query(PayeeCorrection).filter(
                PayeeCorrection.user_id == user_id
            ).order_by(
                PayeeCorrection.created_at.desc()
            ).limit(limit * 2).all()
            
            payee_ids = [c.payee_id for c in recent_corrections]
            if payee_ids:
                query = query.filter(Payee.id.in_(payee_ids))
        
        return query.order_by(Payee.updated_at.desc()).limit(limit).all()

