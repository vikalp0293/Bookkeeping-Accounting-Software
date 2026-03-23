"""
Language detection service for flagging non-English content.
"""
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Try to import language detection library
try:
    from langdetect import detect, detect_langs, LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    logger.warning("langdetect not available. Install with: pip install langdetect")


class LanguageDetectionService:
    """Service for detecting language in extracted text."""
    
    MIN_TEXT_LENGTH = 10  # Minimum text length for reliable detection
    
    @staticmethod
    def detect_language(text: str) -> Dict[str, any]:
        """
        Detect language of text.
        
        Returns:
            Dictionary with:
            - language: detected language code (e.g., 'en', 'es')
            - confidence: confidence score (0-1)
            - is_english: boolean
            - error: error message if detection failed
        """
        if not text or len(text.strip()) < LanguageDetectionService.MIN_TEXT_LENGTH:
            return {
                "language": "unknown",
                "confidence": 0.0,
                "is_english": True,  # Default to English for short text
                "error": "Text too short for detection"
            }
        
        if not LANGDETECT_AVAILABLE:
            # Fallback: simple heuristic check
            # Count non-ASCII characters
            non_ascii_count = sum(1 for c in text if ord(c) > 127)
            total_chars = len([c for c in text if c.isalnum()])
            
            if total_chars > 0:
                non_ascii_ratio = non_ascii_count / total_chars
                is_english = non_ascii_ratio < 0.1  # Less than 10% non-ASCII
            else:
                is_english = True
            
            return {
                "language": "unknown",
                "confidence": 0.5,
                "is_english": is_english,
                "error": "Language detection library not available"
            }
        
        try:
            # Detect primary language
            primary_lang = detect(text)
            
            # Get confidence scores for all languages
            lang_probs = detect_langs(text)
            confidence = 0.0
            
            for lang_prob in lang_probs:
                if lang_prob.lang == primary_lang:
                    confidence = lang_prob.prob
                    break
            
            return {
                "language": primary_lang,
                "confidence": confidence,
                "is_english": primary_lang == "en",
                "all_languages": [{"lang": lp.lang, "prob": lp.prob} for lp in lang_probs[:3]]
            }
        except LangDetectException as e:
            logger.warning(f"Language detection failed: {e}")
            return {
                "language": "unknown",
                "confidence": 0.0,
                "is_english": True,  # Default to English on error
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Unexpected error in language detection: {e}")
            return {
                "language": "unknown",
                "confidence": 0.0,
                "is_english": True,
                "error": str(e)
            }
    
    @staticmethod
    def is_english(text: str) -> bool:
        """Quick check if text is English."""
        result = LanguageDetectionService.detect_language(text)
        return result.get("is_english", True)

