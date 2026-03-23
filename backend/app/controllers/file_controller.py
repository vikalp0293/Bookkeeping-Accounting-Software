from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status, BackgroundTasks, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import logging
from app.db.base import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.file import FileUploadResponse, FileListResponse
from app.services.file_service import FileService
from app.services.processing_time_service import ProcessingTimeService
from app.services.activity_log_service import ActivityLogService
from app.models.user_activity_log import ActivityActionType
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/files", tags=["Files"])


@router.post("/upload", response_model=FileUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    workspace_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a file and automatically trigger extraction."""
    from app.services.extraction_service import ExtractionService
    
    logger.info(f"Upload request received: filename={file.filename}, workspace_id={workspace_id}, user_id={current_user.id}")
    
    try:
        db_file = FileService.save_uploaded_file(
            db=db,
            file=file,
            workspace_id=workspace_id,
            user_id=current_user.id
        )
        logger.info(f"File uploaded successfully: file_id={db_file.id}, filename={file.filename}")

        # Classify PDF at upload so we can show document type on Upload page (updated after extraction)
        if db_file.file_type.lower() == "pdf":
            try:
                from app.services.document_type_classifier import classify_for_extraction
                classification = classify_for_extraction(db_file.file_path)
                doc_type = classification.get("document_type")
                if doc_type:
                    db_file.document_type = doc_type
                    db.commit()
                    db.refresh(db_file)
                    logger.info(f"Upload-time classification for file_id={db_file.id}: {doc_type}")
            except Exception as classify_err:
                logger.warning(f"Upload-time classification failed for file_id={db_file.id}: {classify_err}")

        # Log activity
        ActivityLogService.log_activity_from_request(
            db=db,
            user_id=current_user.id,
            action_type=ActivityActionType.FILE_UPLOAD.value,
            request=request,
            resource_type="file",
            resource_id=db_file.id,
            workspace_id=workspace_id,
            details={"filename": file.filename, "file_type": db_file.file_type, "file_size": db_file.file_size}
        )
        
        # Automatically trigger extraction for supported file types
        supported_types = ['pdf', 'jpg', 'jpeg', 'png', 'tiff', 'tif']
        if db_file.file_type.lower() in supported_types:
            try:
                logger.info(f"Auto-triggering extraction for file_id={db_file.id}")
                ExtractionService.extract_data_from_file(
                    db=db,
                    file_id=db_file.id,
                    background_tasks=background_tasks
                )
                logger.info(f"Extraction triggered for file_id={db_file.id}")
            except Exception as extract_error:
                # Log error but don't fail the upload
                logger.error(f"Failed to trigger extraction for file_id={db_file.id}: {extract_error}", exc_info=True)
        else:
            logger.info(f"Skipping extraction for unsupported file type: {db_file.file_type}")
        
        return db_file
    except HTTPException as e:
        logger.error(f"Upload failed (HTTP {e.status_code}): {e.detail} - filename={file.filename}, workspace_id={workspace_id}")
        raise
    except Exception as e:
        logger.error(f"Upload failed with unexpected error: {str(e)} - filename={file.filename}, workspace_id={workspace_id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}"
        )


@router.get("/{file_id}", response_model=FileListResponse)
async def get_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get file by ID."""
    file = FileService.get_file_by_id(db=db, file_id=file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    return file


@router.get("/list/all", response_model=List[FileListResponse])
async def list_files(
    workspace_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all files."""
    from app.models.extracted_data import ExtractedData
    from app.services.extraction_service import ExtractionService
    
    # Check and reset any stuck files before listing
    ExtractionService.check_and_reset_stuck_files(db, workspace_id)
    
    files = FileService.list_files(
        db=db,
        workspace_id=workspace_id,
        user_id=current_user.id
    )
    
    # Include error messages from extracted_data
    result = []
    for file in files:
        file_dict = {
            "id": file.id,
            "filename": file.filename,
            "original_filename": file.original_filename,
            "file_type": file.file_type,
            "file_size": file.file_size,
            "status": file.status,
            "workspace_id": file.workspace_id,
            "created_at": file.created_at,
            "updated_at": file.updated_at,
            "error_message": None,
            "document_type": getattr(file, "document_type", None),
        }
        
        # Get error message from extracted_data if file failed
        if file.status.value == "failed" and file.extracted_data:
            file_dict["error_message"] = file.extracted_data.error_message
        
        result.append(file_dict)
    
    return result


@router.get("/{file_id}/download")
async def download_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Download/view a file."""
    file = FileService.get_file_by_id(db=db, file_id=file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    # Check if file exists on disk
    file_path = file.file_path
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk"
        )
    
    # Determine media type
    media_type_map = {
        'pdf': 'application/pdf',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'xls': 'application/vnd.ms-excel'
    }
    file_ext = file.file_type.lower()
    media_type = media_type_map.get(file_ext, 'application/octet-stream')
    
    return FileResponse(
        path=file_path,
        filename=file.original_filename,
        media_type=media_type
    )


@router.get("/{file_id}/estimated-time")
async def get_estimated_time(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get estimated time remaining for a processing file."""
    # Verify file exists and user has access
    file = FileService.get_file_by_id(db=db, file_id=file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    # Get estimated time (accounts for concurrent processing)
    estimated = ProcessingTimeService.get_estimated_time_remaining(db, file_id)
    
    if estimated is None:
        return {
            "estimated_seconds_remaining": None,
            "estimated_minutes_remaining": None,
            "message": "File is not currently processing"
        }
    
    return estimated


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    request: Request,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a file and its associated data."""
    # Get file info before deletion for activity log
    file = FileService.get_file_by_id(db=db, file_id=file_id)
    workspace_id = file.workspace_id if file else None
    
    success = FileService.delete_file(
        db=db,
        file_id=file_id,
        user_id=current_user.id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    # Log activity
    if file:
        ActivityLogService.log_activity_from_request(
            db=db,
            user_id=current_user.id,
            action_type=ActivityActionType.FILE_DELETE.value,
            request=request,
            resource_type="file",
            resource_id=file_id,
            workspace_id=workspace_id,
            details={"filename": file.original_filename}
        )
    
    return None

