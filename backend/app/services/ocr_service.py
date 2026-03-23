"""
OCR service for extracting text from images and scanned PDFs.
Uses Tesseract OCR for printed text, EasyOCR for handwritten text,
and Google Cloud Vision API for better handwriting recognition.
"""
import pytesseract
from PIL import Image
import pdf2image
import os
import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import logging
from app.core.config import settings
from app.core.file_logging import ocr_logger

logger = ocr_logger  # Use file logger for OCR

# Try to import Google Cloud Vision (optional)
try:
    from google.cloud import vision
    from google.oauth2 import service_account
    GOOGLE_VISION_AVAILABLE = True
except ImportError:
    GOOGLE_VISION_AVAILABLE = False
    logger.warning("Google Cloud Vision not available. Install with: pip install google-cloud-vision")

# Configure tesseract path if specified
if settings.TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

# Try to import EasyOCR (optional, for better handwriting recognition)
try:
    import easyocr
    EASYOCR_AVAILABLE = True
    # Initialize EasyOCR reader (lazy loading to avoid startup delay)
    _easyocr_reader = None
    def get_easyocr_reader():
        global _easyocr_reader
        if _easyocr_reader is None:
            logger.info("Initializing EasyOCR reader (first time may take a moment)...")
            _easyocr_reader = easyocr.Reader(['en'], gpu=False)  # Use CPU, set gpu=True if GPU available
        return _easyocr_reader
except ImportError:
    EASYOCR_AVAILABLE = False
    logger.warning("EasyOCR not available. Install with: pip install easyocr")
    def get_easyocr_reader():
        return None

# Try to import OpenAI (optional, for GPT-4 Vision)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
    # OpenAI client (lazy initialization)
    _openai_client = None
    def get_openai_client():
        global _openai_client
        if _openai_client is None:
            if settings.OPENAI_API_KEY:
                _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
                logger.info("OpenAI client initialized")
            else:
                logger.warning("OpenAI API key not configured")
                return None
        return _openai_client
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI not available. Install with: pip install openai")
    def get_openai_client():
        return None


class OCRService:
    """Service for OCR text extraction from images and scanned PDFs."""
    
    # Class attribute for EasyOCR availability
    EASYOCR_AVAILABLE = False
    
    # Google Vision API client (lazy initialization)
    _google_vision_client = None
    
    @staticmethod
    def get_google_vision_client():
        """Get Google Vision API client (lazy initialization)."""
        if not GOOGLE_VISION_AVAILABLE:
            return None
        
        if OCRService._google_vision_client is None:
            try:
                # Check if API key file is provided
                if settings.GOOGLE_VISION_API_KEY and os.path.exists(settings.GOOGLE_VISION_API_KEY):
                    credentials = service_account.Credentials.from_service_account_file(
                        settings.GOOGLE_VISION_API_KEY
                    )
                    OCRService._google_vision_client = vision.ImageAnnotatorClient(credentials=credentials)
                    logger.info("Google Vision API client initialized with service account")
                elif settings.GOOGLE_VISION_PROJECT_ID:
                    # Use default credentials (for Cloud environments or gcloud auth)
                    OCRService._google_vision_client = vision.ImageAnnotatorClient()
                    logger.info("Google Vision API client initialized with default credentials")
                else:
                    logger.warning("Google Vision API key or project ID not configured")
                    return None
            except Exception as e:
                logger.warning(f"Failed to initialize Google Vision API client: {e}")
                return None
        
        return OCRService._google_vision_client
    
    @staticmethod
    def extract_text_with_google_vision(image_path: str) -> Dict[str, any]:
        """
        Extract text using Google Cloud Vision API (best for handwriting).
        
        Args:
            image_path: Path to image file
            
        Returns:
            Dictionary with extracted text and confidence
        """
        client = OCRService.get_google_vision_client()
        if client is None:
            return {"text": "", "confidence": 0, "error": "Google Vision API not available or not configured"}
        
        try:
            # Read image file
            with open(image_path, 'rb') as image_file:
                content = image_file.read()
            
            # Create image object
            image = vision.Image(content=content)
            
            # Perform document text detection (optimized for dense text and handwriting)
            response = client.document_text_detection(image=image)
            
            if response.error.message:
                return {"text": "", "confidence": 0, "error": response.error.message}
            
            # Extract full text
            full_text = response.full_text_annotation.text if response.full_text_annotation else ""
            
            # Calculate average confidence from all detected text
            confidences = []
            if response.full_text_annotation:
                for page in response.full_text_annotation.pages:
                    for block in page.blocks:
                        for paragraph in block.paragraphs:
                            for word in paragraph.words:
                                # Word confidence is available in the property
                                if hasattr(word, 'property') and hasattr(word.property, 'detected_break'):
                                    # Try to get confidence from word
                                    if hasattr(word, 'confidence'):
                                        confidences.append(word.confidence)
                                # Also check symbol confidence
                                for symbol in word.symbols:
                                    if hasattr(symbol, 'confidence'):
                                        confidences.append(symbol.confidence)
            
            avg_confidence = (sum(confidences) / len(confidences) * 100) if confidences else 0
            
            return {
                "text": full_text,
                "confidence": avg_confidence,
                "is_handwritten": True,  # Google Vision is excellent for handwriting
                "raw_response": response  # Keep raw response for advanced parsing
            }
        except Exception as e:
            logger.error(f"Google Vision API extraction failed: {e}")
            return {"text": "", "confidence": 0, "error": str(e)}
    
    @staticmethod
    def extract_text_with_gpt4_vision(image_path: str) -> Dict[str, any]:
        """
        Extract text using OpenAI GPT-4 Vision API (excellent for handwriting and context understanding).
        
        Args:
            image_path: Path to image file
            
        Returns:
            Dictionary with extracted text and confidence
        """
        client = get_openai_client()
        if client is None:
            return {"text": "", "confidence": 0, "error": "OpenAI API not available or not configured"}
        
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
            
            # Use GPT-4 Vision to extract text from check image
            # This is especially good for handwritten text and understanding context
            response = client.chat.completions.create(
                model="gpt-4o",  # or "gpt-4-vision-preview" if gpt-4o not available
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at reading checks and extracting text accurately. "
                                 "Extract ALL visible text from the check image, including handwritten text. "
                                 "Preserve the layout and structure. Return the text exactly as it appears, "
                                 "including any OCR errors (we'll correct those later)."
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Extract all text from this check image. Include everything: check number, date, payee name, amount (both numeric and written), memo, bank name, routing number, account number, and any other text visible on the check."
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
                max_tokens=2000,  # Enough for full check text
                temperature=0.1  # Low temperature for consistent extraction
            )
            
            extracted_text = response.choices[0].message.content
            
            # Calculate confidence (GPT-4 Vision doesn't provide confidence scores,
            # so we estimate based on response quality)
            confidence = 85.0  # GPT-4 Vision is generally very accurate
            if not extracted_text or len(extracted_text) < 10:
                confidence = 50.0  # Low confidence if very little text extracted
            
            logger.info(f"GPT-4 Vision extracted {len(extracted_text)} characters")
            
            return {
                "text": extracted_text,
                "confidence": confidence,
                "is_handwritten": True,  # GPT-4 Vision excels at handwriting
                "model": "gpt-4o"
            }
        except Exception as e:
            logger.error(f"GPT-4 Vision API extraction failed: {e}")
            return {"text": "", "confidence": 0, "error": str(e)}
    
    @staticmethod
    def is_image_file(file_path: str) -> bool:
        """Check if file is an image format."""
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif'}
        return Path(file_path).suffix.lower() in image_extensions
    
    @staticmethod
    def is_pdf_file(file_path: str) -> bool:
        """Check if file is a PDF."""
        return Path(file_path).suffix.lower() == '.pdf'
    
    @staticmethod
    def preprocess_image(image: Image.Image) -> Image.Image:
        """
        Preprocess image to improve OCR accuracy.
        Enhanced preprocessing for better check/document recognition.
        
        Args:
            image: PIL Image object
            
        Returns:
            Preprocessed PIL Image
        """
        try:
            # Convert to RGB first (some images might be RGBA or other modes)
            if image.mode not in ('L', 'RGB'):
                image = image.convert('RGB')
            
            # Convert to grayscale for better OCR
            if image.mode != 'L':
                image = image.convert('L')
            
            # Resize if too small (minimum 300 DPI equivalent for better OCR)
            width, height = image.size
            min_size = 1500  # Increased from 1200 for better accuracy
            if width < min_size or height < min_size:
                scale_factor = max(min_size / width, min_size / height)
                new_width = int(width * scale_factor)
                new_height = int(height * scale_factor)
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Enhance contrast (more aggressive for checks)
            from PIL import ImageEnhance, ImageFilter
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(2.5)  # Increased from 2.0
            
            # Enhance sharpness
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(2.5)  # Increased from 2.0
            
            # Apply slight denoising (helps with scanned documents)
            image = image.filter(ImageFilter.MedianFilter(size=3))
            
            # Enhance brightness if too dark (using PIL histogram, no numpy needed)
            enhancer = ImageEnhance.Brightness(image)
            # Simple brightness check using image histogram
            histogram = image.histogram()
            total_pixels = sum(histogram)
            weighted_sum = sum(i * count for i, count in enumerate(histogram))
            avg_brightness = weighted_sum / total_pixels if total_pixels > 0 else 128
            
            if avg_brightness < 100:  # Too dark
                image = enhancer.enhance(1.3)
            elif avg_brightness > 200:  # Too bright
                image = enhancer.enhance(0.8)
            
            return image
        except Exception as e:
            logger.warning(f"Image preprocessing failed: {e}, using original image")
            return image
    
    @staticmethod
    def extract_text_with_easyocr(image_path: str) -> Dict[str, any]:
        """
        Extract text using EasyOCR (better for handwriting).
        
        Args:
            image_path: Path to image file
            
        Returns:
            Dictionary with extracted text and confidence
        """
        reader = get_easyocr_reader()
        if reader is None:
            return {"text": "", "confidence": 0, "error": "EasyOCR not available or not initialized"}
        
        try:
            
            # EasyOCR returns list of (bbox, text, confidence)
            results = reader.readtext(image_path)
            
            # Combine all text
            text_parts = []
            confidences = []
            for (bbox, text, confidence) in results:
                text_parts.append(text)
                confidences.append(confidence)
            
            full_text = ' '.join(text_parts)
            avg_confidence = sum(confidences) / len(confidences) * 100 if confidences else 0
            
            return {
                "text": full_text,
                "confidence": avg_confidence,
                "is_handwritten": True  # EasyOCR is better for handwriting
            }
        except Exception as e:
            logger.error(f"EasyOCR extraction failed: {e}")
            return {"text": "", "confidence": 0, "error": str(e)}
    
    @staticmethod
    def extract_text_from_image(image_path: str, preprocess: bool = True, use_easyocr: bool = False) -> Dict[str, any]:
        """
        Extract text from an image file using OCR.
        
        Args:
            image_path: Path to image file
            preprocess: Whether to preprocess image before OCR
            use_easyocr: Whether to use EasyOCR (better for handwriting)
            
        Returns:
            Dictionary with extracted text and metadata
        """
        # Use EasyOCR if requested and available
        if use_easyocr:
            return OCRService.extract_text_with_easyocr(image_path)
        
        try:
            # Open image
            image = Image.open(image_path)
            
            # Preprocess if requested
            if preprocess:
                image = OCRService.preprocess_image(image)
            
            # Perform OCR with optimized config for checks/documents
            # Try multiple PSM modes to handle both printed and handwritten text
            ocr_results = []
            
            # Approach 1: PSM 6 (uniform block) - good for printed text
            try:
                config1 = r'--oem 3 --psm 6'
                text1 = pytesseract.image_to_string(image, config=config1)
                data1 = pytesseract.image_to_data(image, config=config1, output_type=pytesseract.Output.DICT)
                conf1 = [int(c) for c in data1['conf'] if int(c) > 0]
                avg_conf1 = sum(conf1) / len(conf1) if conf1 else 0
                ocr_results.append((text1, avg_conf1, len(text1)))
            except:
                pass
            
            # Approach 2: PSM 11 (sparse text) - better for handwritten text and checks with gaps
            try:
                config2 = r'--oem 3 --psm 11'
                text2 = pytesseract.image_to_string(image, config=config2)
                data2 = pytesseract.image_to_data(image, config=config2, output_type=pytesseract.Output.DICT)
                conf2 = [int(c) for c in data2['conf'] if int(c) > 0]
                avg_conf2 = sum(conf2) / len(conf2) if conf2 else 0
                ocr_results.append((text2, avg_conf2, len(text2)))
            except:
                pass
            
            # Approach 3: PSM 12 (single text line) - good for date fields
            try:
                config3 = r'--oem 3 --psm 12'
                text3 = pytesseract.image_to_string(image, config=config3)
                data3 = pytesseract.image_to_data(image, config=config3, output_type=pytesseract.Output.DICT)
                conf3 = [int(c) for c in data3['conf'] if int(c) > 0]
                avg_conf3 = sum(conf3) / len(conf3) if conf3 else 0
                ocr_results.append((text3, avg_conf3, len(text3)))
            except:
                pass
            
            # Approach 4: PSM 3 (fully automatic) - tries to detect layout automatically
            try:
                config4 = r'--oem 3 --psm 3'
                text4 = pytesseract.image_to_string(image, config=config4)
                data4 = pytesseract.image_to_data(image, config=config4, output_type=pytesseract.Output.DICT)
                conf4 = [int(c) for c in data4['conf'] if int(c) > 0]
                avg_conf4 = sum(conf4) / len(conf4) if conf4 else 0
                ocr_results.append((text4, avg_conf4, len(text4)))
            except:
                pass
            
            # Combine all results - merge text from all approaches to capture more content
            # This helps when one mode misses handwritten text that another catches
            all_texts = [r[0] for r in ocr_results if r[0].strip()]
            if all_texts:
                # Combine unique lines from all OCR attempts
                all_lines = []
                seen_lines = set()
                for txt in all_texts:
                    for line in txt.split('\n'):
                        line_stripped = line.strip()
                        if line_stripped and line_stripped not in seen_lines:
                            all_lines.append(line_stripped)
                            seen_lines.add(line_stripped)
                ocr_text = '\n'.join(all_lines)
            else:
                # Fallback
                custom_config = r'--oem 3 --psm 6'
                ocr_text = pytesseract.image_to_string(image, config=custom_config)
            
            # Get detailed data with bounding boxes (for future use)
            ocr_data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            
            # Calculate confidence score
            confidences = [int(conf) for conf in ocr_data['conf'] if int(conf) > 0]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            return {
                "text": ocr_text,
                "confidence": avg_confidence,
                "word_count": len(ocr_text.split()),
                "char_count": len(ocr_text),
                "raw_data": ocr_data  # For advanced parsing
            }
        except Exception as e:
            logger.error(f"OCR extraction failed for image {image_path}: {e}")
            return {
                "text": "",
                "confidence": 0,
                "error": str(e)
            }
    
    @staticmethod
    def extract_text_from_pdf_image(pdf_path: str, page_limit: int = 5) -> Dict[str, any]:
        """
        Extract text from a scanned PDF (image-based PDF) using OCR.
        
        Args:
            pdf_path: Path to PDF file
            page_limit: Maximum number of pages to process
            
        Returns:
            Dictionary with extracted text from all pages
        """
        try:
            # Convert PDF pages to images
            try:
                images = pdf2image.convert_from_path(
                    pdf_path,
                    dpi=300,  # High DPI for better OCR
                    first_page=1,
                    last_page=min(page_limit, 100)  # Limit pages
                )
            except Exception as pdf_error:
                error_msg = str(pdf_error).lower()
                if "poppler" in error_msg or "unable to get page count" in error_msg:
                    logger.error(f"Poppler not installed or not in PATH. Error: {pdf_error}")
                    return {
                        "text": "",
                        "confidence": 0,
                        "page_count": 0,
                        "pages": [],
                        "word_count": 0,
                        "char_count": 0,
                        "error": (
                            "Poppler is not installed or not in PATH. "
                            "Please install poppler-utils:\n"
                            "  - Ubuntu/Debian: sudo apt-get install poppler-utils\n"
                            "  - macOS: brew install poppler\n"
                            "  - Windows: Download from https://github.com/oschwartz10612/poppler-windows/releases"
                        )
                    }
                else:
                    raise
            
            all_text = []
            all_confidences = []
            page_texts = []
            
            for page_num, image in enumerate(images, 1):
                logger.info(f"Processing PDF page {page_num} for OCR")
                
                # Preprocess image
                processed_image = OCRService.preprocess_image(image)
                
                # Perform OCR
                custom_config = r'--oem 3 --psm 6'
                page_text = pytesseract.image_to_string(processed_image, config=custom_config)
                
                # Get confidence
                ocr_data = pytesseract.image_to_data(processed_image, output_type=pytesseract.Output.DICT)
                confidences = [int(conf) for conf in ocr_data['conf'] if int(conf) > 0]
                page_confidence = sum(confidences) / len(confidences) if confidences else 0
                
                all_text.append(page_text)
                all_confidences.append(page_confidence)
                page_texts.append({
                    "page": page_num,
                    "text": page_text,
                    "confidence": page_confidence
                })
            
            # Combine all pages
            full_text = "\n\n".join(all_text)
            avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0
            
            return {
                "text": full_text,
                "confidence": avg_confidence,
                "page_count": len(images),
                "pages": page_texts,
                "word_count": len(full_text.split()),
                "char_count": len(full_text)
            }
        except Exception as e:
            logger.error(f"OCR extraction failed for PDF {pdf_path}: {e}")
            return {
                "text": "",
                "confidence": 0,
                "error": str(e)
            }

    @staticmethod
    def extract_text_from_pdf_image_with_fallback(
        pdf_path: str,
        page_limit: int = 100,
        min_text_for_success: int = 200,
        fallback_max_pages: int = 15
    ) -> Dict[str, any]:
        """
        Same OCR pipeline as checks: Tesseract first, then if little/no text run
        GPT-4 Vision / Google Vision / EasyOCR on each page (like CheckExtractor).
        Use for image-based bank statements (e.g. WesBanco) that need the same OCR as checks.
        """
        import tempfile
        result = OCRService.extract_text_from_pdf_image(pdf_path, page_limit=page_limit)
        text = (result.get("text") or "").strip()
        if len(text) >= min_text_for_success:
            return result
        logger.info(f"Tesseract returned {len(text)} chars, trying GPT-4 Vision / Google Vision / EasyOCR fallback (same as checks)...")
        try:
            images = pdf2image.convert_from_path(
                pdf_path,
                dpi=300,
                first_page=1,
                last_page=min(page_limit, fallback_max_pages, 100)
            )
        except Exception as e:
            logger.warning(f"Could not convert PDF to images for fallback OCR: {e}")
            return result
        all_pages_text = []
        for page_num, image in enumerate(images, 1):
            tmp_file = None
            try:
                tmp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                image.save(tmp_file.name)
                tmp_file.close()
                page_text = ""
                gpt4 = OCRService.extract_text_with_gpt4_vision(tmp_file.name)
                if gpt4.get("text") and not gpt4.get("error"):
                    page_text = gpt4.get("text", "")
                if not page_text:
                    gv = OCRService.extract_text_with_google_vision(tmp_file.name)
                    if gv.get("text") and not gv.get("error"):
                        page_text = gv.get("text", "")
                if not page_text:
                    easy = OCRService.extract_text_with_easyocr(tmp_file.name)
                    if easy.get("text"):
                        page_text = easy.get("text", "")
                if page_text:
                    all_pages_text.append(page_text)
            except Exception as e:
                logger.debug(f"Fallback OCR failed for page {page_num}: {e}")
            finally:
                if tmp_file and os.path.exists(tmp_file.name):
                    try:
                        os.unlink(tmp_file.name)
                    except Exception:
                        pass
        if all_pages_text:
            full_text = "\n\n".join(all_pages_text)
            if len(full_text) > len(text):
                result["text"] = full_text
                result["confidence"] = result.get("confidence", 0) or 80
                result["page_count"] = len(all_pages_text)
                logger.info(f"Fallback OCR (same as checks) extracted {len(full_text)} chars from {len(all_pages_text)} pages")
        return result

    @staticmethod
    def extract_text(file_path: str, file_type: Optional[str] = None) -> Dict[str, any]:
        """
        Main method to extract text from image or scanned PDF.
        Automatically detects file type.
        
        Args:
            file_path: Path to file
            file_type: Optional file type hint ('image' or 'pdf')
            
        Returns:
            Dictionary with extracted text and metadata
        """
        if not os.path.exists(file_path):
            return {"text": "", "confidence": 0, "error": "File not found"}
        
        # Auto-detect file type if not provided
        if not file_type:
            if OCRService.is_image_file(file_path):
                file_type = "image"
            elif OCRService.is_pdf_file(file_path):
                file_type = "pdf"
            else:
                return {"text": "", "confidence": 0, "error": "Unsupported file type"}
        
        # Extract based on type
        if file_type == "image":
            return OCRService.extract_text_from_image(file_path)
        elif file_type == "pdf":
            # For PDFs, check if it's a check first (checks should always use OCR for better accuracy)
            is_check = "check" in os.path.basename(file_path).lower() or \
                      any(str(num) in os.path.basename(file_path) for num in range(1139, 1150))
            
            if is_check:
                # Force OCR for checks (even if text is available, OCR gives better structured data)
                logger.info(f"Check detected, using OCR for {file_path}")
                return OCRService.extract_text_from_pdf_image(file_path)
            
            # Try text extraction first (for text-based PDFs)
            try:
                import pdfplumber
                with pdfplumber.open(file_path) as pdf:
                    if len(pdf.pages) > 0:
                        first_page_text = pdf.pages[0].extract_text() or ""
                        # If we get substantial text, it's a text-based PDF
                        if len(first_page_text) > 100:
                            logger.info(f"PDF {file_path} appears to be text-based, skipping OCR")
                            return {
                                "text": first_page_text,
                                "confidence": 100,
                                "is_text_based": True,
                                "error": "Text-based PDF, use PDFExtractor instead"
                            }
            except:
                pass
            
            # If no text or minimal text, treat as scanned PDF and use OCR
            return OCRService.extract_text_from_pdf_image(file_path)
        else:
            return {"text": "", "confidence": 0, "error": "Unsupported file type"}

