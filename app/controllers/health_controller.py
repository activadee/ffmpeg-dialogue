"""
Health check and system status controller
"""
from flask import Blueprint, jsonify
from ..models.response_models import HealthResponse, ErrorResponse
from ..config.logging_config import get_logger
from ..config.settings import settings
from ..services import (
    AudioService, 
    TranscriptionService, 
    FFmpegService, 
    FileService
)

logger = get_logger(__name__)

# Create blueprint
health_bp = Blueprint('health', __name__)

# Initialize services for health checks
audio_service = AudioService()
transcription_service = TranscriptionService()
ffmpeg_service = FFmpegService()
file_service = FileService()


@health_bp.route('/health', methods=['GET'])
def health_check():
    """
    Basic health check endpoint
    
    Returns:
        JSON response with service health status
    """
    try:
        response = HealthResponse(
            status='ok',
            service='video-generator',
            version='1.0.0'
        )
        return jsonify(response.dict()), 200
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        error_response = ErrorResponse(error="Health check failed")
        return jsonify(error_response.dict()), 500


@health_bp.route('/health/detailed', methods=['GET'])
def detailed_health_check():
    """
    Detailed health check with service validation
    
    Returns:
        JSON response with detailed system status
    """
    try:
        logger.debug("Performing detailed health check...")
        
        # Check all services
        health_status = {
            'service': 'video-generator',
            'status': 'ok',
            'version': '1.0.0',
            'timestamp': health_bp.json.encode_datetime(HealthResponse().timestamp),
            'checks': {}
        }
        
        # File system check
        file_errors = file_service.validate_file_permissions()
        health_status['checks']['filesystem'] = {
            'status': 'ok' if not file_errors else 'error',
            'errors': file_errors,
            'output_directory': settings.output_dir
        }
        
        # FFmpeg availability check
        ffmpeg_available = ffmpeg_service.validate_ffmpeg_availability()
        ffmpeg_version = ffmpeg_service.get_ffmpeg_version()
        health_status['checks']['ffmpeg'] = {
            'status': 'ok' if ffmpeg_available else 'error',
            'available': ffmpeg_available,
            'version': ffmpeg_version
        }
        
        # Transcription service check
        transcription_errors = transcription_service.validate_transcription_setup()
        whisper_info = transcription_service.whisper_service.get_info()
        health_status['checks']['transcription'] = {
            'status': 'ok' if not transcription_errors else 'warning',
            'errors': transcription_errors,
            'enabled': settings.enable_subtitles,
            'backend': 'python',
            'whisper_info': whisper_info
        }
        
        # Disk usage check
        disk_usage = file_service.get_disk_usage()
        health_status['checks']['storage'] = {
            'status': 'ok',
            'usage': disk_usage
        }
        
        # Configuration check
        config_issues = _validate_configuration()
        health_status['checks']['configuration'] = {
            'status': 'ok' if not config_issues else 'warning',
            'issues': config_issues,
            'environment': 'development' if settings.is_development else 'production'
        }
        
        # Determine overall status
        has_errors = any(
            check.get('status') == 'error' 
            for check in health_status['checks'].values()
        )
        has_warnings = any(
            check.get('status') == 'warning' 
            for check in health_status['checks'].values()
        )
        
        if has_errors:
            health_status['status'] = 'error'
            status_code = 503  # Service Unavailable
        elif has_warnings:
            health_status['status'] = 'warning' 
            status_code = 200  # OK but with warnings
        else:
            health_status['status'] = 'ok'
            status_code = 200
        
        return jsonify(health_status), status_code
        
    except Exception as e:
        logger.error(f"Detailed health check failed: {e}")
        error_response = ErrorResponse(error="Detailed health check failed")
        return jsonify(error_response.dict()), 500


@health_bp.route('/metrics', methods=['GET'])
def metrics():
    """
    System metrics endpoint
    
    Returns:
        JSON response with system metrics
    """
    try:
        logger.debug("Collecting system metrics...")
        
        # Get disk usage
        disk_usage = file_service.get_disk_usage()
        
        # Get video list for metrics
        videos = file_service.list_video_files(limit=1000)
        
        # Calculate metrics
        metrics_data = {
            'videos': {
                'total_count': len(videos),
                'total_size_mb': disk_usage['total_size_mb'],
                'total_size_gb': disk_usage['total_size_gb']
            },
            'storage': disk_usage,
            'configuration': {
                'audio_workers': settings.audio_analysis_workers,
                'transcription_workers': settings.transcription_workers,
                'subtitles_enabled': settings.enable_subtitles,
                'output_directory': settings.output_dir,
                'cleanup_interval': settings.cleanup_interval
            },
            'system': {
                'ffmpeg_available': ffmpeg_service.validate_ffmpeg_availability(),
                'ffmpeg_version': ffmpeg_service.get_ffmpeg_version(),
                'supported_audio_formats': transcription_service.get_supported_audio_formats()
            }
        }
        
        return jsonify(metrics_data), 200
        
    except Exception as e:
        logger.error(f"Metrics collection failed: {e}")
        error_response = ErrorResponse(error="Metrics collection failed")
        return jsonify(error_response.dict()), 500


@health_bp.route('/ready', methods=['GET'])
def readiness_check():
    """
    Kubernetes-style readiness check
    
    Returns:
        200 if service is ready to accept requests, 503 otherwise
    """
    try:
        # Check critical dependencies
        critical_checks = []
        
        # File system must be writable
        file_errors = file_service.validate_file_permissions()
        if file_errors:
            critical_checks.extend(file_errors)
        
        # FFmpeg must be available
        if not ffmpeg_service.validate_ffmpeg_availability():
            critical_checks.append("FFmpeg not available")
        
        if critical_checks:
            logger.warning(f"Readiness check failed: {critical_checks}")
            return jsonify({
                'status': 'not_ready',
                'issues': critical_checks
            }), 503
        
        return jsonify({'status': 'ready'}), 200
        
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 503


@health_bp.route('/live', methods=['GET'])
def liveness_check():
    """
    Kubernetes-style liveness check
    
    Returns:
        200 if service is alive, 503 if it should be restarted
    """
    try:
        # Basic liveness - service can respond
        return jsonify({'status': 'alive'}), 200
        
    except Exception as e:
        logger.error(f"Liveness check failed: {e}")
        return jsonify({'status': 'dead', 'error': str(e)}), 503


def _validate_configuration() -> list:
    """
    Validate configuration settings
    
    Returns:
        List of configuration issues
    """
    issues = []
    
    # Check required settings
    if settings.audio_analysis_workers < 1:
        issues.append("Invalid audio analysis worker count")
    
    if settings.transcription_workers < 1:
        issues.append("Invalid transcription worker count")
    
    if settings.ffmpeg_timeout < 60:
        issues.append("FFmpeg timeout too low (minimum 60 seconds)")
    
    if not settings.output_dir:
        issues.append("Output directory not configured")
    
    # Check Whisper availability
    if settings.enable_subtitles:
        try:
            from ..services.whisper_python_service import WhisperPythonService
            whisper_service = WhisperPythonService()
            if not whisper_service.is_available():
                issues.append("Python Whisper not available but subtitles enabled")
        except ImportError:
            issues.append("Python Whisper dependencies not installed")
    
    # Check disk space (warning if less than 1GB free)
    import shutil
    try:
        free_space = shutil.disk_usage(settings.output_dir).free
        free_gb = free_space / (1024**3)
        if free_gb < 1:
            issues.append(f"Low disk space: {free_gb:.1f}GB free")
    except Exception:
        issues.append("Cannot check disk space")
    
    return issues