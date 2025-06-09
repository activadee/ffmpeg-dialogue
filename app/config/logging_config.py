"""
Logging configuration
"""
import logging
import sys
from typing import Dict, Any
from .settings import settings


class ColoredFormatter(logging.Formatter):
    """Colored log formatter for development"""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record):
        if settings.is_development:
            color = self.COLORS.get(record.levelname, self.RESET)
            record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logging() -> None:
    """Configure application logging"""
    
    # Root logger configuration
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format=settings.log_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Get root logger
    root_logger = logging.getLogger()
    
    # Use colored formatter in development
    if settings.is_development:
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setFormatter(ColoredFormatter(settings.log_format))
    
    # Set specific logger levels
    logging.getLogger('werkzeug').setLevel(logging.WARNING)  # Reduce Flask noise
    logging.getLogger('urllib3').setLevel(logging.WARNING)   # Reduce HTTP noise
    
    # Application loggers
    setup_app_loggers()


def setup_app_loggers() -> None:
    """Set up application-specific loggers"""
    
    # Service loggers
    logging.getLogger('app.services.audio').setLevel(logging.INFO)
    logging.getLogger('app.services.transcription').setLevel(logging.INFO)
    logging.getLogger('app.services.ffmpeg').setLevel(logging.INFO)
    logging.getLogger('app.services.subtitle').setLevel(logging.INFO)
    logging.getLogger('app.services.file').setLevel(logging.INFO)
    
    # Controller loggers
    logging.getLogger('app.controllers').setLevel(logging.INFO)
    
    # Utility loggers
    logging.getLogger('app.utils').setLevel(logging.DEBUG if settings.is_development else logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger instance"""
    return logging.getLogger(name)