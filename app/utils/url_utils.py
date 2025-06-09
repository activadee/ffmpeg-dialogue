"""
URL processing utilities, especially for Google Drive
"""
import requests
from typing import Optional
from ..config.logging_config import get_logger
from ..config.settings import settings
from ..exceptions.custom_exceptions import URLProcessingError

logger = get_logger(__name__)


def process_gdrive_url(url: str) -> str:
    """
    Process Google Drive URLs to ensure they're in the correct format
    
    Args:
        url: Original URL (may be share link or direct link)
        
    Returns:
        Processed URL in export format
        
    Raises:
        URLProcessingError: If URL processing fails
    """
    try:
        if 'drive.google.com' not in url:
            return url
            
        file_id = None
        
        # Extract file ID from various Google Drive URL formats
        if 'id=' in url:
            file_id = url.split('id=')[1].split('&')[0]
        elif '/file/d/' in url:
            file_id = url.split('/file/d/')[1].split('/')[0]
        
        if file_id:
            # Validate file ID format
            if file_id and len(file_id) > 20 and file_id.replace('_', '').replace('-', '').isalnum():
                processed_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                logger.debug(f"Processed Google Drive URL: {url} -> {processed_url}")
                return processed_url
            else:
                logger.warning(f"Invalid Google Drive file ID: {file_id}")
                
        return url
        
    except Exception as e:
        logger.error(f"Failed to process Google Drive URL {url}: {e}")
        raise URLProcessingError(f"Failed to process Google Drive URL: {e}")


def resolve_redirect_url(url: str) -> str:
    """
    Resolve redirect URLs to get final direct URL
    
    Args:
        url: URL that may redirect
        
    Returns:
        Final resolved URL
        
    Raises:
        URLProcessingError: If URL resolution fails
    """
    try:
        # For Google Drive URLs, follow redirects to get final URL
        if 'drive.google.com' in url:
            logger.debug(f"Resolving Google Drive redirect: {url}")
            
            # Create session with SSL certificate verification disabled
            session = requests.Session()
            
            response = session.head(
                url, 
                allow_redirects=True, 
                timeout=settings.url_redirect_timeout
            )
            response.raise_for_status()
            
            final_url = response.url
            logger.debug(f"Final URL after redirects: {final_url}")
            return final_url
        
        return url
        
    except requests.RequestException as e:
        logger.error(f"Failed to resolve redirect for {url}: {e}")
        raise URLProcessingError(f"Failed to resolve redirect: {e}")
    except Exception as e:
        logger.error(f"Unexpected error resolving redirect for {url}: {e}")
        raise URLProcessingError(f"Unexpected error resolving redirect: {e}")


def validate_url(url: str) -> bool:
    """
    Validate if URL is accessible
    
    Args:
        url: URL to validate
        
    Returns:
        True if URL is accessible, False otherwise
    """
    try:
        response = requests.head(url, timeout=settings.url_redirect_timeout)
        return response.status_code < 400
    except:
        return False


def extract_file_extension(url: str, content_type: Optional[str] = None) -> str:
    """
    Extract file extension from URL or content type
    
    Args:
        url: File URL
        content_type: HTTP content-type header
        
    Returns:
        File extension (with dot)
    """
    # Try content type first
    if content_type:
        if 'mp3' in content_type:
            return '.mp3'
        elif 'wav' in content_type:
            return '.wav'
        elif 'mp4' in content_type:
            return '.mp4'
        elif 'png' in content_type:
            return '.png'
        elif 'jpg' in content_type or 'jpeg' in content_type:
            return '.jpg'
    
    # Fall back to URL extension
    if '.' in url:
        ext = '.' + url.split('.')[-1].split('?')[0].split('#')[0]
        if len(ext) <= 5:  # Reasonable extension length
            return ext
    
    # Default based on common patterns
    if any(audio_hint in url.lower() for audio_hint in ['audio', 'mp3', 'wav']):
        return '.mp3'
    elif any(video_hint in url.lower() for video_hint in ['video', 'mp4']):
        return '.mp4'
    elif any(image_hint in url.lower() for image_hint in ['image', 'img', 'png', 'jpg']):
        return '.png'
    
    return '.tmp'  # Fallback