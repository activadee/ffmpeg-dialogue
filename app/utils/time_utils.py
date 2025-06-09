"""
Time formatting utilities
"""
from typing import Union


def format_ass_time(seconds: Union[int, float]) -> str:
    """
    Format time for ASS subtitle format (H:MM:SS.CC)
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted time string
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def format_duration(seconds: Union[int, float]) -> str:
    """
    Format duration for human-readable display
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}h {minutes}m {secs:.1f}s"


def parse_time_to_seconds(time_str: str) -> float:
    """
    Parse time string to seconds
    
    Args:
        time_str: Time string in various formats (HH:MM:SS, MM:SS, SS)
        
    Returns:
        Time in seconds
    """
    try:
        parts = time_str.split(':')
        if len(parts) == 1:
            # Just seconds
            return float(parts[0])
        elif len(parts) == 2:
            # MM:SS
            return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            # HH:MM:SS
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        else:
            raise ValueError("Invalid time format")
    except ValueError:
        raise ValueError(f"Cannot parse time string: {time_str}")


def seconds_to_timecode(seconds: Union[int, float], fps: int = 30) -> str:
    """
    Convert seconds to timecode format (HH:MM:SS:FF)
    
    Args:
        seconds: Time in seconds
        fps: Frames per second
        
    Returns:
        Timecode string
    """
    total_frames = int(seconds * fps)
    
    hours = total_frames // (3600 * fps)
    total_frames %= (3600 * fps)
    
    minutes = total_frames // (60 * fps)
    total_frames %= (60 * fps)
    
    secs = total_frames // fps
    frames = total_frames % fps
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"


def validate_time_range(start_time: float, end_time: float) -> bool:
    """
    Validate time range
    
    Args:
        start_time: Start time in seconds
        end_time: End time in seconds
        
    Returns:
        True if valid range
    """
    return start_time >= 0 and end_time > start_time