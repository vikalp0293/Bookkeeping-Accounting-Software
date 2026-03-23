import os
import uuid
import logging
from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException, status
from app.models.file import File, FileStatus
from app.models.workspace import Workspace
from app.models.extracted_data import ExtractedData
from app.core.config import settings

logger = logging.getLogger(__name__)


class FileService:
    @staticmethod
    def ensure_upload_dir():
        """Ensure upload directory exists."""
        upload_path = Path(settings.UPLOAD_DIR)
        upload_path.mkdir(parents=True, exist_ok=True)
        return upload_path
    
    @staticmethod
    def save_uploaded_file(
        db: Session,
        file: UploadFile,
        workspace_id: int,
        user_id: int
    ) -> File:
        """Save uploaded file and create database record."""
        # Ensure upload directory exists
        upload_dir = FileService.ensure_upload_dir()
        
        # Validate file size
        file_content = file.file.read()
        file_size = len(file_content)
        if file_size > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE} bytes"
            )
        
        # Check workspace exists
        workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found"
            )
        
        # Generate unique filename
        file_extension = Path(file.filename).suffix
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = upload_dir / unique_filename
        
        # Save file
        with open(file_path, "wb") as f:
            f.write(file_content)
        
        # Determine file type
        file_type = file_extension.lower().lstrip(".")
        if file_type not in ["pdf", "jpg", "jpeg", "png", "xlsx", "xls"]:
            file_type = "other"
        
        # Create database record
        db_file = File(
            filename=unique_filename,
            original_filename=file.filename,
            file_path=str(file_path),
            file_type=file_type,
            file_size=file_size,
            status=FileStatus.UPLOADED,
            workspace_id=workspace_id,
            uploaded_by=user_id
        )
        db.add(db_file)
        db.commit()
        db.refresh(db_file)
        
        return db_file
    
    @staticmethod
    def get_file_by_id(db: Session, file_id: int) -> Optional[File]:
        """Get file by ID."""
        return db.query(File).filter(File.id == file_id).first()
    
    @staticmethod
    def list_files(db: Session, workspace_id: Optional[int] = None, user_id: Optional[int] = None) -> list:
        """List files with optional filters."""
        try:
            query = db.query(File)
            
            if workspace_id:
                query = query.filter(File.workspace_id == workspace_id)
            
            if user_id:
                query = query.filter(File.uploaded_by == user_id)
            
            files = query.order_by(File.created_at.desc()).all()
            logger.debug(f"Listed {len(files)} files (workspace_id={workspace_id}, user_id={user_id})")
            return files
        except Exception as e:
            logger.error(f"Error listing files: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    def delete_file(db: Session, file_id: int, user_id: int) -> bool:
        """Delete a file and its associated data."""
        file = db.query(File).filter(File.id == file_id).first()
        if not file:
            return False
        
        # Check if user owns the file or has permission
        if file.uploaded_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this file"
            )
        
        # Delete physical file from disk
        if os.path.exists(file.file_path):
            try:
                os.remove(file.file_path)
            except Exception as e:
                # Log error but continue with database deletion
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to delete file from disk: {e}")
        
        # Delete from database (cascade will handle extracted_data automatically)
        # But we can also explicitly delete it for clarity
        if file.extracted_data:
            db.delete(file.extracted_data)
        
        db.delete(file)
        db.commit()
        
        return True

