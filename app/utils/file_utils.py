"""
File operation utilities
"""
import os
import tempfile
import requests
from typing import Optional, List
import urllib3

from ..config.logging_config import get_logger
from ..config.settings import settings
from ..exceptions.custom_exceptions import FileOperationError
from .url_utils import resolve_redirect_url, extract_file_extension

logger = get_logger(__name__)


def download_file(url: str, temp_dir: str, file_type: str = "file") -> Optional[str]:
    """
    Download file from URL to temporary location
    
    Args:
        url: File URL
        temp_dir: Temporary directory
        file_type: Type of file for logging (e.g., "audio", "image")
        
    Returns:
        Path to downloaded file or None if failed
        
    Raises:
        FileOperationError: If download fails
    """
    try:
        logger.info(f"Downloading {file_type}: {url}")
        
        # Resolve redirects first
        resolved_url = resolve_redirect_url(url)
        
        # Download file
        response = requests.get(
            resolved_url, 
            timeout=settings.download_timeout, 
            stream=True
        )
        response.raise_for_status()
        
        # Determine file extension
        content_type = response.headers.get('content-type', '')
        suffix = extract_file_extension(url, content_type)
        
        # Create temp file
        temp_file = tempfile.NamedTemporaryFile(
            delete=False, 
            suffix=suffix, 
            dir=temp_dir
        )
        temp_path = temp_file.name
        temp_file.close()
        
        # Write file data
        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        file_size = os.path.getsize(temp_path)
        logger.info(f"✓ {file_type.capitalize()} downloaded: {temp_path} ({file_size} bytes)")
        return temp_path
        
    except requests.RequestException as e:
        logger.error(f"✗ {file_type.capitalize()} download failed: {e}")
        raise FileOperationError(f"Failed to download {file_type}: {e}")
    except Exception as e:
        logger.error(f"✗ Unexpected error downloading {file_type}: {e}")
        # Clean up partial file
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.unlink(temp_path)
        raise FileOperationError(f"Unexpected error downloading {file_type}: {e}")


def cleanup_files(file_paths: List[str]) -> None:
    """
    Clean up temporary files
    
    Args:
        file_paths: List of file paths to clean up
    """
    for file_path in file_paths:
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                logger.debug(f"Cleaned up file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup file {file_path}: {e}")


def cleanup_old_files(directory: str, max_age_seconds: int) -> None:
    """
    Clean up files older than specified age
    
    Args:
        directory: Directory to clean
        max_age_seconds: Maximum file age in seconds
    """
    try:
        import time
        current_time = time.time()
        
        if not os.path.exists(directory):
            return
            
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            if os.path.isfile(file_path):
                file_age = current_time - os.path.getctime(file_path)
                if file_age > max_age_seconds:
                    os.remove(file_path)
                    logger.info(f"Cleaned up old file: {filename}")
                    
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")


def ensure_directory(directory: str) -> None:
    """
    Ensure directory exists
    
    Args:
        directory: Directory path to create
        
    Raises:
        FileOperationError: If directory creation fails
    """
    try:
        os.makedirs(directory, exist_ok=True)
    except Exception as e:
        raise FileOperationError(f"Failed to create directory {directory}: {e}")


def get_file_size_mb(file_path: str) -> float:
    """
    Get file size in megabytes
    
    Args:
        file_path: Path to file
        
    Returns:
        File size in MB
    """
    try:
        size_bytes = os.path.getsize(file_path)
        return round(size_bytes / (1024 * 1024), 2)
    except:
        return 0.0


def is_file_accessible(file_path: str) -> bool:
    """
    Check if file exists and is accessible
    
    Args:
        file_path: Path to file
        
    Returns:
        True if file is accessible
    """
    return os.path.exists(file_path) and os.path.isfile(file_path)