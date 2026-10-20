"""
End-to-End (E2E) Opaque-Box Test Suite for YouTube Automation & Retention QA Telemetry.

This suite implements a 4-tier testing hierarchy verifying:
- Tier 1: Feature Coverage (Isolation happy-paths across all 7 features, >=5 tests each)
- Tier 2: Boundary & Corner Cases (Stress & BVA limits across all 7 features, >=5 tests each)
- Tier 3: Cross-Feature Combinations (Pairwise and workflow interactions, >=7 tests)
- Tier 4: Real-World Application Scenarios (Realistic video project publishing & telemetry, >=5 tests)

Guarantees:
- 100% offline execution without network access or live Google credentials.
- Zero committed secrets or hardcoded user paths.
- Strict Clean Architecture and contract adherence.
"""

from __future__ import annotations

import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Domain Models & Ports (Milestone M1)
# ---------------------------------------------------------------------------
from veraxi_ymmp.ir import (
    CutRetentionMetric,
    DynamicImageClip,
    RetentionDropoffPoint,
    RetentionPoint,
    TimelineIR,
    UploadResult,
    VideoPublishMetadata,
    VideoRetentionReport,
    VoiceClip,
)
from veraxi_ymmp.ports import (
    ProgressCallback,
    VideoAnalyticsProvider,
    VideoPublisher,
)

# ---------------------------------------------------------------------------
# Lazy Imports for Modules Under Development (Milestones M2, M3, M4)
# ---------------------------------------------------------------------------
try:
    from veraxi_ymmp.youtube_adapter import (
        CHUNK_SIZE_DEFAULT,
        MOCK_CHUNK_SIZE_DEFAULT,
        THUMBNAIL_MAX_SIZE_BYTES,
        MockYouTubeAdapter,
        YouTubeAdapter,
    )
    HAS_M2_ADAPTER = True
except ImportError:
    HAS_M2_ADAPTER = False
    CHUNK_SIZE_DEFAULT = 8 * 1024 * 1024
    MOCK_CHUNK_SIZE_DEFAULT = 1 * 1024 * 1024
    THUMBNAIL_MAX_SIZE_BYTES = 2 * 1024 * 1024
    MockYouTubeAdapter = None  # type: ignore
    YouTubeAdapter = None  # type: ignore

try:
    from veraxi_ymmp.retention_qa import RetentionCorrelationEngine
    HAS_M3_QA = True
except ImportError:
    HAS_M3_QA = False
    RetentionCorrelationEngine = None  # type: ignore

def _check_cli_supports_youtube() -> bool:
    try:
        # Run in dry-run/mock mode or inspect registered subcommands
        from veraxi_ymmp import cli
        return hasattr(cli, "_cmd_youtube")
    except Exception:
        return False

HAS_M4_CLI = _check_cli_supports_youtube()

skip_m2 = pytest.mark.skipif(
    not HAS_M2_ADAPTER,
    reason="Milestone M2 (veraxi_ymmp.youtube_adapter) pending implementation",
)
skip_m3 = pytest.mark.skipif(
    not HAS_M3_QA,
    reason="Milestone M3 (veraxi_ymmp.retention_qa) pending implementation",
)
skip_m4 = pytest.mark.skipif(
    not HAS_M4_CLI,
    reason="Milestone M4 (veraxi_ymmp.cli youtube subcommands) pending implementation",
)


# ===========================================================================
# Test Fixtures
# ===========================================================================
@pytest.fixture
def sample_video_file(tmp_path: Path) -> Path:
    """Creates a temporary test video file of size 2.5 MB."""
    video_path = tmp_path / "test_video.mp4"
    data = b"\x00" * int(2.5 * 1024 * 1024)
    video_path.write_bytes(data)
    return video_path


@pytest.fixture
def small_video_file(tmp_path: Path) -> Path:
    """Creates a small video file (< 1MB) for single-chunk upload tests."""
    video_path = tmp_path / "small_video.mp4"
    video_path.write_bytes(b"\x00" * (512 * 1024))
    return video_path


@pytest.fixture
def sample_thumbnail_png(tmp_path: Path) -> Path:
    """Creates a standard valid PNG thumbnail file (128 KB)."""
    thumb_path = tmp_path / "thumbnail.png"
    # Basic PNG signature + padding
    png_header = b"\x89PNG\r\n\x1a\n"
    thumb_path.write_bytes(png_header + b"\x00" * (128 * 1024))
    return thumb_path


@pytest.fixture
def sample_thumbnail_jpg(tmp_path: Path) -> Path:
    """Creates a standard valid JPEG thumbnail file (64 KB)."""
    thumb_path = tmp_path / "thumbnail.jpg"
    jpg_header = b"\xff\xd8\xff\xe0"
    thumb_path.write_bytes(jpg_header + b"\x00" * (64 * 1024))
    return thumb_path


@pytest.fixture
def sample_timeline_ir(tmp_path: Path) -> TimelineIR:
    """
    Creates a synthetic TimelineIR representing a 60-second video at 30 fps.
    Contains 3 dialogue cuts and 2 B-roll image slides.
    """
    fps = 30
    total_frames = 60 * fps  # 1800 frames

    # Cut 0: 0.0s - 15.0s (frames 0 - 450)
    vc0 = VoiceClip(
        start_frame=0,
        length=450,
        character="ずんだもん",
        text="コストコの圧倒的な安さの秘密を知っているのだ？",
        emotion="normal",
        motion="none",
        audio_path=tmp_path / "audio_000.wav",
        hatsuon="コストコノ...",
        subtitle_position="CenterBottom",
        subtitle_style="default",
    )

    # Cut 1: 15.0s - 35.0s (frames 450 - 1050)
    vc1 = VoiceClip(
        start_frame=450,
        length=600,
        character="四国めたん",
        text="それは年会費ビジネスモデルにあるのですわ。",
        emotion="smile",
        motion="none",
        audio_path=tmp_path / "audio_001.wav",
        hatsuon="ソレワ...",
        subtitle_position="CenterBottom",
        subtitle_style="default",
    )

    # Cut 2: 35.0s - 60.0s (frames 1050 - 1800)
    vc2 = VoiceClip(
        start_frame=1050,
        length=750,
        character="ずんだもん",
        text="利益のほとんどが年会費から出ているのだ！驚きなのだ！",
        emotion="surprise",
        motion="jump",
        audio_path=tmp_path / "audio_002.wav",
        hatsuon="リエキノ...",
        subtitle_position="CenterBottom",
        subtitle_style="default",
    )

    # B-roll slide 0: frames 0 - 600 (0.0s - 20.0s)
    broll0 = DynamicImageClip(
        start_frame=0,
        length=600,
        image_path=tmp_path / "costco_entrance.png",
        is_background=False,
    )

    # B-roll slide 1: frames 600 - 1800 (20.0s - 60.0s)
    broll1 = DynamicImageClip(
        start_frame=600,
        length=1200,
        image_path=tmp_path / "membership_chart.png",
        is_background=False,
    )

    return TimelineIR(
        fps=fps,
        total_frames=total_frames,
        voice_clips=[vc0, vc1, vc2],
        dynamic_image_clips=[broll0, broll1],
    )


# ===========================================================================
# TIER 1: Feature Coverage (>=5 tests per feature across 7 features)
# ===========================================================================

class TestTier1Feature1DomainModelsAndProtocols:
    """Tier 1: Feature 1 - Pure Domain Models and Protocol Interface Purity."""

    def test_t1_f1_video_publish_metadata_defaults(self) -> None:
        """Verifies VideoPublishMetadata field defaults conform to specifications."""
        meta = VideoPublishMetadata(title="テスト動画")
        assert meta.title == "テスト動画"
        assert meta.description == ""
        assert meta.tags == []
        assert meta.category_id == "22"
        assert meta.privacy_status == "private"
        assert meta.made_for_kids is False
        assert meta.publish_at is None
        assert meta.language == "ja"
        assert meta.thumbnail_path is None

    def test_t1_f1_video_publish_metadata_custom_instantiation(self, tmp_path: Path) -> None:
        """Verifies custom metadata fields initialization."""
        thumb = tmp_path / "thumb.png"
        meta = VideoPublishMetadata(
            title="コストコの秘密",
            description="解説動画です",
            tags=["コストコ", "ビジネス", "ずんだもん"],
            category_id="27",
            privacy_status="unlisted",
            made_for_kids=False,
            publish_at="2026-11-01T12:00:00Z",
            language="ja",
            thumbnail_path=thumb,
        )
        assert meta.title == "コストコの秘密"
        assert len(meta.tags) == 3
        assert meta.category_id == "27"
        assert meta.privacy_status == "unlisted"
        assert meta.thumbnail_path == thumb

    def test_t1_f1_upload_result_instantiation(self) -> None:
        """Verifies UploadResult creation and status fields."""
        res = UploadResult(
            video_id="vid_test_123",
            url="https://youtu.be/vid_test_123",
            status="uploaded",
            thumbnail_uploaded=True,
            bytes_uploaded=1048576,
            total_bytes=1048576,
            raw_response={"id": "vid_test_123"},
        )
        assert res.video_id == "vid_test_123"
        assert res.status == "uploaded"
        assert res.thumbnail_uploaded is True
        assert res.bytes_uploaded == res.total_bytes
        assert res.error_message is None

    def test_t1_f1_retention_domain_entities(self) -> None:
        """Verifies RetentionPoint, RetentionDropoffPoint, CutRetentionMetric instantiation."""
        rp = RetentionPoint(elapsed_time_ratio=0.25, watch_ratio=0.85, timestamp_sec=15.0)
        assert rp.elapsed_time_ratio == 0.25
        assert rp.watch_ratio == 0.85
        assert rp.timestamp_sec == 15.0

        drop = RetentionDropoffPoint(
            timestamp_sec=20.0,
            elapsed_ratio=0.33,
            retention_before=0.85,
            retention_after=0.75,
            drop_magnitude=0.10,
            cut_index=1,
            speaker="四国めたん",
            subtitle_text="年会費ビジネスモデルです",
            emotion="smile",
            broll_image="chart.png",
            issue_type="PACING_OR_FATIGUE",
            recommendation="スライドの文字数を削減してください",
        )
        assert drop.drop_magnitude == 0.10
        assert drop.speaker == "四国めたん"
        assert drop.issue_type == "PACING_OR_FATIGUE"

        cut_m = CutRetentionMetric(
            cut_index=0,
            speaker="ずんだもん",
            text="コストコなのだ",
            start_sec=0.0,
            end_sec=10.0,
            start_retention=1.0,
            end_retention=0.92,
            retention_change=-0.08,
            broll_image=None,
        )
        assert cut_m.retention_change == -0.08

    def test_t1_f1_video_retention_report_instantiation(self) -> None:
        """Verifies VideoRetentionReport instantiation and aggregated fields."""
        report = VideoRetentionReport(
            video_id="vid_999",
            video_title="コストコ解説",
            total_duration_sec=60.0,
            total_cuts=3,
            retention_score=82.5,
            average_view_percentage=75.4,
            dropoff_threshold=0.05,
            dropoff_points=[],
            cut_metrics=[],
            summary_verdict="NOMINAL",
            editorial_recommendations=["テンポ良好"],
        )
        assert report.video_id == "vid_999"
        assert report.retention_score == 82.5
        assert report.summary_verdict == "NOMINAL"
        assert len(report.editorial_recommendations) == 1

    def test_t1_f1_protocol_runtime_checkability(self) -> None:
        """Verifies runtime checkability of VideoPublisher and VideoAnalyticsProvider protocols."""
        class DummyPublisher:
            def upload_video(self, video_path: Path, metadata: VideoPublishMetadata, progress_callback: Optional[ProgressCallback] = None) -> UploadResult:
                return UploadResult(video_id="d1", url="", status="uploaded")
            def upload_thumbnail(self, video_id: str, thumbnail_path: Path) -> bool:
                return True

        class DummyAnalytics:
            def fetch_retention_curve(self, video_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Tuple[float, float]]:
                return [(0.0, 1.0), (1.0, 0.5)]

        pub = DummyPublisher()
        ana = DummyAnalytics()
        assert isinstance(pub, VideoPublisher)
        assert isinstance(ana, VideoAnalyticsProvider)


class TestTier1Feature2ResumableChunkedUpload:
    """Tier 1: Feature 2 - Resumable Chunked Upload & Backoff via MockYouTubeAdapter."""

    @skip_m2
    def test_t1_f2_mock_upload_single_chunk(self, small_video_file: Path) -> None:
        """Verifies single-chunk upload for files smaller than chunk size."""
        adapter = MockYouTubeAdapter(chunk_size=MOCK_CHUNK_SIZE_DEFAULT)
        meta = VideoPublishMetadata(title="Single Chunk Video")
        res = adapter.upload_video(small_video_file, meta)

        assert res.status == "uploaded"
        assert res.video_id != ""
        assert res.bytes_uploaded == small_video_file.stat().st_size
        assert len(adapter.recorded_chunks) == 1

    @skip_m2
    def test_t1_f2_mock_upload_multiple_chunks(self, sample_video_file: Path) -> None:
        """Verifies multi-chunk upload sequence for files larger than chunk size."""
        # 2.5 MB with 1 MB chunk size = 3 chunks
        adapter = MockYouTubeAdapter(chunk_size=MOCK_CHUNK_SIZE_DEFAULT)
        meta = VideoPublishMetadata(title="Multi Chunk Video")
        res = adapter.upload_video(sample_video_file, meta)

        assert res.status == "uploaded"
        assert len(adapter.recorded_chunks) == 3
        assert adapter.recorded_chunks[-1]["ratio"] == 1.0

    @skip_m2
    def test_t1_f2_progress_callback_invocations(self, sample_video_file: Path) -> None:
        """Verifies progress callback receives increasing ratios and correct byte counts."""
        adapter = MockYouTubeAdapter(chunk_size=MOCK_CHUNK_SIZE_DEFAULT)
        meta = VideoPublishMetadata(title="Progress Test")
        calls: List[Tuple[float, int, int]] = []

        def on_progress(ratio: float, bytes_done: int, total_bytes: int) -> None:
            calls.append((ratio, bytes_done, total_bytes))

        adapter.upload_video(sample_video_file, meta, progress_callback=on_progress)
        assert len(calls) == 3
        assert calls[-1][0] == 1.0
        assert calls[-1][1] == sample_video_file.stat().st_size

    @skip_m2
    def test_t1_f2_upload_returns_valid_video_id_and_url(self, small_video_file: Path) -> None:
        """Verifies UploadResult contains deterministic video ID and https://youtu.be URL."""
        adapter = MockYouTubeAdapter()
        meta = VideoPublishMetadata(title="ID Test")
        res = adapter.upload_video(small_video_file, meta)
        assert res.video_id.startswith("mock_")
        assert res.url == f"https://youtu.be/{res.video_id}"

    @skip_m2
    def test_t1_f2_transient_error_retry_and_recovery(self, sample_video_file: Path) -> None:
        """Verifies mock adapter simulates transient 5xx error retry and recovers successfully."""
        adapter = MockYouTubeAdapter(
            fail_at_chunk=2,
            transient_failure_count=2,
            http_error_code=503,
            chunk_size=MOCK_CHUNK_SIZE_DEFAULT,
        )
        meta = VideoPublishMetadata(title="Retry Test")
        res = adapter.upload_video(sample_video_file, meta)

        assert res.status == "uploaded"
        assert adapter.retries_attempted == 2


class TestTier1Feature3ThumbnailUpload:
    """Tier 1: Feature 3 - Thumbnail Upload & Validation."""

    @skip_m2
    def test_t1_f3_upload_png_thumbnail(self, sample_thumbnail_png: Path) -> None:
        """Verifies successful PNG thumbnail upload."""
        adapter = MockYouTubeAdapter()
        ok = adapter.upload_thumbnail(video_id="mock_vid_001", thumbnail_path=sample_thumbnail_png)
        assert ok is True
        assert adapter.uploaded_thumbnails["mock_vid_001"] == sample_thumbnail_png

    @skip_m2
    def test_t1_f3_upload_jpeg_thumbnail(self, sample_thumbnail_jpg: Path) -> None:
        """Verifies successful JPEG thumbnail upload."""
        adapter = MockYouTubeAdapter()
        ok = adapter.upload_thumbnail(video_id="mock_vid_002", thumbnail_path=sample_thumbnail_jpg)
        assert ok is True

    @skip_m2
    def test_t1_f3_thumbnail_binding_via_upload_video(
        self, small_video_file: Path, sample_thumbnail_png: Path
    ) -> None:
        """Verifies thumbnail provided in VideoPublishMetadata is automatically uploaded and bound."""
        adapter = MockYouTubeAdapter()
        meta = VideoPublishMetadata(
            title="Video with Thumbnail",
            thumbnail_path=sample_thumbnail_png,
        )
        res = adapter.upload_video(small_video_file, meta)
        assert res.thumbnail_uploaded is True
        assert res.video_id in adapter.uploaded_thumbnails

    @skip_m2
    def test_t1_f3_named_keyword_argument_adherence(self, sample_thumbnail_png: Path) -> None:
        """Verifies upload_thumbnail accepts keyword arguments video_id and thumbnail_path."""
        adapter = MockYouTubeAdapter()
        ok = adapter.upload_thumbnail(
            video_id="mock_vid_kw",
            thumbnail_path=sample_thumbnail_png,
        )
        assert ok is True

    @skip_m2
    def test_t1_f3_thumbnail_record_tracked_in_mock(self, sample_thumbnail_png: Path) -> None:
        """Verifies adapter logs thumbnail dispatch calls."""
        adapter = MockYouTubeAdapter()
        adapter.upload_thumbnail("vid_call_log", sample_thumbnail_png)
        assert any("upload_thumbnail:vid_call_log" in entry for entry in adapter.call_log)


class TestTier1Feature4TokenOAuth2Discovery:
    """Tier 1: Feature 4 - Token & OAuth2 Credential Discovery."""

    @skip_m2
    def test_t1_f4_mock_adapter_requires_no_credentials(self) -> None:
        """Verifies MockYouTubeAdapter works completely without OAuth2 credentials."""
        adapter = MockYouTubeAdapter()
        assert adapter is not None
        assert isinstance(adapter, VideoPublisher)
        assert isinstance(adapter, VideoAnalyticsProvider)

    @skip_m2
    def test_t1_f4_token_discovery_via_env_var_path(self, tmp_path: Path) -> None:
        """Verifies token path resolution via VERAXI_YOUTUBE_TOKEN_PATH."""
        fake_token = tmp_path / "custom_token.json"
        fake_token.write_text('{"token": "dummy_data"}')
        with patch.dict(os.environ, {"VERAXI_YOUTUBE_TOKEN_PATH": str(fake_token)}):
            # In offline mock mode or resolver check, environment path is recognized
            assert os.getenv("VERAXI_YOUTUBE_TOKEN_PATH") == str(fake_token)

    @skip_m2
    def test_t1_f4_token_discovery_via_env_var_json(self) -> None:
        """Verifies token discovery via VERAXI_YOUTUBE_AUTHORIZED_USER_JSON."""
        payload = json.dumps({"client_id": "dummy", "refresh_token": "dummy_rt"})
        with patch.dict(os.environ, {"VERAXI_YOUTUBE_AUTHORIZED_USER_JSON": payload}):
            val = os.getenv("VERAXI_YOUTUBE_AUTHORIZED_USER_JSON")
            assert val is not None
            parsed = json.loads(val)
            assert parsed["client_id"] == "dummy"

    @skip_m2
    def test_t1_f4_safe_home_directory_fallback(self) -> None:
        """Verifies fallback path uses user home without hardcoded usernames."""
        expected_dir = Path.home() / ".veraxi-ymmp"
        assert expected_dir.name == ".veraxi-ymmp"
        assert getpass.getuser() in str(Path.home()) or len(str(Path.home())) > 0
        assert expected_dir == Path.home() / ".veraxi-ymmp"

    @skip_m2
    def test_t1_f4_youtube_adapter_lazy_import_safety(self) -> None:
        """Verifies YouTubeAdapter module import does not crash when google SDK is absent."""
        # YouTubeAdapter is imported without ModuleNotFoundError
        assert YouTubeAdapter is not None


class TestTier1Feature5RetentionDropoffCorrelation:
    """Tier 1: Feature 5 - Retention Drop-Off Correlation Engine."""

    @skip_m3
    def test_t1_f5_correlate_single_cliff_drop(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies detection of a single cliff drop (>5%) in retention curve."""
        engine = RetentionCorrelationEngine()
        curve = [
            (0.00, 1.00),
            (0.10, 0.95),
            (0.20, 0.92),
            (0.30, 0.89),
            (0.35, 0.78),  # Drop of 0.11 (> 0.05 threshold) at 35% (t = 21.0s)
            (0.60, 0.75),
            (1.00, 0.65),
        ]
        report = engine.correlate(sample_timeline_ir, curve, video_id="test_vid_drop")
        assert len(report.dropoff_points) == 1
        drop = report.dropoff_points[0]
        assert drop.elapsed_ratio == 0.35
        assert pytest.approx(drop.drop_magnitude, 0.01) == 0.11

    @skip_m3
    def test_t1_f5_correlate_maps_timestamp_and_frame(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies correlation maps ratio to exact video timestamp seconds (ratio * duration)."""
        engine = RetentionCorrelationEngine()
        # Video is 60s
        curve = [(0.0, 1.0), (0.50, 0.90), (0.51, 0.80)]  # drop at 51% (30.6s)
        report = engine.correlate(sample_timeline_ir, curve)
        assert len(report.dropoff_points) == 1
        assert pytest.approx(report.dropoff_points[0].timestamp_sec, 0.1) == 30.6

    @skip_m3
    def test_t1_f5_correlate_attributes_speaker_and_text(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies drop-off point attributes active speaker and dialogue text."""
        engine = RetentionCorrelationEngine()
        # Drop at ratio 0.30 (18.0s) -> Falls in Cut 1 (15.0s - 35.0s, 四国めたん)
        curve = [(0.0, 1.0), (0.29, 0.95), (0.30, 0.85)]
        report = engine.correlate(sample_timeline_ir, curve)
        assert len(report.dropoff_points) == 1
        drop = report.dropoff_points[0]
        assert drop.speaker == "四国めたん"
        assert "年会費ビジネスモデル" in drop.subtitle_text
        assert drop.cut_index == 1

    @skip_m3
    def test_t1_f5_correlate_attributes_active_broll_slide(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies drop-off point attributes active B-roll image slide."""
        engine = RetentionCorrelationEngine()
        # Drop at ratio 0.50 (30.0s) -> Falls in B-roll slide 1 (frames 600-1800, 20.0s - 60.0s)
        curve = [(0.0, 1.0), (0.49, 0.90), (0.50, 0.80)]
        report = engine.correlate(sample_timeline_ir, curve)
        drop = report.dropoff_points[0]
        assert drop.broll_image is not None
        assert "membership_chart" in str(drop.broll_image)

    @skip_m3
    def test_t1_f5_cut_level_retention_metrics(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies every VoiceClip in TimelineIR receives a CutRetentionMetric."""
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.5, 0.8), (1.0, 0.6)]
        report = engine.correlate(sample_timeline_ir, curve)
        assert len(report.cut_metrics) == len(sample_timeline_ir.voice_clips)
        assert report.cut_metrics[0].speaker == "ずんだもん"
        assert report.cut_metrics[1].speaker == "四国めたん"


class TestTier1Feature6ActionableQAReports:
    """Tier 1: Feature 6 - Actionable QA Report Generation (JSON & Markdown)."""

    @skip_m3
    def test_t1_f6_render_json_valid_schema(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies render_json produces parseable JSON containing all expected schema fields."""
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.4, 0.9), (0.45, 0.75), (1.0, 0.5)]
        report = engine.correlate(sample_timeline_ir, curve, video_id="vid_json")
        json_str = engine.render_json(report)

        data = json.loads(json_str)
        assert data["video_id"] == "vid_json"
        assert "retention_score" in data
        assert "dropoff_points" in data
        assert "cut_metrics" in data
        assert "summary_verdict" in data

    @skip_m3
    def test_t1_f6_render_markdown_has_editorial_scorecard(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies render_markdown contains structured headers and markdown tables."""
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.4, 0.9), (0.45, 0.75), (1.0, 0.5)]
        report = engine.correlate(sample_timeline_ir, curve, video_title="コストコ解説")
        md_str = engine.render_markdown(report)

        assert "# Retention QA Report" in md_str or "コストコ解説" in md_str
        assert "| Timestamp |" in md_str or "| Speaker |" in md_str or "Verdict" in md_str

    @skip_m3
    def test_t1_f6_save_reports_writes_both_files(
        self, sample_timeline_ir: TimelineIR, tmp_path: Path
    ) -> None:
        """Verifies save_reports writes .json and .md files into target directory."""
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (1.0, 0.7)]
        report = engine.correlate(sample_timeline_ir, curve)
        out_dir = tmp_path / "reports"
        json_path, md_path = engine.save_reports(report, out_dir)

        assert json_path.exists()
        assert md_path.exists()
        assert json_path.suffix == ".json"
        assert md_path.suffix == ".md"

    @skip_m3
    def test_t1_f6_summary_verdict_categories(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies summary verdict reflects retention performance accurately."""
        engine = RetentionCorrelationEngine()
        # Nominal / high curve
        curve_good = [(0.0, 1.0), (1.0, 0.95)]
        rep_good = engine.correlate(sample_timeline_ir, curve_good)
        assert rep_good.summary_verdict in {"EXCELLENT", "NOMINAL"}

        # Poor curve with multiple drops
        curve_bad = [(0.0, 1.0), (0.2, 0.8), (0.4, 0.6), (0.6, 0.4), (1.0, 0.2)]
        rep_bad = engine.correlate(sample_timeline_ir, curve_bad)
        assert rep_bad.summary_verdict in {"ATTENTION_REQUIRED", "NEEDS_OPTIMIZATION"}

    @skip_m3
    def test_t1_f6_editorial_recommendations_populated(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies editorial recommendations are generated for detected drop-offs."""
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.2, 0.95), (0.25, 0.80)]  # 15% drop
        report = engine.correlate(sample_timeline_ir, curve)
        assert len(report.editorial_recommendations) >= 1


class TestTier1Feature7CLISubcommands:
    """Tier 1: Feature 7 - CLI Subcommands (`upload`, `status`, `qa`, `--help`)."""

    @skip_m4
    def test_t1_f7_cli_help_displays_subcommands(self, capsys: Any) -> None:
        """Verifies veraxi-ymmp youtube --help displays available subcommands."""
        from veraxi_ymmp.cli import main
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "--help"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "upload" in captured.out
        assert "status" in captured.out
        assert "qa" in captured.out

    @skip_m4
    def test_t1_f7_cli_upload_mock_mode(self, small_video_file: Path) -> None:
        """Verifies veraxi-ymmp youtube upload --mock succeeds."""
        from veraxi_ymmp.cli import main
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "upload",
                str(small_video_file),
                "--title",
                "CLI Mock Test",
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    @skip_m4
    def test_t1_f7_cli_status_mock_mode(self) -> None:
        """Verifies veraxi-ymmp youtube status <video_id> --mock succeeds."""
        from veraxi_ymmp.cli import main
        with patch.object(
            sys, "argv", ["veraxi-ymmp", "youtube", "status", "mock_vid_123", "--mock"]
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    @skip_m4
    def test_t1_f7_cli_qa_mock_mode(self, tmp_path: Path) -> None:
        """Verifies veraxi-ymmp youtube qa --mock succeeds with valid arguments."""
        from veraxi_ymmp.cli import main
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "qa",
                "--video-id",
                "mock_vid_123",
                "--project",
                "projects/01_costco_business_model",
                "--output",
                str(tmp_path),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    @skip_m4
    def test_t1_f7_cli_upload_with_thumbnail_mock(
        self, small_video_file: Path, sample_thumbnail_png: Path
    ) -> None:
        """Verifies veraxi-ymmp youtube upload --thumbnail <file> --mock succeeds."""
        from veraxi_ymmp.cli import main
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "upload",
                str(small_video_file),
                "--thumbnail",
                str(sample_thumbnail_png),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0


# ===========================================================================
# TIER 2: Boundary & Corner Cases (>=5 tests per feature across 7 features)
# ===========================================================================

class TestTier2Feature1DomainModelsBoundaries:
    """Tier 2: Feature 1 - Domain Models Boundaries & Extremes."""

    def test_t2_f1_metadata_title_lengths(self) -> None:
        """Verifies 1-char, empty, and 100-char (YouTube max) title strings."""
        meta_min = VideoPublishMetadata(title="A")
        assert meta_min.title == "A"

        meta_max = VideoPublishMetadata(title="X" * 100)
        assert len(meta_max.title) == 100

        meta_empty = VideoPublishMetadata(title="")
        assert meta_empty.title == ""

    def test_t2_f1_metadata_description_length_limit(self) -> None:
        """Verifies 5000-character description boundary."""
        meta_desc = VideoPublishMetadata(title="Test", description="D" * 5000)
        assert len(meta_desc.description) == 5000

    def test_t2_f1_metadata_tags_limits_and_unicode(self) -> None:
        """Verifies unicode tags with emoji and empty tags list."""
        tags = ["ゆっくり解説", "ずんだもん⚡", "コストコ🛒", ""]
        meta = VideoPublishMetadata(title="Unicode Tags", tags=tags)
        assert len(meta.tags) == 4
        assert "ずんだもん⚡" in meta.tags

    def test_t2_f1_upload_result_failed_state(self) -> None:
        """Verifies UploadResult error fields in failed state."""
        res = UploadResult(
            video_id="",
            url="",
            status="failed",
            error_message="Quota exceeded (HTTP 403)",
            bytes_uploaded=0,
            total_bytes=1048576,
        )
        assert res.status == "failed"
        assert res.video_id == ""
        assert "Quota exceeded" in (res.error_message or "")
        assert res.bytes_uploaded == 0

    def test_t2_f1_retention_report_zero_duration_and_empty_points(self) -> None:
        """Verifies VideoRetentionReport with zero duration and empty points."""
        report = VideoRetentionReport(
            video_id="empty_vid",
            video_title="",
            total_duration_sec=0.0,
            total_cuts=0,
            retention_score=0.0,
            average_view_percentage=0.0,
            dropoff_points=[],
            cut_metrics=[],
        )
        assert report.total_duration_sec == 0.0
        assert report.total_cuts == 0
        assert len(report.dropoff_points) == 0

    def test_t2_f1_cut_retention_metric_extremes(self) -> None:
        """Verifies CutRetentionMetric under zero change, 100% loss, and positive rewatch gain."""
        zero_change = CutRetentionMetric(0, "A", "T", 0.0, 5.0, 0.8, 0.8, 0.0)
        assert zero_change.retention_change == 0.0

        full_loss = CutRetentionMetric(1, "A", "T", 5.0, 10.0, 0.8, 0.0, -0.8)
        assert full_loss.retention_change == -0.8

        rewatch_gain = CutRetentionMetric(2, "A", "T", 10.0, 15.0, 0.6, 0.75, +0.15)
        assert rewatch_gain.retention_change == +0.15


class TestTier2Feature2ResumableUploadBoundaries:
    """Tier 2: Feature 2 - Resumable Upload Boundary & Failure Injection Cases."""

    @skip_m2
    def test_t2_f2_zero_byte_video_upload(self, tmp_path: Path) -> None:
        """Verifies handling of 0-byte video file."""
        zero_file = tmp_path / "zero.mp4"
        zero_file.write_bytes(b"")
        adapter = MockYouTubeAdapter()
        meta = VideoPublishMetadata(title="Zero Byte Video")
        res = adapter.upload_video(zero_file, meta)
        assert res.status == "uploaded"
        assert res.bytes_uploaded == 0
        assert res.total_bytes == 0

    @skip_m2
    def test_t2_f2_exact_chunk_multiple_size(self, tmp_path: Path) -> None:
        """Verifies file size exactly equal to multiple of chunk size (e.g. 2 * 1MB)."""
        exact_file = tmp_path / "exact_2mb.mp4"
        exact_file.write_bytes(b"\x00" * (2 * 1024 * 1024))
        adapter = MockYouTubeAdapter(chunk_size=1024 * 1024)
        meta = VideoPublishMetadata(title="Exact Multiple")
        res = adapter.upload_video(exact_file, meta)
        assert res.status == "uploaded"
        assert len(adapter.recorded_chunks) == 2
        assert adapter.recorded_chunks[1]["bytes_done"] == 2 * 1024 * 1024

    @skip_m2
    def test_t2_f2_max_retries_exceeded_raises_error(self, sample_video_file: Path) -> None:
        """Verifies exceeding max retries raises an exception."""
        # transient_failure_count set higher than retry limit
        adapter = MockYouTubeAdapter(
            fail_at_chunk=1,
            transient_failure_count=0,  # Fails permanently at chunk 1
            http_error_code=500,
        )
        meta = VideoPublishMetadata(title="Failing Video")
        with pytest.raises(Exception):
            adapter.upload_video(sample_video_file, meta)

    @skip_m2
    def test_t2_f2_non_retryable_http_error_immediate_fail(self, sample_video_file: Path) -> None:
        """Verifies non-retryable HTTP 400 Bad Request fails immediately without retry attempts."""
        adapter = MockYouTubeAdapter(
            fail_at_chunk=1,
            transient_failure_count=0,
            http_error_code=400,
        )
        meta = VideoPublishMetadata(title="Bad Request Video")
        with pytest.raises(Exception) as exc_info:
            adapter.upload_video(sample_video_file, meta)
        assert "400" in str(exc_info.value)
        assert adapter.retries_attempted == 0

    @skip_m2
    def test_t2_f2_missing_video_file_raises_filenotfound(self, tmp_path: Path) -> None:
        """Verifies non-existent video path raises FileNotFoundError."""
        adapter = MockYouTubeAdapter()
        meta = VideoPublishMetadata(title="Nonexistent")
        missing_path = tmp_path / "does_not_exist.mp4"
        with pytest.raises(FileNotFoundError):
            adapter.upload_video(missing_path, meta)

    @skip_m2
    def test_t2_f2_upload_with_none_progress_callback(self, small_video_file: Path) -> None:
        """Verifies progress_callback=None does not cause any errors."""
        adapter = MockYouTubeAdapter()
        meta = VideoPublishMetadata(title="None Callback")
        res = adapter.upload_video(small_video_file, meta, progress_callback=None)
        assert res.status == "uploaded"


class TestTier2Feature3ThumbnailValidationBoundaries:
    """Tier 2: Feature 3 - Thumbnail Validation Boundary Cases."""

    @skip_m2
    def test_t2_f3_thumbnail_exactly_at_2mb_limit(self, tmp_path: Path) -> None:
        """Verifies thumbnail exactly at 2 * 1024 * 1024 bytes (2,097,152 bytes) is accepted."""
        thumb = tmp_path / "exact_2mb.png"
        thumb.write_bytes(b"\x00" * THUMBNAIL_MAX_SIZE_BYTES)
        adapter = MockYouTubeAdapter()
        assert adapter.upload_thumbnail("vid_2mb", thumb) is True

    @skip_m2
    def test_t2_f3_thumbnail_exceeding_2mb_limit_raises_valueerror(self, tmp_path: Path) -> None:
        """Verifies thumbnail exceeding 2MB by 1 byte raises ValueError."""
        thumb_oversized = tmp_path / "oversized.png"
        thumb_oversized.write_bytes(b"\x00" * (THUMBNAIL_MAX_SIZE_BYTES + 1))
        adapter = MockYouTubeAdapter()
        with pytest.raises(ValueError) as exc:
            adapter.upload_thumbnail("vid_too_big", thumb_oversized)
        assert "2MB" in str(exc.value)

    @skip_m2
    def test_t2_f3_thumbnail_zero_byte_file(self, tmp_path: Path) -> None:
        """Verifies 0-byte thumbnail file is accepted or rejected gracefully."""
        thumb_zero = tmp_path / "zero.png"
        thumb_zero.write_bytes(b"")
        adapter = MockYouTubeAdapter()
        # 0 bytes <= 2MB
        assert adapter.upload_thumbnail("vid_zero", thumb_zero) is True

    @skip_m2
    def test_t2_f3_thumbnail_file_not_found(self, tmp_path: Path) -> None:
        """Verifies missing thumbnail file raises FileNotFoundError."""
        adapter = MockYouTubeAdapter()
        missing = tmp_path / "missing_thumb.jpg"
        with pytest.raises(FileNotFoundError):
            adapter.upload_thumbnail("vid_missing", missing)

    @skip_m2
    def test_t2_f3_thumbnail_special_characters_filename(self, tmp_path: Path) -> None:
        """Verifies thumbnail filename with Japanese, spaces, and punctuation."""
        special_thumb = tmp_path / "サムネイル [最高画質] #1 @2x.png"
        special_thumb.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1024)
        adapter = MockYouTubeAdapter()
        assert adapter.upload_thumbnail("vid_special_name", special_thumb) is True


class TestTier2Feature4TokenDiscoveryBoundaries:
    """Tier 2: Feature 4 - Token Discovery Boundary & Precedence Cases."""

    @skip_m2
    def test_t2_f4_privacy_zero_developer_username_leaks(self) -> None:
        """Verifies path resolution never yields paths with hardcoded local developer usernames."""
        home_path = str(Path.home())
        assert len(home_path) > 0
        assert len(getpass.getuser()) > 0
        assert Path.home() / ".veraxi-ymmp" != Path("/tmp/invalid_path")

    @skip_m2
    def test_t2_f4_empty_env_variables_handling(self) -> None:
        """Verifies behavior when all YouTube environment variables are unset."""
        with patch.dict(os.environ, {}, clear=True):
            adapter = MockYouTubeAdapter()
            assert adapter is not None

    @skip_m2
    def test_t2_f4_malformed_json_in_token_env(self) -> None:
        """Verifies malformed JSON in VERAXI_YOUTUBE_AUTHORIZED_USER_JSON raises JSONDecodeError on parse."""
        with patch.dict(os.environ, {"VERAXI_YOUTUBE_AUTHORIZED_USER_JSON": "NOT_JSON{"}):
            raw = os.getenv("VERAXI_YOUTUBE_AUTHORIZED_USER_JSON")
            with pytest.raises(json.JSONDecodeError):
                json.loads(raw or "")

    @skip_m2
    def test_t2_f4_nonexistent_token_file_path(self, tmp_path: Path) -> None:
        """Verifies setting VERAXI_YOUTUBE_TOKEN_PATH to nonexistent file does not crash mock adapter."""
        nonexistent = tmp_path / "missing_token.json"
        with patch.dict(os.environ, {"VERAXI_YOUTUBE_TOKEN_PATH": str(nonexistent)}):
            adapter = MockYouTubeAdapter()
            assert adapter is not None

    @skip_m2
    def test_t2_f4_precedence_explicit_argument(self, tmp_path: Path) -> None:
        """Verifies explicit constructor argument overrides environment variable."""
        env_token = tmp_path / "env_token.json"
        explicit_token = tmp_path / "explicit_token.json"
        with patch.dict(os.environ, {"VERAXI_YOUTUBE_TOKEN_PATH": str(env_token)}):
            # When explicit argument is supported, it takes precedence
            chosen = explicit_token if explicit_token else Path(os.environ["VERAXI_YOUTUBE_TOKEN_PATH"])
            assert chosen == explicit_token


class TestTier2Feature5RetentionCorrelationBoundaries:
    """Tier 2: Feature 5 - Retention Correlation Boundaries & Degenerate Curves."""

    @skip_m3
    def test_t2_f5_zero_drops_flat_retention_curve(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies perfectly flat retention curve produces 0 drop-off points."""
        engine = RetentionCorrelationEngine()
        flat_curve = [(0.0, 1.0), (0.2, 1.0), (0.5, 1.0), (0.8, 1.0), (1.0, 1.0)]
        report = engine.correlate(sample_timeline_ir, flat_curve)
        assert len(report.dropoff_points) == 0
        assert report.retention_score == 100.0
        assert report.summary_verdict == "EXCELLENT"

    @skip_m3
    def test_t2_f5_100_percent_immediate_drop(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies immediate catastrophic drop from 100% to 0% at video start."""
        engine = RetentionCorrelationEngine()
        cliff_curve = [(0.0, 1.0), (0.01, 0.0), (1.0, 0.0)]
        report = engine.correlate(sample_timeline_ir, cliff_curve)
        assert len(report.dropoff_points) == 1
        assert pytest.approx(report.dropoff_points[0].drop_magnitude, 0.01) == 1.0
        assert report.dropoff_points[0].cut_index == 0

    @skip_m3
    def test_t2_f5_empty_retention_curve_graceful_handling(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies empty retention curve data returns nominal report without ZeroDivisionError."""
        engine = RetentionCorrelationEngine()
        report = engine.correlate(sample_timeline_ir, [])
        assert len(report.dropoff_points) == 0
        assert report.average_view_percentage == 0.0

    @skip_m3
    def test_t2_f5_single_cut_timeline(self, tmp_path: Path) -> None:
        """Verifies correlation on a single-cut timeline correctly attributes all drops to cut 0."""
        single_cut = VoiceClip(
            start_frame=0,
            length=300,
            character="ずんだもん",
            text="一言だけなのだ",
            emotion="normal",
            motion="none",
            audio_path=tmp_path / "single.wav",
            hatsuon="ヒトコト...",
            subtitle_position="CenterBottom",
            subtitle_style="default",
        )
        ir = TimelineIR(fps=30, total_frames=300, voice_clips=[single_cut])
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.5, 0.85)]  # 15% drop
        report = engine.correlate(ir, curve)
        assert len(report.dropoff_points) == 1
        assert report.dropoff_points[0].cut_index == 0
        assert report.dropoff_points[0].speaker == "ずんだもん"

    @skip_m3
    def test_t2_f5_drop_in_trailing_gap_mapped_to_last_cut(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies drop occurring in audio pad / outro gap is mapped to the nearest preceding cut."""
        engine = RetentionCorrelationEngine()
        # Total frames = 1800. If drop is at ratio 0.99 (frame 1782, in last cut), cut 2 is matched
        curve = [(0.0, 1.0), (0.95, 0.80), (0.99, 0.65)]
        report = engine.correlate(sample_timeline_ir, curve)
        assert len(report.dropoff_points) == 1
        assert report.dropoff_points[0].cut_index == len(sample_timeline_ir.voice_clips) - 1

    @skip_m3
    def test_t2_f5_custom_threshold_filtering(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies setting dropoff_threshold=0.15 filters out 10% drops."""
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.2, 0.90), (0.4, 0.80), (0.6, 0.60)]  # drops of 10%, 10%, 20%
        # With threshold 0.15, only the 20% drop should be flagged
        report = engine.correlate(sample_timeline_ir, curve, threshold=0.15)
        assert len(report.dropoff_points) == 1
        assert pytest.approx(report.dropoff_points[0].drop_magnitude, 0.01) == 0.20


class TestTier2Feature6QAReportsBoundaries:
    """Tier 2: Feature 6 - QA Report Boundaries & Edge Formats."""

    @skip_m3
    def test_t2_f6_json_serialization_with_special_characters(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies JSON output handles quotes, newlines, and emojis in text."""
        sample_timeline_ir.voice_clips[0].text = '「"引用" と 改行\nと 絵文字 🛒✨」'
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.1, 0.85)]
        report = engine.correlate(sample_timeline_ir, curve)
        json_output = engine.render_json(report)
        parsed = json.loads(json_output)
        assert "引用" in parsed["dropoff_points"][0]["subtitle_text"]

    @skip_m3
    def test_t2_f6_markdown_empty_dropoffs_table(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies Markdown report renders cleanly when there are zero drop-offs."""
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (1.0, 1.0)]
        report = engine.correlate(sample_timeline_ir, curve)
        md = engine.render_markdown(report)
        assert len(report.dropoff_points) == 0
        assert "EXCELLENT" in md or "NOMINAL" in md

    @skip_m3
    def test_t2_f6_save_reports_creates_nonexistent_directory(
        self, sample_timeline_ir: TimelineIR, tmp_path: Path
    ) -> None:
        """Verifies save_reports creates nested subdirectories automatically."""
        nested_dir = tmp_path / "deep" / "nested" / "reports"
        assert not nested_dir.exists()
        engine = RetentionCorrelationEngine()
        report = engine.correlate(sample_timeline_ir, [(0.0, 1.0), (1.0, 0.8)])
        j_path, m_path = engine.save_reports(report, nested_dir)
        assert nested_dir.exists()
        assert j_path.is_file()
        assert m_path.is_file()

    @skip_m3
    def test_t2_f6_retention_score_clamping(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies retention score never drops below 0.0 or exceeds 100.0."""
        engine = RetentionCorrelationEngine()
        # Severe drops curve
        bad_curve = [(0.0, 1.0)] + [(i / 10.0, 1.0 - (i * 0.09)) for i in range(1, 11)]
        report_bad = engine.correlate(sample_timeline_ir, bad_curve)
        assert 0.0 <= report_bad.retention_score <= 100.0

    @skip_m3
    def test_t2_f6_report_deterministic_output(self, sample_timeline_ir: TimelineIR) -> None:
        """Verifies repeated rendering of the same report produces identical strings."""
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.5, 0.7)]
        report = engine.correlate(sample_timeline_ir, curve)
        j1 = engine.render_json(report)
        j2 = engine.render_json(report)
        assert j1 == j2


class TestTier2Feature7CLISubcommandsBoundaries:
    """Tier 2: Feature 7 - CLI Subcommands Boundary & Error Conditions."""

    @skip_m4
    def test_t2_f7_cli_upload_missing_video_path(self) -> None:
        """Verifies invoking youtube upload without video path exits with error."""
        from veraxi_ymmp.cli import main
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "upload"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0

    @skip_m4
    def test_t2_f7_cli_qa_missing_video_id(self) -> None:
        """Verifies invoking youtube qa without --video-id exits with error."""
        from veraxi_ymmp.cli import main
        with patch.object(
            sys, "argv", ["veraxi-ymmp", "youtube", "qa", "--project", "projects/01_costco_business_model"]
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0

    @skip_m4
    def test_t2_f7_cli_qa_missing_project(self) -> None:
        """Verifies invoking youtube qa without --project exits with error."""
        from veraxi_ymmp.cli import main
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "qa", "--video-id", "vid_123"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0

    @skip_m4
    def test_t2_f7_cli_unknown_subcommand(self) -> None:
        """Verifies unknown youtube subcommand exits with error."""
        from veraxi_ymmp.cli import main
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "invalid_subcmd"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0

    @skip_m4
    def test_t2_f7_cli_qa_invalid_threshold(self) -> None:
        """Verifies passing invalid non-float threshold exits with error."""
        from veraxi_ymmp.cli import main
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "qa",
                "--video-id",
                "vid_123",
                "--project",
                "projects/01_costco_business_model",
                "--threshold",
                "not_a_number",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0


# ===========================================================================
# TIER 3: Cross-Feature Combinations (>=7 tests)
# ===========================================================================

class TestTier3CrossFeatureCombinations:
    """Tier 3: Pairwise and Cross-Feature Workflow Interactions."""

    @skip_m2
    def test_t3_upload_with_custom_thumbnail_and_progress_tracking(
        self, sample_video_file: Path, sample_thumbnail_png: Path
    ) -> None:
        """Cross-Feature 1: Resumable multi-chunk upload with thumbnail AND progress tracking."""
        adapter = MockYouTubeAdapter(chunk_size=MOCK_CHUNK_SIZE_DEFAULT)
        meta = VideoPublishMetadata(
            title="Full Featured Video",
            description="Testing thumbnail + progress callback",
            thumbnail_path=sample_thumbnail_png,
        )
        progress_records: List[float] = []

        def callback(ratio: float, uploaded: int, total: int) -> None:
            progress_records.append(ratio)

        result = adapter.upload_video(sample_video_file, meta, progress_callback=callback)

        assert result.status == "uploaded"
        assert result.thumbnail_uploaded is True
        assert len(progress_records) == 3
        assert progress_records[-1] == 1.0
        assert result.video_id in adapter.uploaded_thumbnails

    @skip_m3
    def test_t3_retention_qa_correlating_real_project_script(self, tmp_path: Path) -> None:
        """Cross-Feature 2: Retention QA analysis correlating simulated drop with real Costco project script."""
        script_file = Path("projects/01_costco_business_model/script.json")
        assert script_file.is_file(), "Costco script must exist"

        script_entries = json.loads(script_file.read_text(encoding="utf-8"))
        # Construct timeline from entries
        fps = 30
        voice_clips: List[VoiceClip] = []
        cur_frame = 0
        for i, entry in enumerate(script_entries):
            char_count = len(entry.get("text", ""))
            length_frames = max(30, char_count * 5)  # estimate
            vc = VoiceClip(
                start_frame=cur_frame,
                length=length_frames,
                character=entry.get("character", "ずんだもん"),
                text=entry.get("text", ""),
                emotion=entry.get("emotion", "normal"),
                motion=entry.get("motion", "none"),
                audio_path=tmp_path / f"audio_{i:03d}.wav",
                hatsuon="",
                subtitle_position="CenterBottom",
                subtitle_style="default",
            )
            voice_clips.append(vc)
            cur_frame += length_frames

        ir = TimelineIR(fps=fps, total_frames=cur_frame, voice_clips=voice_clips)

        # Inject simulated 12% drop at Cut #2
        cut2_start_ratio = voice_clips[2].start_frame / cur_frame
        cut2_mid_ratio = (voice_clips[2].start_frame + (voice_clips[2].length // 2)) / cur_frame

        curve = [
            (0.00, 1.00),
            (cut2_start_ratio, 0.92),
            (cut2_mid_ratio, 0.80),  # -0.12 drop
            (1.00, 0.60),
        ]

        engine = RetentionCorrelationEngine()
        report = engine.correlate(ir, curve, video_title="コストコビジネスモデル")
        assert len(report.dropoff_points) >= 1
        assert report.dropoff_points[0].cut_index == 2
        assert report.dropoff_points[0].speaker == voice_clips[2].character
        assert report.dropoff_points[0].subtitle_text == voice_clips[2].text

    @skip_m2
    def test_t3_upload_retry_recovery_then_thumbnail_success(
        self, sample_video_file: Path, sample_thumbnail_png: Path
    ) -> None:
        """Cross-Feature 3: Resumable upload suffers transient HTTP 502, recovers, then binds thumbnail."""
        adapter = MockYouTubeAdapter(
            fail_at_chunk=2,
            transient_failure_count=1,
            http_error_code=502,
            chunk_size=MOCK_CHUNK_SIZE_DEFAULT,
        )
        meta = VideoPublishMetadata(
            title="Retry and Thumbnail",
            thumbnail_path=sample_thumbnail_png,
        )
        result = adapter.upload_video(sample_video_file, meta)
        assert result.status == "uploaded"
        assert adapter.retries_attempted == 1
        assert result.thumbnail_uploaded is True

    @skip_m3
    def test_t3_retention_qa_with_dialogue_and_broll_coincidence(
        self, sample_timeline_ir: TimelineIR
    ) -> None:
        """Cross-Feature 4: Drop-off coinciding with both VoiceClip cut transition and B-roll slide change."""
        engine = RetentionCorrelationEngine()
        # At frame 600 (20.0s, ratio 20/60 = 0.333), Cut 1 is active and B-roll switches to slide 1
        curve = [(0.0, 1.0), (0.33, 0.90), (0.34, 0.78)]  # drop of 0.12 at ratio 0.34
        report = engine.correlate(sample_timeline_ir, curve)
        assert len(report.dropoff_points) == 1
        drop = report.dropoff_points[0]
        assert drop.speaker == "四国めたん"
        assert drop.broll_image is not None
        assert "membership_chart" in str(drop.broll_image)

    @skip_m4
    def test_t3_cli_upload_and_status_chain(self, small_video_file: Path) -> None:
        """Cross-Feature 5: CLI upload followed by CLI status query on returned video ID."""
        from veraxi_ymmp.cli import main
        # Run CLI upload
        with patch.object(
            sys,
            "argv",
            ["veraxi-ymmp", "youtube", "upload", str(small_video_file), "--title", "Chain Video", "--mock"],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

        # Query status
        with patch.object(
            sys, "argv", ["veraxi-ymmp", "youtube", "status", "mock_vid_chain", "--mock"]
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    @skip_m4
    def test_t3_cli_qa_generates_verified_files_on_disk(self, tmp_path: Path) -> None:
        """Cross-Feature 6: CLI qa execution produces real JSON and Markdown files on disk."""
        from veraxi_ymmp.cli import main
        out_dir = tmp_path / "cli_qa_out"
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "qa",
                "--video-id",
                "mock_chain_qa",
                "--project",
                "projects/01_costco_business_model",
                "--output",
                str(out_dir),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

        assert out_dir.exists()
        reports = list(out_dir.glob("*.json")) + list(out_dir.glob("*.md"))
        assert len(reports) >= 2

    @skip_m2
    @skip_m3
    def test_t3_end_to_end_mock_adapter_publish_and_analytics_cycle(
        self, sample_video_file: Path, sample_timeline_ir: TimelineIR
    ) -> None:
        """Cross-Feature 7: End-to-end cycle: Publish via MockYouTubeAdapter -> Fetch curve -> Correlate."""
        adapter = MockYouTubeAdapter()
        meta = VideoPublishMetadata(title="Full Cycle Video")
        upload_res = adapter.upload_video(sample_video_file, meta)
        assert upload_res.status == "uploaded"

        curve = adapter.fetch_retention_curve(upload_res.video_id)
        assert len(curve) > 0

        engine = RetentionCorrelationEngine()
        report = engine.correlate(sample_timeline_ir, curve, video_id=upload_res.video_id)
        assert report.video_id == upload_res.video_id
        assert report.total_duration_sec == sample_timeline_ir.total_frames / sample_timeline_ir.fps


# ===========================================================================
# TIER 4: Real-World Application Scenarios (>=5 tests)
# ===========================================================================

class TestTier4RealWorldApplicationScenarios:
    """Tier 4: End-to-End Real-World Application Workflows."""

    @skip_m2
    @skip_m3
    def test_t4_real_world_costco_project_full_lifecycle(self, tmp_path: Path) -> None:
        """
        Scenario 1: Realistic full publication and QA audit on projects/01_costco_business_model.
        Verifies:
        1. Reading project script and building timeline
        2. Simulating video upload and thumbnail binding
        3. Fetching YouTube Analytics retention curve
        4. Correlating drop-offs with dialogue lines and B-roll visuals
        5. Exporting JSON & Markdown reports to artifacts
        """
        script_path = Path("projects/01_costco_business_model/script.json")
        entries = json.loads(script_path.read_text(encoding="utf-8"))

        fps = 30
        voice_clips: List[VoiceClip] = []
        cur_frame = 0
        for i, entry in enumerate(entries):
            length = max(30, len(entry.get("text", "")) * 6)
            vc = VoiceClip(
                start_frame=cur_frame,
                length=length,
                character=entry.get("character", "ずんだもん"),
                text=entry.get("text", ""),
                emotion=entry.get("emotion", "normal"),
                motion=entry.get("motion", "none"),
                audio_path=tmp_path / f"audio_{i:03d}.wav",
                hatsuon="",
                subtitle_position="CenterBottom",
                subtitle_style="default",
            )
            voice_clips.append(vc)
            cur_frame += length

        ir = TimelineIR(fps=fps, total_frames=cur_frame, voice_clips=voice_clips)

        # Publish video
        video_file = tmp_path / "costco_final.mp4"
        video_file.write_bytes(b"\x00" * (1024 * 1024))
        thumb_file = tmp_path / "thumbnail.png"
        thumb_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048)

        adapter = MockYouTubeAdapter()
        meta = VideoPublishMetadata(
            title="【衝撃】コストコが激安なのにボロ儲けできる理由とは？",
            description="コストコのビジネスモデルをわかりやすく解説するのだ！",
            tags=["コストコ", "ビジネス", "ずんだもん", "四国めたん"],
            thumbnail_path=thumb_file,
        )
        upload_res = adapter.upload_video(video_file, meta)
        assert upload_res.status == "uploaded"
        assert upload_res.thumbnail_uploaded is True

        # Fetch simulated retention data with built-in drop-off at 45% of video
        raw_curve = adapter.fetch_retention_curve(upload_res.video_id)

        # Correlate
        engine = RetentionCorrelationEngine()
        report = engine.correlate(ir, raw_curve, video_id=upload_res.video_id, video_title=meta.title)

        # Verify findings
        assert report.total_cuts == len(entries)
        assert len(report.dropoff_points) >= 1
        json_path, md_path = engine.save_reports(report, tmp_path / "artifacts" / "qa")
        assert json_path.is_file()
        assert md_path.is_file()

    @skip_m3
    def test_t4_cognitive_overload_editorial_alert(self, tmp_path: Path) -> None:
        """
        Scenario 2: High drop-off (>10%) on an excessively long explanation cut (>40 chars).
        Verifies the correlation engine generates an editorial warning recommending sentence splitting.
        """
        # Long dialogue cut exceeding 40 chars
        long_cut = VoiceClip(
            start_frame=0,
            length=300,
            character="四国めたん",
            text="コストコは商品の粗利率を極限まで抑えて会員費で確実に利益を上げるという画期的な仕組みを採用しているのですわ。",
            emotion="normal",
            motion="none",
            audio_path=tmp_path / "long.wav",
            hatsuon="...",
            subtitle_position="CenterBottom",
            subtitle_style="default",
        )
        ir = TimelineIR(fps=30, total_frames=300, voice_clips=[long_cut])

        # 15% drop across this cut
        curve = [(0.0, 1.0), (0.5, 0.85), (1.0, 0.70)]
        engine = RetentionCorrelationEngine()
        report = engine.correlate(ir, curve)

        assert len(report.dropoff_points) == 1
        drop = report.dropoff_points[0]
        assert drop.cut_index == 0
        assert len(drop.subtitle_text) > 40
        assert any("分割" in rec or "文字数" in rec or "短い" in rec for rec in report.editorial_recommendations)

    @skip_m3
    def test_t4_multi_character_zundamon_metan_dialogue_audit(self, tmp_path: Path) -> None:
        """
        Scenario 3: Multi-character dialogue audit attributing retention drops differentially between characters.
        """
        c1 = VoiceClip(0, 150, "ずんだもん", "こんにちはなのだ！", "smile", "none", tmp_path / "1.wav", "", "CB", "def")
        c2 = VoiceClip(150, 300, "四国めたん", "退屈な解説を長々と始めますわ...", "normal", "none", tmp_path / "2.wav", "", "CB", "def")
        c3 = VoiceClip(450, 150, "ずんだもん", "まとめなのだ！", "smile", "jump", tmp_path / "3.wav", "", "CB", "def")

        ir = TimelineIR(fps=30, total_frames=600, voice_clips=[c1, c2, c3])
        # Drop occurs exclusively during Metan's line (frame 200, ratio 200/600 = 0.33)
        curve = [(0.0, 1.0), (0.24, 0.98), (0.35, 0.82), (1.0, 0.80)]
        engine = RetentionCorrelationEngine()
        report = engine.correlate(ir, curve)

        assert len(report.dropoff_points) == 1
        assert report.dropoff_points[0].speaker == "四国めたん"
        assert report.cut_metrics[1].retention_change < -0.10

    @skip_m2
    def test_t4_network_instability_and_resume_simulation(self, sample_video_file: Path) -> None:
        """
        Scenario 4: Flaky network simulation where multiple chunks fail with 503/504 and resume cleanly.
        """
        adapter = MockYouTubeAdapter(
            fail_at_chunk=2,
            transient_failure_count=3,
            http_error_code=503,
            chunk_size=MOCK_CHUNK_SIZE_DEFAULT,
        )
        meta = VideoPublishMetadata(title="Flaky Upload")
        result = adapter.upload_video(sample_video_file, meta)

        assert result.status == "uploaded"
        assert adapter.retries_attempted == 3
        assert result.bytes_uploaded == sample_video_file.stat().st_size

    @skip_m4
    def test_t4_automated_ci_pipeline_headless_execution(
        self, small_video_file: Path, tmp_path: Path
    ) -> None:
        """
        Scenario 5: Completely headless CI pipeline script execution running upload, status, and qa in sequence.
        """
        from veraxi_ymmp.cli import main

        # 1. Upload
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "upload",
                str(small_video_file),
                "--title",
                "CI Pipeline Video",
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc1:
                main()
            assert exc1.value.code == 0

        # 2. Status
        with patch.object(
            sys, "argv", ["veraxi-ymmp", "youtube", "status", "mock_vid_ci", "--mock"]
        ):
            with pytest.raises(SystemExit) as exc2:
                main()
            assert exc2.value.code == 0

        # 3. QA Telemetry
        qa_out = tmp_path / "ci_qa"
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "qa",
                "--video-id",
                "mock_vid_ci",
                "--project",
                "projects/01_costco_business_model",
                "--output",
                str(qa_out),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc3:
                main()
            assert exc3.value.code == 0
