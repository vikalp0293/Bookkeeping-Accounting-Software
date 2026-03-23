"""
Local directory scanning service.
Scans user-selected directories for new files and triggers extraction.
"""
import os
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.local_directory import LocalDirectory
from app.models.file import File, FileStatus
from app.models.workspace import Workspace
from app.services.file_service import FileService
from app.services.extraction_service import ExtractionService

logger = logging.getLogger(__name__)


class LocalDirectoryService:
    """Service for scanning local directories and processing new files."""
    
    # Supported file extensions
    SUPPORTED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}
    
    @staticmethod
    def set_directory(
        db: Session,
        workspace_id: int,
        directory_path: str,
        is_active: bool = True,
        scan_interval_minutes: int = 60
    ) -> LocalDirectory:
        """Set or update local directory for workspace."""
        # Validate directory exists and is accessible
        if not os.path.exists(directory_path):
            raise ValueError(f"Directory does not exist: {directory_path}")
        
        if not os.path.isdir(directory_path):
            raise ValueError(f"Path is not a directory: {directory_path}")
        
        if not os.access(directory_path, os.R_OK):
            raise ValueError(f"Directory is not readable: {directory_path}")
        
        # Check if directory already exists for this workspace
        existing = db.query(LocalDirectory).filter(
            LocalDirectory.workspace_id == workspace_id
        ).first()
        
        if existing:
            existing.directory_path = directory_path
            existing.is_active = is_active
            existing.scan_interval_minutes = scan_interval_minutes
            existing.updated_at = datetime.utcnow()
            try:
                db.commit()
                db.refresh(existing)
                return existing
            except Exception as e:
                db.rollback()
                raise ValueError(f"Failed to update directory: {str(e)}")
        
        # Create new directory record
        local_dir = LocalDirectory(
            workspace_id=workspace_id,
            directory_path=directory_path,
            is_active=is_active,
            scan_interval_minutes=scan_interval_minutes
        )
        db.add(local_dir)
        try:
            db.commit()
            db.refresh(local_dir)
            return local_dir
        except Exception as e:
            db.rollback()
            raise ValueError(f"Failed to create directory record: {str(e)}")
    
    @staticmethod
    def get_directory(db: Session, workspace_id: int) -> Optional[LocalDirectory]:
        """Get local directory for workspace."""
        return db.query(LocalDirectory).filter(
            LocalDirectory.workspace_id == workspace_id
        ).first()
    
    @staticmethod
    def calculate_file_hash(file_path: str) -> str:
        """Calculate hash of file for duplicate detection."""
        try:
            with open(file_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
            return file_hash
        except Exception as e:
            logger.error(f"Error calculating file hash: {e}")
            # Fallback: use filename + modified time
            stat = os.stat(file_path)
            return f"{os.path.basename(file_path)}_{stat.st_mtime}"
    
    @staticmethod
    def scan_directory(
        db: Session,
        workspace_id: int,
        force_scan: bool = False
    ) -> Dict[str, any]:
        """
        Scan directory for new files and process them.
        
        Returns:
            Dictionary with scan results
        """
        local_dir = LocalDirectoryService.get_directory(db, workspace_id)
        
        if not local_dir:
            return {
                "success": False,
                "error": "No directory configured for this workspace"
            }
        
        if not local_dir.is_active and not force_scan:
            return {
                "success": False,
                "error": "Directory scanning is disabled"
            }
        
        directory_path = local_dir.directory_path
        
        if not os.path.exists(directory_path):
            return {
                "success": False,
                "error": f"Directory no longer exists: {directory_path}"
            }
        
        # Get workspace to find user_id
        workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if not workspace:
            return {
                "success": False,
                "error": "Workspace not found"
            }
        
        # Scan for files
        new_files = []
        processed_files = []
        errors = []
        
        try:
            # Get all files in directory
            for file_path in Path(directory_path).rglob('*'):
                if not file_path.is_file():
                    continue
                
                # Check if file extension is supported
                if file_path.suffix.lower() not in LocalDirectoryService.SUPPORTED_EXTENSIONS:
                    continue
                
                # Check if file already processed
                file_hash = LocalDirectoryService.calculate_file_hash(str(file_path))
                
                # Check if file already exists in database (by path or hash)
                existing_file = db.query(File).filter(
                    File.file_path == str(file_path)
                ).first()
                
                if existing_file:
                    processed_files.append(str(file_path))
                    continue
                
                # New file found - process it
                try:
                    # Create File record
                    file_type = file_path.suffix.lower().lstrip('.')
                    file_size = file_path.stat().st_size
                    
                    db_file = File(
                        filename=file_path.name,
                        original_filename=file_path.name,
                        file_path=str(file_path),
                        file_type=file_type,
                        file_size=file_size,
                        status=FileStatus.UPLOADED,
                        workspace_id=workspace_id,
                        uploaded_by=workspace.owner_id
                    )
                    db.add(db_file)
                    db.commit()
                    db.refresh(db_file)
                    
                    # Trigger extraction
                    try:
                        ExtractionService.extract_data_from_file(
                            db=db,
                            file_id=db_file.id
                        )
                        new_files.append({
                            "file_id": db_file.id,
                            "filename": file_path.name,
                            "path": str(file_path)
                        })
                    except Exception as extract_error:
                        logger.error(f"Failed to trigger extraction for {file_path}: {extract_error}")
                        errors.append({
                            "file": str(file_path),
                            "error": str(extract_error)
                        })
                
                except Exception as file_error:
                    logger.error(f"Error processing file {file_path}: {file_error}")
                    errors.append({
                        "file": str(file_path),
                        "error": str(file_error)
                    })
        
        except Exception as scan_error:
            logger.error(f"Error scanning directory: {scan_error}")
            return {
                "success": False,
                "error": str(scan_error)
            }
        
        # Update last scan time
        local_dir.last_scan_at = datetime.utcnow()
        db.commit()
        
        return {
            "success": True,
            "new_files": new_files,
            "processed_files_count": len(processed_files),
            "errors": errors,
            "scan_time": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    def toggle_scanning(
        db: Session,
        workspace_id: int,
        is_active: bool
    ) -> LocalDirectory:
        """Enable or disable directory scanning."""
        local_dir = LocalDirectoryService.get_directory(db, workspace_id)
        
        if not local_dir:
            raise ValueError("No directory configured for this workspace")
        
        local_dir.is_active = is_active
        db.commit()
        db.refresh(local_dir)
        
        return local_dir

