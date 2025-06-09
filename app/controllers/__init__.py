"""
Controller layer initialization
"""
from .video_controller import video_bp
from .health_controller import health_bp

__all__ = [
    'video_bp',
    'health_bp'
]