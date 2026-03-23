"""
OCR Logs Controller
Provides endpoints to view OCR and extraction logs.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from pathlib import Path
import os
from datetime import datetime
import logging

router = APIRouter(prefix="/logs", tags=["Logs"])

# Find log files - try multiple locations
LOG_DIR = None
OCR_LOG_FILE = None
EXTRACTION_LOG_FILE = None

# 1. Check if LOG_DIR environment variable is set
if os.getenv("LOG_DIR"):
    LOG_DIR = Path(os.getenv("LOG_DIR"))
else:
    # 2. Try relative to current working directory
    if Path("logs").exists():
        LOG_DIR = Path("logs").resolve()
    else:
        # 3. Try relative to backend directory
        backend_dir = Path(__file__).parent.parent.parent
        LOG_DIR = backend_dir / "logs"

# Ensure log directory exists
if LOG_DIR:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    OCR_LOG_FILE = LOG_DIR / "ocr.log"
    EXTRACTION_LOG_FILE = LOG_DIR / "extraction.log"
    # Also check for general app log
    APP_LOG_FILE = LOG_DIR / "app.log"


def find_log_file(log_name: str) -> Path:
    """Find log file in various locations."""
    # Try LOG_DIR first
    if LOG_DIR:
        potential_log = LOG_DIR / log_name
        if potential_log.exists():
            return potential_log
    
    # Try common locations
    common_paths = [
        Path("logs") / log_name,
        Path("/var/log/sync-accounting") / log_name,
        Path("/app/logs") / log_name,
        Path("/tmp/logs") / log_name,
    ]
    
    for path in common_paths:
        if path.exists():
            return path
    
    # Return default location (will be created if needed)
    if LOG_DIR:
        return LOG_DIR / log_name
    
    return Path("logs") / log_name


@router.get("/ocr")
async def get_ocr_logs(
    lines: int = Query(500, ge=1, le=5000, description="Number of lines to return"),
    level: str = Query(None, description="Filter by log level (INFO, ERROR, WARNING, DEBUG)"),
    file_id: int = Query(None, description="Filter by file ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get OCR logs.
    Returns the last N lines from OCR log file.
    """
    log_file = find_log_file("ocr.log")
    
    if not log_file.exists():
        return JSONResponse(
            status_code=200,
            content={
                "logs": [],
                "total_lines": 0,
                "message": "OCR log file not found. Logs will appear here once OCR operations start.",
                "log_file_path": str(log_file)
            }
        )
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        
        # Handle empty file
        if not all_lines:
            return JSONResponse(
                status_code=200,
                content={
                    "logs": [],
                    "total_lines": 0,
                    "returned_lines": 0,
                    "message": "OCR log file is empty. Logs will appear here once OCR operations start.",
                    "log_file_path": str(log_file)
                }
            )
        
        # Filter by level if specified
        if level:
            all_lines = [line for line in all_lines if f" - {level.upper()} -" in line]
        
        # Filter by file_id if specified
        if file_id:
            all_lines = [line for line in all_lines if f"file_id={file_id}" in line or f"file_id: {file_id}" in line]
        
        # Get last N lines
        last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        
        # Parse log lines
        parsed_logs = []
        for line in last_lines:
            parsed_logs.append({
                "raw": line.strip(),
                "timestamp": None,
                "level": None,
                "message": line.strip()
            })
            
            # Try to parse timestamp and level
            # Format: "2025-01-23 10:30:45 - module_name - INFO - message"
            parts = line.split(" - ", 3)
            if len(parts) >= 4:
                try:
                    parsed_logs[-1]["timestamp"] = parts[0]
                    parsed_logs[-1]["level"] = parts[2]
                    parsed_logs[-1]["message"] = parts[3].strip()
                except:
                    pass
        
        return JSONResponse(
            status_code=200,
            content={
                "logs": parsed_logs,
                "total_lines": len(all_lines),
                "returned_lines": len(parsed_logs),
                "log_file_path": str(log_file)
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error reading OCR log file: {str(e)}"
        )


@router.get("/extraction")
async def get_extraction_logs(
    lines: int = Query(500, ge=1, le=5000, description="Number of lines to return"),
    level: str = Query(None, description="Filter by log level"),
    file_id: int = Query(None, description="Filter by file ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get extraction logs.
    Returns the last N lines from extraction log file.
    """
    log_file = find_log_file("extraction.log")
    
    if not log_file.exists():
        return JSONResponse(
            status_code=200,
            content={
                "logs": [],
                "total_lines": 0,
                "message": "Extraction log file not found.",
                "log_file_path": str(log_file)
            }
        )
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        
        # Handle empty file
        if not all_lines:
            return JSONResponse(
                status_code=200,
                content={
                    "logs": [],
                    "total_lines": 0,
                    "returned_lines": 0,
                    "message": "Extraction log file is empty. Logs will appear here once extraction operations start.",
                    "log_file_path": str(log_file)
                }
            )
        
        # Apply filters
        if level:
            all_lines = [line for line in all_lines if f" - {level.upper()} -" in line]
        if file_id:
            all_lines = [line for line in all_lines if f"file_id={file_id}" in line or f"file_id: {file_id}" in line]
        
        last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        
        parsed_logs = []
        for line in last_lines:
            parsed_logs.append({
                "raw": line.strip(),
                "timestamp": None,
                "level": None,
                "message": line.strip()
            })
            
            parts = line.split(" - ", 3)
            if len(parts) >= 4:
                try:
                    parsed_logs[-1]["timestamp"] = parts[0]
                    parsed_logs[-1]["level"] = parts[2]
                    parsed_logs[-1]["message"] = parts[3].strip()
                except:
                    pass
        
        return JSONResponse(
            status_code=200,
            content={
                "logs": parsed_logs,
                "total_lines": len(all_lines),
                "returned_lines": len(parsed_logs),
                "log_file_path": str(log_file)
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error reading extraction log file: {str(e)}"
        )


@router.get("/info")
async def get_log_info(
    current_user: User = Depends(get_current_user)
):
    """Get information about log file locations."""
    return JSONResponse(
        status_code=200,
        content={
            "log_directory": str(LOG_DIR) if LOG_DIR else "Not configured",
            "ocr_log_file": str(find_log_file("ocr.log")),
            "extraction_log_file": str(find_log_file("extraction.log")),
            "app_log_file": str(find_log_file("app.log")),
            "ocr_log_exists": find_log_file("ocr.log").exists(),
            "extraction_log_exists": find_log_file("extraction.log").exists(),
        }
    )
