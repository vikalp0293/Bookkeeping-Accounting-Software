from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.file import FileStatus


class FileUploadResponse(BaseModel):
    id: int
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    status: FileStatus
    workspace_id: int
    created_at: datetime
    document_type: Optional[str] = None  # individual_check | bank_statement_only | bank_statement_with_checks | multi_check

    class Config:
        from_attributes = True


class FileListResponse(BaseModel):
    id: int
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    status: FileStatus
    workspace_id: int
    created_at: datetime
    updated_at: Optional[datetime]
    error_message: Optional[str] = None  # Error message from extraction if failed
    document_type: Optional[str] = None  # individual_check | bank_statement_only | bank_statement_with_checks | multi_check

    class Config:
        from_attributes = True

