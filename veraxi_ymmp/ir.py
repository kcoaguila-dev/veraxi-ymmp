from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path

@dataclass
class IRClip:
    """Base class for all timeline clips."""
    start_frame: int
    length: int

@dataclass
class VoiceClip(IRClip):
    character: str
    text: str
    emotion: str
    motion: str
    audio_path: Optional[Path]
    hatsuon: str
    subtitle_position: str
    subtitle_style: str
    audio_query: Optional[Dict] = None

@dataclass
class CharacterClip(IRClip):
    """Represents a standing picture (Tachie) spanning a duration."""
    character: str
    position: str

@dataclass
class GlobalClip(IRClip):
    """Represents a BGM or Background item spanning the video."""
    template_item: Dict  # For now, we preserve the template item directly for exact YMM4 rendering

@dataclass
class DynamicImageClip(IRClip):
    """Represents an image that appears dynamically for a specific duration."""
    image_path: Path

@dataclass
class TimelineIR:
    fps: int
    total_frames: int
    voice_clips: List[VoiceClip] = field(default_factory=list)
    character_clips: List[CharacterClip] = field(default_factory=list)
    global_clips: List[GlobalClip] = field(default_factory=list)
    dynamic_image_clips: List[DynamicImageClip] = field(default_factory=list)
    
    # We still need to pass down the template data so the YMM4 renderer knows how to style things
    template_data: Dict = field(default_factory=dict)
