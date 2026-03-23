from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.extraction import ExtractionRequest, ExtractionResponse
from app.services.extraction_service import ExtractionService
from app.services.activity_log_service import ActivityLogService
from app.models.user_activity_log import ActivityActionType

router = APIRouter(prefix="/extract", tags=["Extraction"])


@router.post("/{file_id}", response_model=ExtractionResponse, status_code=status.HTTP_202_ACCEPTED)
async def extract_data(
    request: Request,
    file_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Initiate data extraction from file."""
    # Get file for workspace_id
    from app.services.file_service import FileService
    file = FileService.get_file_by_id(db=db, file_id=file_id)
    
    extracted_data = ExtractionService.extract_data_from_file(
        db=db,
        file_id=file_id,
        background_tasks=background_tasks
    )
    
    # Log activity
    if file:
        ActivityLogService.log_activity_from_request(
            db=db,
            user_id=current_user.id,
            action_type=ActivityActionType.EXTRACTION_START.value,
            request=request,
            resource_type="file",
            resource_id=file_id,
            workspace_id=file.workspace_id,
            details={"filename": file.original_filename}
        )
    
    return extracted_data


@router.get("/{file_id}", response_model=ExtractionResponse)
async def get_extraction(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get extraction results for a file."""
    extracted_data = ExtractionService.get_extraction_by_file_id(db=db, file_id=file_id)
    return extracted_data


@router.post("/{file_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_extraction(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel an ongoing extraction."""
    result = ExtractionService.cancel_extraction(db=db, file_id=file_id, user_id=current_user.id)
    return result


@router.post("/{file_id}/retry", response_model=ExtractionResponse, status_code=status.HTTP_202_ACCEPTED)
async def retry_extraction(
    request: Request,
    file_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retry extraction for a failed file."""
    # Get file for workspace_id
    from app.services.file_service import FileService
    file = FileService.get_file_by_id(db=db, file_id=file_id)
    
    extracted_data = ExtractionService.retry_extraction(
        db=db,
        file_id=file_id,
        background_tasks=background_tasks
    )
    
    # Log activity
    if file:
        ActivityLogService.log_activity_from_request(
            db=db,
            user_id=current_user.id,
            action_type=ActivityActionType.EXTRACTION_RETRY.value,
            request=request,
            resource_type="file",
            resource_id=file_id,
            workspace_id=file.workspace_id,
            details={"filename": file.original_filename}
        )
    
    return extracted_data

