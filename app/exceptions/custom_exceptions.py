"""
Custom exception classes for the video generator service
"""
from typing import Optional, Dict, Any


class VideoGeneratorException(Exception):
    """Base exception for all video generator errors"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class ConfigurationError(VideoGeneratorException):
    """Raised when there's an error in video configuration"""
    pass


class AudioProcessingError(VideoGeneratorException):
    """Raised when audio processing fails"""
    pass


class TranscriptionError(VideoGeneratorException):
    """Raised when audio transcription fails"""
    pass


class SubtitleGenerationError(VideoGeneratorException):
    """Raised when subtitle generation fails"""
    pass


class FFmpegError(VideoGeneratorException):
    """Raised when FFmpeg command execution fails"""
    
    def __init__(self, message: str, command: Optional[str] = None, stderr: Optional[str] = None):
        self.command = command
        self.stderr = stderr
        details = {}
        if command:
            details['command'] = command
        if stderr:
            details['stderr'] = stderr
        super().__init__(message, details)


class FileOperationError(VideoGeneratorException):
    """Raised when file operations fail"""
    pass


class URLProcessingError(VideoGeneratorException):
    """Raised when URL processing fails"""
    pass


class ValidationError(VideoGeneratorException):
    """Raised when input validation fails"""
    pass


class TimeoutError(VideoGeneratorException):
    """Raised when operations timeout"""
    pass


class ServiceUnavailableError(VideoGeneratorException):
    """Raised when external services are unavailable"""
    pass