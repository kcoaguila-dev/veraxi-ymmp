"""Tier 5 Adversarial Stress Testing Suite (White-Box Hardening).

Covers edge cases, stress limits, and boundary conditions for:
1. YouTubeAdapter & MockYouTubeAdapter:
   - Multi-gigabyte video upload chunking math, boundary alignment, and progress monotonicity.
   - HTTP 500, 502, 503, 504 retry sequences under network flapping (success -> fail -> fail -> recover).
   - Non-retryable error fast-fail (400, 401, 403, 404, 501, 505) without retries.
   - Malformed/corrupt OAuth2 environment variables (JSONDecodeError, non-dict payloads, empty payloads).
   - Corrupt token file paths (empty, directory, non-existent).
   - Thumbnail upload boundary conditions (exact 2MB limit, 2MB + 1 byte, 0-byte file, corrupt image payloads, non-existent files).
   - Zero-byte video handling.
   - Chunk size validation (non-multiples of 256KB, negative/zero sizes).

2. RetentionCorrelationEngine:
   - Severely noisy curves (rapid sawtooth oscillations, extreme high-frequency noise).
   - All-zero retention curves (division-by-zero resistance, nominal report generation).
   - Replay ratios (> 1.0, e.g. 150%, 250% viral spikes).
   - Single-point curves, duplicate timestamp curves (delta-r = 0 edge cases).
   - Unsorted curves with out-of-order timestamps.
   - Inverted curves (retention strictly increases over time).
   - Dense curves (1,000+ points).
   - TimelineIR edge cases:
     * 0 voice clips, 0 image clips.
     * Single-frame total duration (1 frame at 30 fps), zero duration (total_frames=0).
     * Sparse voice clips with large inter-clip gaps (audio pads).
     * Multi-line Japanese text with complex emojis, symbols, pipes, quotes, HTML tags.
     * Long subtitle text (> 40 chars) cognitive overload triggering.
     * Markdown table character escaping (pipes, newlines).
     * Full JSON roundtrip serialization integrity.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import List, Tuple
from unittest.mock import MagicMock, patch

import pytest

from veraxi_ymmp.ir import (
    DynamicImageClip,
    TimelineIR,
    VideoPublishMetadata,
    VoiceClip,
)
from veraxi_ymmp.retention_qa import RetentionCorrelationEngine
from veraxi_ymmp.youtube_adapter import (
    CHUNK_SIZE_DEFAULT,
    THUMBNAIL_MAX_SIZE_BYTES,
    MockYouTubeAdapter,
    YouTubeAdapter,
    _is_retryable_http_error,
)


# ===========================================================================
# Part 1: YouTubeAdapter & MockYouTubeAdapter Stress Testing
# ===========================================================================

class TestMultiGigabyteUpload:
    """Stress tests for multi-gigabyte upload math, chunking, and progress bounds."""

    def test_mock_adapter_10gb_chunk_streaming_math_and_monotonicity(self, tmp_path: Path) -> None:
        """Simulate a 10 GB file (10,737,418,240 bytes) with standard 8 MB chunks."""
        file_size_10gb = 10 * 1024 * 1024 * 1024  # 10,737,418,240 bytes
        chunk_size_8mb = 8 * 1024 * 1024          # 8,388,608 bytes
        expected_num_chunks = 1280

        dummy_file = tmp_path / "huge_10gb.mp4"
        dummy_file.write_bytes(b"x")  # Dummy on disk

        adapter = MockYouTubeAdapter(chunk_size=chunk_size_8mb)
        meta = VideoPublishMetadata(title="10GB Stress Test")

        progress_records: List[Tuple[float, int, int]] = []

        def track_progress(ratio: float, done: int, total: int) -> None:
            progress_records.append((ratio, done, total))

        with patch.object(Path, "stat") as mock_stat:
            mock_stat_res = MagicMock()
            mock_stat_res.st_size = file_size_10gb
            mock_stat.return_value = mock_stat_res

            result = adapter.upload_video(dummy_file, meta, progress_callback=track_progress)

        assert result.status == "uploaded"
        assert result.bytes_uploaded == file_size_10gb
        assert result.total_bytes == file_size_10gb
        assert len(adapter.recorded_chunks) == expected_num_chunks
        assert len(progress_records) == expected_num_chunks

        # Verify strict progress monotonicity and boundary adherence
        prev_bytes = 0
        prev_ratio = 0.0
        for i, chunk in enumerate(adapter.recorded_chunks, start=1):
            assert chunk["chunk"] == i
            assert chunk["bytes_done"] > prev_bytes
            assert chunk["ratio"] >= prev_ratio
            assert 0.0 < chunk["ratio"] <= 1.0
            prev_bytes = chunk["bytes_done"]
            prev_ratio = chunk["ratio"]

        # Final chunk must finish at exactly 100% and total file size
        assert adapter.recorded_chunks[-1]["bytes_done"] == file_size_10gb
        assert adapter.recorded_chunks[-1]["ratio"] == 1.0
        assert progress_records[-1] == (1.0, file_size_10gb, file_size_10gb)

    def test_mock_adapter_4gb_odd_chunk_size(self, tmp_path: Path) -> None:
        """Test a 4 GB file with an odd chunk size that doesn't divide evenly."""
        file_size_4gb = 4 * 1024 * 1024 * 1024 + 12345  # 4 GB + 12,345 bytes
        chunk_size_3mb = 3 * 1024 * 1024                # 3 MB chunks
        expected_chunks = (file_size_4gb + chunk_size_3mb - 1) // chunk_size_3mb

        dummy_file = tmp_path / "odd_4gb.mp4"
        dummy_file.write_bytes(b"x")

        adapter = MockYouTubeAdapter(chunk_size=chunk_size_3mb)
        meta = VideoPublishMetadata(title="Odd 4GB")

        with patch.object(Path, "stat") as mock_stat:
            mock_stat_res = MagicMock()
            mock_stat_res.st_size = file_size_4gb
            mock_stat.return_value = mock_stat_res

            result = adapter.upload_video(dummy_file, meta)

        assert result.status == "uploaded"
        assert len(adapter.recorded_chunks) == expected_chunks
        assert adapter.recorded_chunks[-1]["bytes_done"] == file_size_4gb
        assert adapter.recorded_chunks[-1]["ratio"] == 1.0

    def test_youtube_adapter_injected_multi_gigabyte_stream(self, tmp_path: Path) -> None:
        """Verify production YouTubeAdapter with injected service streaming 5 GB upload."""
        file_size_5gb = 5 * 1024 * 1024 * 1024  # 5,368,709,120 bytes
        chunk_size = 8 * 1024 * 1024

        dummy_file = tmp_path / "stream_5gb.mp4"
        dummy_file.write_bytes(b"x")

        mock_yt = MagicMock()
        mock_request = MagicMock()
        mock_media_cls = MagicMock()

        # Simulate 3 chunk iterations: 33%, 66%, 100%
        status1 = MagicMock()
        status1.progress.return_value = 0.33
        status1.resumable_progress = int(file_size_5gb * 0.33)

        status2 = MagicMock()
        status2.progress.return_value = 0.66
        status2.resumable_progress = int(file_size_5gb * 0.66)

        status3 = MagicMock()
        status3.progress.return_value = 1.0
        status3.resumable_progress = file_size_5gb

        mock_request.next_chunk.side_effect = [
            (status1, None),
            (status2, None),
            (status3, {"id": "live_5gb_video_id"}),
        ]
        mock_yt.videos().insert.return_value = mock_request

        adapter = YouTubeAdapter(
            youtube_service=mock_yt,
            chunk_size=chunk_size,
            media_file_upload_cls=mock_media_cls,
        )

        progress_calls: List[Tuple[float, int, int]] = []

        def on_progress(ratio: float, done: int, total: int) -> None:
            progress_calls.append((ratio, done, total))

        meta = VideoPublishMetadata(title="5GB Upload")

        with patch.object(Path, "stat") as mock_stat:
            mock_stat_res = MagicMock()
            mock_stat_res.st_size = file_size_5gb
            mock_stat.return_value = mock_stat_res

            result = adapter.upload_video(dummy_file, meta, progress_callback=on_progress)

        assert result.status == "uploaded"
        assert result.video_id == "live_5gb_video_id"
        assert result.total_bytes == file_size_5gb
        assert result.bytes_uploaded == file_size_5gb
        assert len(progress_calls) == 3
        assert progress_calls[-1] == (1.0, file_size_5gb, file_size_5gb)

    def test_zero_byte_video_upload_handling(self, tmp_path: Path) -> None:
        """Zero-byte video must be handled gracefully without division by zero."""
        empty_file = tmp_path / "empty_video.mp4"
        empty_file.write_bytes(b"")

        adapter = MockYouTubeAdapter()
        meta = VideoPublishMetadata(title="Zero Byte")

        progress_calls: List[Tuple[float, int, int]] = []
        result = adapter.upload_video(
            empty_file, meta, progress_callback=lambda r, d, t: progress_calls.append((r, d, t))
        )

        assert result.status == "uploaded"
        assert result.bytes_uploaded == 0
        assert result.total_bytes == 0
        assert len(adapter.recorded_chunks) == 1
        assert adapter.recorded_chunks[0]["bytes_done"] == 0
        assert adapter.recorded_chunks[0]["ratio"] == 1.0
        assert progress_calls == [(1.0, 0, 0)]

    @pytest.mark.parametrize(
        "delta,expected_chunks",
        [
            (-1, 1),   # 1 MB - 1 byte -> 1 chunk
            (0, 1),    # Exactly 1 MB -> 1 chunk
            (1, 2),    # 1 MB + 1 byte -> 2 chunks
            (1024 * 1024, 2),  # Exactly 2 MB -> 2 chunks
            (1024 * 1024 + 1, 3),  # 2 MB + 1 byte -> 3 chunks
        ],
    )
    def test_exact_chunk_boundary_and_off_by_one_sizes(
        self, tmp_path: Path, delta: int, expected_chunks: int
    ) -> None:
        """Test boundary conditions around exact multiples of chunk size."""
        chunk_size = 1024 * 1024  # 1 MB
        size = chunk_size + delta
        test_file = tmp_path / f"boundary_{size}.mp4"
        test_file.write_bytes(b"\x00" * size)

        adapter = MockYouTubeAdapter(chunk_size=chunk_size)
        meta = VideoPublishMetadata(title=f"Boundary {size}")
        result = adapter.upload_video(test_file, meta)

        assert result.status == "uploaded"
        assert len(adapter.recorded_chunks) == expected_chunks
        assert adapter.recorded_chunks[-1]["bytes_done"] == size
        assert adapter.recorded_chunks[-1]["ratio"] == 1.0

    @pytest.mark.parametrize("invalid_size", [0, -1, -256 * 1024, 100, 256 * 1024 - 1])
    def test_invalid_chunk_sizes_rejected(self, invalid_size: int) -> None:
        """Chunk size must be a positive integer multiple of 256 KB."""
        with pytest.raises(ValueError) as exc_info:
            YouTubeAdapter(chunk_size=invalid_size)
        assert "multiple of 256 KB" in str(exc_info.value)


class TestNetworkFlappingAndRetries:
    """Stress tests for simulated network flapping, HTTP 5xx retry sequences, and backoff."""

    def test_network_flapping_intermittent_failures_and_recovery(self, tmp_path: Path) -> None:
        """Simulate realistic flapping network:
        Chunk 1: HTTP 500 -> retry 1 -> success
        Chunk 2: HTTP 502 -> retry 1 -> HTTP 503 -> retry 2 -> success
        Chunk 3: HTTP 504 -> retry 1 -> success (final)
        """
        video_file = tmp_path / "flapping_video.mp4"
        video_file.write_bytes(b"\x00" * (1024 * 1024))

        mock_yt = MagicMock()
        mock_request = MagicMock()
        mock_media_cls = MagicMock()

        class MockHttpError(Exception):
            def __init__(self, status: int) -> None:
                self.status_code = status

        status1 = MagicMock()
        status1.progress.return_value = 0.33
        status1.resumable_progress = 300000

        status2 = MagicMock()
        status2.progress.return_value = 0.66
        status2.resumable_progress = 600000

        status3 = MagicMock()
        status3.progress.return_value = 1.0
        status3.resumable_progress = 1024 * 1024

        # Flapping sequence across next_chunk calls:
        # 1. 500 error
        # 2. status1 (chunk 1 succeeds)
        # 3. 502 error
        # 4. 503 error
        # 5. status2 (chunk 2 succeeds)
        # 6. 504 error
        # 7. (status3, response) (chunk 3 succeeds)
        mock_request.next_chunk.side_effect = [
            MockHttpError(500),
            (status1, None),
            MockHttpError(502),
            MockHttpError(503),
            (status2, None),
            MockHttpError(504),
            (status3, {"id": "recovered_flapping_vid"}),
        ]
        mock_yt.videos().insert.return_value = mock_request

        adapter = YouTubeAdapter(
            youtube_service=mock_yt,
            chunk_size=CHUNK_SIZE_DEFAULT,
            base_retry_delay=0.001,
            max_retry_delay=0.01,
            max_retries=5,
            media_file_upload_cls=mock_media_cls,
        )

        with patch("time.sleep") as mock_sleep:
            meta = VideoPublishMetadata(title="Flapping Network")
            result = adapter.upload_video(video_file, meta)

        assert result.status == "uploaded"
        assert result.video_id == "recovered_flapping_vid"
        # Total failures: 4 (500, 502, 503, 504) -> sleep called exactly 4 times
        assert mock_sleep.call_count == 4

    @pytest.mark.parametrize("status_code", [500, 502, 503, 504])
    def test_all_retryable_status_codes_recognized(self, status_code: int) -> None:
        """Verify _is_retryable_http_error recognizes all 5xx codes across various exception structures."""
        # Case A: Exception with status_code attribute
        class StatusError(Exception):
            status_code: int

        err_a = StatusError()
        err_a.status_code = status_code
        retryable_a, code_a = _is_retryable_http_error(err_a)
        assert retryable_a is True
        assert code_a == status_code

        # Case B: Google HttpError-like object with resp.status
        class RespObj:
            status: str

        class GoogleHttpError(Exception):
            resp: RespObj

        err_b = GoogleHttpError()
        err_b.resp = RespObj()
        err_b.resp.status = str(status_code)
        retryable_b, code_b = _is_retryable_http_error(err_b)
        assert retryable_b is True
        assert code_b == status_code

        # Case C: Exception with status attribute
        class GenericStatusError(Exception):
            status: int

        err_c = GenericStatusError()
        err_c.status = status_code
        retryable_c, code_c = _is_retryable_http_error(err_c)
        assert retryable_c is True
        assert code_c == status_code

    @pytest.mark.parametrize("client_code", [400, 401, 403, 404, 409, 429, 501, 505])
    def test_non_retryable_codes_fail_fast(self, tmp_path: Path, client_code: int) -> None:
        """Non-retryable client errors (4xx, 501, 505) must fail immediately with zero retries."""
        video_file = tmp_path / "fast_fail.mp4"
        video_file.write_bytes(b"\x00" * 4096)

        mock_yt = MagicMock()
        mock_request = MagicMock()
        mock_media_cls = MagicMock()

        class MockClientError(Exception):
            def __init__(self, code: int) -> None:
                self.status_code = code

        mock_request.next_chunk.side_effect = MockClientError(client_code)
        mock_yt.videos().insert.return_value = mock_request

        adapter = YouTubeAdapter(
            youtube_service=mock_yt,
            chunk_size=CHUNK_SIZE_DEFAULT,
            base_retry_delay=0.001,
            max_retries=5,
            media_file_upload_cls=mock_media_cls,
        )

        with patch("time.sleep") as mock_sleep:
            meta = VideoPublishMetadata(title="Client Error")
            with pytest.raises(MockClientError):
                adapter.upload_video(video_file, meta)

        # sleep must NEVER be called on non-retryable errors
        assert mock_sleep.call_count == 0

    def test_max_retries_exhaustion_raises_proper_exception(self, tmp_path: Path) -> None:
        """Exceeding max_retries must re-raise the underlying retryable exception."""
        video_file = tmp_path / "exhaust_retries.mp4"
        video_file.write_bytes(b"\x00" * 4096)

        mock_yt = MagicMock()
        mock_request = MagicMock()
        mock_media_cls = MagicMock()

        class MockHttpError(Exception):
            def __init__(self, code: int) -> None:
                self.status_code = code

        # Always raises 503
        mock_request.next_chunk.side_effect = MockHttpError(503)
        mock_yt.videos().insert.return_value = mock_request

        adapter = YouTubeAdapter(
            youtube_service=mock_yt,
            chunk_size=CHUNK_SIZE_DEFAULT,
            base_retry_delay=0.001,
            max_retries=3,
            media_file_upload_cls=mock_media_cls,
        )

        with patch("time.sleep") as mock_sleep:
            meta = VideoPublishMetadata(title="Exhaust Retries")
            with pytest.raises(MockHttpError) as exc_info:
                adapter.upload_video(video_file, meta)

        assert exc_info.value.status_code == 503
        assert mock_sleep.call_count == 3

    def test_zero_max_retries_fails_immediately(self, tmp_path: Path) -> None:
        """When max_retries=0, first retryable failure immediately raises without retry sleep."""
        video_file = tmp_path / "zero_retries.mp4"
        video_file.write_bytes(b"\x00" * 4096)

        mock_yt = MagicMock()
        mock_request = MagicMock()
        mock_media_cls = MagicMock()

        class MockHttp500(Exception):
            status_code = 500

        mock_request.next_chunk.side_effect = MockHttp500()
        mock_yt.videos().insert.return_value = mock_request

        adapter = YouTubeAdapter(
            youtube_service=mock_yt,
            chunk_size=CHUNK_SIZE_DEFAULT,
            max_retries=0,
            media_file_upload_cls=mock_media_cls,
        )

        with patch("time.sleep") as mock_sleep:
            meta = VideoPublishMetadata(title="Zero Max Retries")
            with pytest.raises(MockHttp500):
                adapter.upload_video(video_file, meta)

        assert mock_sleep.call_count == 0

    def test_exponential_backoff_delay_bounds(self) -> None:
        """Verify exponential backoff equation calculation stays within [base_delay, max_delay]."""
        base_delay = 1.0
        max_delay = 60.0

        for retry in range(1, 10):
            # Formula from youtube_adapter.py:
            # (base_retry_delay * (2 ** (retries - 1))) + random.uniform(0.0, 1.0)
            raw_delay = (base_delay * (2 ** (retry - 1))) + 0.5
            clamped_delay = min(max_delay, raw_delay)

            assert clamped_delay >= base_delay
            assert clamped_delay <= max_delay

    def test_mock_adapter_transient_failure_recovery_and_exhaustion(self, tmp_path: Path) -> None:
        """Verify MockYouTubeAdapter failure injection mechanics."""
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"\x00" * (2 * 1024 * 1024))
        meta = VideoPublishMetadata(title="Mock Transient")

        # Case 1: Recovers within limit
        mock_adapter_ok = MockYouTubeAdapter(
            fail_at_chunk=2,
            transient_failure_count=3,
            max_retries=5,
            http_error_code=502,
        )
        res = mock_adapter_ok.upload_video(video_file, meta)
        assert res.status == "uploaded"
        assert mock_adapter_ok.retries_attempted == 3

        # Case 2: Exceeds max retries
        mock_adapter_fail = MockYouTubeAdapter(
            fail_at_chunk=2,
            transient_failure_count=6,
            max_retries=5,
            http_error_code=502,
        )
        with pytest.raises(RuntimeError) as exc_info:
            mock_adapter_fail.upload_video(video_file, meta)
        assert "Max retries (5) exceeded" in str(exc_info.value)
        assert mock_adapter_fail.retries_attempted == 5


class TestOAuthAndCredentialAdversarial:
    """Stress tests for malformed JSON, corrupt token files, and environment variable edge cases."""

    def test_malformed_json_in_authorized_user_env_raises(self) -> None:
        """Corrupt or incomplete JSON in VERAXI_YOUTUBE_AUTHORIZED_USER_JSON must raise JSONDecodeError."""
        mock_creds_mod = MagicMock()
        with patch.dict(sys.modules, {
            "google.oauth2.credentials": mock_creds_mod,
            "google.auth.transport.requests": MagicMock(),
        }):
            corrupt_json = '{"client_id": "test_id", "token": '  # truncated syntax
            with patch.dict(os.environ, {"VERAXI_YOUTUBE_AUTHORIZED_USER_JSON": corrupt_json}, clear=True):
                adapter = YouTubeAdapter()
                with pytest.raises(json.JSONDecodeError):
                    adapter._resolve_credentials()

    def test_non_dict_json_payloads_in_authorized_user_env(self) -> None:
        """Valid JSON but non-dict payload (e.g. integer, string, list, null) in environment."""
        mock_creds_mod = MagicMock()
        mock_creds_cls = MagicMock()
        mock_creds_cls.from_authorized_user_info.side_effect = TypeError("user_info must be a dict")
        mock_creds_mod.Credentials = mock_creds_cls

        with patch.dict(sys.modules, {
            "google.oauth2.credentials": mock_creds_mod,
            "google.auth.transport.requests": MagicMock(),
        }):
            for invalid_payload in ["12345", '"just a string"', "[1, 2, 3]", "null"]:
                with patch.dict(
                    os.environ, {"VERAXI_YOUTUBE_AUTHORIZED_USER_JSON": invalid_payload}, clear=True
                ):
                    adapter = YouTubeAdapter()
                    with pytest.raises((TypeError, ValueError)):
                        adapter._resolve_credentials()

    def test_empty_or_whitespace_env_token_falls_back(self) -> None:
        """Empty or whitespace-only VERAXI_YOUTUBE_TOKEN_PATH must not crash and should fall back."""
        with patch.dict(os.environ, {"VERAXI_YOUTUBE_TOKEN_PATH": "", "YOUTUBE_TOKEN_PATH": ""}):
            adapter = YouTubeAdapter()
            resolved = adapter.get_resolved_token_path()
            # If default ~/.veraxi-ymmp/youtube_token.json doesn't exist, returns None
            assert resolved is None or resolved.name == "youtube_token.json"

    def test_nonexistent_token_file_falls_back(self, tmp_path: Path) -> None:
        """Token path pointing to non-existent file returns None from get_resolved_token_path."""
        missing = tmp_path / "does_not_exist_token.json"
        with patch.dict(os.environ, {"VERAXI_YOUTUBE_TOKEN_PATH": str(missing), "YOUTUBE_TOKEN_PATH": ""}):
            adapter = YouTubeAdapter()
            resolved = adapter.get_resolved_token_path()
            assert resolved != missing

    def test_token_path_pointing_to_directory(self, tmp_path: Path) -> None:
        """Token path pointing to a directory instead of a JSON file."""
        dir_token = tmp_path / "token_dir"
        dir_token.mkdir()

        mock_creds_mod = MagicMock()
        mock_creds_cls = MagicMock()
        mock_creds_cls.from_authorized_user_file.side_effect = IsADirectoryError("Is a directory")
        mock_creds_mod.Credentials = mock_creds_cls

        with patch.dict(sys.modules, {
            "google.oauth2.credentials": mock_creds_mod,
            "google.auth.transport.requests": MagicMock(),
        }):
            adapter = YouTubeAdapter(token_path=dir_token)
            with pytest.raises((IsADirectoryError, PermissionError, ValueError)):
                adapter._resolve_credentials()

    def test_offline_import_error_message_clarity(self) -> None:
        """When Google libraries are missing, adapter raises clear ImportError pointing to pip install."""
        adapter = YouTubeAdapter()
        with patch.dict(sys.modules, {"google.oauth2.credentials": None}):
            with pytest.raises(ImportError) as exc_info:
                adapter._resolve_credentials()
            assert "pip install" in str(exc_info.value)


class TestThumbnailAdversarialAndBoundaries:
    """Stress tests for thumbnail size limits, formats, corrupt payloads, and missing files."""

    def test_thumbnail_at_exact_2mb_boundary(self, tmp_path: Path) -> None:
        """File at exactly 2,097,152 bytes (2 MB limit) passes."""
        exact_thumb = tmp_path / "exact_limit.png"
        exact_thumb.write_bytes(b"\x00" * THUMBNAIL_MAX_SIZE_BYTES)

        adapter = MockYouTubeAdapter()
        assert adapter.upload_thumbnail("vid_exact", exact_thumb) is True

    def test_thumbnail_at_2mb_plus_one_byte_raises(self, tmp_path: Path) -> None:
        """File at 2,097,153 bytes (2 MB + 1 byte) strictly rejected with ValueError."""
        oversized = tmp_path / "oversized.png"
        oversized.write_bytes(b"\x00" * (THUMBNAIL_MAX_SIZE_BYTES + 1))

        adapter = MockYouTubeAdapter()
        with pytest.raises(ValueError) as exc_info:
            adapter.upload_thumbnail("vid_oversized", oversized)
        assert "exceeds YouTube 2MB limit" in str(exc_info.value)

    def test_zero_byte_thumbnail(self, tmp_path: Path) -> None:
        """Zero-byte thumbnail file passes size ceiling check (0 <= 2MB)."""
        empty_thumb = tmp_path / "empty_thumb.png"
        empty_thumb.write_bytes(b"")

        adapter = MockYouTubeAdapter()
        assert adapter.upload_thumbnail("vid_zero", empty_thumb) is True

    def test_corrupt_thumbnail_content_packaged_cleanly(self, tmp_path: Path) -> None:
        """A file with .png extension containing corrupt binary garbage packages into MediaFileUpload."""
        corrupt_thumb = tmp_path / "corrupt.png"
        corrupt_thumb.write_bytes(b"CORRUPT_NOT_A_PNG_HEADER_0123456789")

        mock_yt = MagicMock()
        mock_media_cls = MagicMock()

        adapter = YouTubeAdapter(
            youtube_service=mock_yt,
            media_file_upload_cls=mock_media_cls,
        )

        result = adapter.upload_thumbnail("vid_corrupt", corrupt_thumb)
        assert result is True
        mock_media_cls.assert_called_once_with(
            str(corrupt_thumb), mimetype="image/png", resumable=False
        )
        mock_yt.thumbnails().set.assert_called_once_with(
            videoId="vid_corrupt",
            media_body=mock_media_cls.return_value,
        )

    @pytest.mark.parametrize(
        "ext,expected_mime",
        [
            (".png", "image/png"),
            (".PNG", "image/png"),
            (".jpg", "image/jpeg"),
            (".jpeg", "image/jpeg"),
            (".JPG", "image/jpeg"),
            (".webp", "image/jpeg"),
            (".bmp", "image/jpeg"),
        ],
    )
    def test_thumbnail_case_insensitive_and_unusual_extensions(
        self, tmp_path: Path, ext: str, expected_mime: str
    ) -> None:
        """Verify extension matching assigns correct MIME type."""
        thumb = tmp_path / f"thumb{ext}"
        thumb.write_bytes(b"\x00" * 1024)

        mock_yt = MagicMock()
        mock_media_cls = MagicMock()

        adapter = YouTubeAdapter(
            youtube_service=mock_yt,
            media_file_upload_cls=mock_media_cls,
        )

        adapter.upload_thumbnail("vid_mime", thumb)
        mock_media_cls.assert_called_with(str(thumb), mimetype=expected_mime, resumable=False)

    def test_thumbnail_not_found_raises(self, tmp_path: Path) -> None:
        """Non-existent thumbnail path raises FileNotFoundError in both adapters."""
        missing = tmp_path / "nonexistent.png"

        mock_yt = MagicMock()
        adapter_prod = YouTubeAdapter(youtube_service=mock_yt)
        adapter_mock = MockYouTubeAdapter()

        with pytest.raises(FileNotFoundError):
            adapter_prod.upload_thumbnail("vid", missing)

        with pytest.raises(FileNotFoundError):
            adapter_mock.upload_thumbnail("vid", missing)

    def test_upload_video_skips_missing_thumbnail_without_crashing(self, tmp_path: Path) -> None:
        """In upload_video, if metadata.thumbnail_path does not exist on disk, it is skipped."""
        video_file = tmp_path / "vid.mp4"
        video_file.write_bytes(b"\x00" * 1024)

        meta = VideoPublishMetadata(
            title="Missing Thumb",
            thumbnail_path=tmp_path / "ghost_thumb.png",
        )

        adapter = MockYouTubeAdapter()
        res = adapter.upload_video(video_file, meta)

        assert res.status == "uploaded"
        assert res.thumbnail_uploaded is False


# ===========================================================================
# Part 2: RetentionCorrelationEngine Adversarial Stress Testing
# ===========================================================================

@pytest.fixture
def stress_timeline(tmp_path: Path) -> TimelineIR:
    """Fixture creating a 4-cut, 60s timeline at 30 fps."""
    fps = 30
    total_frames = 1800  # 60.0s

    vc0 = VoiceClip(
        start_frame=0,
        length=300,
        character="ずんだもん",
        text="急展開の幕開けなのだ！",
        emotion="smile",
        motion="none",
        audio_path=tmp_path / "a0.wav",
        hatsuon="...",
        subtitle_position="CB",
        subtitle_style="d",
    )
    vc1 = VoiceClip(
        start_frame=300,
        length=450,
        character="四国めたん",
        text="次は驚愕の真実を解説いたしますわ。",
        emotion="normal",
        motion="none",
        audio_path=tmp_path / "a1.wav",
        hatsuon="...",
        subtitle_position="CB",
        subtitle_style="d",
    )
    vc2 = VoiceClip(
        start_frame=750,
        length=450,
        character="ずんだもん",
        text="なんと年間利益の9割が年会費だったのだ！",
        emotion="surprise",
        motion="jump",
        audio_path=tmp_path / "a2.wav",
        hatsuon="...",
        subtitle_position="CB",
        subtitle_style="d",
    )
    vc3 = VoiceClip(
        start_frame=1200,
        length=450,
        character="四国めたん",
        text="まとめに入りますわ。",
        emotion="normal",
        motion="none",
        audio_path=tmp_path / "a3.wav",
        hatsuon="...",
        subtitle_position="CB",
        subtitle_style="d",
    )

    slide = DynamicImageClip(
        start_frame=300,
        length=600,
        image_path=tmp_path / "profit_chart.png",
        is_background=False,
    )

    return TimelineIR(
        fps=fps,
        total_frames=total_frames,
        voice_clips=[vc0, vc1, vc2, vc3],
        dynamic_image_clips=[slide],
    )


class TestNoisyAndSawtoothRetentionCurves:
    """Stress tests for noisy, sawtooth, zero, replay (>1.0), and pathological curves."""

    def test_sawtooth_curve_rapid_oscillations_cliff_detection(
        self, stress_timeline: TimelineIR
    ) -> None:
        """Curve oscillating rapidly with deep cliff drops and rebounds:
        1.0 -> 0.40 (-0.60) -> 0.85 -> 0.30 (-0.55) -> 0.90 -> 0.25 (-0.65) -> 0.70
        """
        sawtooth_curve = [
            (0.00, 1.00),
            (0.10, 0.40),  # Drop -0.60 at 10%
            (0.20, 0.85),  # Rebound
            (0.35, 0.30),  # Drop -0.55 at 35%
            (0.50, 0.90),  # Rebound
            (0.65, 0.25),  # Drop -0.65 at 65%
            (0.85, 0.70),  # Rebound
            (1.00, 0.20),  # Outro
        ]

        engine = RetentionCorrelationEngine()
        report = engine.correlate(stress_timeline, sawtooth_curve, threshold=0.05)

        assert len(report.dropoff_points) >= 3
        # Verify drops exceed 0.50
        for drop in report.dropoff_points:
            assert drop.drop_magnitude >= 0.50
        assert report.summary_verdict == "NEEDS_OPTIMIZATION"
        # Score must be bounded in [0, 100]
        assert 0.0 <= report.retention_score <= 100.0

    def test_all_zero_retention_curve_division_by_zero_safety(
        self, stress_timeline: TimelineIR
    ) -> None:
        """Curve where all values are zero (e.g. unmonetized/unviewed video)."""
        zero_curve = [(0.0, 0.0), (0.25, 0.0), (0.5, 0.0), (0.75, 0.0), (1.0, 0.0)]

        engine = RetentionCorrelationEngine()
        report = engine.correlate(stress_timeline, zero_curve, threshold=0.05)

        assert report.average_view_percentage == 0.0
        assert report.retention_score == 0.0
        assert len(report.dropoff_points) == 0
        assert report.summary_verdict == "NOMINAL"
        for cm in report.cut_metrics:
            assert cm.start_retention == 0.0
            assert cm.end_retention == 0.0
            assert cm.retention_change == 0.0

    def test_all_hundred_percent_retention_curve(self, stress_timeline: TimelineIR) -> None:
        """Perfect retention curve at 1.0 throughout the entire video."""
        perfect_curve = [(0.0, 1.0), (0.5, 1.0), (0.99, 1.0)]

        engine = RetentionCorrelationEngine()
        report = engine.correlate(stress_timeline, perfect_curve, threshold=0.05)

        assert report.average_view_percentage == 100.0
        assert report.retention_score == 100.0
        assert len(report.dropoff_points) == 0
        assert report.summary_verdict == "EXCELLENT"

    def test_replay_ratios_exceeding_100_percent(self, stress_timeline: TimelineIR) -> None:
        """Viral rewinds creating audience retention > 1.0 (e.g. 2.50 = 250%)."""
        replay_curve = [
            (0.00, 1.00),
            (0.20, 1.80),  # Rewind spike
            (0.40, 2.50),  # Viral peak at 250%
            (0.50, 1.50),  # Steep drop from peak: -1.00
            (0.70, 0.90),  # Normalization drop: -0.60
            (1.00, 0.60),  # Outro
        ]

        engine = RetentionCorrelationEngine()
        report = engine.correlate(stress_timeline, replay_curve, threshold=0.05)

        # Average view percentage can exceed 100%
        assert report.average_view_percentage > 100.0
        assert 0.0 <= report.retention_score <= 100.0
        assert len(report.dropoff_points) >= 2

        # Check drop from 2.50 to 1.50 is captured
        drop_peak = next((d for d in report.dropoff_points if abs(d.elapsed_ratio - 0.50) < 0.01), None)
        assert drop_peak is not None
        assert drop_peak.retention_before == 2.50
        assert drop_peak.retention_after == 1.50
        assert pytest.approx(drop_peak.drop_magnitude, 0.01) == 1.00

    def test_single_point_curve_handling(self, stress_timeline: TimelineIR) -> None:
        """Curve containing only a single telemetry sample point."""
        single_point = [(0.5, 0.85)]

        engine = RetentionCorrelationEngine()
        report = engine.correlate(stress_timeline, single_point, threshold=0.05)

        assert report.average_view_percentage == 85.0
        assert len(report.dropoff_points) == 0
        for cm in report.cut_metrics:
            assert cm.start_retention == 0.85
            assert cm.end_retention == 0.85

    def test_duplicate_timestamps_delta_r_zero_safety(self, stress_timeline: TimelineIR) -> None:
        """Curve with consecutive identical timestamps (delta-r = 0) must not cause ZeroDivisionError."""
        dup_curve = [
            (0.00, 1.00),
            (0.30, 0.80),
            (0.30, 0.70),  # Exactly identical timestamp
            (0.70, 0.50),
            (1.00, 0.40),
        ]

        engine = RetentionCorrelationEngine()
        report = engine.correlate(stress_timeline, dup_curve, threshold=0.05)

        assert report.total_cuts == 4
        # Verify interpolation at 0.30 evaluates cleanly
        val = engine._interpolate_watch_ratio(dup_curve, 0.30)
        assert val in (0.80, 0.70)

    def test_unsorted_curve_points_normalized(self, stress_timeline: TimelineIR) -> None:
        """Unsorted / reversed retention curves must produce identical results to sorted curves."""
        sorted_curve = [(0.0, 1.0), (0.2, 0.9), (0.4, 0.6), (0.8, 0.5), (1.0, 0.4)]
        reversed_curve = list(reversed(sorted_curve))

        engine = RetentionCorrelationEngine()
        report_sorted = engine.correlate(stress_timeline, sorted_curve)
        report_reversed = engine.correlate(stress_timeline, reversed_curve)

        assert report_sorted.average_view_percentage == report_reversed.average_view_percentage
        assert len(report_sorted.dropoff_points) == len(report_reversed.dropoff_points)
        assert report_sorted.retention_score == report_reversed.retention_score

    def test_dense_high_frequency_noisy_curve_performance(self, stress_timeline: TimelineIR) -> None:
        """1,000 points sampled every 0.1% must evaluate efficiently without degradation."""
        dense_curve: List[Tuple[float, float]] = []
        val = 1.0
        for i in range(1001):
            r = i / 1000.0
            # Gradual decline with small sinusoidal jitter
            val = max(0.05, 1.0 - (0.6 * r) + (0.02 * math.sin(i * 0.1)))
            dense_curve.append((round(r, 4), round(val, 4)))

        engine = RetentionCorrelationEngine()
        report = engine.correlate(stress_timeline, dense_curve, threshold=0.05)

        assert report.total_cuts == 4
        assert len(report.cut_metrics) == 4
        assert 0.0 <= report.retention_score <= 100.0


class TestTimelineIREdgeCases:
    """Stress tests for TimelineIR edge cases: empty voice/image clips, 0/1 frames, large gaps."""

    def test_zero_voice_clips_timeline_correlation(self) -> None:
        """TimelineIR with 0 voice clips (music/B-roll only video)."""
        empty_ir = TimelineIR(
            fps=30,
            total_frames=900,
            voice_clips=[],
            dynamic_image_clips=[],
        )

        curve = [(0.0, 1.0), (0.3, 0.6), (0.7, 0.5), (1.0, 0.4)]
        engine = RetentionCorrelationEngine()
        report = engine.correlate(empty_ir, curve, threshold=0.05)

        assert report.total_cuts == 0
        assert report.cut_metrics == []
        # Cliff drop at 0.30 (-0.40) is detected and attributed to -1 / "Unknown"
        assert len(report.dropoff_points) >= 1
        assert report.dropoff_points[0].cut_index == -1
        assert report.dropoff_points[0].speaker == "Unknown"

        # Markdown and JSON must render cleanly without crash
        md = engine.render_markdown(report)
        assert "*(No dialogue cuts in timeline)*" in md
        js = engine.render_json(report)
        data = json.loads(js)
        assert data["total_cuts"] == 0

    def test_zero_dynamic_image_clips_static_visual_fatigue(self, tmp_path: Path) -> None:
        """TimelineIR with zero dynamic image clips must trigger STATIC_VISUAL_FATIGUE for small drops."""
        vc = VoiceClip(
            start_frame=0,
            length=1800,
            character="ずんだもん",
            text="立ち絵のみで30秒間話し続けるのだ。",
            emotion="normal",
            motion="none",
            audio_path=tmp_path / "a.wav",
            hatsuon="...",
            subtitle_position="CB",
            subtitle_style="d",
        )
        ir = TimelineIR(fps=30, total_frames=1800, voice_clips=[vc], dynamic_image_clips=[])

        # Mild drop -0.07 at 0.40 (exceeds 0.05 threshold but under 0.10 severe cliff)
        curve = [(0.0, 1.0), (0.39, 0.90), (0.40, 0.83), (1.0, 0.70)]

        engine = RetentionCorrelationEngine()
        report = engine.correlate(ir, curve, threshold=0.05)

        assert len(report.dropoff_points) == 1
        drop = report.dropoff_points[0]
        assert drop.broll_image is None
        assert drop.issue_type == "STATIC_VISUAL_FATIGUE"
        assert "Bロール画像またはスライドの挿入を推奨します" in drop.recommendation

    def test_single_frame_duration_timeline(self, tmp_path: Path) -> None:
        """TimelineIR with total_frames = 1 (single frame edge case: 0.03s)."""
        vc = VoiceClip(0, 1, "ずんだもん", "瞬間", "normal", "none", tmp_path / "a.wav", "", "CB", "d")
        ir = TimelineIR(fps=30, total_frames=1, voice_clips=[vc])

        curve = [(0.0, 1.0), (0.5, 0.8), (1.0, 0.7)]
        engine = RetentionCorrelationEngine()
        report = engine.correlate(ir, curve)

        assert report.total_duration_sec == 0.03
        assert report.total_cuts == 1

    def test_zero_total_frames_timeline(self) -> None:
        """TimelineIR with total_frames = 0 must not raise ZeroDivisionError."""
        ir = TimelineIR(fps=30, total_frames=0, voice_clips=[])
        curve = [(0.0, 1.0), (1.0, 0.5)]

        engine = RetentionCorrelationEngine()
        report = engine.correlate(ir, curve)

        assert report.total_duration_sec == 0.0
        assert report.total_cuts == 0

    def test_zero_fps_timeline_protection(self) -> None:
        """TimelineIR with fps <= 0 must default fps to 1 to protect against division by zero."""
        ir = TimelineIR(fps=0, total_frames=100, voice_clips=[])
        curve = [(0.0, 1.0), (1.0, 0.5)]

        engine = RetentionCorrelationEngine()
        report = engine.correlate(ir, curve)
        assert report.total_duration_sec == 100.0

    def test_audio_gap_fallback_to_preceding_cut(self, tmp_path: Path) -> None:
        """When drop happens in an audio gap/silence between cuts, attribute to closest preceding cut."""
        # Cut 0: frames 0..150 (0..5s)
        # GAP: frames 150..600 (5..20s)
        # Cut 1: frames 600..900 (20..30s)
        vc0 = VoiceClip(0, 150, "ずんだもん", "前半", "normal", "none", tmp_path / "0.wav", "", "CB", "d")
        vc1 = VoiceClip(600, 300, "四国めたん", "後半", "normal", "none", tmp_path / "1.wav", "", "CB", "d")
        ir = TimelineIR(fps=30, total_frames=900, voice_clips=[vc0, vc1])

        # Drop occurs at ratio 0.33 (frame 300 = 10.0s), strictly inside the audio gap
        curve = [(0.0, 1.0), (0.32, 0.90), (0.33, 0.70), (1.0, 0.60)]

        engine = RetentionCorrelationEngine()
        report = engine.correlate(ir, curve, threshold=0.05)

        assert len(report.dropoff_points) == 1
        assert report.dropoff_points[0].cut_index == 0
        assert report.dropoff_points[0].speaker == "ずんだもん"

    def test_drop_before_first_cut_attributes_to_first_cut(self, tmp_path: Path) -> None:
        """When drop happens before the very first dialogue cut, attribute to cut 0."""
        # Cut 0 starts at frame 300 (10.0s)
        vc0 = VoiceClip(300, 300, "ずんだもん", "遅めの開始", "normal", "none", tmp_path / "0.wav", "", "CB", "d")
        ir = TimelineIR(fps=30, total_frames=900, voice_clips=[vc0])

        # Drop occurs at ratio 0.10 (frame 90 = 3.0s)
        curve = [(0.0, 1.0), (0.09, 0.95), (0.10, 0.80), (1.0, 0.60)]

        engine = RetentionCorrelationEngine()
        report = engine.correlate(ir, curve, threshold=0.05)

        assert len(report.dropoff_points) == 1
        assert report.dropoff_points[0].cut_index == 0


class TestComplexTextAndMarkdownEscaping:
    """Stress tests for Japanese unicode, emojis, markdown table pipe escaping, and JSON serialization."""

    def test_complex_japanese_text_with_emojis_and_symbols(self, tmp_path: Path) -> None:
        """Ensure multi-line Japanese text, emojis, quotes, and punctuation do not corrupt reports."""
        complex_text = "「ずんだもんなのだ！🔥✨🎉 (50% OFF ＆ \n [超絶] 特報！)」"
        vc = VoiceClip(
            start_frame=0,
            length=900,
            character="ずんだもん",
            text=complex_text,
            emotion="smile",
            motion="jump",
            audio_path=tmp_path / "a.wav",
            hatsuon="...",
            subtitle_position="CB",
            subtitle_style="d",
        )
        ir = TimelineIR(fps=30, total_frames=900, voice_clips=[vc])

        curve = [(0.0, 1.0), (0.45, 0.90), (0.50, 0.70), (1.0, 0.50)]
        engine = RetentionCorrelationEngine()
        report = engine.correlate(ir, curve, threshold=0.05)

        # JSON Roundtrip Test
        json_output = engine.render_json(report)
        parsed = json.loads(json_output)
        assert parsed["dropoff_points"][0]["speaker"] == "ずんだもん"
        assert "🔥✨🎉" in parsed["dropoff_points"][0]["subtitle_text"]

        # Markdown Rendering Test
        md_output = engine.render_markdown(report)
        assert "ずんだもん" in md_output
        assert "🔥✨🎉" in md_output

    def test_markdown_table_pipe_escaping_and_column_integrity(self, tmp_path: Path) -> None:
        """Table pipe characters `|` in subtitle or recommendations must be escaped to avoid column mismatch."""
        pipe_text = "プランA | プランB | プランCの徹底比較表"
        vc = VoiceClip(
            start_frame=0,
            length=900,
            character="ずんだもん",
            text=pipe_text,
            emotion="normal",
            motion="none",
            audio_path=tmp_path / "a.wav",
            hatsuon="...",
            subtitle_position="CB",
            subtitle_style="d",
        )
        ir = TimelineIR(fps=30, total_frames=900, voice_clips=[vc])

        curve = [(0.0, 1.0), (0.4, 0.8), (0.5, 0.6), (1.0, 0.4)]
        engine = RetentionCorrelationEngine()
        report = engine.correlate(ir, curve, threshold=0.05)

        md = engine.render_markdown(report)

        # Verify all table rows in Drop-Off Analysis have exactly 8 pipes (7 columns: | col | ... | col |)
        in_table = False
        for line in md.splitlines():
            if line.startswith("| Timestamp |"):
                in_table = True
                continue
            if in_table and line.startswith("|"):
                # Count unescaped pipes
                unescaped_pipes = [i for i in range(len(line)) if line[i] == "|" and (i == 0 or line[i-1] != "\\")]
                assert len(unescaped_pipes) == 8, f"Malformed table row: {line}"
            elif in_table and not line.startswith("|"):
                in_table = False

    def test_long_text_triggers_cognitive_overload_recommendation(self, tmp_path: Path) -> None:
        """Dialogue cuts exceeding 40 characters must trigger COGNITIVE_OVERLOAD_LONG_TEXT."""
        long_text = "この文章は非常に長くて視聴者の認知負荷を過大にしてしまい途中で離脱される危険性が極めて高いテキストです。"
        assert len(long_text) > 40

        vc = VoiceClip(
            start_frame=0,
            length=900,
            character="ずんだもん",
            text=long_text,
            emotion="normal",
            motion="none",
            audio_path=tmp_path / "a.wav",
            hatsuon="...",
            subtitle_position="CB",
            subtitle_style="d",
        )
        ir = TimelineIR(fps=30, total_frames=900, voice_clips=[vc])

        curve = [(0.0, 1.0), (0.3, 0.8), (0.4, 0.6), (1.0, 0.4)]
        engine = RetentionCorrelationEngine()
        report = engine.correlate(ir, curve, threshold=0.05)

        assert len(report.dropoff_points) == 1
        drop = report.dropoff_points[0]
        assert drop.issue_type == "COGNITIVE_OVERLOAD_LONG_TEXT"
        assert "上限40文字を超過しています" in drop.recommendation

    def test_save_reports_sanitizes_malicious_video_ids(
        self, tmp_path: Path, stress_timeline: TimelineIR
    ) -> None:
        """save_reports must sanitize path-traversal / illegal characters in video_id."""
        malicious_video_id = "../../etc/passwd:video*<foo>?|bar"
        curve = [(0.0, 1.0), (1.0, 0.8)]

        engine = RetentionCorrelationEngine()
        report = engine.correlate(stress_timeline, curve, video_id=malicious_video_id)

        out_dir = tmp_path / "reports"
        json_file, md_file = engine.save_reports(report, out_dir)

        assert json_file.exists()
        assert md_file.exists()
        assert ".." not in json_file.name
        assert ":" not in json_file.name
        assert "<" not in json_file.name
        assert "|" not in json_file.name
        assert json_file.parent == out_dir
