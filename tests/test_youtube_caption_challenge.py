"""Empirical challenge tests for upload_caption in YouTubeAdapter and MockYouTubeAdapter.

Challenges:
1. Non-existent caption path (simple, nested, string input, directory input)
2. Empty file (0 bytes)
3. Non-ASCII paths and content (Japanese, emoji, spaces, UTF-8 BOM)
4. Language codes (BCP-47 tags, regional variants, empty/invalid strings)
5. Multiple caption uploads for the same video (multi-language and duplicate tracks)
6. Error handling on API failures (HTTP 400, 403, 500, network exceptions)
7. Duck typing: Path vs str input
8. Call log and state tracking in MockYouTubeAdapter
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from veraxi_ymmp.youtube_adapter import (
    MockYouTubeAdapter,
    YouTubeAdapter,
)


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_srt(tmp_path: Path) -> Path:
    """Create a standard UTF-8 SRT caption file."""
    srt = tmp_path / "sample.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:02,500\nずんだもんなのだ！\n\n"
        "2\n00:00:02,500 --> 00:00:05,000\n四国めたんですわ。\n",
        encoding="utf-8",
    )
    return srt


@pytest.fixture
def empty_srt(tmp_path: Path) -> Path:
    """Create a 0-byte SRT file."""
    srt = tmp_path / "empty.srt"
    srt.write_bytes(b"")
    return srt


@pytest.fixture
def non_ascii_srt(tmp_path: Path) -> Path:
    """Create an SRT file with unicode directory and filename containing Japanese and emojis."""
    sub_dir = tmp_path / "日本語の字幕ディレクトリ 📁"
    sub_dir.mkdir(parents=True, exist_ok=True)
    srt = sub_dir / "ずんだもん_字幕 (テスト) ⚡🎉.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\n特殊文字テスト：🍣🍜🍺\n\n"
        "2\n00:00:02,000 --> 00:00:04,000\nロシア語: Привет мир / 英語: Hello\n",
        encoding="utf-8",
    )
    return srt


@pytest.fixture
def utf8_bom_srt(tmp_path: Path) -> Path:
    """Create an SRT file with UTF-8 BOM header."""
    srt = tmp_path / "bom_captions.srt"
    content = "1\n00:00:00,000 --> 00:00:02,000\nBOM付きUTF-8字幕\n"
    srt.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
    return srt


# ---------------------------------------------------------------------------
# Challenge 1: Non-existent Caption Paths & Directories
# ---------------------------------------------------------------------------

class TestNonExistentCaptionPaths:
    """Empirical challenge on non-existent paths and directory inputs."""

    def test_mock_adapter_raises_filenotfound_on_missing_file(self, tmp_path: Path) -> None:
        adapter = MockYouTubeAdapter()
        missing = tmp_path / "non_existent.srt"
        with pytest.raises(FileNotFoundError) as exc_info:
            adapter.upload_caption("vid_101", missing)
        assert "not found" in str(exc_info.value).lower()

    def test_mock_adapter_raises_filenotfound_on_nested_missing_path(self, tmp_path: Path) -> None:
        adapter = MockYouTubeAdapter()
        missing = tmp_path / "no_such_dir" / "nested" / "caption.srt"
        with pytest.raises(FileNotFoundError):
            adapter.upload_caption("vid_101", missing)

    def test_mock_adapter_raises_filenotfound_on_string_path(self, tmp_path: Path) -> None:
        adapter = MockYouTubeAdapter()
        missing_str = str(tmp_path / "missing_str.srt")
        with pytest.raises(FileNotFoundError):
            adapter.upload_caption("vid_101", missing_str)  # type: ignore[arg-type]

    def test_youtube_adapter_raises_filenotfound_on_missing_file(self, tmp_path: Path) -> None:
        adapter = YouTubeAdapter()
        missing = tmp_path / "non_existent.srt"
        with pytest.raises(FileNotFoundError) as exc_info:
            adapter.upload_caption("vid_102", missing)
        assert "not found" in str(exc_info.value).lower()

    def test_youtube_adapter_raises_filenotfound_on_string_path(self, tmp_path: Path) -> None:
        adapter = YouTubeAdapter()
        missing_str = str(tmp_path / "missing_str.srt")
        with pytest.raises(FileNotFoundError):
            adapter.upload_caption("vid_102", missing_str)  # type: ignore[arg-type]

    def test_directory_passed_as_caption_path_behavior(self, tmp_path: Path) -> None:
        """When a directory that exists is passed instead of a file."""
        existing_dir = tmp_path / "some_dir"
        existing_dir.mkdir()

        # Mock adapter currently accepts existing dir because exists() is True
        mock_adapter = MockYouTubeAdapter()
        # Test whether mock adapter accepts or raises
        # We record the actual behavior:
        res = mock_adapter.upload_caption("vid_dir", existing_dir)
        assert res is True  # Documents that MockYouTubeAdapter only checks .exists()

        # YouTubeAdapter with injected service: MediaFileUpload might fail or execute
        mock_yt = MagicMock()
        mock_media_cls = MagicMock()
        mock_media_cls.side_effect = IsADirectoryError("Expected file, got directory")
        yt_adapter = YouTubeAdapter(youtube_service=mock_yt, media_file_upload_cls=mock_media_cls)
        # Because of try/except, it catches IsADirectoryError and returns False gracefully
        assert yt_adapter.upload_caption("vid_dir", existing_dir) is False


# ---------------------------------------------------------------------------
# Challenge 2: Empty Caption Files (0 bytes)
# ---------------------------------------------------------------------------

class TestEmptyCaptionFiles:
    """Empirical challenge on 0-byte caption files."""

    def test_mock_adapter_accepts_empty_file(self, empty_srt: Path) -> None:
        adapter = MockYouTubeAdapter()
        result = adapter.upload_caption("vid_empty", empty_srt)
        assert result is True
        assert len(adapter.uploaded_captions) == 1
        assert adapter.uploaded_captions[0]["caption_path"] == empty_srt

    def test_youtube_adapter_handles_empty_file_success_when_api_accepts(
        self, empty_srt: Path
    ) -> None:
        mock_yt = MagicMock()
        mock_req = MagicMock()
        mock_req.execute.return_value = {"id": "cap_empty_01"}
        mock_yt.captions().insert.return_value = mock_req
        mock_media = MagicMock()

        adapter = YouTubeAdapter(youtube_service=mock_yt, media_file_upload_cls=mock_media)
        result = adapter.upload_caption("vid_empty", empty_srt)
        assert result is True
        mock_media.assert_called_once_with(str(empty_srt), mimetype="*/*", resumable=False)

    def test_youtube_adapter_returns_false_when_api_rejects_empty_file(
        self, empty_srt: Path
    ) -> None:
        mock_yt = MagicMock()
        mock_req = MagicMock()
        mock_req.execute.side_effect = Exception("HTTP 400: The caption file is empty (mediaEmpty)")
        mock_yt.captions().insert.return_value = mock_req
        mock_media = MagicMock()

        adapter = YouTubeAdapter(youtube_service=mock_yt, media_file_upload_cls=mock_media)
        result = adapter.upload_caption("vid_empty", empty_srt)
        assert result is False


# ---------------------------------------------------------------------------
# Challenge 3: Non-ASCII Paths and Content
# ---------------------------------------------------------------------------

class TestNonAsciiPathsAndContent:
    """Empirical challenge on unicode file paths, spaces, emojis, and BOM."""

    def test_mock_adapter_handles_non_ascii_path_and_name(self, non_ascii_srt: Path) -> None:
        adapter = MockYouTubeAdapter()
        result = adapter.upload_caption(
            video_id="vid_unicode_01",
            caption_path=non_ascii_srt,
            language="ja",
            name="ずんだもん字幕 ⚡🎉",
        )
        assert result is True
        assert len(adapter.uploaded_captions) == 1
        rec = adapter.uploaded_captions[0]
        assert rec["caption_path"] == non_ascii_srt
        assert rec["name"] == "ずんだもん字幕 ⚡🎉"
        assert "upload_caption:vid_unicode_01" in adapter.call_log

    def test_youtube_adapter_handles_non_ascii_path_and_name(
        self, non_ascii_srt: Path
    ) -> None:
        mock_yt = MagicMock()
        mock_req = MagicMock()
        mock_req.execute.return_value = {"id": "cap_unicode_99"}
        mock_yt.captions().insert.return_value = mock_req
        mock_media = MagicMock()

        adapter = YouTubeAdapter(youtube_service=mock_yt, media_file_upload_cls=mock_media)
        result = adapter.upload_caption(
            video_id="vid_unicode_live",
            caption_path=non_ascii_srt,
            language="ja",
            name="日本語字幕 🚀",
        )
        assert result is True
        mock_media.assert_called_once_with(str(non_ascii_srt), mimetype="*/*", resumable=False)
        _, kwargs = mock_yt.captions().insert.call_args
        assert kwargs["body"]["snippet"]["name"] == "日本語字幕 🚀"
        assert kwargs["body"]["snippet"]["language"] == "ja"

    def test_utf8_with_bom_caption(self, utf8_bom_srt: Path) -> None:
        adapter = MockYouTubeAdapter()
        assert adapter.upload_caption("vid_bom", utf8_bom_srt) is True
        assert len(adapter.uploaded_captions) == 1


# ---------------------------------------------------------------------------
# Challenge 4: Language Codes
# ---------------------------------------------------------------------------

class TestLanguageCodes:
    """Empirical challenge on BCP-47 language tags and edge cases."""

    @pytest.mark.parametrize(
        "lang_code, lang_name",
        [
            ("ja", "Japanese"),
            ("en", "English"),
            ("en-US", "English (United States)"),
            ("zh-Hans", "Chinese (Simplified)"),
            ("es-419", "Spanish (Latin America)"),
            ("pt-BR", "Portuguese (Brazil)"),
            ("", "Empty Lang Code"),
            ("invalid-lang-code-xyz!@#", "Invalid Code"),
        ],
    )
    def test_mock_adapter_preserves_language_codes(
        self, sample_srt: Path, lang_code: str, lang_name: str
    ) -> None:
        adapter = MockYouTubeAdapter()
        ok = adapter.upload_caption(
            video_id="vid_lang",
            caption_path=sample_srt,
            language=lang_code,
            name=lang_name,
        )
        assert ok is True
        assert adapter.uploaded_captions[0]["language"] == lang_code
        assert adapter.uploaded_captions[0]["name"] == lang_name

    def test_youtube_adapter_passes_exact_language_to_body(self, sample_srt: Path) -> None:
        mock_yt = MagicMock()
        mock_req = MagicMock()
        mock_req.execute.return_value = {"id": "cap_lang_01"}
        mock_yt.captions().insert.return_value = mock_req
        mock_media = MagicMock()

        adapter = YouTubeAdapter(youtube_service=mock_yt, media_file_upload_cls=mock_media)
        adapter.upload_caption(
            video_id="vid_lang_check",
            caption_path=sample_srt,
            language="zh-Hant",
            name="Traditional Chinese",
        )
        _, kwargs = mock_yt.captions().insert.call_args
        assert kwargs["body"]["snippet"]["language"] == "zh-Hant"
        assert kwargs["body"]["snippet"]["name"] == "Traditional Chinese"

    def test_youtube_adapter_returns_false_on_invalid_language_api_error(
        self, sample_srt: Path
    ) -> None:
        mock_yt = MagicMock()
        mock_req = MagicMock()
        mock_req.execute.side_effect = Exception("HTTP 400: Invalid BCP-47 language tag: 'invalid'")
        mock_yt.captions().insert.return_value = mock_req
        mock_media = MagicMock()

        adapter = YouTubeAdapter(youtube_service=mock_yt, media_file_upload_cls=mock_media)
        assert (
            adapter.upload_caption(
                video_id="vid_bad_lang",
                caption_path=sample_srt,
                language="invalid",
            )
            is False
        )


# ---------------------------------------------------------------------------
# Challenge 5: Multiple Caption Uploads for the Same Video
# ---------------------------------------------------------------------------

class TestMultipleCaptionUploads:
    """Empirical challenge on uploading multiple tracks for a single video."""

    def test_mock_adapter_tracks_multiple_languages(self, sample_srt: Path, tmp_path: Path) -> None:
        en_srt = tmp_path / "en.srt"
        en_srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello world\n", encoding="utf-8")

        adapter = MockYouTubeAdapter()
        # Upload Japanese track
        ok1 = adapter.upload_caption("vid_multi", sample_srt, language="ja", name="Japanese")
        # Upload English track
        ok2 = adapter.upload_caption("vid_multi", en_srt, language="en", name="English")

        assert ok1 is True
        assert ok2 is True
        assert len(adapter.uploaded_captions) == 2
        assert adapter.uploaded_captions[0]["language"] == "ja"
        assert adapter.uploaded_captions[1]["language"] == "en"
        assert adapter.uploaded_captions[0]["video_id"] == "vid_multi"
        assert adapter.uploaded_captions[1]["video_id"] == "vid_multi"
        assert adapter.call_log == ["upload_caption:vid_multi", "upload_caption:vid_multi"]

    def test_mock_adapter_allows_duplicate_caption_uploads(self, sample_srt: Path) -> None:
        """Calling upload_caption twice with identical metadata records both calls."""
        adapter = MockYouTubeAdapter()
        ok1 = adapter.upload_caption("vid_dup", sample_srt, language="ja", name="Japanese")
        ok2 = adapter.upload_caption("vid_dup", sample_srt, language="ja", name="Japanese")

        assert ok1 is True
        assert ok2 is True
        assert len(adapter.uploaded_captions) == 2
        assert adapter.uploaded_captions[0] == adapter.uploaded_captions[1]

    def test_youtube_adapter_executes_multiple_inserts(
        self, sample_srt: Path, tmp_path: Path
    ) -> None:
        en_srt = tmp_path / "en.srt"
        en_srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\n", encoding="utf-8")

        mock_yt = MagicMock()
        mock_req1 = MagicMock()
        mock_req1.execute.return_value = {"id": "cap_ja"}
        mock_req2 = MagicMock()
        mock_req2.execute.return_value = {"id": "cap_en"}

        mock_yt.captions().insert.side_effect = [mock_req1, mock_req2]
        mock_media = MagicMock()

        adapter = YouTubeAdapter(youtube_service=mock_yt, media_file_upload_cls=mock_media)
        res1 = adapter.upload_caption("vid_multi_yt", sample_srt, language="ja", name="Japanese")
        res2 = adapter.upload_caption("vid_multi_yt", en_srt, language="en", name="English")

        assert res1 is True
        assert res2 is True
        assert mock_yt.captions().insert.call_count == 2


# ---------------------------------------------------------------------------
# Challenge 6: API Error Conditions in YouTubeAdapter
# ---------------------------------------------------------------------------

class TestYouTubeAdapterApiErrors:
    """Empirical challenge on API error conditions: 400, 401, 403, 500, network crash."""

    @pytest.mark.parametrize(
        "error_msg",
        [
            "HTTP 400: Bad Request (Invalid media body)",
            "HTTP 401: Unauthorized (Invalid credentials)",
            "HTTP 403: Forbidden (The user has exceeded their caption quota)",
            "HTTP 403: Forbidden (Captions not enabled for this video)",
            "HTTP 500: Internal Server Error (Backend failure)",
            "ConnectionResetError: [WinError 10054] An existing connection was forcibly closed",
            "TimeoutError: Request timed out after 30000ms",
        ],
    )
    def test_api_errors_caught_and_return_false_without_raising(
        self, sample_srt: Path, error_msg: str
    ) -> None:
        mock_yt = MagicMock()
        mock_req = MagicMock()
        mock_req.execute.side_effect = Exception(error_msg)
        mock_yt.captions().insert.return_value = mock_req
        mock_media = MagicMock()

        adapter = YouTubeAdapter(youtube_service=mock_yt, media_file_upload_cls=mock_media)
        # Must not raise an unhandled exception; must return False and log error
        result = adapter.upload_caption("vid_err_test", sample_srt)
        assert result is False


# ---------------------------------------------------------------------------
# Challenge 7: Duck Typing (String vs Path)
# ---------------------------------------------------------------------------

class TestDuckTypingStringPath:
    """Empirical challenge verifying that str paths are coerced to Path."""

    def test_mock_adapter_accepts_str_path(self, sample_srt: Path) -> None:
        adapter = MockYouTubeAdapter()
        res = adapter.upload_caption("vid_str", str(sample_srt))  # type: ignore[arg-type]
        assert res is True
        assert adapter.uploaded_captions[0]["caption_path"] == sample_srt

    def test_youtube_adapter_accepts_str_path(self, sample_srt: Path) -> None:
        mock_yt = MagicMock()
        mock_req = MagicMock()
        mock_req.execute.return_value = {"id": "cap_str_ok"}
        mock_yt.captions().insert.return_value = mock_req
        mock_media = MagicMock()

        adapter = YouTubeAdapter(youtube_service=mock_yt, media_file_upload_cls=mock_media)
        res = adapter.upload_caption("vid_str", str(sample_srt))  # type: ignore[arg-type]
        assert res is True
        mock_media.assert_called_once_with(str(sample_srt), mimetype="*/*", resumable=False)
