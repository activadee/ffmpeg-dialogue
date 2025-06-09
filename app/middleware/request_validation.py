"""
Request validation and preprocessing middleware
"""
import time
from flask import Flask, request, g, jsonify
from werkzeug.exceptions import BadRequest
from ..models.response_models import ErrorResponse
from ..config.logging_config import get_logger
from ..config.settings import settings

logger = get_logger(__name__)


def register_request_middleware(app: Flask) -> None:
    """
    Register request validation and preprocessing middleware
    
    Args:
        app: Flask application instance
    """
    
    @app.before_request
    def before_request():
        """Process requests before they reach route handlers"""
        # Record request start time
        g.start_time = time.time()
        
        # Generate request ID for tracking
        g.request_id = request.headers.get('X-Request-ID', 'unknown')
        
        # Log incoming request
        logger.info(
            f"[{g.request_id}] {request.method} {request.path} "
            f"from {request.remote_addr}"
        )
        
        # Validate content type for POST requests
        if request.method == 'POST' and request.path != '/health':
            if not request.is_json and not request.content_type:
                logger.warning(f"[{g.request_id}] Missing or invalid content type")
                error_response = ErrorResponse(
                    error="Invalid content type", 
                    details="Content-Type must be application/json"
                )
                return jsonify(error_response.dict()), 400
        
        # Check content length
        if request.content_length and request.content_length > settings.max_content_length:
            logger.warning(f"[{g.request_id}] Content too large: {request.content_length} bytes")
            error_response = ErrorResponse(
                error="Content too large",
                details=f"Maximum size: {settings.max_content_length} bytes"
            )
            return jsonify(error_response.dict()), 413
    
    @app.after_request
    def after_request(response):
        """Process responses after route handlers complete"""
        # Calculate request duration
        if hasattr(g, 'start_time'):
            duration = time.time() - g.start_time
            
            # Add duration header
            response.headers['X-Response-Time'] = f"{duration:.3f}s"
            
            # Log response
            logger.info(
                f"[{getattr(g, 'request_id', 'unknown')}] "
                f"{response.status_code} {request.method} {request.path} "
                f"({duration:.3f}s)"
            )
        
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Add CORS headers if needed
        if settings.is_development:
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Request-ID'
        
        return response
    
    @app.route('/favicon.ico')
    def favicon():
        """Handle favicon requests to prevent 404 errors"""
        return '', 204
    
    logger.info("Request middleware registered successfully")


def validate_json_request() -> dict:
    """
    Validate and parse JSON request data
    
    Returns:
        Parsed JSON data
        
    Raises:
        BadRequest: If JSON is invalid
    """
    try:
        if not request.is_json:
            raise BadRequest("Request must be JSON")
        
        data = request.get_json(force=True)
        if data is None:
            raise BadRequest("Invalid JSON data")
        
        return data
        
    except Exception as e:
        logger.warning(f"JSON validation failed: {e}")
        raise BadRequest(f"Invalid JSON: {e}")


def get_request_id() -> str:
    """
    Get current request ID from Flask context
    
    Returns:
        Request ID string
    """
    return getattr(g, 'request_id', 'unknown')


def get_request_duration() -> float:
    """
    Get current request duration
    
    Returns:
        Duration in seconds
    """
    if hasattr(g, 'start_time'):
        return time.time() - g.start_time
    return 0.0