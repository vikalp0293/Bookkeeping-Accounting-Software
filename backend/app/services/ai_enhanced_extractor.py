"""
AI-Enhanced Check Extractor using GPT-4 Vision with Few-Shot Learning.
Uses ground truth data to train the model on patterns.
"""
import json
import base64
import logging
from pathlib import Path
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
                logger.info("OpenAI client initialized for enhanced extraction")
            else:
                return None
        return _openai_client
except ImportError:
    OPENAI_AVAILABLE = False
    def get_openai_client():
        return None


class AIEnhancedExtractor:
    """Enhanced check extractor using GPT-4 Vision with few-shot learning."""
    
    _ground_truth_data = None
    
    @staticmethod
    def load_ground_truth_data() -> List[Dict]:
        """Load ground truth data from JSON file."""
        if AIEnhancedExtractor._ground_truth_data is not None:
            return AIEnhancedExtractor._ground_truth_data
        
        try:
            ground_truth_file = Path(__file__).parent.parent.parent / 'ground_truth_data.json'
            if ground_truth_file.exists():
                with open(ground_truth_file, 'r') as f:
                    AIEnhancedExtractor._ground_truth_data = json.load(f)
                logger.info(f"Loaded {len(AIEnhancedExtractor._ground_truth_data)} ground truth examples")
                return AIEnhancedExtractor._ground_truth_data
        except Exception as e:
            logger.warning(f"Failed to load ground truth data: {e}")
        
        return []
    
    @staticmethod
    def get_few_shot_examples(count: int = 5) -> str:
        """Get few-shot examples from ground truth data."""
        examples = AIEnhancedExtractor.load_ground_truth_data()
        if not examples:
            return ""
        
        # Select diverse examples
        selected = examples[:count] if len(examples) <= count else examples[::len(examples)//count][:count]
        
        examples_text = "Here are examples of correctly extracted check data:\n\n"
        for i, ex in enumerate(selected, 1):
            examples_text += f"Example {i}:\n"
            examples_text += f"  Company: {ex.get('company', 'N/A')}\n"
            examples_text += f"  Check Number: {ex.get('check_number', 'N/A')}\n"
            examples_text += f"  Date: {ex.get('date', 'N/A')}\n"
            examples_text += f"  Payee: {ex.get('payee', 'N/A')}\n"
            examples_text += f"  Amount: ${ex.get('amount', 0):,.2f}\n"
            examples_text += f"  Amount (written): {ex.get('amount_written', 'N/A')}\n"
            examples_text += f"  Memo: {ex.get('memo', 'N/A')}\n\n"
        
        return examples_text
    
    @staticmethod
    def extract_all_possible_values(image_path: str) -> Dict[str, Any]:
        """
        Use GPT-4 Vision to extract ALL possible values for each field from check image.
        Then use AI to select the correct ones based on patterns.
        
        Args:
            image_path: Path to check image
            
        Returns:
            Dictionary with extracted check data
        """
        if not OPENAI_AVAILABLE:
            return {"error": "OpenAI not available"}
        
        client = get_openai_client()
        if client is None:
            return {"error": "OpenAI client not initialized"}
        
        try:
            import base64
            
            # Read and encode image
            with open(image_path, 'rb') as image_file:
                image_data = image_file.read()
                base64_image = base64.b64encode(image_data).decode('utf-8')
            
            # Determine image format
            image_ext = Path(image_path).suffix.lower()
            mime_type = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }.get(image_ext, 'image/jpeg')
            
            # Get few-shot examples
            few_shot_examples = AIEnhancedExtractor.get_few_shot_examples(count=5)
            
            # Enhanced prompt with few-shot learning
            system_prompt = """You are an expert at extracting check data. Your task is to:
1. Extract ALL possible values for each field (there may be multiple candidates)
2. Identify which values are correct based on check patterns
3. Handle both numeric and written amounts
4. Correct OCR errors automatically

Return a JSON object with this structure:
{
  "check_number": {"candidates": ["1273", "001273"], "selected": "1273", "confidence": 0.95},
  "date": {"candidates": ["02/09/2024", "2/9/2024"], "selected": "02/09/2024", "confidence": 0.9},
  "payee": {"candidates": ["Union Savings Bank", "Union Savings"], "selected": "Union Savings Bank", "confidence": 0.95},
  "amount_numeric": {"candidates": [2036.35, 2036], "selected": 2036.35, "confidence": 0.9},
  "amount_written": {"candidates": ["Two Thousand Thirty-Six and 35/100 Dollars"], "selected": "Two Thousand Thirty-Six and 35/100 Dollars", "confidence": 0.95},
  "memo": {"candidates": ["- 24-02818904", "24-02818904"], "selected": "- 24-02818904", "confidence": 0.8},
  "company": {"candidates": ["1299 Prentis Company, LLC"], "selected": "1299 Prentis Company, LLC", "confidence": 0.9},
  "bank_name": {"candidates": ["PNC Bank", "PNC"], "selected": "PNC Bank", "confidence": 0.85}
}

Important:
- Extract ALL possible values you see (don't just pick one)
- For amounts: extract both numeric ($2036.35) and written ("Two Thousand Thirty-Six...")
- For dates: extract all date formats you see, prefer the one in the "Date:" field
- For payee: correct OCR errors (e.g., "Heiddong" -> "Heidelberg")
- Select the most likely correct value based on check patterns
- Confidence should be 0.0-1.0"""
            
            user_prompt = f"""Extract all possible values from this check image and select the correct ones.

{few_shot_examples}

Analyze the check image and return JSON with all candidates and selected values."""
            
            # Use GPT-4 Vision to extract structured data
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": user_prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=2000,
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            result_json = json.loads(response.choices[0].message.content)
            
            # Convert to standard format
            extracted_data = {
                "check_number": result_json.get("check_number", {}).get("selected"),
                "date": result_json.get("date", {}).get("selected"),
                "payee": result_json.get("payee", {}).get("selected"),
                "amount": result_json.get("amount_numeric", {}).get("selected"),
                "amount_written": result_json.get("amount_written", {}).get("selected"),
                "memo": result_json.get("memo", {}).get("selected"),
                "company_name": result_json.get("company", {}).get("selected"),
                "bank_name": result_json.get("bank_name", {}).get("selected"),
                "confidence": min([
                    result_json.get("check_number", {}).get("confidence", 0),
                    result_json.get("date", {}).get("confidence", 0),
                    result_json.get("payee", {}).get("confidence", 0),
                    result_json.get("amount_numeric", {}).get("confidence", 0),
                ]) * 100 if result_json else 0,
                "all_candidates": result_json,  # Keep all candidates for debugging
                "extraction_method": "gpt4_vision_enhanced"
            }
            
            # Format date to YYYY-MM-DD if needed
            if extracted_data.get("date"):
                date_str = extracted_data["date"]
                # Try to parse and format
                try:
                    from datetime import datetime
                    # Try common formats
                    for fmt in ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y"]:
                        try:
                            dt = datetime.strptime(date_str, fmt)
                            extracted_data["date"] = dt.strftime("%Y-%m-%d")
                            break
                        except:
                            continue
                except:
                    pass
            
            logger.info(f"AI Enhanced extraction completed: {extracted_data.get('check_number')}")
            return extracted_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            return {"error": f"JSON parsing failed: {e}"}
        except Exception as e:
            logger.error(f"AI Enhanced extraction failed: {e}")
            return {"error": str(e)}

