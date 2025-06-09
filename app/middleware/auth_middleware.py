"""
API Key authentication middleware
"""
from functools import wraps
from flask import request, jsonify
from ..config.settings import settings
from ..config.logging_config import get_logger
from ..models.response_models import ErrorResponse

logger = get_logger(__name__)


def require_api_key(f):
    """
    Decorator to require API key authentication for endpoints
    
    Expects API key in header: X-API-Key: your-api-key
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip authentication in development if no API key is configured
        if settings.is_development and not settings.api_key:
            logger.debug(f"Skipping API key check in development mode for {request.endpoint}")
            return f(*args, **kwargs)
        
        # In production or when API key is configured, authentication is required
        if not settings.api_key:
            logger.error("API key not configured but authentication is required")
            return jsonify(ErrorResponse(
                error="Authentication not configured",
                details="Server configuration error"
            ).model_dump()), 500
        
        # Get API key from headers
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            logger.warning(f"API key missing for {request.endpoint} from {request.remote_addr}")
            return jsonify(ErrorResponse(
                error="API key required",
                details="Missing X-API-Key header"
            ).model_dump()), 401
        
        if api_key != settings.api_key:
            logger.warning(f"Invalid API key for {request.endpoint} from {request.remote_addr}")
            return jsonify(ErrorResponse(
                error="Invalid API key",
                details="Provided API key is not valid"
            ).model_dump()), 401
        
        logger.debug(f"Valid API key for {request.endpoint}")
        return f(*args, **kwargs)
    
    return decorated_function


def validate_api_key(api_key: str) -> bool:
    """
    Validate API key against configured value
    
    Args:
        api_key: API key to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not api_key or not settings.api_key:
        return False
    
    return api_key == settings.api_key


class AuthenticationError(Exception):
    """Exception raised for authentication errors"""
    pass