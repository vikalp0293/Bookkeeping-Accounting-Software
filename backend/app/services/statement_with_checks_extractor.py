"""
Extracts from a bank statement PDF that has attached check images.
Statement-first: extract check metadata (number, date, amount) from "Checks Paid" section,
then OCR check image pages (optionally split into grid regions), match by check number,
enrich statement transactions with payees from images.
"""
import os
import re
import tempfile
import logging
from typing import Dict, Any, List, Optional, Tuple

from app.services.pdf_extractor import PDFExtractor
from app.services.check_extractor import CheckExtractor
from app.services.check_ai_extractor import CheckAIExtractor
from app.services.document_type_classifier import classify_for_extraction
from app.utils.statement_check_filter import get_check_number_from_transaction

logger = logging.getLogger(__name__)

# Minimum size for a grid region (avoid tiny crops that OCR poorly)
MIN_REGION_WIDTH = 280
MIN_REGION_HEIGHT = 200


def _normalize_check_number(num: Optional[str]) -> str:
    """Normalize for matching: strip leading zeros, digits only."""
    if not num:
        return ""
    s = re.sub(r"\D", "", str(num))
    return s.lstrip("0") or "0"


def _split_page_into_regions(image) -> List[Tuple[int, int, int, int]]:
    """
    Split a page image into regions (grid) for multiple checks per page.
    US Bank layout: typically 2-4 checks per page (2x2 grid).
    Returns list of (x0, y0, x1, y1) crop boxes.
    """
    w = getattr(image, "width", None) or (image.size[0] if hasattr(image, "size") else 0)
    h = getattr(image, "height", None) or (image.size[1] if hasattr(image, "size") else 0)
    if w < MIN_REGION_WIDTH * 2 or h < MIN_REGION_HEIGHT * 2:
        return [(0, 0, w, h)]
    half_w = w // 2
    half_h = h // 2
    return [
        (0, 0, half_w, half_h),
        (half_w, 0, w, half_h),
        (0, half_h, half_w, h),
        (half_w, half_h, w, h),
    ]


class StatementWithChecksExtractor:
    """Extract statement + enrich check-line transactions from attached check images."""

    @staticmethod
    def extract(file_path: str, original_filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract statement (with check lines included), then OCR check image pages,
        match by check number, and set payee on matching transactions.

        Returns:
            Same shape as PDFExtractor result: document_type, bank_name, transactions, etc.
        """
        # 1) Statement extraction with check lines kept (do not filter)
        result = PDFExtractor.extract_from_pdf(
            file_path,
            original_filename=original_filename,
            skip_statement_check_filter=True,
        )
        if result.get("error"):
            return result

        transactions = result.get("transactions") or []
        if not transactions:
            return result

        # 2) Which pages are check images?
        classification = classify_for_extraction(file_path)
        check_page_indices = classification.get("check_image_page_indices") or []
        logger.info(
            "Statement+checks: %d transactions, %d check image pages (indices %s)",
            len(transactions),
            len(check_page_indices),
            check_page_indices,
        )
        if not check_page_indices:
            logger.info("Statement+checks: no check image pages identified, returning statement as-is")
            return result

        # 3) OCR check image pages: split each page into grid regions (2x2), extract check_number + payee per region
        check_number_to_payee: Dict[str, str] = {}
        try:
            import pdf2image
        except ImportError:
            logger.warning("pdf2image not available, cannot extract payees from check images")
            return result

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
                page_payee_count_before = len(check_number_to_payee)
                for region_idx, (x0, y0, x1, y1) in enumerate(regions):
                    try:
                        cropped = page_img.crop((x0, y0, x1, y1)) if hasattr(page_img, "crop") else page_img
                        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                            cropped.save(tmp.name, "PNG")
                            tmp_path = tmp.name
                        try:
                            check_data = CheckExtractor.extract_check_data(tmp_path)
                            if check_data.get("error"):
                                continue
                            cnum = check_data.get("check_number")
                            payee = (check_data.get("payee") or "").strip()
                            if cnum and not payee:
                                payee_aggressive = CheckAIExtractor.extract_payee_only_aggressive(
                                    tmp_path, check_number_hint=cnum
                                )
                                if payee_aggressive:
                                    payee = payee_aggressive
                                    logger.info(
                                        "Statement+checks: page %d region %d -> Check #%s -> payee from aggressive AI: %s",
                                        page_idx + 1,
                                        region_idx + 1,
                                        cnum,
                                        payee,
                                    )
                            if cnum and payee:
                                key = _normalize_check_number(cnum)
                                if key:
                                    check_number_to_payee[key] = payee
                                    logger.info(
                                        "Statement+checks: page %d region %d -> Check #%s -> %s",
                                        page_idx + 1,
                                        region_idx + 1,
                                        cnum,
                                        payee,
                                    )
                        finally:
                            try:
                                os.unlink(tmp_path)
                            except OSError:
                                pass
                    except Exception as reg_e:
                        logger.debug("Statement+checks: page %d region %d failed: %s", page_idx + 1, region_idx + 1, reg_e)
                # Fallback: if grid yielded no new payees for this page, run OCR on full page (single check or different layout)
                page_payee_count_after = len(check_number_to_payee)
                if page_payee_count_after <= page_payee_count_before and len(regions) > 1:
                    try:
                        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                            page_img.save(tmp.name, "PNG")
                            tmp_path = tmp.name
                        try:
                            check_data = CheckExtractor.extract_check_data(tmp_path)
                            if not check_data.get("error"):
                                cnum = check_data.get("check_number")
                                payee = (check_data.get("payee") or "").strip()
                                if cnum and not payee:
                                    payee = CheckAIExtractor.extract_payee_only_aggressive(
                                        tmp_path, check_number_hint=cnum
                                    ) or ""
                                if cnum and payee:
                                    key = _normalize_check_number(cnum)
                                    if key:
                                        check_number_to_payee[key] = payee
                                        logger.info(
                                            "Statement+checks: page %d (full-page fallback) -> Check #%s -> %s",
                                            page_idx + 1,
                                            cnum,
                                            payee,
                                        )
                        finally:
                            try:
                                os.unlink(tmp_path)
                            except OSError:
                                pass
                    except Exception as fp_e:
                        logger.debug("Statement+checks: page %d full-page fallback failed: %s", page_idx + 1, fp_e)
            except Exception as e:
                logger.warning(f"Statement+checks: failed to extract check from page {page_idx + 1}: {e}")

        # 4) Match statement check lines to image payees by check number (join key)
        check_line_count = 0
        enriched_count = 0
        for trans in transactions:
            trans_check_num = get_check_number_from_transaction(trans)
            if not trans_check_num:
                continue
            check_line_count += 1
            key = _normalize_check_number(trans_check_num)
            payee = check_number_to_payee.get(key)
            if payee:
                trans["payee"] = payee
                enriched_count += 1
                logger.debug(f"Enriched transaction check #{trans_check_num} with payee: {payee}")
            else:
                trans["payee_status"] = "IMAGE_MISSING"

        logger.info(
            "Statement+checks: %d check-line transactions, %d enriched from OCR (OCR map keys: %s)",
            check_line_count,
            enriched_count,
            list(check_number_to_payee.keys()),
        )
        result["document_type"] = "bank_statement"
        result["transactions"] = transactions
        return result
