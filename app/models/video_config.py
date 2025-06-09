"""
Pydantic models for video configuration validation
"""
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, HttpUrl, Field, validator


class SubtitleSettings(BaseModel):
    """Subtitle styling configuration"""
    style: str = Field(default="progressive")  # "progressive" | "classic"
    font_family: str = Field(default="Arial", alias="font-family")
    font_size: int = Field(default=24, alias="font-size", ge=10, le=200)
    word_color: str = Field(default="#FFFFFF", alias="word-color")
    line_color: str = Field(default="#FFFFFF", alias="line-color")
    shadow_color: str = Field(default="#000000", alias="shadow-color")
    shadow_offset: int = Field(default=2, alias="shadow-offset", ge=0, le=10)
    box_color: str = Field(default="#000000", alias="box-color")
    position: str = Field(default="center-top")
    outline_color: str = Field(default="#000000", alias="outline-color")
    outline_width: int = Field(default=3, alias="outline-width", ge=0, le=10)
    
    class Config:
        allow_population_by_field_name = True


class VideoElement(BaseModel):
    """Background video element"""
    type: Literal["video"]
    src: str
    z_index: Optional[int] = Field(default=-1, alias="z-index")
    volume: Optional[float] = Field(default=0.5, ge=0.0, le=1.0)
    resize: Optional[str] = Field(default="fit")
    duration: Optional[float] = Field(default=None, ge=0)


class SubtitleElement(BaseModel):
    """Subtitle element"""
    id: Optional[str] = None
    type: Literal["subtitles"]
    settings: SubtitleSettings
    language: str = Field(default="en")


class ImageElement(BaseModel):
    """Scene image element"""
    type: Literal["image"]
    src: str
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class AudioElement(BaseModel):
    """Scene audio element"""
    type: Literal["audio"]
    src: str


class Scene(BaseModel):
    """Video scene with elements"""
    id: str
    background_color: str = Field(default="transparent", alias="background-color")
    elements: List[Any]  # Union of ImageElement, AudioElement
    
    @validator('elements')
    def validate_elements(cls, v):
        validated = []
        for element in v:
            if element.get('type') == 'image':
                validated.append(ImageElement(**element))
            elif element.get('type') == 'audio':
                validated.append(AudioElement(**element))
            else:
                # Keep unknown elements as-is for backwards compatibility
                validated.append(element)
        return validated
    
    class Config:
        allow_population_by_field_name = True


class VideoConfig(BaseModel):
    """Complete video configuration"""
    comment: Optional[str] = None
    resolution: str = Field(default="custom")
    quality: str = Field(default="high")
    width: int = Field(ge=100, le=4000)
    height: int = Field(ge=100, le=4000)
    scenes: List[Scene]
    elements: List[Any]  # Union of VideoElement, SubtitleElement
    
    @validator('elements')
    def validate_elements(cls, v):
        validated = []
        for element in v:
            if element.get('type') == 'video':
                validated.append(VideoElement(**element))
            elif element.get('type') == 'subtitles':
                validated.append(SubtitleElement(**element))
            else:
                # Keep unknown elements as-is for backwards compatibility
                validated.append(element)
        return validated
    
    def get_background_video(self) -> Optional[VideoElement]:
        """Get the background video element"""
        for element in self.elements:
            if isinstance(element, VideoElement):
                return element
        return None
    
    def get_subtitle_element(self) -> Optional[SubtitleElement]:
        """Get the subtitle element"""
        for element in self.elements:
            if isinstance(element, SubtitleElement):
                return element
        return None
    
    def get_scenes_with_audio(self) -> List[Scene]:
        """Get only scenes that have audio elements"""
        return [scene for scene in self.scenes 
                if any(isinstance(el, AudioElement) for el in scene.elements)]
    
    def get_scenes_with_images(self) -> List[Scene]:
        """Get only scenes that have image elements"""
        return [scene for scene in self.scenes 
                if any(isinstance(el, ImageElement) for el in scene.elements)]