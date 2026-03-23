from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.file import File, FileStatus
from app.models.extracted_data import ExtractedData
from app.models.workspace import Workspace


class DashboardService:
    @staticmethod
    def get_stats(db: Session, user_id: int = None, workspace_id: int = None) -> dict:
        """Get dashboard statistics."""
        # Base queries
        files_query = db.query(File)
        workspaces_query = db.query(Workspace)
        
        # Apply filters
        if workspace_id:
            files_query = files_query.filter(File.workspace_id == workspace_id)
        if user_id:
            files_query = files_query.filter(File.uploaded_by == user_id)
            workspaces_query = workspaces_query.filter(Workspace.owner_id == user_id)
        
        # Get counts
        total_files = files_query.count()
        successful_extractions = files_query.filter(File.status == FileStatus.COMPLETED).count()
        pending_extractions = files_query.filter(File.status == FileStatus.PROCESSING).count()
        failed_extractions = files_query.filter(File.status == FileStatus.FAILED).count()
        total_workspaces = workspaces_query.count()
        
        return {
            "total_files": total_files,
            "successful_extractions": successful_extractions,
            "pending_extractions": pending_extractions,
            "failed_extractions": failed_extractions,
            "total_workspaces": total_workspaces
        }

