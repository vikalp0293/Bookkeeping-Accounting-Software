"""
Classifies a PDF into one of four extraction types:
- individual_check: single check (existing CheckExtractor)
- bank_statement_only: statement only (existing PDFExtractor)
- bank_statement_with_checks: statement + attached check images (StatementWithChecksExtractor)
- multi_check: multiple checks in one PDF (MultiCheckExtractor)

Uses rule-based page classification (deterministic, bank-friendly):
- "IMAGES FOR YOUR ... CHECKING ACCOUNT" -> check image page
- "Checks Paid" / "Check Date Ref Number Amount" -> statement page with check summary
- Fallback: text length and PAY TO THE ORDER OF / STATEMENT keywords
"""
import re
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Rule-based signals (recommended: deterministic, auditable)
IMAGES_FOR_YOUR_SIGNAL = "IMAGES FOR YOUR"  # US Bank: "IMAGES FOR YOUR SILVER BUSINESS CHECKING ACCOUNT"
CHECK_SUMMARY_SIGNALS = ("Checks Paid", "Check Date", "Ref Number", "Amount")  # Check summary table header

# Text length thresholds (chars) - fallback when rule-based signals absent
MIN_TEXT_STATEMENT_PAGE = 1200
MAX_TEXT_CHECK_IMAGE_PAGE = 600
MIN_IMAGES_FOR_CHECK_PAGE = 4

# Keywords (fallback)
CHECK_INDICATORS = ["PAY TO THE ORDER OF", "PAY TO ORDER OF", "DOLLARS", "ROUTING", "RTN"]
STATEMENT_INDICATORS = ["STATEMENT", "BALANCE", "BEGINNING", "ENDING", "ACCOUNT", "TRANSACTION", "DEPOSIT", "WITHDRAWAL", "DEBIT", "CREDIT"]


def classify_for_extraction(file_path: str) -> Dict[str, Any]:
    """
    Classify PDF into one of: individual_check, bank_statement_only, bank_statement_with_checks, multi_check.

    Returns:
        {
            "document_type": "individual_check" | "bank_statement_only" | "bank_statement_with_checks" | "multi_check",
            "confidence": float,
            "reasoning": str,
            "page_count": int,
            "statement_page_indices": [int],
            "check_image_page_indices": [int],
        }
    """
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not available, defaulting to bank_statement_only")
        return {
            "document_type": "bank_statement_only",
            "confidence": 0.5,
            "reasoning": "pdfplumber not available",
            "page_count": 0,
            "statement_page_indices": [],
            "check_image_page_indices": [],
        }

    try:
        with pdfplumber.open(file_path) as pdf:
            page_count = len(pdf.pages)
            if page_count == 0:
                return {
                    "document_type": "bank_statement_only",
                    "confidence": 0.5,
                    "reasoning": "Empty PDF",
                    "page_count": 0,
                    "statement_page_indices": [],
                    "check_image_page_indices": [],
                }

            statement_pages: List[int] = []
            check_pages: List[int] = []

            for idx, page in enumerate(pdf.pages):
                text = (page.extract_text() or "").strip()
                text_upper = text.upper()
                n = len(text)
                num_images = len(getattr(page, "images", []) or [])

                # Phase 1: Rule-based classification (deterministic, preferred)
                if IMAGES_FOR_YOUR_SIGNAL in text_upper:
                    # "IMAGES FOR YOUR ... CHECKING ACCOUNT" -> check image page
                    check_pages.append(idx)
                    continue
                if "Checks Paid" in text_upper or ("Check Date" in text_upper and "Ref Number" in text_upper):
                    # Check summary table or section -> statement page
                    statement_pages.append(idx)
                    continue

                # Fallback: heuristics (require positive check evidence for short pages to avoid misclassifying statement-only PDFs with a short/blank last page)
                has_check_kw = any(kw in text_upper for kw in CHECK_INDICATORS)
                has_stmt_kw = any(kw in text_upper for kw in STATEMENT_INDICATORS)
                if num_images >= MIN_IMAGES_FOR_CHECK_PAGE and n < 1000:
                    check_pages.append(idx)
                elif has_check_kw and not (n >= MIN_TEXT_STATEMENT_PAGE and has_stmt_kw):
                    check_pages.append(idx)
                elif n >= MIN_TEXT_STATEMENT_PAGE or has_stmt_kw:
                    statement_pages.append(idx)
                elif n <= MAX_TEXT_CHECK_IMAGE_PAGE:
                    # Short text only: treat as check page only if it looks like a check (has check keywords), else treat as statement/other so statement-only PDFs with footer pages don't become "statement + checks"
                    if has_check_kw:
                        check_pages.append(idx)
                    else:
                        statement_pages.append(idx)
                else:
                    statement_pages.append(idx)

            # Decide document type
            num_stmt = len(statement_pages)
            num_check = len(check_pages)

            if page_count == 1:
                if num_check == 1 and num_stmt == 0:
                    return {
                        "document_type": "individual_check",
                        "confidence": 0.85,
                        "reasoning": "Single page with check-like content or low text",
                        "page_count": 1,
                        "statement_page_indices": [],
                        "check_image_page_indices": [0],
                    }
                else:
                    return {
                        "document_type": "bank_statement_only",
                        "confidence": 0.85,
                        "reasoning": "Single page with substantial text (statement)",
                        "page_count": 1,
                        "statement_page_indices": [0],
                        "check_image_page_indices": [],
                    }

            # Multiple pages
            if num_stmt > 0 and num_check > 0:
                return {
                    "document_type": "bank_statement_with_checks",
                    "confidence": 0.8,
                    "reasoning": f"Mix of statement pages ({num_stmt}) and check image pages ({num_check})",
                    "page_count": page_count,
                    "statement_page_indices": statement_pages,
                    "check_image_page_indices": check_pages,
                }
            if num_check >= 2 and num_stmt == 0:
                return {
                    "document_type": "multi_check",
                    "confidence": 0.8,
                    "reasoning": f"Multiple pages ({num_check}) with check-like content",
                    "page_count": page_count,
                    "statement_page_indices": [],
                    "check_image_page_indices": check_pages,
                }
            # All statement
            return {
                "document_type": "bank_statement_only",
                "confidence": 0.85,
                "reasoning": f"All {page_count} pages have substantial text (statement)",
                "page_count": page_count,
                "statement_page_indices": list(range(page_count)),
                "check_image_page_indices": [],
            }

    except Exception as e:
        logger.warning(f"Document type classification failed: {e}", exc_info=True)
        return {
            "document_type": "bank_statement_only",
            "confidence": 0.5,
            "reasoning": f"Classification error: {e}",
            "page_count": 0,
            "statement_page_indices": [],
            "check_image_page_indices": [],
        }
