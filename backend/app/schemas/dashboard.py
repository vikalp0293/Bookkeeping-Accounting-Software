from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_files: int
    successful_extractions: int
    pending_extractions: int
    failed_extractions: int
    total_workspaces: int

