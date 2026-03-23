"""
AI-powered text correction service.
Uses GPT-4 to fix OCR errors and improve extraction accuracy.
"""
import re
import logging
from typing import Dict, Optional, Any, List
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
                logger.info("OpenAI client initialized for text correction")
            else:
                logger.warning("OpenAI API key not configured for text correction")
                return None
        return _openai_client
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI not available. Install with: pip install openai")
    def get_openai_client():
        return None


class AICorrectionService:
    """Service for AI-powered OCR text correction and field validation."""
    
    @staticmethod
    def correct_ocr_text(ocr_text: str, context: str = "check") -> str:
        """
        Use GPT-4 to correct common OCR errors in extracted text.
        
        Args:
            ocr_text: Raw OCR text with potential errors
            context: Context hint (e.g., "check", "bank statement")
            
        Returns:
            Corrected text
        """
        if not OPENAI_AVAILABLE or not settings.OPENAI_API_KEY:
            logger.debug("OpenAI not available, skipping OCR correction")
            return ocr_text
        
        if not ocr_text or len(ocr_text.strip()) < 10:
            return ocr_text
        
        client = get_openai_client()
        if client is None:
            return ocr_text
        
        try:
            # Use GPT-4 to correct OCR errors
            response = client.chat.completions.create(
                model="gpt-4o",  # or "gpt-4-turbo-preview"
                messages=[
                    {
                        "role": "system",
                        "content": f"You are an expert at correcting OCR errors in {context} documents. "
                                 "Fix common OCR mistakes like character substitutions (e.g., '0' vs 'O', '1' vs 'I', 'l'), "
                                 "spacing issues, and garbled text. Preserve the original structure and layout. "
                                 "Return ONLY the corrected text, no explanations."
                    },
                    {
                        "role": "user",
                        "content": f"Correct OCR errors in this {context} text:\n\n{ocr_text[:2000]}"  # Limit to avoid token limits
                    }
                ],
                temperature=0.1,  # Low temperature for consistent corrections
                max_tokens=2500
            )
            
            corrected_text = response.choices[0].message.content.strip()
            
            # Remove any markdown formatting if present
            corrected_text = re.sub(r'^```\w*\n', '', corrected_text)
            corrected_text = re.sub(r'\n```$', '', corrected_text)
            corrected_text = corrected_text.strip()
            
            if corrected_text and len(corrected_text) > len(ocr_text) * 0.5:  # Reasonable length check
                logger.info(f"AI corrected OCR text: {len(ocr_text)} -> {len(corrected_text)} chars")
                return corrected_text
            else:
                logger.warning("AI correction returned suspicious result, using original")
                return ocr_text
                
        except Exception as e:
            logger.warning(f"AI text correction failed: {e}, using original text")
            return ocr_text
    
    @staticmethod
    def normalize_transaction_description(description: str) -> str:
        """
        Use GPT-4 to normalize transaction descriptions by separating concatenated text.
        Examples:
        - "STRIPETRANSFER" -> "STRIPE TRANSFER"
        - "DoorDash,Inc." -> "DoorDash, Inc."
        - "BANKCARD8076MTOTDEP" -> "BANKCARD 8076 MTOT DEP"
        - "CITYOFSPRINGFIELDUTILITY" -> "CITY OF SPRINGFIELD UTILITY"
        
        Args:
            description: Raw transaction description with potentially concatenated text
            
        Returns:
            Normalized description with proper spacing
        """
        if not OPENAI_AVAILABLE or not settings.OPENAI_API_KEY:
            return description
        
        if not description or len(description.strip()) < 5:
            return description
        
        client = get_openai_client()
        if client is None:
            return description
        
        try:
            # Use GPT-4 to normalize the description
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert at normalizing bank transaction descriptions.
Your task is to separate concatenated words and add proper spacing while preserving the original meaning.

Examples:
- "STRIPETRANSFER ST-K3J2A5D4P9S7" -> "STRIPE TRANSFER ST-K3J2A5D4P9S7"
- "DoorDash,Inc.2959-2987" -> "DoorDash, Inc. 2959-2987"
- "BANKCARD8076MTOTDEP" -> "BANKCARD 8076 MTOT DEP"
- "CITYOFSPRINGFIELDUTILITY" -> "CITY OF SPRINGFIELD UTILITY"
- "FIRSTENERGY OPCO FE ECHECK" -> "FIRSTENERGY OPCO FE ECHECK" (already correct)
- "PURCHASE KROGER #7 2899" -> "PURCHASE KROGER #7 2899" (already correct)

Rules:
1. Separate concatenated company names (e.g., "DoorDash,Inc." -> "DoorDash, Inc.")
2. Separate concatenated words in all-caps (e.g., "STRIPETRANSFER" -> "STRIPE TRANSFER")
3. Preserve transaction IDs, reference numbers, and codes (e.g., "ST-K3J2A5D4P9S7")
4. Keep proper spacing around punctuation
5. Don't change the meaning or remove important information
6. Return ONLY the normalized description, no explanations"""
                    },
                    {
                        "role": "user",
                        "content": f"Normalize this transaction description by separating concatenated words:\n\n{description}"
                    }
                ],
                temperature=0.1,  # Low temperature for consistent normalization
                max_tokens=200
            )
            
            normalized = response.choices[0].message.content.strip()
            
            # Remove any markdown formatting if present
            normalized = re.sub(r'^```\w*\n', '', normalized)
            normalized = re.sub(r'\n```$', '', normalized)
            normalized = normalized.strip()
            
            # Validate: normalized should be similar length or longer (spaces added)
            if normalized and len(normalized) >= len(description) * 0.8:  # Allow some shortening but not too much
                logger.debug(f"AI normalized description: '{description}' -> '{normalized}'")
                return normalized
            else:
                logger.debug(f"AI normalization returned suspicious result, using original")
                return description
                
        except Exception as e:
            logger.debug(f"AI description normalization failed: {e}, using original")
            return description
    
    @staticmethod
    def normalize_transaction_descriptions_batch(descriptions: List[str], batch_size: int = 20) -> List[str]:
        """
        Normalize multiple transaction descriptions in batches for efficiency.
        
        Args:
            descriptions: List of transaction descriptions to normalize
            batch_size: Number of descriptions to process per API call
            
        Returns:
            List of normalized descriptions
        """
        if not OPENAI_AVAILABLE or not settings.OPENAI_API_KEY:
            return descriptions
        
        if not descriptions:
            return descriptions
        
        client = get_openai_client()
        if client is None:
            return descriptions
        
        normalized_descriptions = []
        
        # Process in batches to avoid token limits
        for i in range(0, len(descriptions), batch_size):
            batch = descriptions[i:i + batch_size]
            
            try:
                # Prepare batch for AI
                batch_text = "\n".join([f"{idx + 1}. {desc}" for idx, desc in enumerate(batch)])
                
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": """You are an expert at normalizing bank transaction descriptions.
Your task is to separate concatenated words and add proper spacing while preserving the original meaning.

Examples:
- "STRIPETRANSFER ST-K3J2A5D4P9S7" -> "STRIPE TRANSFER ST-K3J2A5D4P9S7"
- "DoorDash,Inc.2959-2987" -> "DoorDash, Inc. 2959-2987"
- "BANKCARD8076MTOTDEP" -> "BANKCARD 8076 MTOT DEP"
- "CITYOFSPRINGFIELDUTILITY" -> "CITY OF SPRINGFIELD UTILITY"

Rules:
1. Separate concatenated company names
2. Separate concatenated words in all-caps
3. Preserve transaction IDs and reference numbers
4. Keep proper spacing around punctuation
5. Return the normalized descriptions in the same order, one per line"""
                        },
                        {
                            "role": "user",
                            "content": f"Normalize these transaction descriptions by separating concatenated words:\n\n{batch_text}\n\nReturn only the normalized descriptions, one per line, in the same order."
                        }
                    ],
                    temperature=0.1,
                    max_tokens=2000
                )
                
                result_text = response.choices[0].message.content.strip()
                
                # Remove markdown if present
                result_text = re.sub(r'^```\w*\n', '', result_text)
                result_text = re.sub(r'\n```$', '', result_text)
                
                # Parse normalized descriptions (one per line)
                normalized_batch = [line.strip() for line in result_text.split('\n') if line.strip()]
                
                # Match up with original batch (handle cases where AI returns fewer/more lines)
                for idx, original_desc in enumerate(batch):
                    if idx < len(normalized_batch):
                        normalized_descriptions.append(normalized_batch[idx])
                    else:
                        # Fallback: use original if AI didn't return enough
                        normalized_descriptions.append(original_desc)
                
                logger.debug(f"AI normalized batch of {len(batch)} descriptions")
                
            except Exception as e:
                logger.warning(f"AI batch normalization failed: {e}, using original descriptions")
                normalized_descriptions.extend(batch)  # Fallback to original
        
        return normalized_descriptions if normalized_descriptions else descriptions
    
    @staticmethod
    def correct_payee_name(payee: str, ocr_context: str = "") -> str:
        """
        Use GPT-4 to correct payee name OCR errors.
        Examples: "Heiddong Dost" -> "Heidelberg", "Bounight" -> "Bonbright"
        
        Args:
            payee: Potentially incorrect payee name from OCR
            ocr_context: Additional context from OCR text
            
        Returns:
            Corrected payee name
        """
        if not OPENAI_AVAILABLE or not settings.OPENAI_API_KEY:
            return payee
        
        if not payee or len(payee.strip()) < 2:
            return payee
        
        # If payee looks correct (no obvious OCR errors), skip AI correction
        if re.match(r'^[A-Za-z\s\.,&\'-]+$', payee) and len(payee.split()) <= 5:
            # Check for common OCR error patterns
            common_errors = ['0', 'O', '1', 'I', 'l', '|', '5', 'S']
            if not any(char in payee for char in common_errors):
                return payee  # Looks correct, skip AI
        
        client = get_openai_client()
        if client is None:
            return payee
        
        try:
            # Use GPT-4 to correct payee name
            prompt = f"Correct this payee name from a check (likely has OCR errors): '{payee}'"
            if ocr_context:
                prompt += f"\n\nContext from check: {ocr_context[:200]}"
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at correcting OCR errors in business/payee names. "
                                 "Fix common mistakes like: 'Heiddong' -> 'Heidelberg', 'Bounight' -> 'Bonbright', "
                                 "'Cinimagi' -> 'Cincinnati'. Return ONLY the corrected name, nothing else."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_tokens=50
            )
            
            corrected = response.choices[0].message.content.strip()
            
            # Clean up response
            corrected = re.sub(r'^["\']|["\']$', '', corrected)  # Remove quotes
            corrected = corrected.strip()
            
            if corrected and 2 <= len(corrected) <= 100:  # Reasonable length
                logger.info(f"AI corrected payee: '{payee}' -> '{corrected}'")
                return corrected
            else:
                return payee
                
        except Exception as e:
            logger.warning(f"AI payee correction failed: {e}")
            return payee
    
    @staticmethod
    def validate_and_correct_fields(extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use GPT-4 to validate and correct extracted check fields.
        
        Args:
            extracted_data: Dictionary with extracted check fields
            
        Returns:
            Validated and corrected data
        """
        if not OPENAI_AVAILABLE or not settings.OPENAI_API_KEY:
            return extracted_data
        
        client = get_openai_client()
        if client is None:
            return extracted_data
        
        try:
            # Prepare data for validation
            fields_summary = {
                "check_number": extracted_data.get("check_number", ""),
                "date": extracted_data.get("date", ""),
                "payee": extracted_data.get("payee", ""),
                "amount": extracted_data.get("amount", 0),
                "memo": extracted_data.get("memo", "")
            }
            
            # Use GPT-4 to validate and suggest corrections
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at validating check data. Review the extracted fields and "
                                 "identify any obvious errors. Return a JSON object with corrected fields if needed, "
                                 "or return empty object {} if everything looks correct. "
                                 "Format: {\"check_number\": \"...\", \"date\": \"YYYY-MM-DD\", \"payee\": \"...\", \"amount\": 0.00, \"memo\": \"...\"}"
                    },
                    {
                        "role": "user",
                        "content": f"Validate and correct these check fields:\n{fields_summary}"
                    }
                ],
                temperature=0.1,
                max_tokens=300,
                response_format={"type": "json_object"}
            )
            
            import json
            corrections = json.loads(response.choices[0].message.content)
            
            # Apply corrections if any
            if corrections:
                for key, value in corrections.items():
                    if key in extracted_data and value:
                        logger.info(f"AI corrected {key}: {extracted_data[key]} -> {value}")
                        extracted_data[key] = value
            
            return extracted_data
            
        except Exception as e:
            logger.warning(f"AI field validation failed: {e}")
            return extracted_data

