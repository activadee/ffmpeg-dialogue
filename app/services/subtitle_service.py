"""
Subtitle generation service for ASS file creation with styling
"""
import tempfile
import os
from typing import List, Optional, Dict, Any
from ..models.video_config import SubtitleElement, SubtitleSettings
from ..models.response_models import SceneTiming, TranscriptionResult
from ..config.logging_config import get_logger
from ..utils.time_utils import format_ass_time
from ..exceptions.custom_exceptions import SubtitleGenerationError

logger = get_logger(__name__)


class SubtitleService:
    """Service for subtitle generation and ASS file creation"""
    
    def __init__(self):
        pass
    
    def create_ass_subtitle_file(
        self, 
        transcriptions: List[TranscriptionResult], 
        scene_timings: List[SceneTiming], 
        subtitle_config: SubtitleSettings, 
        temp_dir: str
    ) -> Optional[str]:
        """
        Create ASS subtitle file with styling from configuration
        
        Args:
            transcriptions: List of transcription results
            scene_timings: Scene timing information
            subtitle_config: Subtitle styling configuration
            temp_dir: Temporary directory for file creation
            
        Returns:
            Path to created ASS file or None if creation failed
            
        Raises:
            SubtitleGenerationError: If subtitle file creation fails
        """
        try:
            logger.info("Creating ASS subtitle file...")
            
            # Filter successful transcriptions
            valid_transcriptions = [
                (t, s) for t, s in zip(transcriptions, scene_timings)
                if t.success and t.transcription and t.transcription.strip()
            ]
            
            if not valid_transcriptions:
                logger.warning("No valid transcriptions found for subtitle generation")
                return None
            
            # Generate ASS content
            ass_content = self._generate_ass_header(subtitle_config)
            ass_content += self._generate_ass_events(valid_transcriptions, subtitle_config)
            
            # Save ASS file
            ass_file = tempfile.NamedTemporaryFile(
                mode='w', 
                suffix='.ass', 
                dir=temp_dir, 
                delete=False,
                encoding='utf-8'
            )
            
            ass_file.write(ass_content)
            ass_file.close()
            
            logger.info(f"ASS subtitle file created: {ass_file.name}")
            return ass_file.name
            
        except Exception as e:
            logger.error(f"Failed to create ASS subtitle file: {e}")
            raise SubtitleGenerationError(f"Subtitle file creation failed: {e}")
    
    def _generate_ass_header(self, config: SubtitleSettings) -> str:
        """
        Generate ASS file header with styling
        
        Args:
            config: Subtitle styling configuration
            
        Returns:
            ASS header string
        """
        # Parse color values (remove # and convert to &H format)
        word_color = self._parse_color(config.word_color)
        line_color = self._parse_color(config.line_color)
        outline_color = self._parse_color(config.outline_color)
        box_color = self._parse_color(config.box_color)
        
        # Map position to alignment
        alignment = self._get_alignment(config.position)
        
        header = f"""[Script Info]
Title: Generated Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{config.font_family},{config.font_size},{word_color},{line_color},{outline_color},{box_color},1,0,0,0,100,100,0,0,1,{config.outline_width},{config.shadow_offset},{alignment},10,10,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        return header
    
    def _generate_ass_events(self, valid_transcriptions: List[tuple], subtitle_config: SubtitleSettings) -> str:
        """
        Generate ASS events (subtitle lines) from transcriptions
        
        Args:
            valid_transcriptions: List of (transcription_result, scene_timing) tuples
            subtitle_config: Subtitle configuration
            
        Returns:
            ASS events string
        """
        events = ""
        
        for transcription_result, scene_timing in valid_transcriptions:
            if subtitle_config.style == "progressive" and hasattr(transcription_result, 'word_timestamps'):
                # Generate progressive word-by-word events
                events += self._generate_progressive_events(
                    transcription_result, 
                    scene_timing, 
                    subtitle_config
                )
            else:
                # Generate classic full-line events
                start_time = format_ass_time(scene_timing.start_time)
                end_time = format_ass_time(scene_timing.end_time)
                
                # Clean text for ASS format
                clean_text = self._clean_text_for_ass(transcription_result.transcription)
                
                # Add dialogue line
                events += f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{clean_text}\n"
        
        return events
    
    def _generate_progressive_events(self, transcription_result, scene_timing, subtitle_config: SubtitleSettings) -> str:
        """
        Generate progressive word-by-word subtitle events for TikTok-style animation
        
        Args:
            transcription_result: Transcription with word timestamps
            scene_timing: Scene timing information
            subtitle_config: Subtitle configuration
            
        Returns:
            Progressive ASS events string
        """
        events = ""
        
        # Get word timestamps - progressive mode requires word timestamps
        if not (hasattr(transcription_result, 'word_timestamps') and transcription_result.word_timestamps):
            logger.warning("Progressive subtitles require word timestamps, skipping")
            return ""
        
        words = transcription_result.word_timestamps
        
        # Generate events for word-by-word display using Whisper timestamps
        for i, word_data in enumerate(words):
            word_text = word_data.get('word', '').strip()
            # Convert relative Whisper timestamps to absolute video timeline
            whisper_start = word_data.get('start', 0)
            whisper_end = word_data.get('end', 0)
            
            # Add scene start time to make timestamps absolute to video timeline
            absolute_start = scene_timing.start_time + whisper_start
            absolute_end = scene_timing.start_time + whisper_end
            
            # Ensure we don't exceed scene boundaries
            absolute_start = max(absolute_start, scene_timing.start_time)
            absolute_end = min(absolute_end, scene_timing.end_time)
            
            if word_text:
                # Clean single word text
                clean_text = self._clean_text_for_ass(word_text)
                
                # Calculate when this word should start and end
                subtitle_start = absolute_start
                
                # End this word when next word starts (or at scene end if last word)
                if i + 1 < len(words):
                    next_word_start = scene_timing.start_time + words[i + 1].get('start', 0)
                    subtitle_end = min(next_word_start, scene_timing.end_time)
                else:
                    # Last word - show until scene end
                    subtitle_end = scene_timing.end_time
                
                # Format timing
                start_time = format_ass_time(subtitle_start)
                end_time = format_ass_time(subtitle_end)
                
                # Add single word dialogue line
                events += f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{clean_text}\n"
        
        return events
    
    
    def _parse_color(self, hex_color: str) -> str:
        """
        Parse color from hex to ASS format
        
        Args:
            hex_color: Color in hex format (#RRGGBB)
            
        Returns:
            Color in ASS format (&HBBGGRR)
        """
        try:
            if hex_color.startswith('#'):
                hex_color = hex_color[1:]
            
            # Convert RGB to BGR for ASS format
            if len(hex_color) == 6:
                r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
                return f"&H00{b}{g}{r}"
            
            return "&H00FFFFFF"  # Default white
            
        except Exception:
            logger.warning(f"Invalid color format: {hex_color}, using white")
            return "&H00FFFFFF"
    
    def _get_alignment(self, position: str) -> int:
        """
        Map position string to ASS alignment number
        
        Args:
            position: Position string (e.g., "center-center")
            
        Returns:
            ASS alignment number
        """
        alignment_map = {
            "left-bottom": 1,
            "center-bottom": 2,
            "right-bottom": 3,
            "left-center": 4,
            "center-center": 5,
            "right-center": 6,
            "left-top": 7,
            "center-top": 8,
            "right-top": 9
        }
        
        return alignment_map.get(position, 2)  # Default to center-bottom
    
    def _clean_text_for_ass(self, text: str) -> str:
        """
        Clean text for ASS format
        
        Args:
            text: Raw transcription text
            
        Returns:
            Cleaned text suitable for ASS format
        """
        if not text:
            return ""
        
        # Remove or escape problematic characters
        clean_text = text.replace('\n', '\\N')  # Convert newlines to ASS format
        clean_text = clean_text.replace('{', '\\{')  # Escape braces
        clean_text = clean_text.replace('}', '\\}')
        clean_text = clean_text.replace('|', '\\h')  # Hard space
        
        # Remove extra whitespace
        clean_text = ' '.join(clean_text.split())
        
        return clean_text
    
    def validate_subtitle_config(self, config: SubtitleSettings) -> List[str]:
        """
        Validate subtitle configuration
        
        Args:
            config: Subtitle configuration to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Validate font size
        if config.font_size < 10 or config.font_size > 200:
            errors.append(f"Font size {config.font_size} out of range (10-200)")
        
        # Validate colors
        for color_name, color_value in [
            ("word_color", config.word_color),
            ("line_color", config.line_color),
            ("outline_color", config.outline_color),
            ("box_color", config.box_color)
        ]:
            if not self._is_valid_color(color_value):
                errors.append(f"Invalid {color_name}: {color_value}")
        
        # Validate outline width
        if config.outline_width < 0 or config.outline_width > 10:
            errors.append(f"Outline width {config.outline_width} out of range (0-10)")
        
        # Validate shadow offset
        if config.shadow_offset < 0 or config.shadow_offset > 10:
            errors.append(f"Shadow offset {config.shadow_offset} out of range (0-10)")
        
        return errors
    
    def _is_valid_color(self, color: str) -> bool:
        """
        Check if color string is valid hex format
        
        Args:
            color: Color string to validate
            
        Returns:
            True if valid hex color
        """
        try:
            if not color.startswith('#'):
                return False
            
            hex_part = color[1:]
            if len(hex_part) != 6:
                return False
            
            int(hex_part, 16)  # Try to parse as hex
            return True
            
        except ValueError:
            return False
    
    def get_estimated_subtitle_duration(self, transcriptions: List[TranscriptionResult]) -> float:
        """
        Estimate total duration of subtitles
        
        Args:
            transcriptions: List of transcription results
            
        Returns:
            Estimated duration in seconds
        """
        total_chars = 0
        for transcription in transcriptions:
            if transcription.success and transcription.transcription:
                total_chars += len(transcription.transcription)
        
        # Rough estimate: 150 words per minute, 5 chars per word
        chars_per_second = (150 * 5) / 60  # ~12.5 chars/second
        return total_chars / chars_per_second if chars_per_second > 0 else 0
    
    def get_subtitle_statistics(self, transcriptions: List[TranscriptionResult]) -> Dict[str, Any]:
        """
        Get statistics about generated subtitles
        
        Args:
            transcriptions: List of transcription results
            
        Returns:
            Dictionary with subtitle statistics
        """
        successful = sum(1 for t in transcriptions if t.success)
        failed = len(transcriptions) - successful
        total_chars = sum(
            len(t.transcription) for t in transcriptions 
            if t.success and t.transcription
        )
        
        return {
            "total_scenes": len(transcriptions),
            "successful_transcriptions": successful,
            "failed_transcriptions": failed,
            "total_characters": total_chars,
            "estimated_duration": self.get_estimated_subtitle_duration(transcriptions),
            "success_rate": (successful / len(transcriptions)) * 100 if transcriptions else 0
        }