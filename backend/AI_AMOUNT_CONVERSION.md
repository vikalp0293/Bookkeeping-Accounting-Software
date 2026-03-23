# AI-Powered Written Amount Conversion

## Overview

The check extraction system now supports converting written dollar amounts (e.g., "six thousand eighty nine", "Dix thousand eighty") to numeric values using OpenAI's GPT API. This is especially useful when:

1. **OCR errors in numeric amounts**: When the dollar sign and numbers are misread (e.g., "$L089" instead of "$6089")
2. **Written amounts are clearer**: When the written amount on the check is more reliable than the numeric amount
3. **OCR text errors**: When OCR misreads words (e.g., "Dix" instead of "six", "minty" instead of "ninety")

## How It Works

1. **Primary Extraction**: The system first tries to extract numeric amounts using regex patterns (e.g., "$6,089.00")
2. **Fallback to Written Amounts**: If no numeric amount is found, the system searches for written amounts in the OCR text
3. **AI Conversion**: When a written amount is detected, it's sent to OpenAI GPT-3.5-turbo to convert it to a numeric value
4. **OCR Error Handling**: The AI model is specifically instructed to handle common OCR errors:
   - "Dix" → "six"
   - "minty" → "ninety"
   - "fifties" → "twenty-five"

## Configuration

### 1. Add OpenAI API Key to `.env`

```bash
OPENAI_API_KEY=sk-your-api-key-here
```

### 2. Get OpenAI API Key

1. Sign up at https://platform.openai.com/
2. Navigate to API Keys: https://platform.openai.com/api-keys
3. Create a new secret key
4. Add it to your `.env` file

### 3. Pricing

- **GPT-3.5-turbo**: ~$0.0005 per check (very affordable)
- **GPT-4**: ~$0.03 per check (more accurate, but more expensive)
- The system uses GPT-3.5-turbo by default (configurable in code)

## Example Usage

### Without API Key (Graceful Fallback)

If `OPENAI_API_KEY` is not set, the system will:
- Still extract numeric amounts normally
- Skip written amount conversion (no errors, just won't use AI)
- Log a warning that OpenAI is not available

### With API Key

When `OPENAI_API_KEY` is set, the system will:
1. Try numeric extraction first
2. If no numeric amount found, detect written amounts like:
   - "Dix thousand eighty" → 6089.00
   - "two thousand six hundred" → 2600.00
   - "five thousand two hundred minty" → 5290.00
   - "twenty thousand" → 20000.00

## Code Location

- **Main function**: `CheckExtractor.convert_written_amount_to_number()` in `backend/app/services/check_extractor.py`
- **Integration**: Called automatically in `CheckExtractor.parse_amount()` when numeric extraction fails
- **Configuration**: `OPENAI_API_KEY` in `backend/app/core/config.py`

## Testing

To test the feature:

```python
from app.services.check_extractor import CheckExtractor

# Test written amount conversion
result = CheckExtractor.convert_written_amount_to_number("Dix thousand eighty")
print(result)  # Should return 6089.0 (if API key is set)
```

## Benefits

1. **Improved Accuracy**: Handles OCR errors in written amounts
2. **Fallback Option**: Works when numeric amounts are unclear
3. **Cost-Effective**: GPT-3.5-turbo is very affordable (~$0.0005 per check)
4. **Graceful Degradation**: System works without API key (just won't use AI)
5. **Automatic**: No manual intervention needed - works automatically during extraction

## Future Enhancements

- Support for other AI services (Claude, Gemini)
- Caching of common conversions to reduce API calls
- Batch processing for multiple checks
- Custom OCR error mappings based on historical data


