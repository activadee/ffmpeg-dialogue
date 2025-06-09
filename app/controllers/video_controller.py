"""
Video generation REST API controller
"""
import uuid
import os
import tempfile
from typing import Dict, Any, List
from flask import Blueprint, request, jsonify, send_file
from pydantic import ValidationError
from ..models.video_config import VideoConfig
from ..models.response_models import (
    VideoGenerationResponse, 
    ErrorResponse, 
    VideoStatusResponse,
    AudioAnalysisResult
)
from ..services import (
    AudioService, 
    TranscriptionService, 
    SubtitleService, 
    FFmpegService, 
    FileService
)
from ..config.logging_config import get_logger
from ..config.settings import settings
from ..exceptions.custom_exceptions import (
    VideoGeneratorException,
    ValidationError as CustomValidationError,
    ConfigurationError
)

logger = get_logger(__name__)

# Create blueprint
video_bp = Blueprint('video', __name__)

# Initialize services
audio_service = AudioService()
transcription_service = TranscriptionService()
subtitle_service = SubtitleService()
ffmpeg_service = FFmpegService()
file_service = FileService()


@video_bp.route('/generate-video', methods=['POST'])
def generate_video():
    """
    Generate video from JSON configuration
    
    Returns:
        JSON response with video generation results
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] Video generation request received")
    
    try:
        # Parse and validate input
        config = _parse_video_config(request.get_json(force=True))
        logger.info(f"[{request_id}] Configuration validated successfully")
        
        # Analyze audio durations
        logger.info(f"[{request_id}] Starting audio analysis...")
        audio_info, total_duration = audio_service.analyze_audio_durations(config)
        
        if not audio_info:
            raise ConfigurationError("No audio files found in configuration")
        
        logger.info(f"[{request_id}] Audio analysis complete: {len(audio_info)} files, {total_duration:.1f}s total")
        
        # Generate unique video ID and paths
        video_id = str(uuid.uuid4())
        output_filename = f"{video_id}.mp4"
        output_path = os.path.join(settings.output_dir, output_filename)
        
        # Create temporary directory for processing
        temp_dir = tempfile.mkdtemp()
        temp_files = [temp_dir]
        
        try:
            # Calculate scene timings
            scene_timings = audio_service.calculate_scene_timings(audio_info)
            
            # Generate subtitles if enabled
            subtitle_file_path = None
            transcription_count = 0
            
            if settings.enable_subtitles and config.get_subtitle_element():
                logger.info(f"[{request_id}] Starting transcription...")
                
                # Convert audio_info to dict format for transcription service
                audio_info_dict = [
                    {
                        'scene_index': info.scene_index,
                        'url': info.url,
                        'duration': info.duration
                    }
                    for info in audio_info
                ]
                
                transcriptions = transcription_service.transcribe_scene_audios(
                    config, audio_info_dict, scene_timings, temp_dir
                )
                
                if transcriptions:
                    subtitle_config = config.get_subtitle_element().settings
                    subtitle_file_path = subtitle_service.create_ass_subtitle_file(
                        transcriptions, scene_timings, subtitle_config, temp_dir
                    )
                    
                    if subtitle_file_path:
                        temp_files.append(subtitle_file_path)
                        transcription_count = sum(1 for t in transcriptions if t.success)
                        logger.info(f"[{request_id}] Subtitles generated: {transcription_count} scenes transcribed")
            
            # Generate FFmpeg command
            logger.info(f"[{request_id}] Generating FFmpeg command...")
            ffmpeg_cmd = ffmpeg_service.generate_ffmpeg_command(
                config, audio_info, output_path, subtitle_file_path
            )
            
            # Execute FFmpeg
            logger.info(f"[{request_id}] Executing FFmpeg...")
            ffmpeg_service.execute_ffmpeg_command(ffmpeg_cmd)
            
            # Get output file size
            output_size_mb = file_service.get_video_file_info(video_id)['size_mb'] if os.path.exists(output_path) else 0
            
            logger.info(f"[{request_id}] Video generated successfully: {output_filename} ({output_size_mb}MB)")
            
            # Build response
            response = VideoGenerationResponse(
                success=True,
                video_id=video_id,
                download_url=f'/download/{video_id}',
                audio_analysis=audio_info,
                total_duration=total_duration + 2,  # Include buffer
                ffmpeg_command=' '.join(ffmpeg_cmd),
                output_size_mb=output_size_mb,
                subtitle_enabled=subtitle_file_path is not None,
                transcription_count=transcription_count
            )
            
            return jsonify(response.dict()), 200
            
        finally:
            # Clean up temporary files
            file_service.cleanup_temp_files(temp_files)
    
    except ValidationError as e:
        logger.warning(f"[{request_id}] Validation error: {e}")
        error_response = ErrorResponse(
            error="Invalid configuration",
            details=str(e),
            request_id=request_id
        )
        return jsonify(error_response.dict()), 400
    
    except VideoGeneratorException as e:
        logger.error(f"[{request_id}] Video generation error: {e}")
        error_response = ErrorResponse(
            error=e.message,
            details=str(e.details) if e.details else None,
            request_id=request_id
        )
        return jsonify(error_response.dict()), 500
    
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error: {e}", exc_info=True)
        error_response = ErrorResponse(
            error="Internal server error",
            details=str(e) if settings.is_development else None,
            request_id=request_id
        )
        return jsonify(error_response.dict()), 500


@video_bp.route('/download/<video_id>', methods=['GET'])
def download_video(video_id: str):
    """
    Download generated video file
    
    Args:
        video_id: Video ID
        
    Returns:
        Video file or error response
    """
    try:
        logger.info(f"Download request for video: {video_id}")
        
        # Validate video ID format
        if not _is_valid_uuid(video_id):
            error_response = ErrorResponse(error="Invalid video ID format")
            return jsonify(error_response.dict()), 400
        
        # Get file info
        file_info = file_service.get_video_file_info(video_id)
        if not file_info or not file_info['exists']:
            error_response = ErrorResponse(error="Video not found")
            return jsonify(error_response.dict()), 404
        
        # Send file
        return send_file(
            file_info['path'],
            as_attachment=True,
            download_name=f"generated_video_{video_id}.mp4",
            mimetype='video/mp4'
        )
        
    except Exception as e:
        logger.error(f"Error downloading video {video_id}: {e}")
        error_response = ErrorResponse(error="Download failed")
        return jsonify(error_response.dict()), 500


@video_bp.route('/status/<video_id>', methods=['GET'])
def video_status(video_id: str):
    """
    Check video generation status and file information
    
    Args:
        video_id: Video ID
        
    Returns:
        JSON response with video status
    """
    try:
        logger.debug(f"Status check for video: {video_id}")
        
        # Validate video ID format
        if not _is_valid_uuid(video_id):
            error_response = ErrorResponse(error="Invalid video ID format")
            return jsonify(error_response.dict()), 400
        
        # Get file info
        file_info = file_service.get_video_file_info(video_id)
        
        if file_info and file_info['exists']:
            from datetime import datetime
            response = VideoStatusResponse(
                exists=True,
                size_mb=file_info['size_mb'],
                created=datetime.fromtimestamp(file_info['created_timestamp']),
                download_url=f'/download/{video_id}'
            )
        else:
            response = VideoStatusResponse(exists=False)
        
        return jsonify(response.dict()), 200
        
    except Exception as e:
        logger.error(f"Error checking status for video {video_id}: {e}")
        error_response = ErrorResponse(error="Status check failed")
        return jsonify(error_response.dict()), 500


@video_bp.route('/videos', methods=['GET'])
def list_videos():
    """
    List all generated videos
    
    Returns:
        JSON response with list of videos
    """
    try:
        # Get query parameters
        limit = min(int(request.args.get('limit', 50)), 100)  # Max 100
        
        logger.debug(f"Listing videos (limit: {limit})")
        
        # Get video list
        videos = file_service.list_video_files(limit)
        
        # Get disk usage
        disk_usage = file_service.get_disk_usage()
        
        response = {
            'videos': videos,
            'total_count': len(videos),
            'disk_usage': disk_usage
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Error listing videos: {e}")
        error_response = ErrorResponse(error="Failed to list videos")
        return jsonify(error_response.dict()), 500


@video_bp.route('/videos/<video_id>', methods=['DELETE'])
def delete_video(video_id: str):
    """
    Delete a generated video
    
    Args:
        video_id: Video ID
        
    Returns:
        JSON response with deletion status
    """
    try:
        logger.info(f"Delete request for video: {video_id}")
        
        # Validate video ID format
        if not _is_valid_uuid(video_id):
            error_response = ErrorResponse(error="Invalid video ID format")
            return jsonify(error_response.dict()), 400
        
        # Delete video
        success = file_service.delete_video_file(video_id)
        
        if success:
            response = {'success': True, 'message': 'Video deleted successfully'}
            return jsonify(response), 200
        else:
            error_response = ErrorResponse(error="Video not found or already deleted")
            return jsonify(error_response.dict()), 404
        
    except Exception as e:
        logger.error(f"Error deleting video {video_id}: {e}")
        error_response = ErrorResponse(error="Deletion failed")
        return jsonify(error_response.dict()), 500


def _parse_video_config(data: Any) -> VideoConfig:
    """
    Parse and validate video configuration from request data
    
    Args:
        data: Raw request data
        
    Returns:
        Validated VideoConfig object
        
    Raises:
        ValidationError: If validation fails
    """
    try:
        # Handle array input (take first config)
        if isinstance(data, list):
            if not data:
                raise ValidationError("Empty configuration array")
            config_data = data[0]
        else:
            config_data = data
        
        if not isinstance(config_data, dict):
            raise ValidationError("Configuration must be a JSON object")
        
        # Validate with Pydantic
        return VideoConfig(**config_data)
        
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(f"Invalid configuration format: {e}")


def _is_valid_uuid(value: str) -> bool:
    """
    Check if string is a valid UUID format
    
    Args:
        value: String to check
        
    Returns:
        True if valid UUID format
    """
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError):
        return False