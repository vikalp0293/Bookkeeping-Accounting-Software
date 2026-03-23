from sqlalchemy.orm import Session
from fastapi import HTTPException, status, BackgroundTasks
from app.models.file import File, FileStatus
from app.models.extracted_data import ExtractedData
from app.services.file_service import FileService
from app.services.pdf_extractor import PDFExtractor
from app.services.ocr_service import OCRService
from app.services.check_extractor import CheckExtractor
from app.services.language_detection_service import LanguageDetectionService
from app.services.payee_service import PayeeService
from app.services.review_queue_service import ReviewQueueService
from app.services.document_classifier import DocumentClassifier
from app.services.bank_statement_ai_extractor import BankStatementAIExtractor
from app.models.review_queue import ReviewPriority, ReviewReason
from datetime import datetime
import os
import logging
from app.core.file_logging import extraction_logger

logger = extraction_logger  # Use file logger for extraction


class ExtractionService:
    @staticmethod
    def extract_data_from_file(db: Session, file_id: int, background_tasks: BackgroundTasks = None) -> ExtractedData:
        """Initiate data extraction from file."""
        import asyncio
        import threading
        
        # Get file
        file = FileService.get_file_by_id(db, file_id)
        if not file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )
        
        # Check if extraction already exists and is completed
        existing_extraction = db.query(ExtractedData).filter(ExtractedData.file_id == file_id).first()
        if existing_extraction and existing_extraction.extraction_status == "completed":
            return existing_extraction
        
        # Check if file is already processing - prevent duplicate extractions
        if file.status == FileStatus.PROCESSING:
            # Check if extraction is actually in progress or stuck
            if existing_extraction and existing_extraction.extraction_status == "pending":
                # Check how long it's been processing (if updated_at is old, it might be stuck)
                from datetime import datetime, timedelta
                if existing_extraction.updated_at:
                    time_diff = datetime.utcnow() - existing_extraction.updated_at.replace(tzinfo=None)
                    # If stuck for more than 10 minutes, reset it
                    if time_diff > timedelta(minutes=10):
                        logger.warning(f"File {file_id} appears stuck in processing, resetting...")
                        file.status = FileStatus.FAILED
                        existing_extraction.extraction_status = "failed"
                        existing_extraction.error_message = "Extraction timed out - please retry"
                        db.commit()
                    else:
                        # Still processing, return existing
                        return existing_extraction
                else:
                    # No updated_at, might be stuck, reset it
                    logger.warning(f"File {file_id} has no updated_at, resetting...")
                    file.status = FileStatus.FAILED
                    if existing_extraction:
                        existing_extraction.extraction_status = "failed"
                        existing_extraction.error_message = "Extraction appears stuck - please retry"
                    db.commit()
                    # Continue to retry
            else:
                # Processing but no extraction record, might be stuck
                logger.warning(f"File {file_id} is processing but has no extraction record, resetting...")
                file.status = FileStatus.FAILED
                db.commit()
        
        # Update file status
        file.status = FileStatus.PROCESSING
        db.commit()
        
        # Create or update extraction record
        if existing_extraction:
            extracted_data = existing_extraction
            extracted_data.extraction_status = "pending"
        else:
            extracted_data = ExtractedData(
                file_id=file_id,
                extraction_status="pending",
                raw_data={},
                processed_data={}
            )
            db.add(extracted_data)
        db.commit()
        db.refresh(extracted_data)
        
        # Process extraction in background thread for faster response
        # This ensures the task actually runs
        def run_extraction():
            try:
                logger.info(f"Background extraction thread started for file_id: {file_id}")
                ExtractionService._process_extraction(file_id)
                logger.info(f"Background extraction thread completed for file_id: {file_id}")
            except Exception as thread_error:
                logger.error(f"Background extraction thread crashed for file_id {file_id}: {thread_error}", exc_info=True)
                # Try to update status even if thread crashes
                try:
                    from app.db.base import SessionLocal
                    db_thread = SessionLocal()
                    file_thread = db_thread.query(File).filter(File.id == file_id).first()
                    if file_thread:
                        file_thread.status = FileStatus.FAILED
                        file_thread.updated_at = datetime.utcnow()
                        extracted_data_thread = db_thread.query(ExtractedData).filter(ExtractedData.file_id == file_id).first()
                        if extracted_data_thread:
                            extracted_data_thread.extraction_status = "failed"
                            extracted_data_thread.updated_at = datetime.utcnow()
                            extracted_data_thread.error_message = f"Extraction thread crashed: {str(thread_error)}"
                        db_thread.commit()
                    db_thread.close()
                except Exception as update_error:
                    logger.error(f"Failed to update status after thread crash: {update_error}", exc_info=True)
        
        extraction_thread = threading.Thread(target=run_extraction, daemon=True)
        extraction_thread.start()
        logger.info(f"Started extraction thread for file_id: {file_id}, thread_id: {extraction_thread.ident}")
        
        return extracted_data
    
    @staticmethod
    def _process_extraction(file_id: int):
        """Background task to process extraction from PDF file."""
        from app.db.base import SessionLocal
        from datetime import datetime
            
        logger.info(f"Starting extraction for file_id: {file_id}")
        
        db = SessionLocal()
        try:
            file = db.query(File).filter(File.id == file_id).first()
            if not file:
                logger.error(f"File {file_id} not found")
                return
            
            extracted_data = db.query(ExtractedData).filter(ExtractedData.file_id == file_id).first()
            if not extracted_data:
                logger.error(f"Extraction record not found for file_id: {file_id}")
                file.status = FileStatus.FAILED
                db.commit()
                return
            
            # Update timestamp at start of processing to prevent false "stuck" detection
            extracted_data.updated_at = datetime.utcnow()
            file.updated_at = datetime.utcnow()
            db.commit()
            logger.info(f"Updated timestamps for file_id: {file_id}")
            
            # Check if file exists
            if not os.path.exists(file.file_path):
                error_msg = f"File not found on disk: {file.file_path}"
                logger.error(f"Extraction failed for file_id {file_id}: {error_msg}")
                extracted_data.extraction_status = "failed"
                extracted_data.error_message = error_msg
                extracted_data.updated_at = datetime.utcnow()
                file.status = FileStatus.FAILED
                file.updated_at = datetime.utcnow()
                db.commit()
                return
            
            # Extract based on file type
            if file.file_type.lower() == "pdf":
                logger.info(f"Extracting PDF: {file.file_path}")
                # Use PDF extractor with timeout protection
                try:
                    # Check if extraction was cancelled before starting
                    db.refresh(file)
                    if file.status != FileStatus.PROCESSING:
                        logger.info(f"Extraction cancelled for file_id: {file_id}")
                        return
                    
                    # Multi-page: four-way classification (statement+checks, multi-check, or existing flow)
                    import pdfplumber
                    with pdfplumber.open(file.file_path) as pdf:
                        page_count = len(pdf.pages)
                    extracted_result = None
                    classification = None
                    if page_count > 1:
                        from app.services.document_type_classifier import classify_for_extraction
                        from app.services.statement_with_checks_extractor import StatementWithChecksExtractor
                        from app.services.multi_check_extractor import MultiCheckExtractor
                        four_way = classify_for_extraction(file.file_path)
                        dt4 = four_way.get("document_type", "bank_statement_only")
                        if dt4 == "bank_statement_with_checks":
                            logger.info("Multi-page: statement with attached check images, using StatementWithChecksExtractor")
                            extracted_result = StatementWithChecksExtractor.extract(file.file_path, file.original_filename)
                            classification = four_way
                        elif dt4 == "multi_check":
                            logger.info("Multi-page: multiple checks, using MultiCheckExtractor")
                            extracted_result = MultiCheckExtractor.extract(file.file_path)
                            classification = four_way

                    if extracted_result is None:
                        # Step 1: Use AI to classify the document (check vs bank statement)
                        logger.info("Classifying document using AI...")
                        classification = DocumentClassifier.classify_document(file.file_path, "pdf")
                        doc_type = classification.get("document_type", "other")
                        confidence = classification.get("confidence", 0.5)
                        logger.info(f"AI Classification: {doc_type} (confidence: {confidence:.2f})")
                        
                        # Step 2: Route to appropriate extractor based on AI classification
                        if doc_type == "check" and confidence >= 0.6:
                            logger.info(f"AI classified as check (confidence: {confidence:.2f}), using CheckExtractor")
                            extracted_result = CheckExtractor.extract_check_data(file.file_path)
                            # Ensure document_type is set
                            if not extracted_result.get("document_type"):
                                extracted_result["document_type"] = "check"
                        elif doc_type == "bank_statement" and confidence >= 0.6:
                            logger.info(f"AI classified as bank statement (confidence: {confidence:.2f})")
                            
                            # Use PDF extractor first (faster), then enhance with AI if needed
                            logger.info("Extracting bank statement using PDFExtractor (fast method)...")
                            extracted_result = PDFExtractor.extract_from_pdf(file.file_path, file.original_filename)
                            
                            # Check if we got both deposits AND withdrawals
                            transactions = extracted_result.get("transactions", [])
                            has_deposits = any(t.get("transaction_type") == "DEPOSIT" for t in transactions)
                            has_withdrawals = any(t.get("transaction_type") in ["WITHDRAWAL", "FEE"] for t in transactions)
                            
                            # WesBanco image-based PDF: try OCR whenever we have WesBanco and no transactions (don't require should_use_ai)
                            if extracted_result.get("bank_name") == "WesBanco" and not transactions:
                                logger.info("WesBanco with no transactions (image PDF), trying OCR extraction...")
                                try:
                                    # Use full OCR fallback (Tesseract then GPT-4 Vision/Google Vision/EasyOCR) when Tesseract returns little/garbage text
                                    ocr_result = OCRService.extract_text_from_pdf_image_with_fallback(
                                        file.file_path,
                                        page_limit=100,
                                        min_text_for_success=500,  # Require substantial text so image PDFs trigger vision fallback
                                        fallback_max_pages=25,
                                    )
                                    ocr_text = (ocr_result or {}).get("text", "")
                                    ocr_len = len((ocr_text or "").strip())
                                    logger.info(f"WesBanco OCR returned {ocr_len} chars")
                                    if ocr_text and ocr_len > 50:
                                        wesbanco_from_text = PDFExtractor.extract_wesbanco_from_text(ocr_text)
                                        tx_count = len(wesbanco_from_text.get("transactions") or [])
                                        logger.info(f"WesBanco parse from text: {tx_count} transactions (OCR length {ocr_len})")
                                        if tx_count:
                                            extracted_result["transactions"] = wesbanco_from_text["transactions"]
                                            for key in ("statement_period_start", "statement_period_end", "account_number", "beginning_balance", "ending_balance"):
                                                if wesbanco_from_text.get(key) is not None and extracted_result.get(key) is None:
                                                    extracted_result[key] = wesbanco_from_text[key]
                                            transactions = extracted_result["transactions"]
                                            logger.info(f"WesBanco OCR extraction: {len(transactions)} transactions")
                                    elif ocr_len <= 50:
                                        logger.warning(f"WesBanco OCR returned too little text ({ocr_len} chars), no parse attempted")
                                except Exception as ocr_err:
                                    logger.warning(f"WesBanco OCR fallback failed: {ocr_err}")

                            # Refresh transaction list after WesBanco OCR may have filled it
                            transactions = extracted_result.get("transactions", [])
                            has_deposits = any(t.get("transaction_type") == "DEPOSIT" for t in transactions)
                            has_withdrawals = any(t.get("transaction_type") in ["WITHDRAWAL", "FEE"] for t in transactions)
                            should_use_ai = (
                                extracted_result.get("error") or
                                (transactions and len(transactions) < 5) or
                                (has_deposits and not has_withdrawals and len(transactions) < 50)
                            )
                            if should_use_ai and not extracted_result.get("transactions"):
                                logger.info(f"PDF extraction incomplete (deposits: {has_deposits}, withdrawals: {has_withdrawals}, count: {len(transactions)}), trying AI extraction...")
                                import pdfplumber
                                with pdfplumber.open(file.file_path) as pdf:
                                    total_pages = len(pdf.pages)
                                ai_result = BankStatementAIExtractor.extract_bank_statement_with_ai(
                                    file.file_path,
                                    max_pages=total_pages
                                )
                                if ai_result and not ai_result.get("error") and ai_result.get("transactions"):
                                    ai_transactions = ai_result.get("transactions", [])
                                    ai_has_withdrawals = any(t.get("transaction_type") in ["WITHDRAWAL", "FEE"] for t in ai_transactions)
                                    if ai_has_withdrawals or len(ai_transactions) > len(transactions):
                                        logger.info(f"AI extraction successful: {len(ai_transactions)} transactions (withdrawals: {ai_has_withdrawals})")
                                        extracted_result = ai_result
                                    else:
                                        logger.info(f"AI extraction didn't improve results, keeping PDF extraction")
                            elif extracted_result.get("transactions"):
                                logger.info(f"PDF extraction successful: {len(extracted_result.get('transactions', []))} transactions (deposits: {has_deposits}, withdrawals: {has_withdrawals})")
                                # AI enhancement is already applied in PDFExtractor.apply_ai_enhancements()
                                # It will skip if extraction is complete (has both deposits and withdrawals)
                            
                            # Ensure document_type is set
                            if not extracted_result.get("document_type"):
                                extracted_result["document_type"] = "bank_statement"
                        else:
                            # Low confidence or "other" - try both approaches
                            logger.info(f"Low confidence classification ({confidence:.2f}) or 'other', trying PDF extraction first")
                            
                            # Try PDF extraction first (for text-based PDFs and bank statements)
                            extracted_result = PDFExtractor.extract_from_pdf(file.file_path, file.original_filename)
                            
                            # If PDF extraction failed or returned minimal data, try OCR classification
                            if "error" in extracted_result or (not extracted_result.get("transactions") and not extracted_result.get("account_number")):
                                logger.info(f"PDF extraction returned minimal data, trying OCR-based classification")
                                
                                # Quick OCR to get text for classification (first page only for speed)
                                try:
                                    import pdf2image
                                    from PIL import Image
                                    # Convert just first page to image for faster OCR
                                    images = pdf2image.convert_from_path(file.file_path, first_page=1, last_page=1, dpi=150)
                                    if images:
                                        import tempfile
                                        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                                            images[0].save(tmp_file.name, 'PNG')
                                            ocr_result = OCRService.extract_text_from_image(tmp_file.name)
                                            os.unlink(tmp_file.name)
                                    else:
                                        ocr_result = OCRService.extract_text_from_pdf_image(file.file_path)
                                except Exception as e:
                                    logger.warning(f"Failed to extract first page for classification: {e}, using full OCR")
                                    ocr_result = OCRService.extract_text_from_pdf_image(file.file_path)
                                ocr_text = ocr_result.get("text", "")
                                
                                if ocr_text:
                                    # Classify from text (faster than image classification)
                                    text_classification = DocumentClassifier.classify_from_text(ocr_text)
                                    text_doc_type = text_classification.get("document_type", "other")
                                    text_confidence = text_classification.get("confidence", 0.5)
                                    
                                    logger.info(f"Text-based classification: {text_doc_type} (confidence: {text_confidence:.2f})")
                                    
                                    if text_doc_type == "check" and text_confidence >= 0.6:
                                        logger.info("Text classification suggests check, using CheckExtractor")
                                        extracted_result = CheckExtractor.extract_check_data(file.file_path)
                                    elif text_doc_type == "bank_statement":
                                        # Already tried PDFExtractor, but it failed
                                        # Try full OCR extraction for scanned bank statement
                                        logger.info("Text classification suggests bank statement, but PDF extraction failed")
                                        if ocr_result.get("text"):
                                            extracted_result = {
                                                "raw_text": ocr_result["text"],
                                                "confidence": ocr_result.get("confidence", 0),
                                                "document_type": "bank_statement",
                                                "message": "Scanned bank statement detected, OCR extraction completed. Manual review recommended."
                                            }
                                    else:
                                        # Unknown type, use OCR result
                                        if ocr_result.get("text"):
                                            extracted_result = {
                                                "raw_text": ocr_result["text"],
                                                "confidence": ocr_result.get("confidence", 0),
                                                "message": "Scanned PDF detected, OCR extraction completed. Manual review recommended."
                                            }
                                else:
                                    # OCR failed, use PDF extraction result (even if minimal)
                                    logger.warning("OCR failed, using PDF extraction result")
                    
                    # Check again if cancelled during extraction
                    db.refresh(file)
                    if file.status != FileStatus.PROCESSING:
                        logger.info(f"Extraction cancelled during processing for file_id: {file_id}")
                        return
                except Exception as extract_error:
                    error_msg = f"Extraction failed: {str(extract_error)}"
                    logger.error(f"PDF extraction error for file_id {file_id}: {error_msg}", exc_info=True)
                    logger.error(f"File: {file.original_filename}, Type: {file.file_type}, Path: {file.file_path}")
                    extracted_result = {"error": error_msg}
                
                if "error" in extracted_result:
                    error_msg = extracted_result["error"]
                    logger.error(f"PDF extraction failed for file_id {file_id}: {error_msg}")
                    extracted_data.extraction_status = "failed"
                    extracted_data.error_message = error_msg
                    extracted_data.updated_at = datetime.utcnow()
                    file.status = FileStatus.FAILED
                    file.updated_at = datetime.utcnow()
                else:
                    # Store extracted data
                    # Ensure document_type is set from classification if not already set
                    if not extracted_result.get("document_type") and classification:
                        extracted_result["document_type"] = classification.get("document_type")
                    
                    if "transactions" in extracted_result:
                        transaction_count = len(extracted_result.get("transactions", []))
                        logger.info(f"Extraction successful: {transaction_count} transactions extracted")
                    else:
                        logger.info(f"Extraction completed (check or OCR data)")
                    
                    # Store classification info in raw_data for reference
                    if classification:
                        extracted_result["_classification"] = {
                            "document_type": classification.get("document_type"),
                            "confidence": classification.get("confidence"),
                            "reasoning": classification.get("reasoning"),
                            "bank_name": classification.get("bank_name")
                        }
                    
                    extracted_data.raw_data = extracted_result
                    
                    # Post-process: language detection, payee matching, flagging
                    processed_result = ExtractionService._post_process_extraction(
                        db, file, extracted_result
                    )
                    extracted_data.processed_data = processed_result
                    extracted_data.extraction_status = "completed"
                    file.status = FileStatus.COMPLETED
                    # Update file document_type to match extraction (matched after extraction)
                    resolved_dt = ExtractionService._resolved_document_type_for_file(classification, extracted_result)
                    if resolved_dt:
                        file.document_type = resolved_dt
            elif file.file_type.lower() in ["jpg", "jpeg", "png", "bmp", "tiff", "tif", "gif"]:
                # Image file - use AI classification first
                logger.info(f"Extracting image: {file.file_path}")
                try:
                    # Check if extraction was cancelled before starting
                    db.refresh(file)
                    if file.status != FileStatus.PROCESSING:
                        logger.info(f"Extraction cancelled for file_id: {file_id}")
                        return
                    
                    # Use AI to classify the image
                    logger.info("Classifying image document using AI...")
                    classification = DocumentClassifier.classify_document(file.file_path, "image")
                    doc_type = classification.get("document_type", "other")
                    confidence = classification.get("confidence", 0.5)
                    logger.info(f"AI Classification: {doc_type} (confidence: {confidence:.2f})")
                    
                    # Route to appropriate extractor
                    if doc_type == "check" and confidence >= 0.6:
                        logger.info(f"AI classified as check, using CheckExtractor")
                        # Log to OCR logs that we're processing a check
                        from app.core.file_logging import ocr_logger
                        ocr_logger.info(f"Processing check for file_id: {file_id}, filename: {file.original_filename}")
                        extracted_result = CheckExtractor.extract_check_data(file.file_path)
                        # Log OCR completion
                        if extracted_result and not extracted_result.get("error"):
                            ocr_logger.info(f"Check extraction completed for file_id: {file_id}, confidence: {extracted_result.get('confidence', 0):.2f}")
                        else:
                            ocr_logger.error(f"Check extraction failed for file_id: {file_id}")
                    else:
                        # Generic OCR extraction for other types
                        from app.core.file_logging import ocr_logger
                        ocr_logger.info(f"Starting OCR extraction for file_id: {file_id}, filename: {file.original_filename}, type: {file.file_type}")
                        ocr_result = OCRService.extract_text_from_image(file.file_path)
                        ocr_logger.info(f"OCR extraction completed for file_id: {file_id}, confidence: {ocr_result.get('confidence', 0):.2f}, text_length: {len(ocr_result.get('text', ''))}")
                        extracted_result = {
                            "raw_text": ocr_result.get("text", ""),
                            "confidence": ocr_result.get("confidence", 0),
                            "document_type": doc_type if doc_type != "other" else None,
                            "message": "Image OCR extraction completed. Manual review recommended."
                        }
                    
                    # Check again if cancelled during extraction
                    db.refresh(file)
                    if file.status != FileStatus.PROCESSING:
                        logger.info(f"Extraction cancelled during processing for file_id: {file_id}")
                        return
                except Exception as extract_error:
                    error_msg = f"OCR extraction failed: {str(extract_error)}"
                    logger.error(f"Image OCR extraction error for file_id {file_id}: {error_msg}", exc_info=True)
                    logger.error(f"File: {file.original_filename}, Type: {file.file_type}, Path: {file.file_path}")
                    extracted_result = {"error": error_msg}
                
                if "error" in extracted_result:
                    error_msg = extracted_result["error"]
                    logger.error(f"Image OCR extraction failed for file_id {file_id}: {error_msg}")
                    extracted_data.extraction_status = "failed"
                    extracted_data.error_message = error_msg
                    extracted_data.updated_at = datetime.utcnow()
                    file.status = FileStatus.FAILED
                    file.updated_at = datetime.utcnow()
                else:
                    logger.info(f"Image OCR extraction completed")
                    extracted_data.raw_data = extracted_result
                    
                    # Post-process: language detection, payee matching, flagging
                    processed_result = ExtractionService._post_process_extraction(
                        db, file, extracted_result
                    )
                    extracted_data.processed_data = processed_result
                    extracted_data.extraction_status = "completed"
                    extracted_data.updated_at = datetime.utcnow()
                    file.status = FileStatus.COMPLETED
                    file.updated_at = datetime.utcnow()
                    # Update file document_type to match extraction (matched after extraction)
                    resolved_dt = ExtractionService._resolved_document_type_for_file(classification, extracted_result)
                    if resolved_dt:
                        file.document_type = resolved_dt
            else:
                # For other file types, store basic info
                extracted_data.raw_data = {
                    "file_type": file.file_type,
                    "filename": file.original_filename,
                    "message": "Extraction for this file type not yet implemented"
                }
                extracted_data.processed_data = extracted_data.raw_data
                extracted_data.extraction_status = "completed"
                extracted_data.updated_at = datetime.utcnow()
                file.status = FileStatus.COMPLETED
                file.updated_at = datetime.utcnow()
            
            db.commit()
            logger.info(f"Extraction completed successfully for file_id: {file_id}")
        
        except Exception as e:
            # Handle errors with detailed logging
            error_msg = str(e)
            error_type = type(e).__name__
            logger.error(
                f"Extraction failed for file_id {file_id}: {error_type}: {error_msg}",
                exc_info=True
            )
            logger.error(f"File details - filename: {file.original_filename if 'file' in locals() else 'unknown'}, "
                        f"file_type: {file.file_type if 'file' in locals() else 'unknown'}, "
                        f"file_path: {file.file_path if 'file' in locals() else 'unknown'}")
            try:
                # Try to update file status in database
                try:
                    file = db.query(File).filter(File.id == file_id).first()
                    if file:
                        file.status = FileStatus.FAILED
                        file.updated_at = datetime.utcnow()
                        extracted_data = db.query(ExtractedData).filter(ExtractedData.file_id == file_id).first()
                        if extracted_data:
                            extracted_data.extraction_status = "failed"
                            extracted_data.updated_at = datetime.utcnow()
                            # Include error type in error message for better debugging
                            extracted_data.error_message = f"{error_type}: {error_msg}"
                        db.commit()
                        logger.info(f"Updated file {file_id} status to FAILED with error message")
                except Exception as db_error:
                    logger.error(f"Failed to update database after extraction error: {str(db_error)}", exc_info=True)
                    db.rollback()  # Rollback any partial changes
            except Exception as final_error:
                logger.error(f"Unexpected error in error handler: {final_error}", exc_info=True)
        finally:
            # Always close the database connection
            try:
                db.close()
                logger.info(f"Extraction task completed for file_id: {file_id}")
            except Exception as close_error:
                logger.error(f"Error closing database connection: {close_error}", exc_info=True)
    
    @staticmethod
    def check_and_reset_stuck_files(db: Session, workspace_id: int = None):
        """Check for files stuck in processing state and reset them."""
        from datetime import datetime, timedelta
        from app.models.file import File, FileStatus
        
        # Find files that have been processing for more than 10 minutes
        cutoff_time = datetime.utcnow() - timedelta(minutes=10)
        
        query = db.query(File).filter(File.status == FileStatus.PROCESSING)
        if workspace_id:
            query = query.filter(File.workspace_id == workspace_id)
        
        stuck_files = query.all()
        reset_count = 0
        
        for file in stuck_files:
            # Check extraction record
            extracted_data = db.query(ExtractedData).filter(ExtractedData.file_id == file.id).first()
            
            should_reset = False
            reason = ""
            
            # Check file's updated_at timestamp
            if file.updated_at:
                file_time_diff = datetime.utcnow() - file.updated_at.replace(tzinfo=None)
                if file_time_diff > timedelta(minutes=10):
                    should_reset = True
                    reason = f"File stuck in processing for {file_time_diff}"
            else:
                # No updated_at on file, check created_at
                if file.created_at:
                    file_time_diff = datetime.utcnow() - file.created_at.replace(tzinfo=None)
                    if file_time_diff > timedelta(minutes=10):
                        should_reset = True
                        reason = f"File stuck in processing since creation ({file_time_diff})"
            
            # Also check extraction record
            if extracted_data:
                if extracted_data.updated_at:
                    ext_time_diff = datetime.utcnow() - extracted_data.updated_at.replace(tzinfo=None)
                    if ext_time_diff > timedelta(minutes=10):
                        should_reset = True
                        reason = f"Extraction stuck for {ext_time_diff}"
                elif not should_reset:
                    # No updated_at on extraction, might be stuck
                    should_reset = True
                    reason = "Extraction record has no updated_at timestamp"
            else:
                # Processing but no extraction record, might be stuck
                if not should_reset:
                    should_reset = True
                    reason = "File processing but no extraction record exists"
            
            if should_reset:
                logger.warning(f"Resetting stuck file {file.id} ({file.original_filename}): {reason}")
                file.status = FileStatus.FAILED
                if extracted_data:
                    extracted_data.extraction_status = "failed"
                    extracted_data.error_message = f"Extraction timed out - {reason}. Please retry."
                else:
                    # Create a failed extraction record
                    extracted_data = ExtractedData(
                        file_id=file.id,
                        extraction_status="failed",
                        error_message=f"Extraction timed out - {reason}. Please retry.",
                        raw_data={},
                        processed_data={}
                    )
                    db.add(extracted_data)
                reset_count += 1
        
        if reset_count > 0:
            db.commit()
            logger.info(f"Reset {reset_count} stuck file(s)")
        
        return reset_count
    
    @staticmethod
    def get_extraction_by_file_id(db: Session, file_id: int) -> ExtractedData:
        """Get extraction data by file ID with filtered transactions."""
        extracted_data = db.query(ExtractedData).filter(ExtractedData.file_id == file_id).first()
        if not extracted_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Extraction data not found"
            )

        # Normalize single-check stored data: if processed_data has no "transactions" but has check fields, build one
        if extracted_data.processed_data and isinstance(extracted_data.processed_data, dict):
            pd = extracted_data.processed_data
            if not pd.get("transactions") and (
                pd.get("document_type") == "check" or (pd.get("payee") is not None or pd.get("amount") is not None)
            ):
                try:
                    amt = float(pd["amount"]) if pd.get("amount") is not None else 0.0
                except (TypeError, ValueError):
                    amt = 0.0
                pd["transactions"] = [
                    {
                        "date": pd.get("date") or "",
                        "amount": amt,
                        "description": f"Check #{pd.get('check_number') or ''}".strip(),
                        "payee": (pd.get("payee") or "").strip() or "Unknown",
                        "transaction_type": "WITHDRAWAL",
                        "reference_number": pd.get("check_number"),
                        "check_number": pd.get("check_number"),
                        "memo": pd.get("memo"),
                    }
                ]
        
        # Filter out balance activity entries from transactions before returning
        # This ensures the UI and other consumers get clean data
        if extracted_data.processed_data and isinstance(extracted_data.processed_data, dict):
            import re
            from app.utils.transaction_filter import filter_transactions

            transactions = extracted_data.processed_data.get('transactions', [])
            if transactions:
                stmt_start = extracted_data.processed_data.get('statement_period_start')
                stmt_end = extracted_data.processed_data.get('statement_period_end')

                # Filter transactions
                filtered_transactions = filter_transactions(transactions, stmt_start, stmt_end)

                # Ensure reference_number (check #) is set for check-like transactions so UI can show Check # column
                check_desc_re = re.compile(r"Check\s*#?\s*(\d{3,6})\b", re.IGNORECASE)
                for trans in filtered_transactions:
                    if trans.get("reference_number"):
                        continue
                    desc = trans.get("description") or trans.get("memo") or ""
                    if not desc:
                        continue
                    m = check_desc_re.search(str(desc))
                    if m:
                        trans["reference_number"] = m.group(1)

                # Create a copy of processed_data with filtered transactions (don't modify the original)
                # We'll create a temporary copy for the response
                if len(filtered_transactions) != len(transactions):
                    logger.info(f"Filtered {len(transactions) - len(filtered_transactions)} balance activity entries from file_id {file_id}")
                filtered_data = extracted_data.processed_data.copy()
                filtered_data['transactions'] = filtered_transactions
                # Temporarily replace processed_data for this response (doesn't modify DB)
                original_processed_data = extracted_data.processed_data
                extracted_data.processed_data = filtered_data
                # Store original to restore later (though it won't be persisted)
                extracted_data._original_processed_data = original_processed_data

        return extracted_data
    
    @staticmethod
    def cancel_extraction(db: Session, file_id: int, user_id: int) -> dict:
        """Cancel an ongoing extraction."""
        file = FileService.get_file_by_id(db, file_id)
        if not file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )
        
        # Check if user owns the file
        if file.uploaded_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to cancel this extraction"
            )
        
        # Only allow cancellation if status is processing
        if file.status != FileStatus.PROCESSING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel extraction. File status is: {file.status}"
            )
        
        # Update file and extraction status
        file.status = FileStatus.FAILED
        
        extracted_data = db.query(ExtractedData).filter(ExtractedData.file_id == file_id).first()
        if extracted_data:
            extracted_data.extraction_status = "failed"
            extracted_data.error_message = "Extraction cancelled by user"
        
        db.commit()
        
        return {
            "message": "Extraction cancelled successfully",
            "file_id": file_id,
            "status": "cancelled"
        }
    
    @staticmethod
    def retry_extraction(db: Session, file_id: int, background_tasks: BackgroundTasks = None) -> ExtractedData:
        """Retry extraction for a failed file."""
        import threading
        
        # Get file
        file = FileService.get_file_by_id(db, file_id)
        if not file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )
        
        # Allow retry for failed files or completed files (e.g. re-run for incomplete extraction like image-based WesBanco)
        if file.status not in (FileStatus.FAILED, FileStatus.COMPLETED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot retry extraction. Current status: {file.status}. Retry is allowed for failed or completed files."
            )
        
        # Get or create extraction record
        extracted_data = db.query(ExtractedData).filter(ExtractedData.file_id == file_id).first()
        
        if extracted_data:
            # Reset extraction data
            extracted_data.extraction_status = "pending"
            extracted_data.error_message = None
            extracted_data.raw_data = {}
            extracted_data.processed_data = {}
        else:
            # Create new extraction record
            extracted_data = ExtractedData(
                file_id=file_id,
                extraction_status="pending",
                raw_data={},
                processed_data={}
            )
            db.add(extracted_data)
        
        # Reset file status
        file.status = FileStatus.PROCESSING
        db.commit()
        db.refresh(extracted_data)
        
        # Process extraction in background thread
        def run_extraction():
            ExtractionService._process_extraction(file_id)
        
        extraction_thread = threading.Thread(target=run_extraction, daemon=True)
        extraction_thread.start()
        
        logger.info(f"Retrying extraction for file_id: {file_id}")
        return extracted_data
    
    @staticmethod
    def _resolved_document_type_for_file(classification: dict, extracted_result: dict):
        """Resolve document_type for file record from classification and/or extracted result (four-way or AI)."""
        dt = None
        if classification:
            dt = classification.get("document_type")
        if not dt and extracted_result:
            dt = extracted_result.get("document_type")
        if dt == "check":
            return "individual_check"
        if dt == "bank_statement":
            return "bank_statement_only"
        if dt in ("individual_check", "bank_statement_only", "bank_statement_with_checks", "multi_check"):
            return dt
        return None

    @staticmethod
    def _post_process_extraction(
        db: Session,
        file: File,
        extracted_result: dict
    ) -> dict:
        """
        Post-process extracted data:
        - Language detection
        - Missing fields detection
        - Payee matching
        - Auto-add to review queue if needed
        """
        processed = extracted_result.copy()
        flags = []
        needs_review = False

        # Normalize single-check result to have a "transactions" array (so API and Sync Checks get consistent shape)
        if "transactions" not in processed or not processed.get("transactions"):
            doc_type = extracted_result.get("document_type", "")
            has_check_data = (
                extracted_result.get("payee") is not None
                or (extracted_result.get("amount") is not None and doc_type == "check")
            )
            if doc_type == "check" or has_check_data:
                amount = extracted_result.get("amount")
                if amount is not None:
                    try:
                        amount_float = float(amount)
                    except (TypeError, ValueError):
                        amount_float = 0.0
                else:
                    amount_float = 0.0
                processed["transactions"] = [
                    {
                        "date": extracted_result.get("date") or "",
                        "amount": amount_float,
                        "description": f"Check #{extracted_result.get('check_number') or ''}".strip(),
                        "payee": (extracted_result.get("payee") or "").strip() or "Unknown",
                        "transaction_type": "WITHDRAWAL",
                        "reference_number": extracted_result.get("check_number"),
                        "check_number": extracted_result.get("check_number"),
                        "memo": extracted_result.get("memo"),
                    }
                ]
        
        # Get OCR text for language detection
        ocr_text = ""
        if "raw_text" in extracted_result:
            ocr_text = extracted_result["raw_text"]
        elif "transactions" in extracted_result:
            # Combine transaction text
            ocr_text = " ".join([
                str(t.get("payee", "")) + " " + str(t.get("description", ""))
                for t in extracted_result["transactions"]
            ])
        elif extracted_result.get("document_type") == "check":
            ocr_text = " ".join([
                str(extracted_result.get("payee", "")),
                str(extracted_result.get("memo", "")),
                str(extracted_result.get("amount_written", ""))
            ])
        
        # 1. Language detection
        if ocr_text:
            lang_result = LanguageDetectionService.detect_language(ocr_text)
            processed["language_detection"] = lang_result
            
            if not lang_result.get("is_english", True):
                flags.append("non_english")
                needs_review = True
                logger.info(f"Non-English content detected: {lang_result.get('language')}")
        
        # 2. Missing fields detection
        missing_fields = []
        document_type = extracted_result.get("document_type", "unknown")
        
        if document_type == "check":
            # Required fields for checks
            required_fields = ["payee", "amount", "date"]
            for field in required_fields:
                if not extracted_result.get(field):
                    missing_fields.append(field)
        elif "transactions" in extracted_result:
            # Check transactions for missing fields
            for idx, trans in enumerate(extracted_result["transactions"]):
                trans_missing = []
                if not trans.get("date"):
                    trans_missing.append("date")
                if not trans.get("amount"):
                    trans_missing.append("amount")
                if not trans.get("payee") and not trans.get("depositor"):
                    trans_missing.append("payee")
                
                if trans_missing:
                    missing_fields.append(f"transaction_{idx}: {', '.join(trans_missing)}")
        else:
            # Check if it's an unstructured document (raw_text only, no check or transaction data)
            # This happens when OCR extracts text but can't identify it as a check or bank statement
            has_raw_text = "raw_text" in extracted_result and extracted_result.get("raw_text")
            has_transactions = "transactions" in extracted_result and extracted_result.get("transactions")
            has_check_data = document_type == "check" or extracted_result.get("payee") or extracted_result.get("amount")
            
            if has_raw_text and not has_transactions and not has_check_data:
                # Unstructured document - needs manual review to determine what it is
                flags.append("unstructured_document")
                needs_review = True
                logger.info(f"Unstructured document detected (raw_text only, no transactions or check data) - requires manual review")
        
        if missing_fields:
            processed["missing_fields"] = missing_fields
            flags.append("missing_fields")
            needs_review = True
            logger.info(f"Missing fields detected: {missing_fields}")
        
        # 3. Low confidence detection
        confidence = extracted_result.get("confidence", 100)
        if confidence < 70:
            flags.append("low_confidence")
            needs_review = True
            logger.info(f"Low confidence detected: {confidence}%")
        
        processed["flags"] = flags
        
        # 4. Payee matching for checks
        if document_type == "check" and extracted_result.get("payee"):
            try:
                payee_name = extracted_result["payee"]
                
                # Validate that payee_name is not an amount before processing
                if PayeeService.is_amount(payee_name):
                    logger.warning(f"Skipping payee creation for check: '{payee_name}' appears to be an amount, not a payee name")
                else:
                    match_result = PayeeService.find_matching_payee(
                        db, payee_name, file.workspace_id
                    )
                    
                    if match_result:
                        matched_payee, similarity = match_result
                        processed["payee_match"] = {
                            "matched_payee_id": matched_payee.id,
                            "matched_display_name": matched_payee.display_name,
                            "similarity_score": similarity
                        }
                        
                        # If similarity is low, flag for review
                        if similarity < 95:
                            needs_review = True
                    else:
                        # No match found - create new payee or flag for review
                        payee, is_new, _ = PayeeService.create_or_get_payee(
                            db, payee_name, file.workspace_id, auto_match=True
                        )
                        processed["payee_match"] = {
                            "payee_id": payee.id,
                            "is_new": is_new
                        }
                        if is_new:
                            needs_review = True  # New payee might need verification
            except ValueError as ve:
                # Handle validation errors (e.g., amount detected as payee)
                logger.warning(f"Payee validation failed for check: {ve}")
            except Exception as e:
                logger.warning(f"Payee matching failed: {e}")
        
        # 5. Payee matching for transactions
        if "transactions" in extracted_result:
            for idx, trans in enumerate(extracted_result["transactions"]):
                payee_name = trans.get("payee") or trans.get("depositor")
                if payee_name:
                    # Validate that payee_name is not an amount before processing
                    if PayeeService.is_amount(payee_name):
                        logger.warning(f"Skipping payee creation for transaction {idx}: '{payee_name}' appears to be an amount, not a payee name")
                        continue
                    
                    try:
                        match_result = PayeeService.find_matching_payee(
                            db, payee_name, file.workspace_id
                        )
                        
                        if match_result:
                            matched_payee, similarity = match_result
                            if "payee_matches" not in processed:
                                processed["payee_matches"] = {}
                            processed["payee_matches"][str(idx)] = {
                                "matched_payee_id": matched_payee.id,
                                "matched_display_name": matched_payee.display_name,
                                "similarity_score": similarity
                            }
                            
                            if similarity < 95:
                                needs_review = True
                        else:
                            # Create new payee
                            payee, is_new, _ = PayeeService.create_or_get_payee(
                                db, payee_name, file.workspace_id, auto_match=True
                            )
                            if "payee_matches" not in processed:
                                processed["payee_matches"] = {}
                            processed["payee_matches"][str(idx)] = {
                                "payee_id": payee.id,
                                "is_new": is_new
                            }
                            if is_new:
                                needs_review = True
                    except ValueError as ve:
                        # Handle validation errors (e.g., amount detected as payee)
                        logger.warning(f"Payee validation failed for transaction {idx}: {ve}")
                    except Exception as e:
                        logger.warning(f"Payee matching failed for transaction {idx}: {e}")
        
        # 6. Add to review queue if needed
        if needs_review:
            try:
                priority = ReviewPriority.HIGH
                if "low_confidence" in flags:
                    priority = ReviewPriority.HIGH
                elif "missing_fields" in flags:
                    priority = ReviewPriority.MEDIUM
                elif "non_english" in flags:
                    priority = ReviewPriority.MEDIUM
                else:
                    priority = ReviewPriority.LOW
                
                # Determine review reason
                reason = ReviewReason.OTHER
                if "low_confidence" in flags:
                    reason = ReviewReason.LOW_CONFIDENCE
                elif "missing_fields" in flags:
                    reason = ReviewReason.MISSING_FIELDS
                elif "non_english" in flags:
                    reason = ReviewReason.NON_ENGLISH
                elif "unstructured_document" in flags:
                    reason = ReviewReason.OTHER  # Unstructured document needs manual review
                elif not processed.get("payee_match") and document_type == "check":
                    reason = ReviewReason.NO_PAYEE_MATCH
                
                ReviewQueueService.add_to_queue(
                    db=db,
                    file_id=file.id,
                    review_reason=reason,
                    priority=priority,
                    notes=f"Auto-flagged: {', '.join(flags)}"
                )
                processed["review_queued"] = True
                logger.info(f"Added file {file.id} to review queue: {reason}")
            except Exception as e:
                logger.error(f"Failed to add to review queue: {e}")
        
        return processed

