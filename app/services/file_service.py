"""
File management service for downloads, cleanup, and temporary file handling
"""
import os
import time
import threading
from typing import List, Optional, Dict, Any
from ..config.logging_config import get_logger
from ..config.settings import settings
from ..utils.file_utils import cleanup_old_files, ensure_directory, get_file_size_mb, is_file_accessible
from ..exceptions.custom_exceptions import FileOperationError

logger = get_logger(__name__)


class FileService:
    """Service for file management and cleanup operations"""
    
    def __init__(self):
        self.cleanup_thread = None
        self.cleanup_running = False
        self._temp_files = []
        self._temp_files_lock = threading.Lock()
        
        # Ensure output directory exists
        self.ensure_output_directory()
        
        # Start cleanup thread
        self.start_cleanup_service()
    
    def ensure_output_directory(self) -> None:
        """
        Ensure output directory exists and is writable
        
        Raises:
            FileOperationError: If directory creation fails
        """
        try:
            ensure_directory(settings.output_dir)
            logger.info(f"Output directory ready: {settings.output_dir}")
        except Exception as e:
            logger.error(f"Failed to create output directory: {e}")
            raise FileOperationError(f"Output directory creation failed: {e}")
    
    def register_temp_file(self, file_path: str) -> None:
        """
        Register a temporary file for tracking and cleanup
        
        Args:
            file_path: Path to temporary file
        """
        with self._temp_files_lock:
            if file_path not in self._temp_files:
                self._temp_files.append(file_path)
                logger.debug(f"Registered temp file: {file_path}")
    
    def cleanup_temp_files(self, file_paths: Optional[List[str]] = None) -> None:
        """
        Clean up temporary files
        
        Args:
            file_paths: Specific files to clean up, or None for all registered files
        """
        files_to_clean = file_paths or self._temp_files.copy()
        
        for file_path in files_to_clean:
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
                    logger.debug(f"Cleaned up temp file: {file_path}")
                
                # Remove from tracking
                with self._temp_files_lock:
                    if file_path in self._temp_files:
                        self._temp_files.remove(file_path)
                        
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file {file_path}: {e}")
    
    def start_cleanup_service(self) -> None:
        """Start the background cleanup service"""
        if self.cleanup_running:
            return
        
        self.cleanup_running = True
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_worker, 
            daemon=True,
            name="file-cleanup"
        )
        self.cleanup_thread.start()
        logger.info("File cleanup service started")
    
    def stop_cleanup_service(self) -> None:
        """Stop the background cleanup service"""
        self.cleanup_running = False
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            self.cleanup_thread.join(timeout=5)
        logger.info("File cleanup service stopped")
    
    def _cleanup_worker(self) -> None:
        """Background worker for file cleanup"""
        while self.cleanup_running:
            try:
                # Clean up old files in output directory
                cleanup_old_files(settings.output_dir, settings.max_file_age)
                
                # Clean up orphaned temp files
                self._cleanup_orphaned_temp_files()
                
                # Sleep for cleanup interval
                time.sleep(settings.cleanup_interval)
                
            except Exception as e:
                logger.error(f"Error in cleanup worker: {e}")
                time.sleep(60)  # Sleep shorter on error
    
    def _cleanup_orphaned_temp_files(self) -> None:
        """Clean up temporary files that are too old"""
        current_time = time.time()
        
        with self._temp_files_lock:
            orphaned_files = []
            for file_path in self._temp_files:
                try:
                    if os.path.exists(file_path):
                        file_age = current_time - os.path.getctime(file_path)
                        if file_age > 3600:  # 1 hour
                            orphaned_files.append(file_path)
                    else:
                        # File doesn't exist, remove from tracking
                        orphaned_files.append(file_path)
                except Exception:
                    # If we can't check the file, consider it orphaned
                    orphaned_files.append(file_path)
            
            # Clean up orphaned files
            for file_path in orphaned_files:
                try:
                    if os.path.exists(file_path):
                        os.unlink(file_path)
                        logger.debug(f"Cleaned up orphaned temp file: {file_path}")
                    self._temp_files.remove(file_path)
                except Exception as e:
                    logger.warning(f"Failed to cleanup orphaned file {file_path}: {e}")
    
    def get_video_file_info(self, video_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a generated video file
        
        Args:
            video_id: Video ID
            
        Returns:
            Dictionary with file information or None if not found
        """
        try:
            filename = f"{video_id}.mp4"
            file_path = os.path.join(settings.output_dir, filename)
            
            if not is_file_accessible(file_path):
                return None
            
            file_size = get_file_size_mb(file_path)
            created_time = os.path.getctime(file_path)
            
            return {
                'exists': True,
                'path': file_path,
                'size_mb': file_size,
                'created_timestamp': created_time,
                'created': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(created_time)),
                'download_url': f'/download/{video_id}'
            }
            
        except Exception as e:
            logger.error(f"Error getting video file info for {video_id}: {e}")
            return None
    
    def delete_video_file(self, video_id: str) -> bool:
        """
        Delete a generated video file
        
        Args:
            video_id: Video ID
            
        Returns:
            True if file was deleted successfully
        """
        try:
            filename = f"{video_id}.mp4"
            file_path = os.path.join(settings.output_dir, filename)
            
            if os.path.exists(file_path):
                os.unlink(file_path)
                logger.info(f"Deleted video file: {video_id}")
                return True
            
            logger.warning(f"Video file not found for deletion: {video_id}")
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete video file {video_id}: {e}")
            return False
    
    def list_video_files(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        List all generated video files
        
        Args:
            limit: Maximum number of files to return
            
        Returns:
            List of video file information dictionaries
        """
        try:
            video_files = []
            
            if not os.path.exists(settings.output_dir):
                return video_files
            
            # Get all mp4 files
            files = [
                f for f in os.listdir(settings.output_dir) 
                if f.endswith('.mp4') and os.path.isfile(os.path.join(settings.output_dir, f))
            ]
            
            # Sort by creation time (newest first)
            files.sort(
                key=lambda f: os.path.getctime(os.path.join(settings.output_dir, f)), 
                reverse=True
            )
            
            # Limit results
            files = files[:limit]
            
            # Get file info for each
            for filename in files:
                video_id = filename[:-4]  # Remove .mp4 extension
                file_info = self.get_video_file_info(video_id)
                if file_info:
                    file_info['video_id'] = video_id
                    video_files.append(file_info)
            
            return video_files
            
        except Exception as e:
            logger.error(f"Error listing video files: {e}")
            return []
    
    def get_disk_usage(self) -> Dict[str, Any]:
        """
        Get disk usage statistics for output directory
        
        Returns:
            Dictionary with disk usage information
        """
        try:
            total_size = 0
            file_count = 0
            
            if os.path.exists(settings.output_dir):
                for filename in os.listdir(settings.output_dir):
                    file_path = os.path.join(settings.output_dir, filename)
                    if os.path.isfile(file_path):
                        total_size += os.path.getsize(file_path)
                        file_count += 1
            
            return {
                'total_files': file_count,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'total_size_gb': round(total_size / (1024 * 1024 * 1024), 2),
                'output_directory': settings.output_dir
            }
            
        except Exception as e:
            logger.error(f"Error getting disk usage: {e}")
            return {
                'total_files': 0,
                'total_size_bytes': 0,
                'total_size_mb': 0,
                'total_size_gb': 0,
                'output_directory': settings.output_dir,
                'error': str(e)
            }
    
    def validate_file_permissions(self) -> List[str]:
        """
        Validate file system permissions
        
        Returns:
            List of permission errors (empty if all valid)
        """
        errors = []
        
        # Check output directory
        if not os.path.exists(settings.output_dir):
            try:
                ensure_directory(settings.output_dir)
            except Exception as e:
                errors.append(f"Cannot create output directory: {e}")
                return errors
        
        # Check write permissions
        if not os.access(settings.output_dir, os.W_OK):
            errors.append(f"No write permission for output directory: {settings.output_dir}")
        
        # Check read permissions
        if not os.access(settings.output_dir, os.R_OK):
            errors.append(f"No read permission for output directory: {settings.output_dir}")
        
        return errors