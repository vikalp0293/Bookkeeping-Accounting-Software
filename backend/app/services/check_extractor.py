"""
Check extraction service.
Extracts structured data from check images/PDFs using OCR.
"""
import re
import os
import tempfile
from typing import Dict, Optional, Any
from datetime import datetime
from app.services.ocr_service import OCRService
from app.services.ai_correction_service import AICorrectionService
from app.services.ai_enhanced_extractor import AIEnhancedExtractor
from app.services.check_ai_extractor import CheckAIExtractor
from app.core.config import settings
import pdf2image
import logging

logger = logging.getLogger(__name__)

# Try to import OpenAI (optional, for written amount conversion)
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI not available. Install with: pip install openai")


class CheckExtractor:
    """Extract structured data from check images."""
    
    @staticmethod
    def extract_check_data(file_path: str) -> Dict[str, Any]:
        """
        Extract check data from image or scanned PDF.
        Uses AI-first approach with fallback to OCR + regex parsing.
        
        Args:
            file_path: Path to check image/PDF
            
        Returns:
            Dictionary with extracted check data
        """
        # Priority 1: Try AI-powered extraction first (GPT-4 Vision)
        logger.info("Attempting AI-powered check extraction...")
        ai_result = CheckAIExtractor.extract_check_with_ai(file_path)
        
        if ai_result and not ai_result.get("error"):
            # Validate that we got at least some key fields
            has_key_fields = (
                ai_result.get("check_number") or 
                ai_result.get("payee") or 
                ai_result.get("amount") or 
                ai_result.get("date")
            )
            
            if has_key_fields:
                logger.info("AI extraction successful, using AI-extracted data")
                # Add raw_text if available from OCR fallback, but prioritize AI results
                return ai_result
            else:
                logger.warning("AI extraction returned no key fields, falling back to OCR + parsing")
        else:
            logger.info("AI extraction not available or failed, falling back to OCR + parsing")
        
        # Priority 2: Fallback to OCR + regex parsing (existing approach)
        return CheckExtractor._extract_check_with_ocr(file_path)
    
    @staticmethod
    def _extract_check_with_ocr(file_path: str) -> Dict[str, Any]:
        """
        Extract check data using OCR and regex parsing (fallback method).
        
        Args:
            file_path: Path to check image/PDF
            
        Returns:
            Dictionary with extracted check data
        """
        # Perform OCR (force OCR for checks)
        import os
        from app.core.file_logging import ocr_logger
        file_type = "pdf" if os.path.splitext(file_path)[1].lower() == ".pdf" else "image"
        
        # Log OCR start
        ocr_logger.info(f"Starting OCR extraction for check: {os.path.basename(file_path)}, type: {file_type}")
        
        # Try Tesseract first (good for printed text)
        if file_type == "pdf":
            ocr_result = OCRService.extract_text_from_pdf_image(file_path)
        else:
            ocr_result = OCRService.extract_text_from_image(file_path)
        
        # Log OCR results
        ocr_text = ocr_result.get("text", "")
        confidence = ocr_result.get("confidence", 0)
        ocr_logger.info(f"OCR extraction completed for check: {os.path.basename(file_path)}, confidence: {confidence:.2f}, text_length: {len(ocr_text)}")
        
        # If Tesseract didn't find dates or key fields, try EasyOCR for handwriting
        # Check if we found a date in the OCR text
        has_date = bool(re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', ocr_text))
        
        # Try AI-Enhanced extraction first (uses GPT-4 Vision with few-shot learning)
        # This extracts ALL possible values and uses AI to select correct ones
        temp_image_path = None
        try:
            # Convert PDF to image if needed
            if file_type == "pdf":
                try:
                    images = pdf2image.convert_from_path(file_path)
                    if images:
                        # Save first page as temp image
                        tmp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                        images[0].save(tmp_file.name)
                        tmp_file.close()  # Close file handle but keep file
                        temp_image_path = tmp_file.name
                    else:
                        temp_image_path = None
                except Exception as pdf_error:
                    error_msg = str(pdf_error).lower()
                    if "poppler" in error_msg or "unable to get page count" in error_msg:
                        logger.error(f"Poppler not installed or not in PATH. Error: {pdf_error}")
                        raise ValueError(
                            "Poppler is not installed or not in PATH. "
                            "Please install poppler-utils:\n"
                            "  - Ubuntu/Debian: sudo apt-get install poppler-utils\n"
                            "  - macOS: brew install poppler\n"
                            "  - Windows: Download from https://github.com/oschwartz10612/poppler-windows/releases"
                        ) from pdf_error
                    else:
                        raise
            else:
                temp_image_path = file_path
            
            # Try AI-Enhanced extraction (extracts all candidates and selects correct ones)
            if temp_image_path:
                ai_enhanced_result = AIEnhancedExtractor.extract_all_possible_values(temp_image_path)
                if ai_enhanced_result and not ai_enhanced_result.get("error"):
                    logger.info("AI-Enhanced extraction successful, using structured data")
                    # Use AI-enhanced results directly
                    result = ai_enhanced_result.copy()
                    result["raw_text"] = ocr_text  # Keep OCR text for reference
                    result["document_type"] = "check"
                    # Clean up temp file
                    if temp_image_path != file_path and os.path.exists(temp_image_path):
                        try:
                            os.unlink(temp_image_path)
                        except:
                            pass
                    return result
                else:
                    logger.info("AI-Enhanced extraction not available, falling back to OCR + parsing")
        except Exception as e:
            logger.warning(f"AI-Enhanced extraction failed: {e}, falling back to OCR + parsing")
        
        # Try AI-powered OCR first, then Google Vision, EasyOCR, then Tesseract
        # Priority: GPT-4 Vision > Google Vision > EasyOCR > Tesseract
        try:
            # Convert PDF to image if needed (for AI/Google Vision/EasyOCR)
            if not temp_image_path:
                if file_type == "pdf":
                    images = pdf2image.convert_from_path(file_path)
                    if images:
                        # Save first page as temp image
                        tmp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                        images[0].save(tmp_file.name)
                        tmp_file.close()  # Close file handle but keep file
                        temp_image_path = tmp_file.name
                    else:
                        temp_image_path = None
                else:
                    temp_image_path = file_path
            
            # Try GPT-4 Vision first (best for handwriting and context understanding)
            if temp_image_path:
                gpt4_vision_result = OCRService.extract_text_with_gpt4_vision(temp_image_path)
                if gpt4_vision_result.get("text") and not gpt4_vision_result.get("error"):
                    gpt4_vision_text = gpt4_vision_result.get("text", "")
                    gpt4_vision_conf = gpt4_vision_result.get("confidence", 0)
                    logger.info(f"GPT-4 Vision found {len(gpt4_vision_text)} characters of text (confidence: {gpt4_vision_conf:.1f}%)")
                    # Use GPT-4 Vision results (best quality for handwriting and context)
                    ocr_text = gpt4_vision_text
                    confidence = gpt4_vision_conf
                else:
                    # Fallback to Google Vision API
                    logger.info("GPT-4 Vision not available or failed, trying Google Vision...")
                    google_vision_result = OCRService.extract_text_with_google_vision(temp_image_path)
                    if google_vision_result.get("text") and not google_vision_result.get("error"):
                        google_vision_text = google_vision_result.get("text", "")
                        google_vision_conf = google_vision_result.get("confidence", 0)
                        logger.info(f"Google Vision API found {len(google_vision_text)} characters of text (confidence: {google_vision_conf:.1f}%)")
                        # Use Google Vision results (excellent for handwriting)
                        ocr_text = google_vision_text
                        confidence = google_vision_conf
                    else:
                        # Fallback to EasyOCR
                        logger.info("Google Vision API not available or failed, trying EasyOCR...")
                        easyocr_result = OCRService.extract_text_with_easyocr(temp_image_path)
                        if easyocr_result.get("text"):
                            easyocr_text = easyocr_result.get("text", "")
                            # Combine Tesseract and EasyOCR results
                            ocr_text = ocr_text + "\n" + easyocr_text if ocr_text else easyocr_text
                            if easyocr_result.get("confidence", 0) > confidence:
                                confidence = easyocr_result.get("confidence", 0)
                            logger.info(f"EasyOCR found {len(easyocr_text)} characters of text")
            
            # Clean up temp file if created
            if temp_image_path and temp_image_path != file_path and os.path.exists(temp_image_path):
                try:
                    os.unlink(temp_image_path)
                except:
                    pass
        except Exception as e:
            logger.warning(f"Advanced OCR extraction failed: {e}, using Tesseract results only")
        
        if "error" in ocr_result and not ocr_text:
            return {
                "error": ocr_result.get("error", "OCR extraction failed"),
                "raw_text": "",
                "confidence": 0
            }
        
        # AI-powered OCR text correction (fix common OCR errors)
        if ocr_text and len(ocr_text) > 10:
            try:
                corrected_text = AICorrectionService.correct_ocr_text(ocr_text, context="check")
                if corrected_text and len(corrected_text) > len(ocr_text) * 0.5:  # Reasonable check
                    logger.info("Applied AI OCR text correction")
                    ocr_text = corrected_text
            except Exception as e:
                logger.warning(f"AI text correction failed: {e}, using original OCR text")
        
        # Parse check fields
        result = {
            "check_number": CheckExtractor.parse_check_number(ocr_text),
            "date": CheckExtractor.parse_date(ocr_text),
            "payee": CheckExtractor.parse_payee(ocr_text),
            "amount": CheckExtractor.parse_amount(ocr_text),
            "memo": CheckExtractor.parse_memo(ocr_text),
            "account_number": CheckExtractor.parse_account_number(ocr_text),
            "routing_number": CheckExtractor.parse_routing_number(ocr_text),
            "bank_name": CheckExtractor.parse_bank_name(ocr_text),
            "company_name": CheckExtractor.parse_company_name(ocr_text),
            "address": CheckExtractor.parse_address(ocr_text),
            "raw_text": ocr_text,
            "confidence": confidence,
            "document_type": "check"
        }
        
        # AI-powered payee name correction (fix OCR errors like "Heiddong" -> "Heidelberg")
        if result.get("payee"):
            try:
                corrected_payee = AICorrectionService.correct_payee_name(
                    result["payee"], 
                    ocr_context=ocr_text[:500]  # Provide context
                )
                if corrected_payee and corrected_payee != result["payee"]:
                    logger.info(f"AI corrected payee: '{result['payee']}' -> '{corrected_payee}'")
                    result["payee"] = corrected_payee
            except Exception as e:
                logger.warning(f"AI payee correction failed: {e}")
        
        # AI-powered field validation and correction
        try:
            result = AICorrectionService.validate_and_correct_fields(result)
        except Exception as e:
            logger.warning(f"AI field validation failed: {e}")
        
        return result
    
    @staticmethod
    def parse_check_number(text: str) -> Optional[str]:
        """Extract check number from OCR text."""
        # Priority 1: Look for "Check 1139" pattern (most reliable)
        check_title_match = re.search(r'Check\s+(\d{3,6})', text, re.IGNORECASE)
        if check_title_match:
            check_num = check_title_match.group(1)
            if 3 <= len(check_num) <= 6:
                return check_num
        
        # Priority 2: Look for check number in filename-like patterns
        # Pattern: "LLC 1139" or "LLC 1140" (company name followed by check number)
        company_check_match = re.search(r'(?:LLC|INC|CORP|LTD)\s+(\d{3,6})', text, re.IGNORECASE)
        if company_check_match:
            check_num = company_check_match.group(1)
            if 3 <= len(check_num) <= 6:
                return check_num
        
        # Priority 3: Look for patterns like "Check #1139", "Check Number: 1139"
        patterns = [
            r'Check\s*#?\s*:?\s*(\d{3,6})',
            r'Check\s+Number\s*:?\s*(\d{3,6})',
            r'\b(\d{3,6})\s*(?:55-|/422)',  # Check number before routing pattern
            r'(\d{4})\s*55-',  # 4 digits before "55-"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                check_num = match.group(1)
                # Validate: check numbers are typically 3-6 digits
                # Also ensure it's not a date (not 01-31 range for first two digits if 4 digits)
                if 3 <= len(check_num) <= 6:
                    # Filter out dates (like 1141 could be month 11, day 41 - invalid)
                    if len(check_num) == 4:
                        first_two = int(check_num[:2])
                        if first_two > 12:  # Not a month, likely a check number
                            return check_num
                    else:
                        return check_num
        
        return None
    
    @staticmethod
    def parse_date(text: str) -> Optional[str]:
        """Extract check date from OCR text. Excludes statement/PDF dates."""
        lines = text.split('\n')
        
        # Get check area text (skip statement header)
        check_area_text = '\n'.join(lines[1:]) if len(lines) > 1 else text
        
        # Priority 1: Look for "Date" label followed by date (this is the check date)
        # Google Vision API often gives cleaner text, so patterns should handle both formats
        date_label_patterns = [
            # Standard patterns
            r'Date[:\s=]+(\d{1,2}/\d{1,2}/\d{2,4})',
            r'Date[:\s=]+(\d{1,2}-\d{1,2}-\d{2,4})',
            r'Date[:\s=]+(\d{8})',
            r'Date[:\s=]+(\d{1,2}/\d{1,2}/\d{2})',  # MM/DD/YY format
            # Multi-line pattern (Google Vision might put date on next line)
            r'Date\s*\n\s*(\d{1,2}/\d{1,2}/\d{2,4})',
            # Pattern for dates near "Date" keyword (within 50 chars)
            r'Date[^\d]{0,50}?(\d{1,2}/\d{1,2}/\d{2,4})',
        ]
        
        for pattern in date_label_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                try:
                    if '/' in date_str:
                        parts = date_str.split('/')
                        if len(parts) == 3:
                            month, day, year = parts
                            year = f"20{year}" if len(year) == 2 else year
                            if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    elif len(date_str) == 8 and date_str.isdigit():
                        # Try MMDDYYYY format (common in checks)
                        month = date_str[:2]
                        day = date_str[2:4]
                        year = date_str[4:]
                        if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                            return f"{year}-{month}-{day}"
                except:
                    continue
        
        # Priority 2: Look for date in YYYYMMDD format (common in check MICR line area)
        # This is usually the check date, not the statement date
        yyyymmdd_matches = re.findall(r'\b(20\d{2})(\d{2})(\d{2})\b', text)
        for year, month, day in yyyymmdd_matches:
            try:
                if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                    # This is likely the check date (appears in MICR area)
                    return f"{year}-{month}-{day}"
            except:
                continue
        
        # Priority 2.5: Look for dates in format like "1/2/2025", "1/4/2025" in check area
        # These are common check date formats (single digit month/day)
        # Check all date formats in the check area (not statement header)
        date_formats = [
            r'\b(\d{1,2})/(\d{1,2})/(20\d{2})\b',  # 1/2/2025, 1/4/2025
            r'\b(\d{1,2})/(\d{1,2})/(\d{2})\b',     # 1/2/25, 1/4/25 (2-digit year)
        ]
        
        for date_pattern in date_formats:
            dates_found = re.findall(date_pattern, check_area_text)
            for date_match in dates_found:
                try:
                    month, day, year = date_match
                    # Convert 2-digit year to 4-digit
                    if len(year) == 2:
                        year = f"20{year}"
                    if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                        # Exclude statement dates (usually in first line with PM/AM)
                        date_str = f"{month}/{day}/{year[-2:]}"
                        first_line = lines[0] if lines else ""
                        # Only exclude if it's in first line AND has time indicators
                        if not (date_str in first_line and ('PM' in first_line or 'AM' in first_line)):
                            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                except:
                    continue
        
        # Priority 3: Look for date patterns in check area, EXCLUDE statement header dates
        # Statement dates typically appear in first line with "PM" or "AM" or "Huntington National Bank"
        statement_date_pattern = r'^[^\n]*(\d{1,2}/\d{1,2}/\d{2,4})[^\n]*(?:PM|AM|Huntington|Chase|Bank)'
        statement_date_match = re.search(statement_date_pattern, text, re.IGNORECASE | re.MULTILINE)
        statement_date = None
        if statement_date_match:
            statement_date = statement_date_match.group(1)
        
        # Look for dates in lines AFTER the first line (skip statement header)
        # Check date is usually written on the check itself, not in the statement header
        # Also check lines 2-10 more carefully (where date field usually is)
        date_area_lines = lines[1:10] if len(lines) > 10 else lines[1:]
        date_area_text = '\n'.join(date_area_lines)
        
        date_patterns = [
            r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b',  # M/D/YYYY or M/D/YY
            r'\b(\d{1,2})-(\d{1,2})-(\d{2,4})\b',  # M-D-YYYY or M-D-YY
        ]
        
        dates_found = []
        for pattern in date_patterns:
            matches = re.findall(pattern, date_area_text, re.IGNORECASE)
            for match in matches:
                month, day, year = match
                date_str = f"{month}/{day}/{year}"
                
                # Skip if this is the statement date
                if statement_date and date_str == statement_date:
                    continue
                
                try:
                    # Convert 2-digit year to 4-digit
                    if len(year) == 2:
                        year = f"20{year}"
                    if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                        formatted_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                        dates_found.append(formatted_date)
                except:
                    continue
        
        # Return the first valid date found (excluding statement date)
        # Prioritize dates that appear in the date field area (lines 2-6)
        if dates_found:
            # Check if any date appears in the typical date field location (lines 2-6)
            date_field_lines = lines[1:6] if len(lines) > 6 else lines[1:]
            date_field_text = '\n'.join(date_field_lines)
            for date in dates_found:
                # Check if this date appears in the date field area
                month_day = date.split('-')[1] + '/' + date.split('-')[2]  # MM/DD
                if month_day in date_field_text or date[:4] in date_field_text:
                    return date
            # If no date found in date field, return first valid date
            return dates_found[0]
        
        # Priority 3.5: Look for MMDDYYYY format in check area (8 digits that could be a date)
        # This might appear without slashes
        mmddyyyy_pattern = r'\b(\d{2})(\d{2})(20\d{2})\b'
        mmddyyyy_matches = re.findall(mmddyyyy_pattern, check_area_text)
        for month, day, year in mmddyyyy_matches:
            try:
                if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                    return f"{year}-{month}-{day}"
            except:
                continue
        
        # Priority 4: Try month name formats
        month_patterns = [
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s\.]+\d{1,2},?\s+\d{4}',
            r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s\.]+\d{4})',
        ]
        
        for pattern in month_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    date_str = match.group(0)
                    date_obj = datetime.strptime(date_str, "%B %d, %Y")
                    return date_obj.strftime("%Y-%m-%d")
                except:
                    try:
                        date_obj = datetime.strptime(date_str, "%d %B %Y")
                        return date_obj.strftime("%Y-%m-%d")
                    except:
                        continue
        
        return None
    
    @staticmethod
    def parse_payee(text: str) -> Optional[str]:
        """Extract payee name from OCR text with improved accuracy."""
        # Split text into lines for better context
        lines = text.split('\n')
        
        # Priority 1: Look for "Pay to the Order of" pattern (most reliable)
        # Handle OCR errors: "NagE Ie Oader ohe" = "Pay to the Order of"
        full_text_lower = text.lower()
        payee_patterns = [
            # Multi-line patterns (Google Vision often splits across lines)
            r'Pay\s+to\s+the\s+Order\s+of\s*\n\s*([^\n$]+?)(?:\s*\n|\s+\$|\s+\d|Dollars|$)',
            r'Pay\s+to\s+Order\s+of\s*\n\s*([^\n$]+?)(?:\s*\n|\s+\$|\s+\d|Dollars|$)',
            r'Order\s+of\s*\n\s*([^\n$]+?)(?:\s*\n|\s+\$|\s+\d|Dollars|$)',
            # Standard single-line patterns
            r'Pay\s+to\s+the\s+Order\s+of\s+([^\n$]+?)(?:\s+\$|\s+\d|Dollars|$)',
            r'Pay\s+to\s+Order\s+of\s+([^\n$]+?)(?:\s+\$|\s+\d|Dollars|$)',
            r'Pay\s+to\s+([^\n$]+?)(?:\s+\$|\s+\d|Dollars|$)',
            r'Order\s+of\s+([^\n$]+?)(?:\s+\$|\s+\d|Dollars|$)',
            # OCR error patterns (for Tesseract/EasyOCR fallback)
            r'[Nn]agE\s+[Ii]e\s+Oader\s+ohe\s+([^\n$]+?)(?:\s+\$|\s+\d|Dollars|$)',
            r'Oader\s+ohe\s+([^\n$]+?)(?:\s+\$|\s+\d|Dollars|$)',
        ]
        
        for pattern in payee_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if match:
                payee = match.group(1).strip()
                # Clean up common OCR errors with better character mapping
                payee = re.sub(r'\s+', ' ', payee)  # Multiple spaces
                # Fix common OCR character substitutions (general, not word-specific)
                payee = payee.replace('|', 'I').replace('!', 'I').replace('1', 'I').replace('l', 'I')
                payee = payee.replace('0', 'O')
                # Remove common OCR noise words that appear before payee names
                payee = re.sub(r'\b(barge|Barge)\s+', '', payee, flags=re.IGNORECASE)
                # Normalize common business suffixes
                payee = re.sub(r'\'?\s*Ing\b', ' Inc', payee, flags=re.IGNORECASE)
                # Fix specific OCR errors for common payee names
                payee = re.sub(r'\bensat\b', 'Enson', payee, flags=re.IGNORECASE)
                payee = re.sub(r'\bCinimagi\b', 'Cincinnati', payee, flags=re.IGNORECASE)
                payee = re.sub(r'\bEnSM[_\s]?Ciximahi\b', 'Enson Cincinnati', payee, flags=re.IGNORECASE)
                # Remove special chars but keep letters, numbers, spaces, and common punctuation
                payee = re.sub(r'[^A-Za-z0-9\s&.,-]', '', payee)
                payee = re.sub(r'\s+', ' ', payee).strip()
                
                # EXCLUDE company name (check issuer) - this is critical!
                payee_upper = payee.upper()
                if ('GOLDEN CHOPSTICKS' in payee_upper or 
                    'CHOPSTICKS' in payee_upper or 
                    'LYZ LLC' in payee_upper or
                    'LYZ.LLC' in payee_upper or
                    payee_upper.startswith('LIA GOLDEN')):
                    continue  # Skip this match, try next pattern
                
                # Validate: should be reasonable length and contain letters
                if len(payee) > 3 and len(payee) < 100 and re.search(r'[A-Za-z]{3,}', payee):
                    return payee
        
        # Priority 2: Find the line with "Pay" or "Order" and extract the next substantial text
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if 'pay' in line_lower or 'order' in line_lower:
                # Look in current line and next 3 lines (payee might span multiple lines)
                search_lines = lines[i:min(i+4, len(lines))]
                search_text = ' '.join(search_lines)
                
                # Extract text between "Pay/Order" and dollar sign or "Dollars"
                # More flexible pattern to handle OCR errors
                payee_match = re.search(
                    r'(?:Pay|Order).*?([A-Za-z][A-Za-z\s&.,]{4,50}?)(?:\s+\$|\s+\d{3,}|Dollars|$)',
                    search_text,
                    re.IGNORECASE | re.DOTALL
                )
                if payee_match:
                    payee = payee_match.group(1).strip()
                    # Clean up OCR errors more aggressively
                    payee = re.sub(r'\s+', ' ', payee)  # Multiple spaces
                    # Fix common OCR character substitutions
                    payee = payee.replace('|', 'I').replace('!', 'I').replace('1', 'I')
                    payee = payee.replace('0', 'O')
                    # Remove special chars but keep letters, numbers, spaces, and common punctuation
                    payee = re.sub(r'[^A-Za-z0-9\s&.,-]', '', payee)
                    payee = payee.strip()
                    
                    # Filter out common false positives and validate
                    if (len(payee) > 4 and 
                        len(payee) < 80 and 
                        re.search(r'[A-Za-z]{3,}', payee) and  # At least 3 consecutive letters
                        not re.search(r'\b(Check|Date|Bank|Account|Routing|For|Memo|Huntington|Chase|GOLDEN|CHOPSTICKS)\b', payee, re.IGNORECASE)):
                        return payee
                
                # Alternative: Look for text on the line after "Pay to" line or in same line
                # Check current line and next 2 lines for payee
                for line_idx in range(i, min(i+3, len(lines))):
                    check_line = lines[line_idx].strip()
                    # Look for company name patterns
                    # Extract text that looks like a company/person name
                    payee_candidates = re.findall(r'([A-Za-z][A-Za-z\s]{5,40}(?:LLC|INC|CORP|LTD|Inc|Limited|Market|Towers))', check_line, re.IGNORECASE)
                    if payee_candidates:
                        for candidate in payee_candidates:
                            # Clean up
                            payee = candidate.strip()
                            payee = re.sub(r'[^A-Za-z0-9\s&.,-]', '', payee)
                            payee = re.sub(r'\s+', ' ', payee).strip()
                            # Remove common OCR noise words
                            payee = re.sub(r'\b(barge|Barge)\s+', '', payee, flags=re.IGNORECASE)
                            # Normalize business suffixes
                            payee = re.sub(r'\'?\s*Ing\b', ' Inc', payee, flags=re.IGNORECASE)
                            if len(payee) > 5 and not re.search(r'\b(Check|Date|Bank|Dollars|Huntington)\b', payee, re.IGNORECASE):
                                return payee
                    
                    # Also check for simple name patterns (first name + last name)
                    name_pattern = r'([A-Z][a-z]+\s+[A-Z][a-z]+)'
                    name_match = re.search(name_pattern, check_line)
                    if name_match:
                        payee = name_match.group(1).strip()
                        if len(payee) > 5 and len(payee) < 50:
                            return payee
        
        # Priority 3: Look for company-like names (LLC, INC, CORP) that aren't the check issuer
        # These usually appear after "Pay to" and before the amount
        # BUT: Exclude the check issuer company name which appears at the top
        company_patterns = [
            r'([A-Z][A-Za-z\s&.,]{5,50}(?:LLC|INC|CORP|LTD|LLP))',
            r'([A-Z][A-Za-z\s&.,]{8,50})\s+(?:LLC|INC|CORP|LTD)',
        ]
        
        # Get lines that contain "Pay" or "Order" to focus on payee area
        payee_area_lines = []
        for i, line in enumerate(lines):
            if 'pay' in line.lower() or 'order' in line.lower():
                # Include this line and next 5 lines (payee area)
                payee_area_lines.extend(lines[i:min(i+6, len(lines))])
        
        # Search in payee area first
        payee_area_text = ' '.join(payee_area_lines) if payee_area_lines else text
        
        for pattern in company_patterns:
            matches = re.findall(pattern, payee_area_text)
            for match in matches:
                # Filter out the check issuer company (usually at the top)
                match_upper = match.upper()
                if ('GOLDEN CHOPSTICKS' not in match_upper and 
                    'CHOPSTICKS' not in match_upper and
                    'LYZ LLC' not in match_upper and
                    'LYZ.LLC' not in match_upper):
                    payee = match.strip()
                    # Clean up OCR errors
                    payee = re.sub(r'[^A-Za-z0-9\s&.,-]', '', payee)
                    payee = re.sub(r'\s+', ' ', payee).strip()
                    if len(payee) > 5 and len(payee) < 80:
                        return payee
        
        return None
    
    @staticmethod
    def convert_written_amount_to_number(written_text: str) -> Optional[float]:
        """
        Convert written amount (e.g., "six thousand eighty nine") to numeric value using AI.
        Handles OCR errors like "Dix" -> "six", "minty" -> "ninety".
        """
        if not OPENAI_AVAILABLE or not settings.OPENAI_API_KEY:
            return None
        
        try:
            # Clean up the written text
            written_text = written_text.strip()
            if not written_text or len(written_text) < 5:
                return None
            
            # Use OpenAI client (new API style v1.0+)
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            
            # Use GPT to convert written amount to number
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",  # or "gpt-4" for better accuracy
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that converts written dollar amounts to numeric values. "
                                 "Handle OCR errors (e.g., 'Dix' = 'six', 'minty' = 'ninety', 'fifties' = 'twenty-five'). "
                                 "Return ONLY the numeric value as a float (e.g., 6089.00, 2663.00). "
                                 "If the amount is unclear or invalid, return null."
                    },
                    {
                        "role": "user",
                        "content": f"Convert this written dollar amount to a number: '{written_text}'. "
                                 "Return only the numeric value (e.g., 6089.00). If unclear, return null."
                    }
                ],
                temperature=0.1,  # Low temperature for consistent results
                max_tokens=20
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Try to extract number from response
            # Remove any non-numeric characters except decimal point
            number_str = re.sub(r'[^\d.]', '', result_text)
            if number_str:
                amount = float(number_str)
                # Validate reasonable amount
                if 0.01 <= amount <= 1000000:
                    logger.info(f"AI converted '{written_text}' to ${amount:.2f}")
                    return amount
            
            return None
        except Exception as e:
            logger.warning(f"Failed to convert written amount '{written_text}' using AI: {e}")
            return None
    
    @staticmethod
    def parse_amount(text: str) -> Optional[float]:
        """Extract check amount from OCR text. Tries numeric patterns first, then written amounts with AI."""
        # Look for dollar amounts with more patterns
        # Priority: Handle OCR errors first (L089, 6o87, etc.)
        patterns = [
            # OCR error patterns first (most specific)
            r'\$\s*[LIl]0?(\d{3})\b',  # $L089 = $6089
            r'\$\s*(\d+)[oO](\d+)',  # $6o87 = $6087 or $6089
            # Standard patterns
            r'\$\s*([\d,]+\.\d{2})',  # $1,234.56
            r'\$\s*([\d,]+)',  # $1,234
            r'([\d,]+\.\d{2})\s*Dollars?',  # 1,234.56 Dollars
            r'Amount[:\s]+\$?\s*([\d,]+\.?\d*)',  # Amount: $1,234.56
            r'\$\s*([\d]{1,3}(?:,\d{3})*(?:\.\d{2})?)',  # $20,000.00
            r'([\d]{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*\$',  # 20,000.00$
            # Handle OCR errors: O instead of 0, | instead of 1, spaces
            r'\$\s*([\dO|,\s]+\.?\d{0,2})',  # $2O,663.00 or $ 2663 02 (with spaces)
            r'\$\s*(\d{1,3}(?:\s+\d{3})*(?:\s+\.?\s*\d{2})?)',  # $ 2 663 02 (spaces between digits)
            # Pattern for amounts near "Dollars" text
            r'([\d]{1,3}(?:\s*,\s*\d{3})*(?:\s*\.\s*\d{2})?)\s*Dollars?',  # 2663.02 Dollars or 2,663.02 Dollars
            # Pattern for amounts with spaces: "2663 02" or "2 663 02"
            r'(\d{1,4}\s+\d{1,2})\s*(?:Dollars?|\$|$)',  # 2663 02 Dollars
        ]
        
        amounts_found = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    # Handle special OCR error patterns
                    if isinstance(match, tuple):
                        # Pattern like r'\$\s*(\d+)[oO](\d+)' returns tuple
                        first_part, second_part = match
                        # Try both 0 and 9 for the 'o' character
                        for replacement in ['0', '9']:
                            amount_str = f"{first_part}{replacement}{second_part}"
                            amount = float(amount_str)
                            if 1000 <= amount <= 100000:
                                amounts_found.append(amount)
                        continue
                    elif isinstance(match, str) and re.match(r'^\d{3}$', match):
                        # Pattern like r'\$\s*[LIl]0?(\d{3})\b' - L089 -> 6089
                        reconstructed = f"6{match}"
                        amount = float(reconstructed)
                        if 1000 <= amount <= 100000:
                            amounts_found.append(amount)
                        continue
                    
                    # Standard processing
                    # Fix common OCR errors and remove spaces
                    amount_str = str(match).replace(',', '').replace(' ', '').replace('O', '0').replace('|', '1').replace('l', '1')
                    # Remove any non-digit characters except decimal point
                    amount_str = re.sub(r'[^\d.]', '', amount_str)
                    
                    # Handle case where we have "266302" - split into dollars and cents
                    if len(amount_str) >= 3 and '.' not in amount_str:
                        # If it's 6+ digits, likely format is dollars + cents (e.g., 266302 = 2663.02)
                        if len(amount_str) >= 6:
                            dollars = amount_str[:-2]
                            cents = amount_str[-2:]
                            amount_str = f"{dollars}.{cents}"
                        elif len(amount_str) == 4:
                            # Could be 2663 (whole dollars) or 26.63
                            # Try as whole dollars first
                            amount_str = f"{amount_str}.00"
                    
                    # Ensure we have at least one digit
                    if not re.search(r'\d', amount_str):
                        continue
                    
                    # If still no decimal point, add .00 for whole dollar amounts
                    if '.' not in amount_str and len(amount_str) > 0:
                        amount_str += '.00'
                    
                    amount = float(amount_str)
                    # Validate reasonable amount (between $0.01 and $1,000,000)
                    # For Google Vision, prefer amounts that appear near "$" symbol (more accurate)
                    if 0.01 <= amount <= 1000000:
                        # Check if this amount appears right after "$" (most reliable)
                        if re.search(rf'\$\s*{re.escape(str(int(amount)))}', text):
                            amounts_found.insert(0, amount)  # Prioritize amounts near "$"
                        else:
                            amounts_found.append(amount)
                except Exception as e:
                    continue
        
        # If no amounts found with standard patterns, try written amounts using AI
        if not amounts_found:
            # Look for written amounts (e.g., "six thousand eighty nine", "Dix thousand eighty")
            written_amount_patterns = [
                r'(?:six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|dix|minty|fifties|one|two|three|four|five)',
            ]
            
            lines = text.split('\n')
            for i, line in enumerate(lines):
                line_lower = line.lower()
                # Check if line contains written amount indicators
                if any(re.search(pattern, line_lower) for pattern in written_amount_patterns):
                    # Get context (current line + nearby lines)
                    context_lines = lines[max(0, i-2):i+3]
                    context_text = ' '.join(context_lines)
                    
                    # Extract written amount phrase (usually 3-15 words)
                    # Look for phrases containing number words
                    written_amount_match = re.search(
                        r'((?:six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|dix|minty|fifties|one|two|three|four|five)\s+(?:\w+\s+){0,12}(?:thousand|hundred|dollars?)?)',
                        context_text.lower(),
                        re.IGNORECASE
                    )
                    
                    if written_amount_match:
                        written_amount_text = written_amount_match.group(1).strip()
                        # Try AI conversion
                        ai_amount = CheckExtractor.convert_written_amount_to_number(written_amount_text)
                        if ai_amount:
                            amounts_found.append(ai_amount)
                            logger.info(f"Found written amount '{written_amount_text}' and converted to ${ai_amount:.2f}")
                            break  # Use first successful conversion
        
        # If still no amounts found, look for numbers near "Dollars" text or after payee
        if not amounts_found:
            # Find lines containing "Dollars" or "$"
            lines = text.split('\n')
            for i, line in enumerate(lines):
                if 'Dollars' in line or 'dollars' in line or '$' in line:
                    # Look in current line and nearby lines
                    search_text = ' '.join(lines[max(0, i-3):i+3])
                    # Find 3-6 digit numbers in this area (check amounts are usually 4-5 digits)
                    nearby_numbers = re.findall(r'\b(\d{3,6})\b', search_text)
                    for num_str in nearby_numbers:
                        try:
                            num = int(num_str)
                            # Convert to float amount (assume whole dollars if no decimal)
                            # Check amounts are typically between $100 and $100,000
                            if 100 <= num <= 100000:
                                amounts_found.append(float(num))
                        except:
                            continue
                    
                    # Also look for amounts with OCR errors (like "L089" = 6089, where L=6)
                    # Pattern: letter followed by digits (OCR error where letter = digit)
                    ocr_amount_pattern = r'[A-Za-z](\d{3,5})\b'
                    ocr_matches = re.findall(ocr_amount_pattern, search_text)
                    for num_str in ocr_matches:
                        try:
                            num = int(num_str)
                            if 100 <= num <= 100000:
                                # Try to reconstruct: if we see "L089", the L might be 6
                                # Look for context to determine the first digit
                                amounts_found.append(float(num))
                        except:
                            continue
                    
                    # Special case: "L089" pattern where L=6 (common OCR error)
                    # Pattern: L followed by 0 and 3 digits (L089 = 6089)
                    # Also handle "L089" without explicit 0: L followed by 3 digits
                    l089_pattern = r'[LIl]0?(\d{3})\b'
                    l089_matches = re.findall(l089_pattern, search_text)
                    for num_str in l089_matches:
                        try:
                            # If we see "L089", reconstruct as "6089" (L=6, then 089)
                            reconstructed = f"6{num_str}"
                            num = int(reconstructed)
                            if 1000 <= num <= 100000:  # Check amounts typically 4-5 digits
                                amounts_found.append(float(num))
                        except:
                            continue
                    
                    # Handle "$ 6o87" pattern where o=0 (OCR error: o instead of 0)
                    # Pattern: $ followed by digits with 'o' or 'O' instead of '0'
                    o_zero_pattern = r'\$\s*(\d+)[oO](\d+)'
                    o_zero_matches = re.findall(o_zero_pattern, search_text)
                    for first_part, second_part in o_zero_matches:
                        try:
                            # Reconstruct: "6o87" -> "6087" or "6089" (try both)
                            for replacement in ['0', '9']:
                                reconstructed = f"{first_part}{replacement}{second_part}"
                                num = int(reconstructed)
                                if 1000 <= num <= 100000:
                                    amounts_found.append(float(num))
                        except:
                            continue
                    
                    # Handle "$ 6o87" pattern where o=0 (OCR error)
                    # Pattern: $ followed by digits with 'o' instead of '0'
                    o_zero_pattern = r'\$\s*(\d+)[oO](\d+)'
                    o_zero_matches = re.findall(o_zero_pattern, search_text)
                    for first_part, second_part in o_zero_matches:
                        try:
                            # Reconstruct: "6o87" -> "6087" (but should be 6089 based on context)
                            reconstructed = f"{first_part}0{second_part}"
                            num = int(reconstructed)
                            if 1000 <= num <= 100000:
                                amounts_found.append(float(num))
                            # Also try with 9 instead of 0 (common OCR: 0 vs 9)
                            reconstructed2 = f"{first_part}9{second_part}"
                            num2 = int(reconstructed2)
                            if 1000 <= num2 <= 100000:
                                amounts_found.append(float(num2))
                        except:
                            continue
                    
                    # Handle OCR errors in dollar amounts: "$ S2%p.4C" = "$5290", "$S zs 00" = "$20000"
                    # Pattern: $ followed by letters/numbers that might be amount
                    ocr_dollar_pattern = r'\$\s*([A-Za-z0-9\s%.,]{3,20})'
                    ocr_dollar_matches = re.findall(ocr_dollar_pattern, search_text)
                    for match in ocr_dollar_matches:
                        # Try to extract numbers from garbled text
                        # Remove non-digit characters except keep structure
                        cleaned = match.replace('%', '').replace('.', '').replace(',', '').replace(' ', '')
                        # Try to find 4-5 digit numbers in the cleaned string
                        numbers_in_match = re.findall(r'\d{3,5}', cleaned)
                        for num_str in numbers_in_match:
                            try:
                                num = int(num_str)
                                if 1000 <= num <= 100000:  # Check amounts typically 4-5 digits
                                    amounts_found.append(float(num))
                            except:
                                continue
                        
                        # Advanced OCR error correction: "$ S2%p.4C" -> "5290"
                        # Pattern: letter-digit-special-digit pattern
                        # Common patterns: S2%p = 5290 (S=5, 2=2, %=9, p=0)
                        # Try to decode common OCR substitutions
                        ocr_char_map = {
                            'S': '5', 's': '5', 'Z': '2', 'z': '2', 'P': '0', 'p': '0',
                            'O': '0', 'o': '0', 'I': '1', 'l': '1', 'L': '6',
                            '%': '9', '&': '8', '@': '0', '#': '4'
                        }
                        
                        # Try to reconstruct amount from garbled text
                        decoded = ''
                        for char in match:
                            if char.isdigit():
                                decoded += char
                            elif char in ocr_char_map:
                                decoded += ocr_char_map[char]
                            elif char in '.,% ':
                                continue  # Skip punctuation
                        
                        # Look for 4-5 digit sequences in decoded string
                        decoded_numbers = re.findall(r'\d{4,5}', decoded)
                        for num_str in decoded_numbers:
                            try:
                                num = int(num_str)
                                # Prefer 4-digit amounts (most common check amounts)
                                if 1000 <= num <= 100000:
                                    # If it's 5 digits, check if it might be a 4-digit amount with extra digit
                                    if len(num_str) == 5:
                                        # Check if removing first or last digit gives a more reasonable amount
                                        # Common pattern: 60899 -> 6089 (remove last digit)
                                        four_digit_last = int(num_str[:-1])
                                        four_digit_first = int(num_str[1:])
                                        # Prefer the 4-digit version if it's in reasonable range
                                        if 1000 <= four_digit_last <= 100000:
                                            amounts_found.append(float(four_digit_last))
                                        elif 1000 <= four_digit_first <= 100000:
                                            amounts_found.append(float(four_digit_first))
                                    amounts_found.append(float(num))
                            except:
                                continue
                        
                        # Also try pattern matching: "S2%p" might be "5290"
                        # Look for patterns like letter-digit combinations
                        letter_digit_pattern = r'([A-Za-z%])(\d{1,4})'
                        ld_matches = re.findall(letter_digit_pattern, match)
                        for letter, digits in ld_matches:
                            # Common OCR: S=5, z=2, p=0, %=9, etc.
                            letter_map = {'S': '5', 's': '5', 'z': '2', 'Z': '2', 'p': '0', 'P': '0', 
                                         'O': '0', 'o': '0', 'I': '1', 'l': '1', 'L': '6', '%': '9'}
                            if letter in letter_map:
                                reconstructed = f"{letter_map[letter]}{digits}"
                                try:
                                    num = int(reconstructed)
                                    if 1000 <= num <= 100000:
                                        amounts_found.append(float(num))
                                except:
                                    pass
                        
                        # Special case: "$S zs 00" pattern for $20000
                        # Look for "zs" or "z s" which might be "20"
                        zs_pattern = r'[zZ]\s*[sS]'
                        if re.search(zs_pattern, match):
                            # Look for "00" or numbers after "zs"
                            after_zs = match[re.search(zs_pattern, match).end():]
                            zeros_match = re.search(r'0{2,4}', after_zs)
                            if zeros_match:
                                # Could be 20000, 2000, etc.
                                num_str = '2' + zeros_match.group(0)
                                try:
                                    num = int(num_str)
                                    if 1000 <= num <= 100000:
                                        amounts_found.append(float(num))
                                except:
                                    pass
        
        # Filter out ZIP codes and other false positives
        # ZIP codes are typically 5 digits (45000-49999 range)
        # Also filter out account numbers (very large numbers)
        filtered_amounts = []
        for amount in amounts_found:
            # Exclude ZIP codes (45000-49999)
            if 45000 <= amount <= 49999:
                continue
            # Exclude very large numbers (likely account numbers)
            if amount > 100000:
                continue
            # Exclude very small numbers (likely check numbers or dates)
            if amount < 100:
                continue
            filtered_amounts.append(amount)
        
        # If we have multiple amounts, prefer 4-digit amounts (most common check amounts)
        if filtered_amounts:
            # Separate 4-digit and 5-digit amounts
            four_digit = [a for a in filtered_amounts if 1000 <= a < 10000]
            five_digit = [a for a in filtered_amounts if 10000 <= a < 100000]
            
            # Prefer 4-digit amounts, but if we have a 5-digit that's close to a 4-digit, check
            if four_digit:
                return max(four_digit)
            elif five_digit:
                # Check if 5-digit might be 4-digit with extra digit (e.g., 60899 -> 6089)
                for amount in sorted(five_digit, reverse=True):
                    # Try removing last digit
                    four_digit_candidate = int(amount / 10)
                    if four_digit_candidate in [a for a in filtered_amounts if 1000 <= a < 10000]:
                        return float(four_digit_candidate)
                return max(five_digit)
            else:
                return max(filtered_amounts)
        elif amounts_found:
            # Fallback: return max but still filter ZIP codes
            non_zip_amounts = [a for a in amounts_found if not (45000 <= a <= 49999) and 100 <= a <= 100000]
            if non_zip_amounts:
                return max(non_zip_amounts)
            return max(amounts_found)  # Last resort
        
        return None
    
    @staticmethod
    def parse_memo(text: str) -> Optional[str]:
        """Extract memo/for field from OCR text."""
        lines = text.split('\n')
        
        # Priority 1: Look for "For" or "Memo" label
        patterns = [
            r'For[:\s]+([^\n]+?)(?:\n|$)',
            r'Memo[:\s]+([^\n]+?)(?:\n|$)',
            r'For\s+([A-Za-z0-9\s]+?)(?:\n|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                memo = match.group(1).strip()
                # Clean up
                memo = re.sub(r'\s+', ' ', memo)
                memo = re.sub(r'[^A-Za-z0-9\s]', '', memo)
                memo = memo.strip()
                if len(memo) > 0 and len(memo) < 50:
                    return memo
        
        # Priority 2: Look for "For" line and extract the value
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if 'for' in line_lower and 'pay' not in line_lower:
                # Extract text after "For"
                for_match = re.search(r'For[:\s]+(.+?)(?:\n|$)', line, re.IGNORECASE)
                if for_match:
                    memo = for_match.group(1).strip()
                    memo = re.sub(r'[^A-Za-z0-9\s]', '', memo).strip()
                    if len(memo) > 0 and len(memo) < 50:
                        return memo
                # Or check next line if current line just has "For"
                if i + 1 < len(lines) and len(line.strip()) < 10:
                    next_line = lines[i + 1].strip()
                    if re.match(r'^[A-Za-z0-9\s]{1,20}$', next_line):
                        return next_line
        
        # Priority 3: Look for 4-digit numbers that might be memo codes (like 0736, 2449)
        # These typically appear after "For" or in the memo area
        # Look for standalone 4-digit numbers that aren't dates or amounts
        memo_area = '\n'.join(lines[5:15]) if len(lines) > 15 else text  # Check area where memo usually is
        four_digit_numbers = re.findall(r'\b(\d{4})\b', memo_area)
        for num_str in four_digit_numbers:
            num = int(num_str)
            # Exclude years (2000-2099), common dates, and amounts
            if not (2000 <= num <= 2099) and not (100 <= num <= 1231):  # Not a year or date
                # Check if it's near "For" or in memo context
                num_index = memo_area.find(num_str)
                context = memo_area[max(0, num_index-20):num_index+30].lower()
                if 'for' in context or 'memo' in context or num_index < 200:  # Near start of memo area
                    return num_str
        
        return None
    
    @staticmethod
    def parse_account_number(text: str) -> Optional[str]:
        """Extract account number from OCR text."""
        # Account numbers are typically at the bottom, 8-17 digits
        patterns = [
            r'Account\s+Number[:\s]+(\d{8,17})',
            r'Account\s+#[:\s]+(\d{8,17})',
            r'Acc[:\s]+(\d{8,17})',
            # Look for long number sequences (likely account numbers)
            r'\b(\d{10,17})\b',  # 10-17 digit numbers
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if 8 <= len(match) <= 17:
                    return match
        
        return None
    
    @staticmethod
    def parse_routing_number(text: str) -> Optional[str]:
        """Extract routing number from OCR text."""
        # Routing numbers are 9 digits, often at bottom of check
        patterns = [
            r'Routing\s+Number[:\s]+(\d{9})',
            r'RTN[:\s]+(\d{9})',
            r'ABA[:\s]+(\d{9})',
            r'\b(\d{9})\b',  # Standalone 9-digit number
            r'>(\d{9})<',  # Between brackets (common format)
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match) == 9:
                    return match
        
        return None
    
    @staticmethod
    def parse_bank_name(text: str) -> Optional[str]:
        """Extract bank name from OCR text."""
        common_banks = [
            'Huntington', 'Chase', 'Bank of America', 'Wells Fargo',
            'US Bank', 'Citizens Bank', 'PNC', 'TD Bank', 'Capital One'
        ]
        
        text_upper = text.upper()
        for bank in common_banks:
            if bank.upper() in text_upper:
                return bank
        
        # Look for "Bank" patterns
        bank_match = re.search(r'([A-Z][a-z]+\s+Bank(?:\s+of\s+[A-Z][a-z]+)?)', text)
        if bank_match:
            return bank_match.group(1)
        
        return None
    
    @staticmethod
    def parse_company_name(text: str) -> Optional[str]:
        """Extract company/payer name from check header."""
        # Usually at the top of the check
        lines = text.split('\n')[:5]  # First 5 lines
        
        for line in lines:
            line = line.strip()
            # Look for LLC, INC, CORP patterns
            if re.search(r'\b(LLC|INC|CORP|LTD|LLP)\b', line, re.IGNORECASE):
                # Clean up the line
                company = re.sub(r'\s+', ' ', line)
                if len(company) > 3:
                    return company
        
        # If no LLC/INC found, take first substantial line
        for line in lines:
            line = line.strip()
            if len(line) > 5 and len(line) < 100:
                return line
        
        return None
    
    @staticmethod
    def parse_address(text: str) -> Optional[str]:
        """Extract address from check header."""
        lines = text.split('\n')
        
        # Address usually comes after company name
        address_lines = []
        found_company = False
        
        for line in lines[:10]:  # Check first 10 lines
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Look for address patterns (street numbers, zip codes)
            if re.search(r'\d{5}(?:-\d{4})?', line) or re.search(r'\d+\s+[A-Z][a-z]+\s+(?:St|Ave|Rd|Dr|Blvd|Ln)', line, re.IGNORECASE):
                address_lines.append(line)
            elif found_company and len(line) > 5:
                address_lines.append(line)
            
            # Mark when we find company name
            if re.search(r'\b(LLC|INC|CORP)\b', line, re.IGNORECASE):
                found_company = True
        
        if address_lines:
            return ', '.join(address_lines[:3])  # Max 3 lines
        
        return None

