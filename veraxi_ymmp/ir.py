from dataclasses import dataclass, field
from datetime import datetime
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


@dataclass
class RetentionPoint:
    """A single data point along a video's audience retention curve."""

    elapsed_time_ratio: float
    watch_ratio: float
    timestamp_sec: float
    relative_retention: Optional[float] = None


@dataclass
class RetentionDropoffPoint:
    """A localized audience retention drop-off exceeding the threshold (>5%)."""

    timestamp_sec: float
    elapsed_ratio: float
    retention_before: float
    retention_after: float
    drop_magnitude: float
    cut_index: int
    speaker: str
    subtitle_text: str
    emotion: str
    broll_image: Optional[str] = None
    issue_type: str = "PACING_OR_FATIGUE"
    recommendation: str = ""


@dataclass
class CutRetentionMetric:
    """Retention telemetry aggregated per dialogue cut."""

    cut_index: int
    speaker: str
    text: str
    start_sec: float
    end_sec: float
    start_retention: float
    end_retention: float
    retention_change: float
    broll_image: Optional[str] = None


@dataclass
class VideoRetentionReport:
    """Complete analytical post-publish QA retention report."""

    video_id: str
    video_title: str
    total_duration_sec: float
    total_cuts: int
    retention_score: float
    average_view_percentage: float
    dropoff_threshold: float = 0.05
    dropoff_points: List[RetentionDropoffPoint] = field(default_factory=list)
    cut_metrics: List[CutRetentionMetric] = field(default_factory=list)
    summary_verdict: str = "NOMINAL"
    editorial_recommendations: List[str] = field(default_factory=list)


@dataclass
class VideoPublishMetadata:
    """Metadata for publishing a video to YouTube."""

    title: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    category_id: str = "22"
    privacy_status: str = "private"
    made_for_kids: bool = False
    publish_at: Optional[str] = None
    language: str = "ja"
    thumbnail_path: Optional[Path] = None

    def __post_init__(self) -> None:
        if self.publish_at is not None:
            try:
                datetime.fromisoformat(self.publish_at.replace("Z", "+00:00"))
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"Invalid ISO-8601 publish_at format: '{self.publish_at}'. {exc}"
                ) from exc

            if self.privacy_status != "private":
                raise ValueError(
                    f"YouTube requires privacy_status='private' for scheduled uploads (got '{self.privacy_status}')."
                )


@dataclass
class UploadResult:
    """Outcome of a video upload operation."""

    video_id: str
    url: str
    status: str
    thumbnail_uploaded: bool = False
    error_message: Optional[str] = None
    bytes_uploaded: int = 0
    total_bytes: int = 0
    raw_response: Dict[str, Any] = field(default_factory=dict)


__all__ = [
    "IRClip",
    "VoiceClip",
    "CharacterClip",
    "GlobalClip",
    "DynamicImageClip",
    "DynamicAudioClip",
    "TimelineIR",
    "RetentionPoint",
    "RetentionDropoffPoint",
    "CutRetentionMetric",
    "VideoRetentionReport",
    "VideoPublishMetadata",
    "UploadResult",
]
