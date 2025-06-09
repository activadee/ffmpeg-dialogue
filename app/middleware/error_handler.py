"""
Global error handling middleware
"""
import traceback
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException
from pydantic import ValidationError
from ..models.response_models import ErrorResponse
from ..config.logging_config import get_logger
from ..config.settings import settings
from ..exceptions.custom_exceptions import VideoGeneratorException

logger = get_logger(__name__)


def register_error_handlers(app: Flask) -> None:
    """
    Register global error handlers with Flask app
    
    Args:
        app: Flask application instance
    """
    
    @app.errorhandler(ValidationError)
    def handle_validation_error(error: ValidationError):
        """Handle Pydantic validation errors"""
        logger.warning(f"Validation error: {error}")
        
        # Extract field errors
        field_errors = []
        for err in error.errors():
            field = '.'.join(str(x) for x in err['loc'])
            message = err['msg']
            field_errors.append(f"{field}: {message}")
        
        error_response = ErrorResponse(
            error="Validation failed",
            details="; ".join(field_errors)
        )
        return jsonify(error_response.dict()), 400
    
    @app.errorhandler(VideoGeneratorException)
    def handle_video_generator_error(error: VideoGeneratorException):
        """Handle custom video generator exceptions"""
        logger.error(f"Video generator error: {error.message}")
        
        error_response = ErrorResponse(
            error=error.message,
            details=str(error.details) if error.details else None
        )
        return jsonify(error_response.dict()), 500
    
    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        """Handle HTTP exceptions (404, 405, etc.)"""
        logger.warning(f"HTTP error {error.code}: {error.description}")
        
        error_response = ErrorResponse(
            error=error.name,
            details=error.description
        )
        return jsonify(error_response.dict()), error.code
    
    @app.errorhandler(413)
    def handle_payload_too_large(error):
        """Handle payload too large errors"""
        logger.warning(f"Payload too large: {request.content_length} bytes")
        
        error_response = ErrorResponse(
            error="Payload too large",
            details=f"Maximum allowed size: {settings.max_content_length} bytes"
        )
        return jsonify(error_response.dict()), 413
    
    @app.errorhandler(500)
    def handle_internal_error(error):
        """Handle internal server errors"""
        logger.error(f"Internal server error: {error}", exc_info=True)
        
        # Include stack trace in development
        details = None
        if settings.is_development:
            details = traceback.format_exc()
        
        error_response = ErrorResponse(
            error="Internal server error",
            details=details
        )
        return jsonify(error_response.dict()), 500
    
    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        """Handle unexpected exceptions"""
        logger.error(f"Unexpected error: {error}", exc_info=True)
        
        # Include error details in development
        details = str(error) if settings.is_development else "An unexpected error occurred"
        
        error_response = ErrorResponse(
            error="Unexpected error",
            details=details
        )
        return jsonify(error_response.dict()), 500
    
    logger.info("Error handlers registered successfully")