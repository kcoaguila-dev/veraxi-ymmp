"""
Architectural Ports and Protocols for Veraxi YMMP.

Defines the formal boundaries and interfaces (Ports) according to Clean Architecture:
- TimelineExporter: Exporter protocol for converting TimelineIR into target formats.
- ExportResult: Data transfer object describing exported artifacts.
- TTSBackend: Unified port for text-to-speech synthesis backends.
- DirectorProvider: Unified port for script directing engines.
- VideoPublisher: Unified port for video uploading and thumbnail binding adapters.
- VideoAnalyticsProvider: Unified port for video performance and audience retention telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

from .director import DirectorProvider
from .ir import (
    CutRetentionMetric,
    RetentionDropoffPoint,
    RetentionPoint,
    RotationEvent,
    ThumbnailExperiment,
    ThumbnailVariant,
    TimelineIR,
    UploadResult,
    VariantMetrics,
    VideoPublishMetadata,
    VideoRetentionReport,
    WinnerDecision,
)


@runtime_checkable
class TTSBackend(Protocol):
    """Protocol defining the interface for TTS backends."""

    def is_available(self) -> bool:
        ...

    def synthesize(self, text: str, speaker_id: int) -> Tuple[bytes, float, Dict[str, Any]]:
        ...

    def get_speakers(self) -> List[Dict[str, Any]]:
        ...


class NullTTSBackend:
    """A dummy TTS backend for testing or placeholder generation."""

    def is_available(self) -> bool:
        return True

    def get_audio_query(self, text: str, speaker_id: int) -> Dict[str, Any]:
        return {}

    def synthesize(self, text: str, speaker_id: int) -> Tuple[bytes, float, Dict[str, Any]]:
        return b"", 0.0, {}

    def get_speakers(self) -> List[Dict[str, Any]]:
        return []


@dataclass(frozen=True)
class VideoStatsRow:
    video_id: str
    date: Optional[str]
    metrics: Dict[str, Optional[float]]


@dataclass(frozen=True)
class VideoStatsReport:
    video_ids: List[str]
    start_date: str
    end_date: str
    granularity: str
    metrics: List[str]
    rows: List[VideoStatsRow]
    fetched_at: str


@dataclass
class ExportResult:
    """Result of exporting a TimelineIR representation to an external target format."""

    target_format: str
    output_path: Path
    artifacts: List[Path] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class TimelineExporter(Protocol):
    """Protocol for timeline exporters that convert TimelineIR to target formats."""

    def export(
        self,
        ir: TimelineIR,
        output_path: Path,
        options: Optional[Dict[str, Any]] = None,
    ) -> ExportResult:
        """Export the given TimelineIR to output_path with optional exporter-specific options."""
        ...


# Progress callback signature: (progress_ratio: float, bytes_uploaded: int, total_bytes: int) -> None
ProgressCallback = Callable[[float, int, int], None]
PipelineProgressCallback = Callable[[str, float, str], None]


@runtime_checkable
class VideoPublisher(Protocol):
    """Protocol for video publishing adapters."""

    def upload_video(
        self,
        video_path: Path,
        metadata: VideoPublishMetadata,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> UploadResult:
        """Upload a video file with chunked resumable streaming and retry backoff."""
        ...

    def upload_thumbnail(
        self,
        video_id: str,
        thumbnail_path: Path,
    ) -> bool:
        """Upload and bind a custom thumbnail image to a video."""
        ...

    def upload_caption(
        self,
        video_id: str,
        caption_path: Path,
        language: str = "ja",
        name: str = "Japanese",
    ) -> bool:
        """Upload and bind a caption/subtitle track (e.g. SRT) to a video."""
        ...


@runtime_checkable
class VideoAnalyticsProvider(Protocol):
    """Protocol defining the interface for video analytics providers (e.g. YouTube Analytics API)."""

    def fetch_retention_curve(
        self,
        video_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Tuple[float, float]]:
        """Fetch audience retention curve as list of (elapsed_time_ratio, audience_watch_ratio) tuples."""
        ...

    def fetch_variant_metrics(
        self,
        video_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> VariantMetrics:
        """Fetch impression, CTR, and watch metrics for a video over a time window."""
        ...

    def fetch_stats_report(
        self,
        video_ids: List[str],
        start_date: str,
        end_date: str,
        metrics: List[str],
        granularity: str = "total",
    ) -> VideoStatsReport:
        """Fetch video stats report for given videos."""
        ...

    def get_channel_info(self) -> Dict[str, Any]:
        """Fetch authenticated channel info."""
        ...


__all__ = [
    "ExportResult",
    "TimelineExporter",
    "TTSBackend",
    "NullTTSBackend",
    "DirectorProvider",
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
    "ProgressCallback",
    "PipelineProgressCallback",
    "VideoPublisher",
    "VideoAnalyticsProvider",
]
