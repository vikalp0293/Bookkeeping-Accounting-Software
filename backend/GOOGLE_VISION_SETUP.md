# Google Cloud Vision API Setup

Google Cloud Vision API provides superior handwriting recognition compared to Tesseract/EasyOCR.

## Setup Instructions

1. **Create a Google Cloud Project**
   - Go to https://console.cloud.google.com
   - Create a new project or select an existing one

2. **Enable Vision API**
   - Navigate to "APIs & Services" > "Library"
   - Search for "Cloud Vision API"
   - Click "Enable"

3. **Create Service Account**
   - Go to "IAM & Admin" > "Service Accounts"
   - Click "Create Service Account"
   - Give it a name (e.g., "vision-ocr-service")
   - Grant role: "Cloud Vision API User"
   - Click "Done"

4. **Download JSON Key**
   - Click on the service account you just created
   - Go to "Keys" tab
   - Click "Add Key" > "Create new key"
   - Select "JSON" format
   - Download the key file

5. **Configure in .env**
   Add one of the following to your `.env` file:
   
   **Option A: Using Service Account Key (Recommended)**
   ```
   GOOGLE_VISION_API_KEY=/path/to/your-service-account-key.json
   ```
   
   **Option B: Using Project ID with gcloud auth**
   ```
   GOOGLE_VISION_PROJECT_ID=your-project-id
   ```
   Then run: `gcloud auth application-default login`

## Usage

Once configured, the system will automatically use Google Vision API for check extraction:
- **Priority**: Google Vision API > EasyOCR > Tesseract
- Google Vision API is specifically optimized for handwriting recognition
- Better accuracy for handwritten dates, amounts, and payee names

## Pricing

Google Cloud Vision API pricing:
- First 1,000 units/month: FREE
- 1,001-5,000,000 units: $1.50 per 1,000 units
- See: https://cloud.google.com/vision/pricing

## Testing

After setup, test with:
```bash
cd backend
source venv/bin/activate
python3 -c "from app.services.ocr_service import OCRService; print('Client:', OCRService.get_google_vision_client())"
```

If configured correctly, it should show the client object instead of None.
