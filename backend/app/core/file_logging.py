"""
File Logging Setup
Configures file handlers for OCR, extraction, and other log files.
"""
import logging
import os
from pathlib import Path
from typing import Optional

# Determine log directory - try multiple locations
LOG_DIR: Optional[Path] = None

# 1. Check if LOG_DIR environment variable is set
if os.getenv("LOG_DIR"):
    LOG_DIR = Path(os.getenv("LOG_DIR"))
elif Path("logs").exists():
    LOG_DIR = Path("logs").resolve()
else:
    # Try relative to backend directory
    backend_dir = Path(__file__).parent.parent.parent
    LOG_DIR = backend_dir / "logs"

# Ensure log directory exists
if LOG_DIR:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_file_logger(logger_name: str, log_file_name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Set up a file logger for a specific service.
    
    Args:
        logger_name: Name of the logger (usually __name__)
        log_file_name: Name of the log file (e.g., "ocr.log", "extraction.log")
        level: Logging level (default: INFO)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    
    # Remove existing file handlers to avoid duplicates
    for handler in logger.handlers[:]:
        if isinstance(handler, logging.FileHandler) and log_file_name in handler.baseFilename:
            logger.removeHandler(handler)
    
    # Create file handler
    if LOG_DIR:
        log_file = LOG_DIR / log_file_name
        file_handler = logging.FileHandler(str(log_file), encoding='utf-8')
        file_handler.setLevel(level)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


# Set up loggers for OCR and extraction services
ocr_logger = setup_file_logger('app.services.ocr_service', 'ocr.log')
extraction_logger = setup_file_logger('app.services.extraction_service', 'extraction.log')
