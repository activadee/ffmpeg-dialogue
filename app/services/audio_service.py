"""
Audio processing service for duration analysis and validation
"""
import subprocess
import json
import concurrent.futures
import threading
from typing import List, Tuple, Dict, Any
from ..models.video_config import VideoConfig, Scene, AudioElement
from ..models.response_models import AudioAnalysisResult, SceneTiming
from ..config.logging_config import get_logger
from ..config.settings import settings
from ..utils.url_utils import process_gdrive_url
from ..exceptions.custom_exceptions import AudioProcessingError, TimeoutError

logger = get_logger(__name__)


class AudioService:
    """Service for audio processing and analysis"""
    
    def __init__(self):
        self.progress_lock = threading.Lock()
        self.completed_count = 0
        self.total_count = 0
    
    def get_audio_duration(self, url: str) -> float:
        """
        Get audio duration using ffprobe with Google Drive redirect handling
        
        Args:
            url: Audio file URL
            
        Returns:
            Duration in seconds
            
        Raises:
            AudioProcessingError: If duration analysis fails
        """
        try:
            # For Google Drive URLs, get the final redirect URL first
            if 'drive.google.com' in url:
                logger.debug(f"Google Drive URL detected, following redirects...")
                redirect_cmd = f'curl -L -s "{url}" -w "%{{url_effective}}" -o /dev/null'
                redirect_result = subprocess.run(
                    redirect_cmd, 
                    shell=True, 
                    capture_output=True, 
                    text=True, 
                    timeout=settings.audio_analysis_timeout
                )
                
                if redirect_result.returncode == 0 and redirect_result.stdout.strip():
                    final_url = redirect_result.stdout.strip()
                    logger.debug(f"Final URL after redirects: {final_url}")
                    
                    # Try ffprobe with the final URL
                    cmd = f'ffprobe -v quiet -print_format json -show_format "{final_url}"'
                    result = subprocess.run(
                        cmd, 
                        shell=True, 
                        capture_output=True, 
                        text=True, 
                        timeout=settings.audio_analysis_timeout
                    )
                    
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        if 'format' in data and 'duration' in data['format']:
                            duration = float(data['format']['duration'])
                            logger.debug(f"Got duration: {duration}s")
                            return duration
            else:
                # For non-Google Drive URLs, try direct ffprobe
                cmd = f'ffprobe -v quiet -print_format json -show_format "{url}"'
                result = subprocess.run(
                    cmd, 
                    shell=True, 
                    capture_output=True, 
                    text=True, 
                    timeout=settings.audio_analysis_timeout
                )
                
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    if 'format' in data and 'duration' in data['format']:
                        duration = float(data['format']['duration'])
                        logger.debug(f"Got duration: {duration}s")
                        return duration
            
            logger.warning(f"Could not get duration for {url}, using default")
            return 10.0
            
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout getting duration for {url}")
            raise TimeoutError(f"Audio duration analysis timed out for {url}")
        except Exception as e:
            logger.error(f"Exception in get_audio_duration: {e}")
            raise AudioProcessingError(f"Failed to get audio duration: {e}")
    
    def analyze_audio_durations(self, config: VideoConfig) -> Tuple[List[AudioAnalysisResult], float]:
        """
        Analyze all audio files concurrently and return their durations
        
        Args:
            config: Video configuration
            
        Returns:
            Tuple of (audio analysis results, total duration)
            
        Raises:
            AudioProcessingError: If audio analysis fails
        """
        try:
            # Collect all audio URLs first
            audio_tasks = []
            
            for i, scene in enumerate(config.scenes):
                for element in scene.elements:
                    if isinstance(element, AudioElement):
                        audio_url = process_gdrive_url(element.src)
                        if audio_url and audio_url.strip():
                            audio_tasks.append({
                                'scene_index': i,
                                'url': audio_url
                            })
            
            if not audio_tasks:
                logger.warning("No audio files found in configuration")
                return [], 0
            
            logger.info(f"Analyzing {len(audio_tasks)} audio files concurrently...")
            
            # Reset progress tracking
            with self.progress_lock:
                self.completed_count = 0
                self.total_count = len(audio_tasks)
            
            # Process audio durations concurrently
            audio_results = []
            total_duration = 0
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=settings.audio_analysis_workers) as executor:
                # Submit all tasks
                future_to_task = {
                    executor.submit(self._get_duration_with_info, task): task 
                    for task in audio_tasks
                }
                
                # Collect results as they complete
                for future in concurrent.futures.as_completed(future_to_task):
                    try:
                        result = future.result(timeout=60)  # 60 second timeout per audio
                        audio_results.append(result)
                        total_duration += result.duration
                        
                        with self.progress_lock:
                            self.completed_count += 1
                            logger.info(f"✓ Audio {self.completed_count}/{self.total_count}: {result.duration}s")
                            
                    except Exception as e:
                        task = future_to_task[future]
                        logger.error(f"✗ Failed to analyze {task['url']}: {e}")
                        # Add with default duration
                        result = AudioAnalysisResult(
                            scene_index=task['scene_index'],
                            url=task['url'],
                            duration=10.0
                        )
                        audio_results.append(result)
                        total_duration += 10.0
            
            # Sort by scene_index to maintain order
            audio_results.sort(key=lambda x: x.scene_index)
            
            logger.info(f"Audio analysis complete: {len(audio_results)} files, total {total_duration}s")
            return audio_results, total_duration
            
        except Exception as e:
            logger.error(f"Failed to analyze audio durations: {e}")
            raise AudioProcessingError(f"Audio duration analysis failed: {e}")
    
    def _get_duration_with_info(self, task: Dict[str, Any]) -> AudioAnalysisResult:
        """
        Get duration with task information (for concurrent processing)
        
        Args:
            task: Task dictionary with scene_index and url
            
        Returns:
            AudioAnalysisResult with duration information
        """
        duration = self.get_audio_duration(task['url'])
        return AudioAnalysisResult(
            scene_index=task['scene_index'],
            url=task['url'],
            duration=duration
        )
    
    def calculate_scene_timings(self, audio_results: List[AudioAnalysisResult]) -> List[SceneTiming]:
        """
        Calculate timing information for each scene based on audio durations
        
        Args:
            audio_results: List of audio analysis results
            
        Returns:
            List of scene timing information
        """
        try:
            # Group audio durations by scene
            scene_audio_durations = {}
            for result in audio_results:
                scene_idx = result.scene_index
                if scene_idx not in scene_audio_durations:
                    scene_audio_durations[scene_idx] = 0
                scene_audio_durations[scene_idx] += result.duration
            
            # Calculate start/end times for each scene
            scene_timings = []
            current_time = 0
            
            for scene_idx in sorted(scene_audio_durations.keys()):
                duration = scene_audio_durations[scene_idx]
                scene_timing = SceneTiming(
                    scene_index=scene_idx,
                    start_time=current_time,
                    end_time=current_time + duration,
                    duration=duration
                )
                scene_timings.append(scene_timing)
                current_time += duration
                
                logger.debug(f"Scene {scene_idx}: {scene_timing.formatted_start_time} - {scene_timing.formatted_end_time}")
            
            return scene_timings
            
        except Exception as e:
            logger.error(f"Failed to calculate scene timings: {e}")
            raise AudioProcessingError(f"Scene timing calculation failed: {e}")
    
    def validate_audio_urls(self, config: VideoConfig) -> List[str]:
        """
        Validate all audio URLs in configuration
        
        Args:
            config: Video configuration
            
        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []
        
        for i, scene in enumerate(config.scenes):
            for j, element in enumerate(scene.elements):
                if isinstance(element, AudioElement):
                    if not element.src or not element.src.strip():
                        errors.append(f"Scene {i}, element {j}: Empty audio URL")
                    elif len(element.src) < 10:
                        errors.append(f"Scene {i}, element {j}: Audio URL too short")
        
        return errors