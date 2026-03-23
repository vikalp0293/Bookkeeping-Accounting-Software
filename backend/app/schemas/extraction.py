from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any


class ExtractionRequest(BaseModel):
    file_id: int


class ExtractionResponse(BaseModel):
    id: int
    file_id: int
    raw_data: Optional[Dict[str, Any]] = None
    processed_data: Optional[Dict[str, Any]] = None
    extraction_status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

