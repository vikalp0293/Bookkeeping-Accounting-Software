"""
AI-Powered Check Extractor using GPT-4 Vision.
Extracts check data directly from images in a format-agnostic way.
"""
import json
import base64
import io
import logging
from typing import Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

# Try to import OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
    _openai_client = None
    
    def get_openai_client():
        global _openai_client
        if _openai_client is None:
            if settings.OPENAI_API_KEY:
                _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
                logger.info("OpenAI client initialized for check extraction")
            else:
                logger.warning("OpenAI API key not configured for check extraction")
                return None
        return _openai_client
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI not available. Install with: pip install openai")
    def get_openai_client():
        return None


class CheckAIExtractor:
    """AI-powered check extraction using GPT-4 Vision."""
    
    @staticmethod
    def extract_check_with_ai(file_path: str) -> Dict[str, Any]:
        """
        Use GPT-4 Vision to extract check data directly from image/PDF.
        AI understands the check format and extracts all fields.
        
        Args:
            file_path: Path to check image or PDF
            
        Returns:
            Dictionary with extracted check data:
            {
                "check_number": str,
                "date": "YYYY-MM-DD",
                "payee": str,
                "amount": float,
                "memo": str or None,
                "account_number": str or None,
                "routing_number": str or None,
                "bank_name": str or None,
                "company_name": str or None,
                "address": str or None,
                "document_type": "check"
            }
        """
        if not OPENAI_AVAILABLE:
            logger.warning("OpenAI not available for AI check extraction")
            return {"error": "OpenAI not available"}
        
        client = get_openai_client()
        if client is None:
            return {"error": "OpenAI client not initialized"}
        
        try:
            import pdf2image
            from PIL import Image
            
            # Convert PDF to image if needed
            image = None
            if file_path.lower().endswith('.pdf'):
                images = pdf2image.convert_from_path(file_path, first_page=1, last_page=1, dpi=200)
                if images:
                    image = images[0]
                else:
                    return {"error": "Failed to convert PDF to image"}
            else:
                # Load image directly
                image = Image.open(file_path)
            
            if not image:
                return {"error": "Failed to load image"}
            
            logger.info("Extracting check data using GPT-4 Vision...")
            result = CheckAIExtractor._extract_check_from_image(client, image)
            
            if result and not result.get("error"):
                result["document_type"] = "check"
                logger.info(f"AI extraction successful: Check #{result.get('check_number', 'N/A')}, "
                          f"Payee: {result.get('payee', 'N/A')}, "
                          f"Amount: ${result.get('amount', 0):,.2f}")
            
            return result
        
        except Exception as e:
            logger.error(f"AI check extraction failed: {e}", exc_info=True)
            return {"error": str(e)}
    
    @staticmethod
    def _extract_check_from_image(client, image) -> Dict[str, Any]:
        """
        Extract check data from a PIL Image using GPT-4 Vision.
        
        Args:
            client: OpenAI client
            image: PIL Image object
            
        Returns:
            Dictionary with extracted check data
        """
        try:
            # Convert PIL image to base64
            img_buffer = io.BytesIO()
            image.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            image_data = img_buffer.read()
            base64_image = base64.b64encode(image_data).decode('utf-8')
            
            system_prompt = """You are an expert at extracting data from checks.
Analyze this check image and extract all available information.

Extract the following fields:
1. check_number: The check number (usually 3-6 digits, found in top-right corner or bottom)
2. date: The date written on the check (normalize to YYYY-MM-DD format)
3. payee: The name of the person/company the check is made out to (after "Pay to the Order of")
4. amount: The check amount in numeric format (e.g., 1234.56)
5. memo: Any memo or "For" field text
6. account_number: Bank account number (usually 8-17 digits at bottom)
7. routing_number: Bank routing number (9 digits, usually at bottom)
8. bank_name: Name of the bank
9. company_name: Name of the company/person issuing the check (usually at top)
10. address: Address of the check issuer (usually below company name)

IMPORTANT RULES:
- The payee is the person/company RECEIVING the check (after "Pay to the Order of")
- The company_name is the person/company ISSUING the check (at the top)
- Do NOT confuse payee with company_name
- Dates should be normalized to YYYY-MM-DD format
- Amounts should be positive numbers (e.g., 1234.56, not -1234.56)
- Handle OCR errors and handwriting variations
- If a field is not visible or unclear, use null

Return JSON:
{
  "check_number": "string or null",
  "date": "YYYY-MM-DD or null",
  "payee": "string or null",
  "amount": number or null,
  "memo": "string or null",
  "account_number": "string or null",
  "routing_number": "string or null",
  "bank_name": "string or null",
  "company_name": "string or null",
  "address": "string or null"
}"""
            
            user_prompt = "Extract all check data from this image. Return only valid JSON, no additional text."
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.1,  # Low temperature for consistent extraction
                max_tokens=2000
            )
            
            result_text = response.choices[0].message.content
            
            # Parse JSON response
            try:
                result = json.loads(result_text)
                
                # Validate and normalize fields
                # Ensure amount is positive
                if result.get("amount") is not None:
                    result["amount"] = abs(float(result["amount"]))
                
                # Ensure date is in correct format
                if result.get("date"):
                    date_str = result["date"]
                    # If not already in YYYY-MM-DD format, try to normalize
                    if not date_str.startswith("20") or len(date_str) != 10:
                        # Try to parse and reformat
                        try:
                            from datetime import datetime
                            # Try common formats
                            for fmt in ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%m-%d-%y"]:
                                try:
                                    dt = datetime.strptime(date_str, fmt)
                                    result["date"] = dt.strftime("%Y-%m-%d")
                                    break
                                except ValueError:
                                    continue
                        except Exception:
                            logger.warning(f"Could not normalize date: {date_str}")
                
                # Clean up string fields
                for field in ["check_number", "payee", "memo", "account_number", "routing_number", 
                             "bank_name", "company_name", "address"]:
                    if result.get(field):
                        result[field] = str(result[field]).strip()
                        if result[field] == "" or result[field].lower() == "null":
                            result[field] = None
                
                return result
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse AI response JSON: {e}")
                logger.debug(f"Response text: {result_text[:500]}")
                return {"error": f"JSON parsing failed: {e}"}
        
        except Exception as e:
            logger.error(f"Error extracting check from image with AI: {e}")
            return {"error": str(e)}

    @staticmethod
    def extract_payee_only_aggressive(file_path: str, check_number_hint: Optional[str] = None) -> Optional[str]:
        """
        Use GPT-4 Vision to extract ONLY the payee name from a check image.
        Optimized for difficult cases: handwriting, poor quality, partial crops.
        Use when standard extraction returned check_number but no payee.

        Args:
            file_path: Path to check image (PNG/JPEG) or single-page PDF
            check_number_hint: Optional check number (e.g. "5495") so the model can confirm it's the right check

        Returns:
            Payee name string, or None if unreadable / not found
        """
        if not OPENAI_AVAILABLE:
            return None
        client = get_openai_client()
        if client is None:
            return None
        try:
            import pdf2image
            from PIL import Image
            if file_path.lower().endswith(".pdf"):
                images = pdf2image.convert_from_path(file_path, first_page=1, last_page=1, dpi=200)
                image = images[0] if images else None
            else:
                image = Image.open(file_path)
            if not image:
                return None
            img_buffer = io.BytesIO()
            image.save(img_buffer, format="PNG")
            img_buffer.seek(0)
            base64_image = base64.b64encode(img_buffer.read()).decode("utf-8")
            hint = f" (Check number may be {check_number_hint})" if check_number_hint else ""
            system_prompt = """You are an expert at reading check images, including handwritten text.
Your ONLY task is to extract the PAYEE name — the name that appears after "Pay to the Order of" (or "Pay to the order of").
- The payee is the person or company RECEIVING the check.
- Payee may be printed or HANDWRITTEN; do your best to read it.
- If the image is blurry, cropped, or the payee line is missing, return exactly: UNREADABLE
- Return only the payee name, nothing else. No quotes, no "Pay to the order of", no explanation.
- If you see multiple lines after "Pay to the Order of", the payee is usually the first line (main name).
- Normalize spacing: single spaces, trim leading/trailing."""
            user_prompt = f"Extract only the payee name from this check image.{hint} Return the name only, or the word UNREADABLE if you cannot read it."
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                        ],
                    },
                ],
                temperature=0.2,
                max_tokens=200,
            )
            text = (response.choices[0].message.content or "").strip()
            if not text or text.upper() == "UNREADABLE":
                return None
            return text if len(text) > 1 and len(text) < 150 else None
        except Exception as e:
            logger.debug("Payee-only aggressive extraction failed: %s", e)
            return None