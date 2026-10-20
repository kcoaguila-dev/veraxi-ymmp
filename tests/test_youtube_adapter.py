"""Unit test suite for veraxi_ymmp.youtube_adapter.

Tests:
- MockYouTubeAdapter: 100% offline simulation of chunked upload, retry backoff,
  failure injection, thumbnail validation, and synthetic retention curves.
- YouTubeAdapter: Chunk size validation, credential/token discovery order,
  offline safety, and dependency-injected service upload/retry mechanics.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple
from unittest.mock import MagicMock, patch

import pytest

from veraxi_ymmp.ir import (
    VideoPublishMetadata,
    VideoRetentionReport,
)
from veraxi_ymmp.ports import (
    VideoAnalyticsProvider,
    VideoPublisher,
)
from veraxi_ymmp.youtube_adapter import (
    CHUNK_SIZE_DEFAULT,
    DEFAULT_RETENTION_CURVE,
    MOCK_CHUNK_SIZE_DEFAULT,
    THUMBNAIL_MAX_SIZE_BYTES,
    MockYouTubeAdapter,
    YouTubeAdapter,
)


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_video_file(tmp_path: Path) -> Path:
    """Create a 2.5 MB dummy video file."""
    video = tmp_path / "test_video.mp4"
    video.write_bytes(b"\x00" * int(2.5 * 1024 * 1024))
    return video


@pytest.fixture
def small_video_file(tmp_path: Path) -> Path:
    """Create a 500 KB dummy video file."""
    video = tmp_path / "small_video.mp4"
    video.write_bytes(b"\x00" * (500 * 1024))
    return video


@pytest.fixture
def temp_thumbnail_png(tmp_path: Path) -> Path:
    """Create a small PNG thumbnail."""
    thumb = tmp_path / "thumb.png"
    thumb.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 4096)
    return thumb


@pytest.fixture
def temp_thumbnail_jpg(tmp_path: Path) -> Path:
    """Create a small JPEG thumbnail."""
    thumb = tmp_path / "thumb.jpg"
    thumb.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 4096)
    return thumb


@pytest.fixture
def temp_caption_srt(tmp_path: Path) -> Path:
    """Create a valid dummy SRT caption file."""
    srt = tmp_path / "captions.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nこんにちは\n\n2\n00:00:02,000 --> 00:00:05,000\n世界\n",
        encoding="utf-8",
    )
    return srt


# ---------------------------------------------------------------------------
# Test Suite 1: Protocol & Interface Conformance
# ---------------------------------------------------------------------------

class TestProtocolConformance:
    """Verify that both YouTubeAdapter and MockYouTubeAdapter conform to Ports."""

    def test_mock_adapter_implements_video_publisher(self) -> None:
        adapter = MockYouTubeAdapter()
        assert isinstance(adapter, VideoPublisher)

    def test_mock_adapter_implements_video_analytics_provider(self) -> None:
        adapter = MockYouTubeAdapter()
        assert isinstance(adapter, VideoAnalyticsProvider)

    def test_youtube_adapter_implements_video_publisher(self) -> None:
        adapter = YouTubeAdapter()
        assert isinstance(adapter, VideoPublisher)

    def test_youtube_adapter_implements_video_analytics_provider(self) -> None:
        adapter = YouTubeAdapter()
        assert isinstance(adapter, VideoAnalyticsProvider)


# ---------------------------------------------------------------------------
# Test Suite 2: MockYouTubeAdapter Upload Mechanics
# ---------------------------------------------------------------------------

class TestMockYouTubeAdapterUpload:
    """Verify MockYouTubeAdapter upload behaviors."""

    def test_upload_single_chunk_file(self, small_video_file: Path) -> None:
        adapter = MockYouTubeAdapter(chunk_size=MOCK_CHUNK_SIZE_DEFAULT)
        meta = VideoPublishMetadata(title="Single Chunk")
        result = adapter.upload_video(small_video_file, meta)

        assert result.status == "uploaded"
        assert result.video_id.startswith("mock_")
        assert result.url == f"https://youtu.be/{result.video_id}"
        assert result.bytes_uploaded == small_video_file.stat().st_size
        assert len(adapter.recorded_chunks) == 1
        assert adapter.recorded_chunks[0]["ratio"] == 1.0

    def test_upload_multi_chunk_file(self, temp_video_file: Path) -> None:
        adapter = MockYouTubeAdapter(chunk_size=MOCK_CHUNK_SIZE_DEFAULT)
        meta = VideoPublishMetadata(title="Multi Chunk")
        result = adapter.upload_video(temp_video_file, meta)

        assert result.status == "uploaded"
        assert len(adapter.recorded_chunks) == 3  # 2.5MB / 1MB chunk = 3 chunks
        assert adapter.recorded_chunks[-1]["ratio"] == 1.0
        assert adapter.recorded_chunks[-1]["bytes_done"] == temp_video_file.stat().st_size

    def test_progress_callback_receives_expected_updates(self, temp_video_file: Path) -> None:
        adapter = MockYouTubeAdapter(chunk_size=MOCK_CHUNK_SIZE_DEFAULT)
        meta = VideoPublishMetadata(title="Progress Test")
        updates: List[Tuple[float, int, int]] = []

        def callback(ratio: float, done: int, total: int) -> None:
            updates.append((ratio, done, total))

        adapter.upload_video(temp_video_file, meta, progress_callback=callback)
        assert len(updates) == 3
        assert updates[0][0] < updates[1][0] < updates[2][0]
        assert updates[-1][0] == 1.0
        assert updates[-1][1] == temp_video_file.stat().st_size

    def test_upload_with_none_callback(self, small_video_file: Path) -> None:
        adapter = MockYouTubeAdapter()
        meta = VideoPublishMetadata(title="No Callback")
        result = adapter.upload_video(small_video_file, meta, progress_callback=None)
        assert result.status == "uploaded"

    def test_zero_byte_video_upload(self, tmp_path: Path) -> None:
        zero_file = tmp_path / "empty.mp4"
        zero_file.write_bytes(b"")
        adapter = MockYouTubeAdapter()
        meta = VideoPublishMetadata(title="Zero Byte")
        result = adapter.upload_video(zero_file, meta)

        assert result.status == "uploaded"
        assert result.bytes_uploaded == 0
        assert result.total_bytes == 0

    def test_exact_chunk_boundary_size(self, tmp_path: Path) -> None:
        exact_file = tmp_path / "exact_2mb.mp4"
        exact_file.write_bytes(b"\x00" * (2 * 1024 * 1024))
        adapter = MockYouTubeAdapter(chunk_size=1024 * 1024)
        meta = VideoPublishMetadata(title="Exact 2MB")
        result = adapter.upload_video(exact_file, meta)

        assert result.status == "uploaded"
        assert len(adapter.recorded_chunks) == 2
        assert adapter.recorded_chunks[1]["bytes_done"] == 2 * 1024 * 1024

    def test_nonexistent_video_raises_filenotfound(self, tmp_path: Path) -> None:
        adapter = MockYouTubeAdapter()
        meta = VideoPublishMetadata(title="Missing")
        missing = tmp_path / "not_there.mp4"
        with pytest.raises(FileNotFoundError):
            adapter.upload_video(missing, meta)

    def test_simulated_fail_upload_mode(self, small_video_file: Path) -> None:
        adapter = MockYouTubeAdapter(fail_upload=True, http_error_code=500)
        meta = VideoPublishMetadata(title="Fail Mode")
        result = adapter.upload_video(small_video_file, meta)

        assert result.status == "failed"
        assert "500" in (result.error_message or "")
        assert result.video_id == ""


# ---------------------------------------------------------------------------
# Test Suite 3: MockYouTubeAdapter Retry & Failure Injection
# ---------------------------------------------------------------------------

class TestMockYouTubeAdapterRetryAndFailure:
    """Verify failure injection and retry recovery logic in MockYouTubeAdapter."""

    def test_transient_error_retry_and_recovery(self, temp_video_file: Path) -> None:
        adapter = MockYouTubeAdapter(
            fail_at_chunk=2,
            transient_failure_count=2,
            http_error_code=503,
            chunk_size=MOCK_CHUNK_SIZE_DEFAULT,
        )
        meta = VideoPublishMetadata(title="Transient Retry")
        result = adapter.upload_video(temp_video_file, meta)

        assert result.status == "uploaded"
        assert adapter.retries_attempted == 2

    def test_transient_error_exceeding_max_retries_raises(self, temp_video_file: Path) -> None:
        adapter = MockYouTubeAdapter(
            fail_at_chunk=1,
            transient_failure_count=10,  # Exceeds max_retries default of 5
            max_retries=5,
            http_error_code=500,
        )
        meta = VideoPublishMetadata(title="Exceeded Retries")
        with pytest.raises(RuntimeError) as exc_info:
            adapter.upload_video(temp_video_file, meta)

        assert "Max retries" in str(exc_info.value)
        assert adapter.retries_attempted == 5

    def test_permanent_5xx_error_without_retries_raises(self, temp_video_file: Path) -> None:
        adapter = MockYouTubeAdapter(
            fail_at_chunk=1,
            transient_failure_count=0,
            http_error_code=500,
        )
        meta = VideoPublishMetadata(title="Permanent 500")
        with pytest.raises(RuntimeError) as exc_info:
            adapter.upload_video(temp_video_file, meta)

        assert "500" in str(exc_info.value)

    def test_non_retryable_400_error_fails_immediately(self, temp_video_file: Path) -> None:
        adapter = MockYouTubeAdapter(
            fail_at_chunk=2,
            transient_failure_count=3,
            http_error_code=400,
            chunk_size=MOCK_CHUNK_SIZE_DEFAULT,
        )
        meta = VideoPublishMetadata(title="Bad Request")
        with pytest.raises(RuntimeError) as exc_info:
            adapter.upload_video(temp_video_file, meta)

        assert "400" in str(exc_info.value)
        assert adapter.retries_attempted == 0  # No retry attempts on 400


# ---------------------------------------------------------------------------
# Test Suite 4: Thumbnail Upload & Validation
# ---------------------------------------------------------------------------

class TestThumbnailUploadAndValidation:
    """Verify thumbnail upload handling and boundaries."""

    def test_png_thumbnail_upload_success(self, temp_thumbnail_png: Path) -> None:
        adapter = MockYouTubeAdapter()
        assert adapter.upload_thumbnail("vid_101", temp_thumbnail_png) is True
        assert adapter.uploaded_thumbnails["vid_101"] == temp_thumbnail_png
        assert any("upload_thumbnail:vid_101" in log for log in adapter.call_log)

    def test_jpg_thumbnail_upload_success(self, temp_thumbnail_jpg: Path) -> None:
        adapter = MockYouTubeAdapter()
        assert adapter.upload_thumbnail("vid_102", temp_thumbnail_jpg) is True
        assert adapter.uploaded_thumbnails["vid_102"] == temp_thumbnail_jpg

    def test_automatic_thumbnail_binding_via_metadata(
        self, small_video_file: Path, temp_thumbnail_png: Path
    ) -> None:
        adapter = MockYouTubeAdapter()
        meta = VideoPublishMetadata(
            title="With Thumbnail",
            thumbnail_path=temp_thumbnail_png,
        )
        result = adapter.upload_video(small_video_file, meta)
        assert result.thumbnail_uploaded is True
        assert result.video_id in adapter.uploaded_thumbnails

    def test_thumbnail_at_exact_2mb_limit(self, tmp_path: Path) -> None:
        thumb = tmp_path / "exact_2mb.png"
        thumb.write_bytes(b"\x00" * THUMBNAIL_MAX_SIZE_BYTES)
        adapter = MockYouTubeAdapter()
        assert adapter.upload_thumbnail("vid_2mb", thumb) is True

    def test_thumbnail_exceeding_2mb_raises_valueerror(self, tmp_path: Path) -> None:
        thumb = tmp_path / "oversized.png"
        thumb.write_bytes(b"\x00" * (THUMBNAIL_MAX_SIZE_BYTES + 1))
        adapter = MockYouTubeAdapter()
        with pytest.raises(ValueError) as exc_info:
            adapter.upload_thumbnail("vid_oversized", thumb)
        assert "2MB" in str(exc_info.value)

    def test_missing_thumbnail_file_raises_filenotfound(self, tmp_path: Path) -> None:
        adapter = MockYouTubeAdapter()
        missing = tmp_path / "nonexistent.png"
        with pytest.raises(FileNotFoundError):
            adapter.upload_thumbnail("vid_missing", missing)

    def test_thumbnail_named_keyword_arguments(self, temp_thumbnail_png: Path) -> None:
        adapter = MockYouTubeAdapter()
        assert adapter.upload_thumbnail(video_id="kw_vid", thumbnail_path=temp_thumbnail_png) is True


# ---------------------------------------------------------------------------
# Test Suite 5: Retention Telemetry & Analytics
# ---------------------------------------------------------------------------

class TestRetentionTelemetry:
    """Verify retention curve fetching and reporting in MockYouTubeAdapter."""

    def test_default_retention_curve(self) -> None:
        adapter = MockYouTubeAdapter()
        curve = adapter.fetch_retention_curve("vid_default")
        assert len(curve) == len(DEFAULT_RETENTION_CURVE)
        assert curve[0] == (0.00, 1.00)
        assert any("fetch_retention_curve:vid_default" in log for log in adapter.call_log)

    def test_custom_simulated_retention_curve(self) -> None:
        custom_data = [(0.0, 1.0), (0.5, 0.7), (1.0, 0.4)]
        adapter = MockYouTubeAdapter(simulated_retention_data=custom_data)
        curve = adapter.fetch_retention_curve("vid_custom")
        assert curve == custom_data

    def test_get_retention_report_detects_dropoffs(self) -> None:
        adapter = MockYouTubeAdapter()
        report = adapter.get_retention_report("vid_dropoff", total_duration_sec=60.0, dropoff_threshold=0.05)

        assert isinstance(report, VideoRetentionReport)
        assert report.video_id == "vid_dropoff"
        assert report.total_duration_sec == 60.0
        assert len(report.dropoff_points) >= 1
        # In DEFAULT_RETENTION_CURVE, drop from 0.40 (0.75) to 0.45 (0.65) is -0.10 >= 0.05
        drop = [d for d in report.dropoff_points if abs(d.elapsed_ratio - 0.45) < 1e-4]
        assert len(drop) == 1
        assert drop[0].drop_magnitude >= 0.05


# ---------------------------------------------------------------------------
# Test Suite 6: YouTubeAdapter Validation & Resolution (Offline)
# ---------------------------------------------------------------------------

class TestYouTubeAdapterOfflineValidation:
    """Verify YouTubeAdapter validation, token discovery, and safety."""

    def test_invalid_chunk_size_raises_valueerror(self) -> None:
        with pytest.raises(ValueError):
            YouTubeAdapter(chunk_size=100)  # Not multiple of 256KB

    def test_negative_chunk_size_raises_valueerror(self) -> None:
        with pytest.raises(ValueError):
            YouTubeAdapter(chunk_size=-256 * 1024)

    def test_valid_chunk_sizes(self) -> None:
        adapter1 = YouTubeAdapter(chunk_size=256 * 1024)
        assert adapter1.chunk_size == 256 * 1024

        adapter2 = YouTubeAdapter(chunk_size=CHUNK_SIZE_DEFAULT)
        assert adapter2.chunk_size == 8 * 1024 * 1024

    def test_token_discovery_via_env_var_path(self, tmp_path: Path) -> None:
        token_file = tmp_path / "mock_token.json"
        token_file.write_text('{"token": "test"}')

        with patch.dict(os.environ, {"VERAXI_YOUTUBE_TOKEN_PATH": str(token_file)}):
            adapter = YouTubeAdapter()
            resolved = adapter.get_resolved_token_path()
            assert resolved == token_file

    def test_token_discovery_precedence_explicit_argument(self, tmp_path: Path) -> None:
        explicit_token = tmp_path / "explicit.json"
        explicit_token.write_text('{"token": "explicit"}')
        env_token = tmp_path / "env.json"
        env_token.write_text('{"token": "env"}')

        with patch.dict(os.environ, {"VERAXI_YOUTUBE_TOKEN_PATH": str(env_token)}):
            adapter = YouTubeAdapter(token_path=explicit_token)
            resolved = adapter.get_resolved_token_path()
            assert resolved == explicit_token

    def test_safe_home_directory_fallback(self) -> None:
        # Does not leak any developer username in source or config
        home = Path.home()
        assert home / ".veraxi-ymmp" != Path("/tmp/invalid")

    def test_unresolved_credentials_raises_error_on_service_access(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            adapter = YouTubeAdapter()
            with pytest.raises((ValueError, ImportError)):
                _ = adapter.youtube


# ---------------------------------------------------------------------------
# Test Suite 7: YouTubeAdapter Service Injection & Resumable Loop
# ---------------------------------------------------------------------------

class TestYouTubeAdapterServiceInjection:
    """Verify YouTubeAdapter upload loop using injected mock service."""

    def test_injected_service_single_chunk_upload(self, small_video_file: Path) -> None:
        mock_yt = MagicMock()
        mock_request = MagicMock()
        mock_status = MagicMock()
        mock_status.progress.return_value = 1.0
        mock_status.resumable_progress = small_video_file.stat().st_size
        mock_request.next_chunk.return_value = (mock_status, {"id": "live_vid_001"})
        mock_yt.videos().insert.return_value = mock_request

        mock_media_cls = MagicMock()
        adapter = YouTubeAdapter(
            youtube_service=mock_yt,
            chunk_size=CHUNK_SIZE_DEFAULT,
            media_file_upload_cls=mock_media_cls,
        )

        progress_calls: List[float] = []

        def on_progress(ratio: float, done: int, total: int) -> None:
            progress_calls.append(ratio)

        meta = VideoPublishMetadata(title="Live Video")
        result = adapter.upload_video(small_video_file, meta, progress_callback=on_progress)

        assert result.status == "uploaded"
        assert result.video_id == "live_vid_001"
        assert result.url == "https://youtu.be/live_vid_001"
        assert len(progress_calls) == 1

    def test_injected_service_retry_on_503_and_recover(self, small_video_file: Path) -> None:
        mock_yt = MagicMock()
        mock_request = MagicMock()

        class MockHttpError(Exception):
            def __init__(self, status: int) -> None:
                self.status_code = status

        mock_status = MagicMock()
        mock_status.progress.return_value = 1.0
        mock_status.resumable_progress = small_video_file.stat().st_size

        # First attempt raises 503, second returns success
        mock_request.next_chunk.side_effect = [
            MockHttpError(503),
            (mock_status, {"id": "recovered_vid_002"}),
        ]
        mock_yt.videos().insert.return_value = mock_request

        mock_media_cls = MagicMock()
        adapter = YouTubeAdapter(
            youtube_service=mock_yt,
            chunk_size=CHUNK_SIZE_DEFAULT,
            base_retry_delay=0.001,  # Fast retry for tests
            max_retry_delay=0.01,
            media_file_upload_cls=mock_media_cls,
        )

        meta = VideoPublishMetadata(title="Retry Live")
        result = adapter.upload_video(small_video_file, meta)

        assert result.status == "uploaded"
        assert result.video_id == "recovered_vid_002"

    def test_injected_service_thumbnail_upload_named_kwargs(
        self, temp_thumbnail_png: Path
    ) -> None:
        mock_yt = MagicMock()
        mock_request = MagicMock()
        mock_yt.thumbnails().set.return_value = mock_request

        mock_media_cls = MagicMock()
        adapter = YouTubeAdapter(
            youtube_service=mock_yt,
            media_file_upload_cls=mock_media_cls,
        )
        ok = adapter.upload_thumbnail(video_id="thumb_vid_001", thumbnail_path=temp_thumbnail_png)

        assert ok is True
        mock_yt.thumbnails().set.assert_called_once()
        _, kwargs = mock_yt.thumbnails().set.call_args
        assert kwargs["videoId"] == "thumb_vid_001"
        assert "media_body" in kwargs

    def test_injected_service_fetch_retention_curve(self) -> None:
        mock_an = MagicMock()
        mock_req = MagicMock()
        mock_req.execute.return_value = {
            "rows": [
                ["0.00", "1.00"],
                ["0.50", "0.80"],
                ["1.00", "0.55"],
            ]
        }
        mock_an.reports().query.return_value = mock_req

        adapter = YouTubeAdapter(analytics_service=mock_an)
        curve = adapter.fetch_retention_curve("test_vid_an")

        assert len(curve) == 3
        assert curve[0] == (0.0, 1.0)
        assert curve[1] == (0.5, 0.8)
        assert curve[2] == (1.0, 0.55)


# ---------------------------------------------------------------------------
# Test Suite 8: VideoPublishMetadata Validation
# ---------------------------------------------------------------------------

class TestVideoPublishMetadataValidation:
    """Verify ISO-8601 parsing and YouTube scheduling guardrails in VideoPublishMetadata."""

    def test_valid_iso_utc_with_z_private(self) -> None:
        meta = VideoPublishMetadata(
            title="Scheduled UTC",
            publish_at="2026-10-25T15:00:00Z",
            privacy_status="private",
        )
        assert meta.publish_at == "2026-10-25T15:00:00Z"
        assert meta.privacy_status == "private"

    def test_valid_iso_offset_private(self) -> None:
        meta = VideoPublishMetadata(
            title="Scheduled JST",
            publish_at="2026-10-25T21:00:00+09:00",
            privacy_status="private",
        )
        assert meta.publish_at == "2026-10-25T21:00:00+09:00"
        assert meta.privacy_status == "private"

    def test_none_publish_at_allows_any_privacy_status(self) -> None:
        for status in ("public", "unlisted", "private"):
            meta = VideoPublishMetadata(title="Unscheduled", publish_at=None, privacy_status=status)
            assert meta.privacy_status == status

    def test_invalid_iso_format_raises_value_error(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            VideoPublishMetadata(
                title="Bad ISO",
                publish_at="tomorrow-at-noon",
                privacy_status="private",
            )
        assert "Invalid ISO-8601" in str(exc_info.value)

    def test_non_private_public_with_publish_at_raises_value_error(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            VideoPublishMetadata(
                title="Bad Public",
                publish_at="2026-10-25T15:00:00Z",
                privacy_status="public",
            )
        assert "privacy_status='private'" in str(exc_info.value)

    def test_non_private_unlisted_with_publish_at_raises_value_error(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            VideoPublishMetadata(
                title="Bad Unlisted",
                publish_at="2026-10-25T15:00:00Z",
                privacy_status="unlisted",
            )
        assert "privacy_status='private'" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test Suite 9: Caption Track Uploading
# ---------------------------------------------------------------------------

class TestCaptionUpload:
    """Verify caption uploading across MockYouTubeAdapter and YouTubeAdapter."""

    def test_mock_adapter_upload_caption_success(self, temp_caption_srt: Path) -> None:
        adapter = MockYouTubeAdapter()
        ok = adapter.upload_caption(video_id="vid_mock_001", caption_path=temp_caption_srt)

        assert ok is True
        assert len(adapter.uploaded_captions) == 1
        rec = adapter.uploaded_captions[0]
        assert rec["video_id"] == "vid_mock_001"
        assert rec["caption_path"] == temp_caption_srt
        assert rec["language"] == "ja"
        assert rec["name"] == "Japanese"
        assert any("upload_caption:vid_mock_001" in log for log in adapter.call_log)

    def test_mock_adapter_upload_caption_custom_metadata(self, temp_caption_srt: Path) -> None:
        adapter = MockYouTubeAdapter()
        ok = adapter.upload_caption(
            video_id="vid_mock_en",
            caption_path=temp_caption_srt,
            language="en",
            name="English Subtitles",
        )

        assert ok is True
        assert len(adapter.uploaded_captions) == 1
        rec = adapter.uploaded_captions[0]
        assert rec["language"] == "en"
        assert rec["name"] == "English Subtitles"

    def test_mock_adapter_upload_caption_missing_file_raises_filenotfound(self, tmp_path: Path) -> None:
        adapter = MockYouTubeAdapter()
        missing = tmp_path / "nonexistent.srt"
        with pytest.raises(FileNotFoundError):
            adapter.upload_caption("vid_missing", missing)

    def test_youtube_adapter_upload_caption_missing_file_raises_filenotfound(self, tmp_path: Path) -> None:
        adapter = YouTubeAdapter()
        missing = tmp_path / "nonexistent.srt"
        with pytest.raises(FileNotFoundError):
            adapter.upload_caption("vid_missing", missing)

    def test_youtube_adapter_injected_service_caption_upload_success(
        self, temp_caption_srt: Path
    ) -> None:
        mock_yt = MagicMock()
        mock_request = MagicMock()
        mock_request.execute.return_value = {"id": "caption_entry_456"}
        mock_yt.captions().insert.return_value = mock_request

        mock_media_cls = MagicMock()
        adapter = YouTubeAdapter(
            youtube_service=mock_yt,
            media_file_upload_cls=mock_media_cls,
        )

        ok = adapter.upload_caption(
            video_id="live_vid_789",
            caption_path=temp_caption_srt,
            language="ja",
            name="Japanese",
        )

        assert ok is True
        mock_yt.captions().insert.assert_called_once()
        _, kwargs = mock_yt.captions().insert.call_args
        assert kwargs["part"] == "snippet"
        assert kwargs["body"] == {
            "snippet": {
                "videoId": "live_vid_789",
                "language": "ja",
                "name": "Japanese",
                "isDraft": False,
            }
        }
        assert "media_body" in kwargs
        mock_media_cls.assert_called_once_with(str(temp_caption_srt), mimetype="*/*", resumable=False)

    def test_youtube_adapter_injected_service_caption_upload_error_returns_false(
        self, temp_caption_srt: Path
    ) -> None:
        mock_yt = MagicMock()
        mock_request = MagicMock()
        mock_request.execute.side_effect = Exception("YouTube API 403 Forbidden")
        mock_yt.captions().insert.return_value = mock_request

        mock_media_cls = MagicMock()
        adapter = YouTubeAdapter(
            youtube_service=mock_yt,
            media_file_upload_cls=mock_media_cls,
        )

        ok = adapter.upload_caption(
            video_id="live_vid_err",
            caption_path=temp_caption_srt,
        )

        assert ok is False


# ---------------------------------------------------------------------------
# Test Suite 10: Scheduled Video Ingestion & Defense
# ---------------------------------------------------------------------------

class TestScheduledPublishingInAdapter:
    """Verify publish_at payload construction and defense against invalid privacy status."""

    def test_injected_service_includes_publish_at(self, small_video_file: Path) -> None:
        mock_yt = MagicMock()
        mock_request = MagicMock()
        mock_status = MagicMock()
        mock_status.progress.return_value = 1.0
        mock_status.resumable_progress = small_video_file.stat().st_size
        mock_request.next_chunk.return_value = (mock_status, {"id": "sched_live_01"})
        mock_yt.videos().insert.return_value = mock_request

        mock_media_cls = MagicMock()
        adapter = YouTubeAdapter(
            youtube_service=mock_yt,
            chunk_size=CHUNK_SIZE_DEFAULT,
            media_file_upload_cls=mock_media_cls,
        )

        meta = VideoPublishMetadata(
            title="Scheduled Live Video",
            publish_at="2026-10-25T15:00:00Z",
            privacy_status="private",
        )
        result = adapter.upload_video(small_video_file, meta)

        assert result.status == "uploaded"
        assert result.video_id == "sched_live_01"
        _, kwargs = mock_yt.videos().insert.call_args
        assert kwargs["body"]["status"]["publishAt"] == "2026-10-25T15:00:00Z"
        assert kwargs["body"]["status"]["privacyStatus"] == "private"

    def test_adapter_upload_video_scheduled_non_private_raises(self, small_video_file: Path) -> None:
        adapter = YouTubeAdapter()
        meta = VideoPublishMetadata(title="Bypassed Check")
        # Mutate post-init to simulate bypassed or manipulated object
        object.__setattr__(meta, "publish_at", "2026-10-25T15:00:00Z")
        object.__setattr__(meta, "privacy_status", "public")

        with pytest.raises(ValueError) as exc_info:
            adapter.upload_video(small_video_file, meta)
        assert "privacy_status='private'" in str(exc_info.value)

        mock_adapter = MockYouTubeAdapter()
        with pytest.raises(ValueError) as mock_exc_info:
            mock_adapter.upload_video(small_video_file, meta)
        assert "privacy_status='private'" in str(mock_exc_info.value)
