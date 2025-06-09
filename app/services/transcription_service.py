"""
Audio transcription service using local Whisper.cpp
"""
import os
import concurrent.futures
import threading
from typing import List, Optional, Dict, Any
from ..models.video_config import VideoConfig
from ..models.response_models import SceneTiming, TranscriptionResult
from ..config.logging_config import get_logger
from ..config.settings import settings
from ..utils.file_utils import cleanup_files
from ..exceptions.custom_exceptions import TranscriptionError, ServiceUnavailableError
from .whisper_python_service import WhisperPythonService

logger = get_logger(__name__)


class TranscriptionService:
    """Service for audio transcription using Whisper backend"""
    
    def __init__(self):
        self.progress_lock = threading.Lock()
        self.completed_count = 0
        self.total_count = 0
        self.whisper_service = WhisperPythonService()
        
        # Validate that Whisper service is available during initialization
        if not self.whisper_service.is_available():
            error_msg = (
                "Python Whisper is not available! "
                "Please install required dependencies: pip install openai-whisper torch"
            )
            logger.error(error_msg)
            raise ServiceUnavailableError(error_msg)
    
    
    def transcribe_audio_url(self, audio_url: str) -> str:
        """
        Transcribe audio from URL using Python Whisper
        
        Args:
            audio_url: URL of audio file
            
        Returns:
            Transcription text (empty string if transcription fails)
        """
        try:
            logger.debug(f"Using Python Whisper for: {audio_url}")
            
            # Use Python Whisper to transcribe URL with word timestamps for progressive subtitles
            full_result = self.whisper_service.transcribe_url_with_words(audio_url)
            result = full_result["text"].strip() if "text" in full_result else ""
            
            logger.debug(f"Transcription result: {result}")
            return result if result else ""
            
        except Exception as e:
            logger.warning(f"Python Whisper transcription failed for {audio_url}: {e}")
            # Return empty string instead of raising - video generation continues
            return ""
    
    def transcribe_scene_audios(
        self, 
        config: VideoConfig, 
        audio_info: List[Dict[str, Any]], 
        scene_timings: List[SceneTiming], 
        temp_dir: str
    ) -> List[TranscriptionResult]:
        """
        Transcribe all scene audios concurrently
        
        Args:
            config: Video configuration
            audio_info: Audio analysis information
            scene_timings: Scene timing information
            temp_dir: Temporary directory
            
        Returns:
            List of transcription results
        """
        # Check if subtitles are enabled
        subtitle_element = config.get_subtitle_element()
        if not subtitle_element:
            logger.info("No subtitle element found in config, skipping transcription")
            return []
        
        if not settings.enable_subtitles:
            logger.info("Subtitles disabled in settings, skipping transcription")
            return []
        
        logger.info(f"Transcribing {len(scene_timings)} scenes concurrently (max {settings.transcription_workers} workers)...")
        
        # Group audio by scene for transcription
        scene_audio_map = {}
        for info in audio_info:
            scene_idx = info['scene_index']
            if scene_idx not in scene_audio_map:
                scene_audio_map[scene_idx] = []
            scene_audio_map[scene_idx].append(info['url'])
        
        # Prepare transcription tasks
        transcription_tasks = []
        for scene_timing in scene_timings:
            scene_idx = scene_timing.scene_index
            if scene_idx in scene_audio_map:
                audio_url = scene_audio_map[scene_idx][0]  # Take first audio from scene
                transcription_tasks.append({
                    'scene_index': scene_idx,
                    'audio_url': audio_url,
                    'timing': scene_timing
                })
        
        if not transcription_tasks:
            logger.warning("No audio files found for transcription")
            return []
        
        # Reset progress tracking
        with self.progress_lock:
            self.completed_count = 0
            self.total_count = len(transcription_tasks)
        
        # Process transcriptions concurrently
        transcription_results = {}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=settings.transcription_workers) as executor:
            # Submit all tasks
            future_to_task = {
                executor.submit(self._transcribe_scene_task, task): task
                for task in transcription_tasks
            }
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_task):
                try:
                    result = future.result(timeout=settings.transcription_timeout)
                    transcription_results[result.scene_index] = result
                except Exception as e:
                    task = future_to_task[future]
                    scene_idx = task['scene_index']
                    logger.error(f"Transcription task failed for scene {scene_idx}: {e}")
                    transcription_results[scene_idx] = TranscriptionResult(
                        scene_index=scene_idx,
                        transcription=None,
                        success=False,
                        error=str(e),
                        word_timestamps=None
                    )
        
        # Reconstruct results in scene order
        results = []
        for scene_timing in scene_timings:
            scene_idx = scene_timing.scene_index
            if scene_idx in transcription_results:
                results.append(transcription_results[scene_idx])
            else:
                results.append(TranscriptionResult(
                    scene_index=scene_idx,
                    transcription=None,
                    success=False,
                    error="No audio found for scene",
                    word_timestamps=None
                ))
        
        logger.info(f"Transcription complete: {len(results)} scenes processed")
        return results
    
    def _transcribe_scene_task(self, task: Dict[str, Any]) -> TranscriptionResult:
        """
        Transcribe a single scene's audio (for concurrent processing)
        
        Args:
            task: Task dictionary with scene info and audio URL
            
        Returns:
            TranscriptionResult for the scene
        """
        scene_idx = task['scene_index']
        audio_url = task['audio_url']
        
        try:
            # Get full transcription result with word timestamps
            full_result = self.whisper_service.transcribe_url_with_words(audio_url)
            transcription = full_result["text"].strip() if "text" in full_result else ""
            
            # Extract word timestamps for progressive subtitles
            word_timestamps = []
            if "segments" in full_result:
                for segment in full_result["segments"]:
                    if "words" in segment:
                        word_timestamps.extend(segment["words"])
            
            with self.progress_lock:
                self.completed_count += 1
                logger.info(f"✓ [{self.completed_count}/{self.total_count}] Scene {scene_idx} transcribed")
            
            return TranscriptionResult(
                scene_index=scene_idx,
                transcription=transcription,
                success=True,
                error=None,
                word_timestamps=word_timestamps
            )
            
        except Exception as e:
            with self.progress_lock:
                self.completed_count += 1
                logger.error(f"✗ [{self.completed_count}/{self.total_count}] Scene {scene_idx} failed: {e}")
            
            return TranscriptionResult(
                scene_index=scene_idx,
                transcription=None,
                success=False,
                error=str(e),
                word_timestamps=None
            )
    
    def validate_transcription_setup(self) -> List[str]:
        """
        Validate transcription service setup
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Check if Python Whisper is available
        if not self.whisper_service.is_available():
            errors.append("Python Whisper not available - install with: pip install openai-whisper torch")
        else:
            whisper_info = self.whisper_service.get_info()
            logger.info(f"✓ Python Whisper validated: {whisper_info['best_model']} model available")
        
        if not settings.enable_subtitles:
            logger.info("Subtitles disabled in configuration")
        
        if settings.transcription_workers < 1:
            errors.append("Invalid transcription worker count")
        
        return errors
    
    def get_supported_audio_formats(self) -> List[str]:
        """
        Get list of supported audio formats
        
        Returns:
            List of supported file extensions
        """
        return ['.mp3', '.wav', '.mp4', '.m4a', '.ogg', '.flac']