"""
Extracts multiple checks from a single PDF (one or more check per page).
Each page is split into a 2x2 grid of regions (like StatementWithChecksExtractor);
each region is run through CheckExtractor. Full-page fallback used when grid yields no check.
"""
import os
import tempfile
import logging
from typing import Dict, Any, List, Tuple

from app.services.check_extractor import CheckExtractor
from app.services.document_type_classifier import classify_for_extraction
from app.services.statement_with_checks_extractor import _split_page_into_regions

logger = logging.getLogger(__name__)


def _check_data_to_transaction(check_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert CheckExtractor result to a statement-like transaction row."""
    amount = check_data.get("amount")
    if amount is None:
        return None
    return {
        "date": check_data.get("date") or "",
        "amount": abs(float(amount)),
        "description": f"Check #{check_data.get('check_number') or ''}",
        "payee": (check_data.get("payee") or "").strip() or "Unknown",
        "transaction_type": "WITHDRAWAL",
        "reference_number": check_data.get("check_number"),
        "check_number": check_data.get("check_number"),
        "memo": check_data.get("memo"),
    }


class MultiCheckExtractor:
    """Extract multiple checks from one PDF; supports multiple checks per page via 2x2 grid split."""

    @staticmethod
    def extract(file_path: str) -> Dict[str, Any]:
        """
        Extract transactions from all check images. Each page is split into up to 4 regions (2x2);
        each region is OCR'd as a check. If no region on a page yields a check, the full page is tried.
        Returns same shape as statement: document_type, transactions (each with payee, amount, date, etc.).
        """
        classification = classify_for_extraction(file_path)
        check_page_indices = classification.get("check_image_page_indices") or []
        page_count = classification.get("page_count", 0)

        # If classifier didn't return check pages but we have multiple pages, treat all as check pages
        if not check_page_indices and page_count > 1:
            check_page_indices = list(range(page_count))
        elif not check_page_indices and page_count == 1:
            check_page_indices = [0]

        transactions: List[Dict[str, Any]] = []
        try:
            import pdf2image
        except ImportError:
            logger.warning("pdf2image not available for multi-check extraction")
            return {
                "document_type": "multi_check",
                "error": "pdf2image not available",
                "transactions": [],
            }

        for page_idx in check_page_indices:
            try:
                page_images = pdf2image.convert_from_path(
                    file_path,
                    first_page=page_idx + 1,
                    last_page=page_idx + 1,
                    dpi=200,
                )
                if not page_images:
                    continue
                page_img = page_images[0]
                regions = _split_page_into_regions(page_img)
                page_transactions_before = len(transactions)

                # Try each grid region (up to 4 checks per page)
                for region_idx, (x0, y0, x1, y1) in enumerate(regions):
                    tmp_path = None
                    try:
                        cropped = page_img.crop((x0, y0, x1, y1)) if hasattr(page_img, "crop") else page_img
                        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                            cropped.save(tmp.name, "PNG")
                            tmp_path = tmp.name
                        check_data = CheckExtractor.extract_check_data(tmp_path)
                        if check_data.get("error"):
                            continue
                        trans = _check_data_to_transaction(check_data)
                        if trans:
                            transactions.append(trans)
                            logger.info(
                                "MultiCheck: page %d region %d -> Check #%s -> %s",
                                page_idx + 1,
                                region_idx + 1,
                                check_data.get("check_number"),
                                trans["payee"],
                            )
                    except Exception as e:
                        logger.debug("MultiCheck: page %d region %d failed: %s", page_idx + 1, region_idx + 1, e)
                    finally:
                        if tmp_path and os.path.exists(tmp_path):
                            try:
                                os.unlink(tmp_path)
                            except OSError:
                                pass

                # Full-page fallback if no region produced a check (e.g. one large check per page)
                if len(transactions) <= page_transactions_before and len(regions) > 1:
                    tmp_path = None
                    try:
                        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                            page_img.save(tmp.name, "PNG")
                            tmp_path = tmp.name
                        check_data = CheckExtractor.extract_check_data(tmp_path)
                        if not check_data.get("error"):
                            trans = _check_data_to_transaction(check_data)
                            if trans:
                                transactions.append(trans)
                                logger.info(
                                    "MultiCheck: page %d (full-page fallback) -> Check #%s -> %s",
                                    page_idx + 1,
                                    check_data.get("check_number"),
                                    trans["payee"],
                                )
                    except Exception as e:
                        logger.debug("MultiCheck: page %d full-page fallback failed: %s", page_idx + 1, e)
                    finally:
                        if tmp_path and os.path.exists(tmp_path):
                            try:
                                os.unlink(tmp_path)
                            except OSError:
                                pass

            except Exception as e:
                logger.warning("MultiCheck: failed to extract from page %d: %s", page_idx + 1, e)

        return {
            "document_type": "multi_check",
            "bank_name": None,
            "account_number": None,
            "statement_period_start": None,
            "statement_period_end": None,
            "beginning_balance": None,
            "ending_balance": None,
            "transactions": transactions,
        }
