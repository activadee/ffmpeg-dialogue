"""
Flask application factory and main entry point
"""
import os
from flask import Flask, jsonify
from .config.settings import settings
from .config.logging_config import setup_logging, get_logger
from .controllers import video_bp, health_bp
from .middleware import register_error_handlers, register_request_middleware

# Setup logging first
setup_logging()
logger = get_logger(__name__)


def create_app() -> Flask:
    """
    Flask application factory
    
    Returns:
        Configured Flask application instance
    """
    logger.info("Creating Flask application...")
    
    # Create Flask app
    app = Flask(__name__)
    
    # Configure app
    configure_app(app)
    
    # Register middleware
    register_middleware(app)
    
    # Register blueprints
    register_blueprints(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Add root route
    register_root_routes(app)
    
    logger.info("Flask application created successfully")
    return app


def configure_app(app: Flask) -> None:
    """
    Configure Flask application settings
    
    Args:
        app: Flask application instance
    """
    # Basic configuration
    app.config['DEBUG'] = settings.debug
    app.config['MAX_CONTENT_LENGTH'] = settings.max_content_length
    app.config['JSON_SORT_KEYS'] = False
    
    # Ensure output directory exists
    settings.ensure_output_dir()
    
    logger.info(f"App configured - Debug: {settings.debug}, Environment: {'development' if settings.is_development else 'production'}")


def register_middleware(app: Flask) -> None:
    """
    Register application middleware
    
    Args:
        app: Flask application instance
    """
    register_request_middleware(app)
    logger.info("Middleware registered")


def register_blueprints(app: Flask) -> None:
    """
    Register application blueprints (route groups)
    
    Args:
        app: Flask application instance
    """
    # Register video generation routes
    app.register_blueprint(video_bp, url_prefix='')
    
    # Register health check routes  
    app.register_blueprint(health_bp, url_prefix='')
    
    logger.info("Blueprints registered")


def register_root_routes(app: Flask) -> None:
    """
    Register root-level routes
    
    Args:
        app: Flask application instance
    """
    @app.route('/')
    def root():
        """Root endpoint with service information"""
        return jsonify({
            'service': 'video-generator',
            'version': '1.0.0',
            'status': 'running',
            'endpoints': {
                'video_generation': '/generate-video',
                'video_download': '/download/<video_id>',
                'video_status': '/status/<video_id>',
                'video_list': '/videos',
                'video_delete': '/videos/<video_id>',
                'health_check': '/health',
                'detailed_health': '/health/detailed',
                'metrics': '/metrics',
                'readiness': '/ready',
                'liveness': '/live'
            },
            'documentation': 'https://github.com/your-repo/video-generator'
        })
    
    @app.route('/ping')
    def ping():
        """Simple ping endpoint"""
        return jsonify({'status': 'pong'})


def main():
    """
    Main entry point for the application
    """
    logger.info("Starting Video Generator Server...")
    logger.info(f"Configuration: {settings.dict()}")
    
    # Create app
    app = create_app()
    
    # Validate system requirements
    validate_system_requirements()
    
    # Run application
    logger.info(f"Starting server on {settings.host}:{settings.port}")
    logger.info(f"Output directory: {os.path.abspath(settings.output_dir)}")
    logger.info("Server endpoints:")
    logger.info("  POST /generate-video  - Generate video from JSON config")
    logger.info("  GET  /download/<id>   - Download generated video")
    logger.info("  GET  /status/<id>     - Check video status")
    logger.info("  GET  /videos          - List all videos")
    logger.info("  DELETE /videos/<id>   - Delete video")
    logger.info("  GET  /health          - Health check")
    logger.info("  GET  /metrics         - System metrics")
    
    try:
        app.run(
            host=settings.host,
            port=settings.port,
            debug=settings.debug,
            threaded=True
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise


def validate_system_requirements() -> None:
    """
    Validate system requirements before starting
    
    Raises:
        SystemExit: If critical requirements are not met
    """
    from .services import FFmpegService, FileService, TranscriptionService
    
    logger.info("Validating system requirements...")
    
    # Check FFmpeg availability
    ffmpeg_service = FFmpegService()
    if not ffmpeg_service.validate_ffmpeg_availability():
        logger.error("FFmpeg not found! Please install FFmpeg to continue.")
        raise SystemExit(1)
    
    ffmpeg_version = ffmpeg_service.get_ffmpeg_version()
    logger.info(f"✓ FFmpeg available: {ffmpeg_version}")
    
    # Check Whisper.cpp availability (CRITICAL)
    try:
        transcription_service = TranscriptionService()
        logger.info("✓ Local Whisper.cpp is available and ready")
    except Exception as e:
        logger.error(f"✗ Local Whisper.cpp validation failed: {e}")
        logger.error("Please run 'setup_whisper_cpp.sh' to install Whisper.cpp")
        raise SystemExit(1)
    
    # Check file system permissions
    file_service = FileService()
    file_errors = file_service.validate_file_permissions()
    if file_errors:
        logger.error(f"File system validation failed: {file_errors}")
        raise SystemExit(1)
    
    logger.info(f"✓ File system permissions validated")
    
    # Check disk space
    disk_usage = file_service.get_disk_usage()
    free_space_gb = disk_usage.get('total_size_gb', 0)
    logger.info(f"✓ Output directory ready: {settings.output_dir}")
    
    logger.info("✓ All system requirements validated")


if __name__ == '__main__':
    main()