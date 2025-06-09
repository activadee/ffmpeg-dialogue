"""
Application configuration management
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # Server Configuration
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=3002, env="PORT")
    debug: bool = Field(default=False, env="DEBUG")
    
    # File Management
    output_dir: str = Field(default="./generated_videos", env="OUTPUT_DIR")
    cleanup_interval: int = Field(default=3600, env="CLEANUP_INTERVAL")  # seconds
    max_file_age: int = Field(default=3600, env="MAX_FILE_AGE")  # seconds
    
    # Audio Processing
    audio_analysis_workers: int = Field(default=10, env="AUDIO_ANALYSIS_WORKERS")
    audio_analysis_timeout: int = Field(default=30, env="AUDIO_ANALYSIS_TIMEOUT")
    
    # Transcription Settings
    transcription_workers: int = Field(default=5, env="TRANSCRIPTION_WORKERS")
    transcription_timeout: int = Field(default=300, env="TRANSCRIPTION_TIMEOUT")  # 5 minutes
    enable_subtitles: bool = Field(default=True, env="ENABLE_SUBTITLES")
    
    # Python Whisper Settings
    whisper_python_model: str = Field(default="medium", env="WHISPER_PYTHON_MODEL")
    whisper_device: str = Field(default="cpu", env="WHISPER_DEVICE")  # "auto" | "cpu" | "cuda" | "mps"
    whisper_cache_dir: str = Field(default="./whisper_cache", env="WHISPER_CACHE_DIR")
    
    # FFmpeg Settings
    ffmpeg_timeout: int = Field(default=600, env="FFMPEG_TIMEOUT")  # 10 minutes
    video_quality_crf: int = Field(default=23, env="VIDEO_QUALITY_CRF")
    video_preset: str = Field(default="fast", env="VIDEO_PRESET")
    
    # URL Processing
    url_redirect_timeout: int = Field(default=10, env="URL_REDIRECT_TIMEOUT")
    download_timeout: int = Field(default=60, env="DOWNLOAD_TIMEOUT")
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        env="LOG_FORMAT"
    )
    
    # Security
    max_content_length: int = Field(default=16 * 1024 * 1024, env="MAX_CONTENT_LENGTH")  # 16MB
    rate_limit_per_minute: int = Field(default=60, env="RATE_LIMIT_PER_MINUTE")
    
    # Health Check
    health_check_timeout: int = Field(default=5, env="HEALTH_CHECK_TIMEOUT")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    def ensure_output_dir(self) -> None:
        """Ensure output directory exists"""
        os.makedirs(self.output_dir, exist_ok=True)
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.debug
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return not self.debug


# Global settings instance
settings = Settings()