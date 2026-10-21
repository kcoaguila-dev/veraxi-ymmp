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


@dataclass
class VariantMetrics:
    """Performance metrics recorded for a thumbnail variant over an observation period."""

    variant_id: str
    impressions: int = 0
    views: int = 0
    ctr: float = 0.0
    average_view_percentage: float = 0.0
    average_view_duration_sec: float = 0.0
    retention_score: float = 0.0
    sample_start: Optional[str] = None
    sample_end: Optional[str] = None
    raw_metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "impressions": self.impressions,
            "views": self.views,
            "ctr": self.ctr,
            "average_view_percentage": self.average_view_percentage,
            "average_view_duration_sec": self.average_view_duration_sec,
            "retention_score": self.retention_score,
            "sample_start": self.sample_start,
            "sample_end": self.sample_end,
            "raw_metrics": dict(self.raw_metrics),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VariantMetrics":
        return cls(
            variant_id=str(data.get("variant_id", "")),
            impressions=int(data.get("impressions", 0)),
            views=int(data.get("views", 0)),
            ctr=float(data.get("ctr", 0.0)),
            average_view_percentage=float(data.get("average_view_percentage", 0.0)),
            average_view_duration_sec=float(data.get("average_view_duration_sec", 0.0)),
            retention_score=float(data.get("retention_score", 0.0)),
            sample_start=data.get("sample_start"),
            sample_end=data.get("sample_end"),
            raw_metrics=dict(data.get("raw_metrics", {})),
        )


@dataclass
class ThumbnailVariant:
    """Represents a candidate thumbnail variant in an A/B experiment."""

    variant_id: str
    name: str
    thumbnail_path: Path
    config: Dict[str, Any] = field(default_factory=dict)
    metrics: VariantMetrics = field(default_factory=lambda: VariantMetrics(variant_id=""))
    is_active: bool = False
    rotation_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "name": self.name,
            "thumbnail_path": str(self.thumbnail_path),
            "config": dict(self.config),
            "metrics": self.metrics.to_dict(),
            "is_active": self.is_active,
            "rotation_count": self.rotation_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThumbnailVariant":
        raw_m = data.get("metrics")
        metrics = VariantMetrics.from_dict(raw_m) if isinstance(raw_m, dict) else VariantMetrics(variant_id=data.get("variant_id", ""))
        return cls(
            variant_id=str(data.get("variant_id", "")),
            name=str(data.get("name", "")),
            thumbnail_path=Path(data["thumbnail_path"]),
            config=dict(data.get("config", {})),
            metrics=metrics,
            is_active=bool(data.get("is_active", False)),
            rotation_count=int(data.get("rotation_count", 0)),
        )


@dataclass
class RotationEvent:
    """Audit entry for a thumbnail rotation event."""

    timestamp: str
    video_id: str
    from_variant_id: Optional[str]
    to_variant_id: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "video_id": self.video_id,
            "from_variant_id": self.from_variant_id,
            "to_variant_id": self.to_variant_id,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RotationEvent":
        return cls(
            timestamp=str(data.get("timestamp", "")),
            video_id=str(data.get("video_id", "")),
            from_variant_id=data.get("from_variant_id"),
            to_variant_id=str(data.get("to_variant_id", "")),
            reason=str(data.get("reason", "")),
        )


@dataclass
class WinnerDecision:
    """Outcome of statistical evaluation and winner commitment."""

    winner_variant_id: Optional[str] = None
    winning_score: float = 0.0
    margin: float = 0.0
    is_significant: bool = False
    p_value: Optional[float] = None
    committed: bool = False
    committed_at: Optional[str] = None
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "winner_variant_id": self.winner_variant_id,
            "winning_score": self.winning_score,
            "margin": self.margin,
            "is_significant": self.is_significant,
            "p_value": self.p_value,
            "committed": self.committed,
            "committed_at": self.committed_at,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WinnerDecision":
        return cls(
            winner_variant_id=data.get("winner_variant_id"),
            winning_score=float(data.get("winning_score", 0.0)),
            margin=float(data.get("margin", 0.0)),
            is_significant=bool(data.get("is_significant", False)),
            p_value=float(data["p_value"]) if data.get("p_value") is not None else None,
            committed=bool(data.get("committed", False)),
            committed_at=data.get("committed_at"),
            rationale=str(data.get("rationale", "")),
        )


@dataclass
class ThumbnailExperiment:
    """Full lifecycle state for a thumbnail A/B experiment."""

    experiment_id: str
    video_id: str
    project_dir: Path
    status: str = "DRAFT"  # "DRAFT", "RUNNING", "CONCLUDED", "PAUSED"
    active_variant_id: Optional[str] = None
    variants: Dict[str, ThumbnailVariant] = field(default_factory=dict)
    rotation_history: List[RotationEvent] = field(default_factory=list)
    winner_decision: Optional[WinnerDecision] = None
    min_impressions: int = 500
    min_observation_hours: float = 24.0
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "video_id": self.video_id,
            "project_dir": str(self.project_dir),
            "status": self.status,
            "active_variant_id": self.active_variant_id,
            "variants": {k: v.to_dict() for k, v in self.variants.items()},
            "rotation_history": [r.to_dict() for r in self.rotation_history],
            "winner_decision": self.winner_decision.to_dict() if self.winner_decision else None,
            "min_impressions": self.min_impressions,
            "min_observation_hours": self.min_observation_hours,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThumbnailExperiment":
        variants = {
            k: ThumbnailVariant.from_dict(v)
            for k, v in data.get("variants", {}).items()
        }
        history = [
            RotationEvent.from_dict(r)
            for r in data.get("rotation_history", [])
        ]
        winner = (
            WinnerDecision.from_dict(data["winner_decision"])
            if data.get("winner_decision")
            else None
        )
        return cls(
            experiment_id=str(data.get("experiment_id", "")),
            video_id=str(data.get("video_id", "")),
            project_dir=Path(data["project_dir"]),
            status=str(data.get("status", "DRAFT")),
            active_variant_id=data.get("active_variant_id"),
            variants=variants,
            rotation_history=history,
            winner_decision=winner,
            min_impressions=int(data.get("min_impressions", 500)),
            min_observation_hours=float(data.get("min_observation_hours", 24.0)),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )


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
    "VariantMetrics",
    "ThumbnailVariant",
    "RotationEvent",
    "WinnerDecision",
    "ThumbnailExperiment",
]
