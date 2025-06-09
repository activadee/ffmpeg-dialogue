"""
API Response models
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class AudioAnalysisResult(BaseModel):
    """Result of audio duration analysis"""
    scene_index: int
    url: str
    duration: float = Field(ge=0)


class VideoGenerationResponse(BaseModel):
    """Response for video generation request"""
    success: bool
    video_id: str
    download_url: str
    audio_analysis: List[AudioAnalysisResult]
    total_duration: float = Field(ge=0)
    ffmpeg_command: str
    output_size_mb: float = Field(ge=0)
    subtitle_enabled: bool = Field(default=False)
    transcription_count: int = Field(default=0, ge=0)


class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str
    details: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: Optional[str] = None


class VideoStatusResponse(BaseModel):
    """Video status check response"""
    exists: bool
    size_mb: Optional[float] = None
    created: Optional[datetime] = None
    download_url: Optional[str] = None


class SceneTiming(BaseModel):
    """Scene timing information"""
    scene_index: int
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    duration: float = Field(ge=0)
    
    @property
    def formatted_start_time(self) -> str:
        """Format start time as HH:MM:SS.SS"""
        hours = int(self.start_time // 3600)
        minutes = int((self.start_time % 3600) // 60)
        seconds = self.start_time % 60
        return f"{hours}:{minutes:02d}:{seconds:05.2f}"
    
    @property
    def formatted_end_time(self) -> str:
        """Format end time as HH:MM:SS.SS"""
        hours = int(self.end_time // 3600)
        minutes = int((self.end_time % 3600) // 60)
        seconds = self.end_time % 60
        return f"{hours}:{minutes:02d}:{seconds:05.2f}"


class TranscriptionResult(BaseModel):
    """Result of audio transcription"""
    scene_index: int
    transcription: Optional[str] = None
    success: bool
    error: Optional[str] = None
    word_timestamps: Optional[List[Any]] = None  # Word-level timing data for progressive subtitles