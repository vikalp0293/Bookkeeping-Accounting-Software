"""
AI-powered document classifier using GPT-4 Vision.
Determines if a document is a check, bank statement, or other type.
"""
import base64
import logging
from pathlib import Path
from typing import Dict, Optional, Any
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
                logger.info("OpenAI client initialized for document classification")
            else:
                return None
        return _openai_client
except ImportError:
    OPENAI_AVAILABLE = False
    def get_openai_client():
        return None


class DocumentClassifier:
    """AI-powered document classification service."""
    
    @staticmethod
    def classify_document(file_path: str, file_type: str = "pdf") -> Dict[str, Any]:
        """
        Use GPT-4 Vision to classify a document as check, bank statement, or other.
        
        Args:
            file_path: Path to the document file
            file_type: Type of file (pdf, image, etc.)
            
        Returns:
            Dictionary with classification results:
            {
                "document_type": "check" | "bank_statement" | "other",
                "confidence": 0.0-1.0,
                "reasoning": "explanation",
                "bank_name": "name if detected",
                "suggested_extractor": "check_extractor" | "pdf_extractor" | "ocr"
            }
        """
        if not OPENAI_AVAILABLE:
            logger.debug("OpenAI not available, using fallback classification")
            return DocumentClassifier._fallback_classify(file_path, file_type)
        
        client = get_openai_client()
        if client is None:
            logger.debug("OpenAI client not initialized, using fallback classification")
            return DocumentClassifier._fallback_classify(file_path, file_type)
        
        try:
            # For PDFs, convert first page to image
            if file_type.lower() == "pdf":
                try:
                    import pdf2image
                    from PIL import Image
                    import io
                    
                    # Convert first page to image
                    images = pdf2image.convert_from_path(file_path, first_page=1, last_page=1, dpi=200)
                    if not images:
                        return DocumentClassifier._fallback_classify(file_path, file_type)
                    
                    # Convert PIL image to base64
                    img_buffer = io.BytesIO()
                    images[0].save(img_buffer, format='PNG')
                    img_buffer.seek(0)
                    image_data = img_buffer.read()
                    base64_image = base64.b64encode(image_data).decode('utf-8')
                    mime_type = 'image/png'
                except Exception as e:
                    logger.warning(f"Failed to convert PDF to image for classification: {e}")
                    return DocumentClassifier._fallback_classify(file_path, file_type)
            else:
                # For images, read directly
                with open(file_path, 'rb') as image_file:
                    image_data = image_file.read()
                    base64_image = base64.b64encode(image_data).decode('utf-8')
                
                image_ext = Path(file_path).suffix.lower()
                mime_type = {
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp'
                }.get(image_ext, 'image/jpeg')
            
            # Use GPT-4 Vision to classify the document
            system_prompt = """You are an expert at classifying financial documents. 
Analyze the document image and determine:
1. Document type: "check", "bank_statement", or "other"
2. Confidence level (0.0-1.0)
3. Bank name if visible
4. Reasoning for your classification

For checks, look for:
- "Pay to the order of" text
- Check number
- Written amount
- Signature line
- Routing/account numbers at bottom

For bank statements, look for:
- Account information header
- Statement period dates
- Beginning/ending balances
- Transaction table/list
- Multiple transactions
- Bank name and logo

Return a JSON object with:
{
  "document_type": "check" | "bank_statement" | "other",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation",
  "bank_name": "bank name if visible, or null",
  "suggested_extractor": "check_extractor" | "pdf_extractor" | "ocr"
}"""
            
            user_prompt = """Analyze this financial document image and classify it. 
Determine if it's a check, bank statement, or other type of document.
Return only valid JSON, no additional text."""
            
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
                                    "url": f"data:{mime_type};base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=500
            )
            
            result_text = response.choices[0].message.content
            import json
            classification = json.loads(result_text)
            
            logger.info(f"AI classification: {classification.get('document_type')} "
                       f"(confidence: {classification.get('confidence', 0):.2f})")
            
            return classification
        
        except Exception as e:
            logger.error(f"AI document classification failed: {e}")
            return DocumentClassifier._fallback_classify(file_path, file_type)
    
    @staticmethod
    def _fallback_classify(file_path: str, file_type: str) -> Dict[str, Any]:
        """
        Fallback classification using filename and basic heuristics.
        """
        filename = Path(file_path).name.lower()
        
        # Check filename for hints
        is_check = "check" in filename
        is_statement = any(keyword in filename for keyword in ["statement", "stmt", "bank"])
        
        if is_check:
            return {
                "document_type": "check",
                "confidence": 0.7,
                "reasoning": "Filename suggests check",
                "bank_name": None,
                "suggested_extractor": "check_extractor"
            }
        elif is_statement:
            return {
                "document_type": "bank_statement",
                "confidence": 0.7,
                "reasoning": "Filename suggests bank statement",
                "bank_name": None,
                "suggested_extractor": "pdf_extractor"
            }
        else:
            return {
                "document_type": "other",
                "confidence": 0.5,
                "reasoning": "Unable to determine from filename",
                "bank_name": None,
                "suggested_extractor": "ocr"
            }
    
    @staticmethod
    def classify_from_text(text: str) -> Dict[str, Any]:
        """
        Classify document from extracted text (faster, no image processing needed).
        
        Args:
            text: Extracted text from document
            
        Returns:
            Classification dictionary
        """
        if not OPENAI_AVAILABLE:
            return DocumentClassifier._classify_from_text_heuristics(text)
        
        client = get_openai_client()
        if client is None:
            return DocumentClassifier._classify_from_text_heuristics(text)
        
        try:
            # Use first 2000 characters for classification
            text_sample = text[:2000] if len(text) > 2000 else text
            
            system_prompt = """You are an expert at classifying financial documents from text.
Analyze the text and determine if it's from a check, bank statement, or other document.

For checks, look for:
- "Pay to the order of" or "Pay to order of"
- Check number
- Written amount (e.g., "One Hundred Dollars")
- Routing/account numbers

For bank statements, look for:
- "Statement Period" or date ranges
- "Beginning Balance" and "Ending Balance"
- Transaction lists/tables
- Account number
- Multiple transaction entries

Return JSON:
{
  "document_type": "check" | "bank_statement" | "other",
  "confidence": 0.0-1.0,
  "reasoning": "explanation",
  "bank_name": "bank name if found"
}"""
            
            user_prompt = f"""Classify this financial document text:
{text_sample}

Return only valid JSON."""
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=300
            )
            
            result_text = response.choices[0].message.content
            import json
            classification = json.loads(result_text)
            
            logger.info(f"AI text classification: {classification.get('document_type')} "
                       f"(confidence: {classification.get('confidence', 0):.2f})")
            
            return classification
        
        except Exception as e:
            logger.warning(f"AI text classification failed: {e}")
            return DocumentClassifier._classify_from_text_heuristics(text)
    
    @staticmethod
    def _classify_from_text_heuristics(text: str) -> Dict[str, Any]:
        """Heuristic-based classification from text."""
        text_upper = text.upper()
        
        # Check indicators
        check_indicators = [
            "PAY TO THE ORDER OF",
            "PAY TO ORDER OF",
            "PAY TO",
            "DOLLARS",
            "ROUTING NUMBER",
            "RTN"
        ]
        check_score = sum(1 for indicator in check_indicators if indicator in text_upper)
        
        # Bank statement indicators
        statement_indicators = [
            "STATEMENT PERIOD",
            "BEGINNING BALANCE",
            "ENDING BALANCE",
            "ACCOUNT NUMBER",
            "TRANSACTION",
            "DEPOSIT",
            "WITHDRAWAL",
            "DEBIT",
            "CREDIT"
        ]
        statement_score = sum(1 for indicator in statement_indicators if indicator in text_upper)
        
        if check_score >= 2:
            return {
                "document_type": "check",
                "confidence": min(0.8, 0.5 + (check_score * 0.1)),
                "reasoning": f"Found {check_score} check indicators",
                "bank_name": None
            }
        elif statement_score >= 3:
            return {
                "document_type": "bank_statement",
                "confidence": min(0.8, 0.5 + (statement_score * 0.1)),
                "reasoning": f"Found {statement_score} bank statement indicators",
                "bank_name": None
            }
        else:
            return {
                "document_type": "other",
                "confidence": 0.5,
                "reasoning": "Insufficient indicators",
                "bank_name": None
            }

