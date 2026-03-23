"""
Service for calculating estimated processing time based on historical averages.
Uses existing File table data - no new database tables needed.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.file import File, FileStatus

logger = logging.getLogger(__name__)


class ProcessingTimeService:
    """Service for estimating processing time based on historical data."""
    
    # In-memory cache: {cache_key: (avg_seconds, cached_at)}
    _cache: Dict[str, Tuple[float, datetime]] = {}
    _cache_ttl = 60  # Cache for 1 minute (learns faster from new completions)
    
    # Default estimates (in seconds) if no historical data
    # These are conservative estimates - will improve as more files are processed
    DEFAULT_ESTIMATES = {
        "pdf": 300,      # 5 minutes for PDFs (conservative, accounts for AI processing)
        "image": 180,    # 3 minutes for images (conservative, accounts for AI processing)
        "excel": 240,    # 4 minutes for Excel
        "jpg": 180,
        "jpeg": 180,
        "png": 180,
        "xlsx": 240,
        "xls": 240,
    }
    
    @staticmethod
    def get_avg_processing_time(db: Session, file_type: str) -> float:
        """
        Calculate average processing time for a file type from completed files.
        Uses in-memory cache to avoid repeated database queries.
        
        Args:
            db: Database session
            file_type: File type (pdf, image, excel, etc.)
            
        Returns:
            Average processing time in seconds
        """
        cache_key = f"avg_time_{file_type.lower()}"
        now = datetime.utcnow()
        
        # Check cache first
        if cache_key in ProcessingTimeService._cache:
            cached_avg, cached_at = ProcessingTimeService._cache[cache_key]
            # Check if cache is still valid (accounting for timezone)
            if cached_at.tzinfo:
                time_diff = (now.replace(tzinfo=cached_at.tzinfo) - cached_at).total_seconds()
            else:
                time_diff = (now - cached_at.replace(tzinfo=None)).total_seconds()
            
            if time_diff < ProcessingTimeService._cache_ttl:
                logger.debug(f"Using cached avg processing time for {file_type}: {cached_avg:.1f}s")
                return cached_avg
        
            # Query completed files of this type (use last 50 for average)
            # Prioritize recent files to learn faster from new patterns
        try:
            completed_files = db.query(File).filter(
                File.status == FileStatus.COMPLETED,
                File.file_type == file_type.lower()
            ).order_by(File.updated_at.desc()).limit(50).all()
            
            if not completed_files:
                # No historical data, use default estimate
                default = ProcessingTimeService.DEFAULT_ESTIMATES.get(
                    file_type.lower(), 
                    90  # Default 90 seconds
                )
                logger.info(f"No historical data for {file_type}, using default: {default}s")
                ProcessingTimeService._cache[cache_key] = (default, now)
                return default
            
            # Calculate average processing time
            total_seconds = 0
            count = 0
            valid_times = []
            
            from datetime import timezone as tz
            for file in completed_files:
                if file.updated_at and file.created_at:
                    # Calculate processing time with proper timezone handling
                    # Make both timezone-aware for consistent comparison
                    updated_at = file.updated_at
                    created_at = file.created_at
                    
                    if updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=tz.utc)
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=tz.utc)
                    
                    # If timezones differ, convert both to UTC
                    if updated_at.tzinfo != created_at.tzinfo:
                        updated_at = updated_at.astimezone(tz.utc)
                        created_at = created_at.astimezone(tz.utc)
                    
                    processing_time = (updated_at - created_at).total_seconds()
                    
                    # Filter outliers: between 10 seconds and 15 minutes
                    # Increased max to 15 minutes to account for AI processing which can take longer
                    if 10 <= processing_time <= 900:
                        valid_times.append(processing_time)
                        total_seconds += processing_time
                        count += 1
            
            if count == 0:
                # No valid times found, use default
                default = ProcessingTimeService.DEFAULT_ESTIMATES.get(
                    file_type.lower(), 
                    300  # Default 5 minutes if no data
                )
                logger.warning(f"No valid processing times for {file_type}, using default: {default}s")
                ProcessingTimeService._cache[cache_key] = (default, now)
                return default
            
            # Calculate average
            avg_seconds = total_seconds / count
            
            # Use median if we have enough samples (more robust to outliers)
            if len(valid_times) >= 5:
                valid_times.sort()
                median_index = len(valid_times) // 2
                avg_seconds = valid_times[median_index]
                logger.debug(f"Using median for {file_type}: {avg_seconds:.1f}s (from {count} samples)")
            else:
                logger.debug(f"Using mean for {file_type}: {avg_seconds:.1f}s (from {count} samples)")
            
            # If we have few samples, use a weighted average with default (learns faster)
            if count < 10:
                # Weight: 70% historical, 30% default (helps learn faster with limited data)
                default = ProcessingTimeService.DEFAULT_ESTIMATES.get(file_type.lower(), 300)
                weighted_avg = (avg_seconds * 0.7) + (default * 0.3)
                logger.debug(f"Using weighted average for {file_type} (few samples): {weighted_avg:.1f}s (70% historical {avg_seconds:.1f}s + 30% default {default}s)")
                avg_seconds = weighted_avg
            
            # Cache the result
            ProcessingTimeService._cache[cache_key] = (avg_seconds, now)
            return avg_seconds
            
        except Exception as e:
            logger.error(f"Error calculating avg processing time for {file_type}: {e}")
            # Return default on error
            default = ProcessingTimeService.DEFAULT_ESTIMATES.get(file_type.lower(), 90)
            return default
    
    @staticmethod
    def get_estimated_time_remaining(
        db: Session,
        file_id: int
    ) -> Optional[Dict[str, float]]:
        """
        Get estimated time remaining for a processing file.
        Accounts for concurrent processing which can slow down extraction.
        
        Args:
            db: Database session
            file_id: File ID
            
        Returns:
            Dictionary with estimated_seconds_remaining and estimated_minutes_remaining,
            or None if file is not processing
        """
        file = db.query(File).filter(File.id == file_id).first()
        
        if not file:
            return None
        
        if file.status != FileStatus.PROCESSING:
            return None
        
        # Calculate elapsed time
        # Use timezone-aware datetime for consistent calculations
        from datetime import timezone
        now = datetime.now(timezone.utc)
        
        # Get the reference timestamp (when processing started)
        if file.updated_at:
            ref_time = file.updated_at
        elif file.created_at:
            ref_time = file.created_at
        else:
            # No timestamps available
            return None
        
        # Make both datetimes timezone-aware for proper comparison
        if ref_time.tzinfo is None:
            # If ref_time is naive, assume it's UTC
            ref_time = ref_time.replace(tzinfo=timezone.utc)
        
        # Calculate elapsed time
        elapsed = (now - ref_time).total_seconds()
        
        # Ensure elapsed is non-negative (shouldn't happen, but safety check)
        if elapsed < 0:
            logger.warning(f"Negative elapsed time for file {file_id}: {elapsed:.1f}s. Using 0.")
            elapsed = 0
        
        # Get average processing time for this file type
        avg_time = ProcessingTimeService.get_avg_processing_time(db, file.file_type)
        
        # Count concurrent processing files (including this one)
        concurrent_count = db.query(File).filter(
            File.status == FileStatus.PROCESSING
        ).count()
        
        # Adjust estimate based on concurrent processing
        # More concurrent files = slower processing (but not linear)
        # Formula: adjusted_time = base_time * (1 + concurrent_factor)
        # concurrent_factor scales sub-linearly (log scale) to avoid over-estimation
        if concurrent_count > 1:
            # Use logarithmic scaling: 2 files = 1.3x, 3 files = 1.5x, 5 files = 1.7x, 10 files = 2.0x
            import math
            concurrent_factor = 1 + (math.log(concurrent_count) * 0.2)  # Logarithmic scaling
            adjusted_avg_time = avg_time * concurrent_factor
            logger.debug(f"Adjusted processing time for {concurrent_count} concurrent files: "
                        f"{avg_time:.1f}s -> {adjusted_avg_time:.1f}s (factor: {concurrent_factor:.2f})")
        else:
            adjusted_avg_time = avg_time
            concurrent_factor = 1.0
        
        # Calculate remaining time
        remaining_seconds = max(0, adjusted_avg_time - elapsed)
        
        # If remaining is very low (< 30 seconds) but file is still processing,
        # add a buffer to avoid showing "0 min" prematurely
        # This happens when estimate is too low - system is still learning
        if remaining_seconds < 30 and elapsed < adjusted_avg_time * 0.8:
            # File is still processing but estimate says almost done
            # Add a conservative buffer (use 50% of average as minimum remaining)
            remaining_seconds = max(remaining_seconds, adjusted_avg_time * 0.5)
            logger.debug(f"Applied buffer to remaining time: {remaining_seconds:.1f}s (file still processing)")
        
        remaining_minutes = round(remaining_seconds / 60, 1)
        
        # Ensure minimum display of 0.5 minutes if still processing
        if remaining_minutes < 0.5 and file.status == FileStatus.PROCESSING:
            remaining_minutes = 0.5
            remaining_seconds = 30
        
        return {
            "estimated_seconds_remaining": remaining_seconds,
            "estimated_minutes_remaining": remaining_minutes,
            "elapsed_seconds": elapsed,
            "average_processing_seconds": avg_time,
            "adjusted_processing_seconds": adjusted_avg_time,
            "concurrent_files": concurrent_count,
            "concurrent_factor": round(concurrent_factor, 2)
        }
    
    @staticmethod
    def clear_cache():
        """Clear the processing time cache (useful for testing)."""
        ProcessingTimeService._cache.clear()
        logger.info("Processing time cache cleared")

