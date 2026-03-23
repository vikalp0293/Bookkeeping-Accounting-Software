"""
Server-side directory browser service.
Allows users to browse and navigate server directories safely.
"""
import os
import logging
from pathlib import Path
from typing import List, Dict, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class DirectoryBrowserService:
    """Service for browsing server-side directories."""
    
    # Base paths that are safe to browse (configurable)
    ALLOWED_BASE_PATHS = [
        os.path.expanduser("~"),  # User home directory
        "/",  # Root (with restrictions)
    ]
    
    # Paths to exclude for security
    EXCLUDED_PATHS = [
        "/etc",
        "/sys",
        "/proc",
        "/dev",
        "/boot",
        "/var/log",
    ]
    
    @staticmethod
    def is_path_allowed(path: str) -> bool:
        """Check if a path is allowed to be browsed."""
        try:
            resolved_path = os.path.abspath(os.path.expanduser(path))
            
            # Check if path is in excluded list
            for excluded in DirectoryBrowserService.EXCLUDED_PATHS:
                if resolved_path.startswith(excluded):
                    return False
            
            # Check if path is within allowed base paths
            for base_path in DirectoryBrowserService.ALLOWED_BASE_PATHS:
                base_resolved = os.path.abspath(os.path.expanduser(base_path))
                if resolved_path.startswith(base_resolved):
                    return True
            
            # Allow if it's a relative path or within current working directory
            if not os.path.isabs(resolved_path):
                return True
            
            return False
        except Exception as e:
            logger.error(f"Error checking path permission: {e}")
            return False
    
    @staticmethod
    def list_directory(path: Optional[str] = None) -> Dict[str, any]:
        """
        List contents of a directory.
        
        Args:
            path: Directory path to list. If None, lists allowed base paths.
        
        Returns:
            Dictionary with directory contents
        """
        if not path:
            # Return base paths user can browse
            base_paths = []
            for base in DirectoryBrowserService.ALLOWED_BASE_PATHS:
                resolved = os.path.abspath(os.path.expanduser(base))
                if os.path.exists(resolved):
                    base_paths.append({
                        "name": os.path.basename(resolved) or resolved,
                        "path": resolved,
                        "type": "directory",
                        "is_base": True
                    })
            return {
                "current_path": None,
                "parent_path": None,
                "items": base_paths
            }
        
        # Validate path
        if not DirectoryBrowserService.is_path_allowed(path):
            raise ValueError(f"Path not allowed: {path}")
        
        resolved_path = os.path.abspath(os.path.expanduser(path))
        
        if not os.path.exists(resolved_path):
            raise ValueError(f"Path does not exist: {resolved_path}")
        
        if not os.path.isdir(resolved_path):
            raise ValueError(f"Path is not a directory: {resolved_path}")
        
        # List directory contents
        items = []
        try:
            for item in os.listdir(resolved_path):
                item_path = os.path.join(resolved_path, item)
                
                # Skip hidden files/folders (optional - can be made configurable)
                if item.startswith('.'):
                    continue
                
                try:
                    is_dir = os.path.isdir(item_path)
                    stat_info = os.stat(item_path)
                    
                    items.append({
                        "name": item,
                        "path": item_path,
                        "type": "directory" if is_dir else "file",
                        "size": stat_info.st_size if not is_dir else None,
                        "modified": stat_info.st_mtime
                    })
                except (OSError, PermissionError) as e:
                    # Skip items we can't access
                    logger.warning(f"Cannot access {item_path}: {e}")
                    continue
            
            # Sort: directories first, then by name
            items.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))
            
        except PermissionError:
            raise ValueError(f"Permission denied: {resolved_path}")
        
        # Get parent path
        parent_path = os.path.dirname(resolved_path) if resolved_path != "/" else None
        
        return {
            "current_path": resolved_path,
            "parent_path": parent_path,
            "items": items
        }
    
    @staticmethod
    def validate_directory(path: str) -> Dict[str, any]:
        """
        Validate that a directory exists and is accessible.
        
        Returns:
            Dictionary with validation result
        """
        try:
            if not DirectoryBrowserService.is_path_allowed(path):
                return {
                    "valid": False,
                    "error": "Path not allowed"
                }
            
            resolved_path = os.path.abspath(os.path.expanduser(path))
            
            if not os.path.exists(resolved_path):
                return {
                    "valid": False,
                    "error": "Path does not exist"
                }
            
            if not os.path.isdir(resolved_path):
                return {
                    "valid": False,
                    "error": "Path is not a directory"
                }
            
            # Check if readable
            if not os.access(resolved_path, os.R_OK):
                return {
                    "valid": False,
                    "error": "Directory is not readable"
                }
            
            return {
                "valid": True,
                "resolved_path": resolved_path
            }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }

