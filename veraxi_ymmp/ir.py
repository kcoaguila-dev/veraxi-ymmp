from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional
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
    audio_query: Optional[Dict[str, Any]] = None

@dataclass
class CharacterClip(IRClip):
    """Represents a standing picture (Tachie) spanning a duration."""
    character: str
    position: str

@dataclass
class GlobalClip(IRClip):
    """Represents a BGM or Background item spanning the video."""
    file_path: Optional[str] = None
    item_type: Optional[str] = None
    volume: float = 100.0
    is_looped: bool = False
    template_item: Dict[str, Any] = field(default_factory=dict)

@dataclass
class DynamicImageClip(IRClip):
    """Represents an image that appears dynamically for a specific duration."""
    image_path: Path
    is_background: bool = False

    @property
    def is_bg(self) -> bool:
        return self.is_background or any(
            k in str(self.image_path).lower() for k in ("bg", "room", "classroom")
        )

@dataclass
class DynamicAudioClip(IRClip):
    """Represents a dynamic audio clip (BGM/SFX)."""
    audio_path: Path
    volume: float = 1.0

@dataclass
class TimelineIR:
    fps: int
    total_frames: int
    voice_clips: List[VoiceClip] = field(default_factory=list)
    character_clips: List[CharacterClip] = field(default_factory=list)
    global_clips: List[GlobalClip] = field(default_factory=list)
    dynamic_image_clips: List[DynamicImageClip] = field(default_factory=list)
    dynamic_audio_clips: List[DynamicAudioClip] = field(default_factory=list)

    # We still need to pass down the template data so the YMM4 renderer knows how to style things
    template_data: Dict[str, Any] = field(default_factory=dict)

    def min_all_speakers_duration(self, default_max: float = 25.0) -> float:
        """Calculate the end time in seconds of the first VoiceClip for each unique character."""
        if not self.voice_clips:
            return default_max
        first_end_frames: Dict[str, int] = {}
        for vc in self.voice_clips:
            if vc.character not in first_end_frames:
                first_end_frames[vc.character] = vc.start_frame + vc.length
        max_first_end_sec = max(first_end_frames.values()) / max(self.fps, 1)
        return max(default_max, max_first_end_sec)
