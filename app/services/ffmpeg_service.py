"""
FFmpeg command generation and execution service
"""
import subprocess
import tempfile
import shlex
from typing import List, Optional, Tuple, Dict, Any
from ..models.video_config import VideoConfig, ImageElement
from ..models.response_models import AudioAnalysisResult, SceneTiming
from ..config.logging_config import get_logger
from ..config.settings import settings
from ..utils.url_utils import process_gdrive_url
from ..exceptions.custom_exceptions import FFmpegError, ConfigurationError

logger = get_logger(__name__)


class FFmpegService:
    """Service for FFmpeg command generation and execution"""
    
    def __init__(self):
        pass
    
    def generate_ffmpeg_command(
        self, 
        config: VideoConfig, 
        audio_info: List[AudioAnalysisResult], 
        output_path: str,
        subtitle_file_path: Optional[str] = None
    ) -> List[str]:
        """
        Generate complete FFmpeg command for video creation
        
        Args:
            config: Video configuration
            audio_info: Audio analysis results
            output_path: Output video file path
            subtitle_file_path: Optional ASS subtitle file path
            
        Returns:
            Complete FFmpeg command as list of arguments
            
        Raises:
            ConfigurationError: If configuration is invalid
            FFmpegError: If command generation fails
        """
        try:
            logger.info("Generating FFmpeg command...")
            
            # Validate configuration
            self._validate_config(config, audio_info)
            
            # Get background video
            bg_video = config.get_background_video()
            if not bg_video:
                raise ConfigurationError("No background video found in configuration")
            
            bg_url = process_gdrive_url(bg_video.src)
            
            # Build command parts
            cmd_parts = ['ffmpeg', '-y']
            
            # Add protocol whitelist for HTTPS access
            cmd_parts.extend(['-protocol_whitelist', 'file,http,https,tcp,tls'])
            
            # Calculate timing and loops
            total_duration = sum(info.duration for info in audio_info) + 2  # +2 seconds buffer
            loops_needed = self._calculate_loops(bg_video.duration, total_duration)
            
            # Add background video with smart loop count
            cmd_parts.extend(['-stream_loop', str(loops_needed), '-i', bg_url])
            
            # Add audio inputs
            audio_urls = [info.url for info in audio_info]
            for audio_url in audio_urls:
                cmd_parts.extend(['-i', audio_url])
            
            # Add image inputs
            image_data = self._collect_image_data(config)
            unique_image_urls = []
            for img in image_data:
                if img['url'] not in unique_image_urls:
                    unique_image_urls.append(img['url'])
                    processed_url = process_gdrive_url(img['url'])
                    cmd_parts.extend(['-i', processed_url])
                    logger.debug(f"✓ Image URL added: {processed_url}")
            
            # Build filter complex
            filters = []
            current_video = '0:v'
            
            # Audio processing
            audio_map = self._generate_audio_filters(filters, audio_urls)
            
            # Image overlays
            if unique_image_urls:
                current_video = self._generate_image_overlays(
                    filters, image_data, unique_image_urls, audio_info, len(audio_urls)
                )
            
            # Subtitle overlay
            if subtitle_file_path:
                current_video = self._add_subtitle_filter(filters, current_video, subtitle_file_path)
            
            # Complete command
            if filters:
                cmd_parts.extend(['-filter_complex', ';'.join(filters)])
                if current_video != '0:v':
                    cmd_parts.extend(['-map', f'[{current_video}]'])
                else:
                    cmd_parts.extend(['-map', '0:v'])
            else:
                cmd_parts.extend(['-map', '0:v'])
            
            cmd_parts.extend(['-map', audio_map])
            
            # Video encoding settings
            cmd_parts.extend([
                '-c:v', 'libx264',
                '-preset', settings.video_preset,
                '-crf', str(settings.video_quality_crf)
            ])
            
            # Resolution
            cmd_parts.extend(['-s', f"{config.width}x{config.height}"])
            
            # Duration
            cmd_parts.extend(['-t', str(total_duration)])
            cmd_parts.append(output_path)
            
            logger.info(f"FFmpeg command generated successfully ({len(cmd_parts)} arguments)")
            return cmd_parts
            
        except Exception as e:
            logger.error(f"Failed to generate FFmpeg command: {e}")
            raise FFmpegError(f"Command generation failed: {e}")
    
    def execute_ffmpeg_command(self, command: List[str]) -> subprocess.CompletedProcess:
        """
        Execute FFmpeg command with proper error handling
        
        Args:
            command: FFmpeg command as list of arguments
            
        Returns:
            Completed process result
            
        Raises:
            FFmpegError: If command execution fails
        """
        try:
            # Build properly escaped command string
            cmd_str = self._build_command_string(command)
            
            logger.info(f"Executing FFmpeg command...")
            logger.debug(f"Command: {cmd_str[:200]}...")
            
            # Execute command
            result = subprocess.run(
                cmd_str, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=settings.ffmpeg_timeout
            )
            
            if result.returncode != 0:
                logger.error(f"FFmpeg execution failed: {result.stderr}")
                raise FFmpegError(
                    f"FFmpeg execution failed with code {result.returncode}",
                    command=cmd_str,
                    stderr=result.stderr
                )
            
            logger.info("FFmpeg command executed successfully")
            return result
            
        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg command timed out after {settings.ffmpeg_timeout} seconds")
            raise FFmpegError("FFmpeg execution timed out")
        except Exception as e:
            logger.error(f"Unexpected error executing FFmpeg: {e}")
            raise FFmpegError(f"FFmpeg execution error: {e}")
    
    def _validate_config(self, config: VideoConfig, audio_info: List[AudioAnalysisResult]) -> None:
        """
        Validate configuration before command generation
        
        Args:
            config: Video configuration
            audio_info: Audio analysis results
            
        Raises:
            ConfigurationError: If configuration is invalid
        """
        if not config.get_background_video():
            raise ConfigurationError("No background video specified")
        
        if not audio_info:
            raise ConfigurationError("No audio files found")
        
        if config.width <= 0 or config.height <= 0:
            raise ConfigurationError("Invalid video dimensions")
        
        if len(config.scenes) == 0:
            raise ConfigurationError("No scenes specified")
    
    def _calculate_loops(self, bg_duration: Optional[float], total_duration: float) -> int:
        """
        Calculate number of loops needed for background video
        
        Args:
            bg_duration: Background video duration
            total_duration: Total required duration
            
        Returns:
            Number of loops needed
        """
        if not bg_duration or bg_duration <= 0:
            return -1  # Infinite loop as fallback
        
        loops_needed = int(total_duration / bg_duration) + 1
        logger.debug(f"Background video: {bg_duration}s, Total: {total_duration}s, Loops: {loops_needed}")
        return loops_needed
    
    def _collect_image_data(self, config: VideoConfig) -> List[Dict[str, Any]]:
        """
        Collect image data from all scenes
        
        Args:
            config: Video configuration
            
        Returns:
            List of image data dictionaries
        """
        image_data = []
        for i, scene in enumerate(config.scenes):
            for element in scene.elements:
                if isinstance(element, ImageElement):
                    img_url = process_gdrive_url(element.src)
                    image_data.append({
                        'url': img_url,
                        'x': element.x,
                        'y': element.y,
                        'scene_index': i
                    })
        return image_data
    
    def _generate_audio_filters(self, filters: List[str], audio_urls: List[str]) -> str:
        """
        Generate audio concatenation filters
        
        Args:
            filters: List to append filters to
            audio_urls: List of audio URLs
            
        Returns:
            Audio map string for final output
        """
        if len(audio_urls) > 1:
            audio_inputs = ''.join([f'[{i+1}:a]' for i in range(len(audio_urls))])
            filters.append(f'{audio_inputs}concat=n={len(audio_urls)}:v=0:a=1[concatenated_audio]')
            filters.append(f'[concatenated_audio]apad=pad_dur=2[final_audio]')
            return '[final_audio]'
        elif len(audio_urls) == 1:
            filters.append(f'[1:a]apad=pad_dur=2[final_audio]')
            return '[final_audio]'
        else:
            return '0:a'
    
    def _generate_image_overlays(
        self, 
        filters: List[str], 
        image_data: List[Dict[str, Any]], 
        unique_image_urls: List[str], 
        audio_info: List[AudioAnalysisResult], 
        audio_input_count: int
    ) -> str:
        """
        Generate image overlay filters with timing
        
        Args:
            filters: List to append filters to
            image_data: Image data from scenes
            unique_image_urls: List of unique image URLs
            audio_info: Audio analysis results
            audio_input_count: Number of audio inputs
            
        Returns:
            Final video stream name
        """
        # Calculate scene timings
        scene_timings = self._calculate_scene_timings(audio_info)
        
        current_video = '0:v'
        overlay_count = 0
        img_input_base = audio_input_count + 1  # First image input index
        
        for i, img_data in enumerate(image_data):
            if img_data['url'] in unique_image_urls:
                # Find the input index for this image URL
                img_input_idx = img_input_base + unique_image_urls.index(img_data['url'])
                scene_idx = img_data['scene_index']
                
                # Find timing for this scene
                scene_timing = next(
                    (t for t in scene_timings if t['scene_index'] == scene_idx), 
                    None
                )
                
                if scene_timing:
                    start_time = scene_timing['start_time']
                    end_time = scene_timing['end_time']
                    x_pos = img_data['x']
                    y_pos = img_data['y']
                    
                    # Scale image
                    filters.append(f'[{img_input_idx}:v]scale=500:500[scaled_img_{i}]')
                    
                    # Overlay with timing
                    if overlay_count == 0:
                        # First overlay
                        filters.append(
                            f'[{current_video}][scaled_img_{i}]overlay={x_pos}:{y_pos}:'
                            f'enable=between(t\\,{start_time}\\,{end_time})[overlay_{overlay_count}]'
                        )
                    else:
                        # Subsequent overlays
                        filters.append(
                            f'[overlay_{overlay_count-1}][scaled_img_{i}]overlay={x_pos}:{y_pos}:'
                            f'enable=between(t\\,{start_time}\\,{end_time})[overlay_{overlay_count}]'
                        )
                    
                    logger.debug(f"Image {i} overlay: scene {scene_idx}, time {start_time:.1f}-{end_time:.1f}s, pos ({x_pos},{y_pos})")
                    overlay_count += 1
        
        return f'overlay_{overlay_count-1}' if overlay_count > 0 else current_video
    
    def _calculate_scene_timings(self, audio_info: List[AudioAnalysisResult]) -> List[Dict[str, Any]]:
        """
        Calculate scene timing information
        
        Args:
            audio_info: Audio analysis results
            
        Returns:
            List of scene timing dictionaries
        """
        # Group audio durations by scene
        scene_audio_durations = {}
        for info in audio_info:
            scene_idx = info.scene_index
            if scene_idx not in scene_audio_durations:
                scene_audio_durations[scene_idx] = 0
            scene_audio_durations[scene_idx] += info.duration
        
        # Calculate start/end times for each scene
        scene_timings = []
        current_time = 0
        
        for scene_idx in sorted(scene_audio_durations.keys()):
            duration = scene_audio_durations[scene_idx]
            scene_timings.append({
                'scene_index': scene_idx,
                'start_time': current_time,
                'end_time': current_time + duration,
                'duration': duration
            })
            current_time += duration
        
        return scene_timings
    
    def _add_subtitle_filter(self, filters: List[str], current_video: str, subtitle_file_path: str) -> str:
        """
        Add subtitle filter to video stream
        
        Args:
            filters: List to append filters to
            current_video: Current video stream name
            subtitle_file_path: Path to ASS subtitle file
            
        Returns:
            Updated video stream name
        """
        if current_video == '0:v':
            filters.append(f'[0:v]ass={subtitle_file_path}[subtitled_video]')
        else:
            filters.append(f'[{current_video}]ass={subtitle_file_path}[subtitled_video]')
        
        logger.info(f"✓ Subtitles added using ASS file: {subtitle_file_path}")
        return 'subtitled_video'
    
    def _build_command_string(self, command: List[str]) -> str:
        """
        Build properly escaped command string for shell execution
        
        Args:
            command: Command as list of arguments
            
        Returns:
            Properly escaped command string
        """
        cmd_str = command[0]  # 'ffmpeg'
        for i in range(1, len(command)):
            part = command[i]
            # Don't quote flags that start with -
            if part.startswith('-'):
                cmd_str += f' {part}'
            else:
                # Properly escape other arguments
                cmd_str += f' {shlex.quote(part)}'
        
        return cmd_str
    
    def validate_ffmpeg_availability(self) -> bool:
        """
        Check if FFmpeg is available on the system
        
        Returns:
            True if FFmpeg is available
        """
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'], 
                capture_output=True, 
                timeout=30
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def get_ffmpeg_version(self) -> Optional[str]:
        """
        Get FFmpeg version information
        
        Returns:
            FFmpeg version string or None if not available
        """
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            if result.returncode == 0:
                # Extract version from first line
                first_line = result.stdout.split('\n')[0]
                return first_line
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None