"""Unit and CLI integration tests for veraxi-ymmp youtube subcommands.

Verifies:
- Top-level and subcommand help screens (upload, status, qa)
- upload subcommand in offline mock mode with video, metadata, and thumbnail
- status subcommand in offline mock mode
- qa subcommand in offline mock mode generating JSON and Markdown reports
- Robust error handling on missing arguments, nonexistent files, and invalid values
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from veraxi_ymmp.cli import main
from veraxi_ymmp.ir import TimelineIR, VoiceClip
from veraxi_ymmp.youtube_adapter import MockYouTubeAdapter


@pytest.fixture
def temp_video(tmp_path: Path) -> Path:
    """Create a temporary video file for upload testing."""
    video = tmp_path / "mock_clip.mp4"
    video.write_bytes(b"\x00" * (128 * 1024))
    return video


@pytest.fixture
def temp_thumbnail(tmp_path: Path) -> Path:
    """Create a temporary PNG thumbnail file."""
    thumb = tmp_path / "thumb.png"
    thumb.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * (64 * 1024))
    return thumb


class TestCLIYouTubeHelp:
    """Verify CLI help screens and subcommand discovery."""

    def test_youtube_top_level_help(self, capsys: Any) -> None:
        """--help displays usage and subcommands (upload, status, qa)."""
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "--help"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "upload" in captured.out
        assert "status" in captured.out
        assert "qa" in captured.out

    def test_youtube_no_args_exits_with_code_2(self) -> None:
        """Invoking 'veraxi-ymmp youtube' without subcommands prints help and exits 2."""
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2

    def test_youtube_upload_help(self, capsys: Any) -> None:
        """'youtube upload --help' displays full upload flags."""
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "upload", "--help"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "--title" in captured.out
        assert "--description" in captured.out
        assert "--tags" in captured.out
        assert "--category-id" in captured.out
        assert "--privacy" in captured.out
        assert "--thumbnail" in captured.out
        assert "--publish-at" in captured.out
        assert "--mock" in captured.out

    def test_youtube_status_help(self, capsys: Any) -> None:
        """'youtube status --help' displays status arguments."""
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "status", "--help"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "video_id" in captured.out
        assert "--mock" in captured.out

    def test_youtube_qa_help(self, capsys: Any) -> None:
        """'youtube qa --help' displays qa arguments."""
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "qa", "--help"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "--video-id" in captured.out
        assert "--project" in captured.out
        assert "--output" in captured.out
        assert "--threshold" in captured.out
        assert "--mock" in captured.out


class TestCLIYouTubeUpload:
    """Verify upload subcommand execution and validation."""

    def test_upload_mock_minimal(self, temp_video: Path) -> None:
        """upload <video> --mock succeeds with code 0."""
        with patch.object(
            sys,
            "argv",
            ["veraxi-ymmp", "youtube", "upload", str(temp_video), "--mock"],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    def test_upload_mock_with_full_metadata(
        self, temp_video: Path, temp_thumbnail: Path
    ) -> None:
        """upload with title, description, tags, category, privacy, and thumbnail."""
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "upload",
                str(temp_video),
                "--title",
                "Integration Test Title",
                "--description",
                "Integration Test Description",
                "--tags",
                "test, python, youtube",
                "--category-id",
                "27",
                "--privacy",
                "unlisted",
                "--thumbnail",
                str(temp_thumbnail),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    def test_upload_missing_video_path(self) -> None:
        """upload without video path exits with code 2."""
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "upload"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2

    def test_upload_nonexistent_video_file(self, tmp_path: Path) -> None:
        """upload with nonexistent video file exits with code 1."""
        nonexistent = tmp_path / "does_not_exist.mp4"
        with patch.object(
            sys,
            "argv",
            ["veraxi-ymmp", "youtube", "upload", str(nonexistent), "--mock"],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_upload_nonexistent_thumbnail(self, temp_video: Path, tmp_path: Path) -> None:
        """upload with nonexistent thumbnail file exits with code 1."""
        nonexistent_thumb = tmp_path / "ghost.png"
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "upload",
                str(temp_video),
                "--thumbnail",
                str(nonexistent_thumb),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1


class TestCLIYouTubeStatus:
    """Verify status subcommand execution and validation."""

    def test_status_mock_success(self) -> None:
        """status <video_id> --mock succeeds with code 0."""
        with patch.object(
            sys, "argv", ["veraxi-ymmp", "youtube", "status", "test_vid_abc", "--mock"]
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    def test_status_missing_video_id(self) -> None:
        """status without video_id exits with code 2."""
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "status"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2


class TestCLIYouTubeQA:
    """Verify qa subcommand execution, report generation, and error handling."""

    def test_qa_mock_success_with_output_dir(self, tmp_path: Path) -> None:
        """qa --mock produces .json and .md reports in specified output dir."""
        out_dir = tmp_path / "qa_out"
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "qa",
                "--video-id",
                "qa_integration_vid",
                "--project",
                "projects/01_costco_business_model",
                "--output",
                str(out_dir),
                "--threshold",
                "0.05",
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

        assert out_dir.exists()
        json_reports = list(out_dir.glob("*.json"))
        md_reports = list(out_dir.glob("*.md"))
        assert len(json_reports) == 1
        assert len(md_reports) == 1

        # Verify JSON report structure
        data = json.loads(json_reports[0].read_text(encoding="utf-8"))
        assert data["video_id"] == "qa_integration_vid"
        assert "retention_score" in data
        assert "dropoff_points" in data
        assert "cut_metrics" in data

    def test_qa_missing_video_id(self) -> None:
        """qa without --video-id exits with error."""
        with patch.object(
            sys,
            "argv",
            ["veraxi-ymmp", "youtube", "qa", "--project", "projects/01_costco_business_model"],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0

    def test_qa_missing_project(self) -> None:
        """qa without --project exits with error."""
        with patch.object(
            sys, "argv", ["veraxi-ymmp", "youtube", "qa", "--video-id", "qa_vid_123"]
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0

    def test_qa_nonexistent_project(self, tmp_path: Path) -> None:
        """qa with nonexistent project path exits with code 1."""
        nonexistent = tmp_path / "no_such_project"
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
                str(nonexistent),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_qa_project_missing_script(self, tmp_path: Path) -> None:
        """qa with project directory missing script.json exits with code 1."""
        empty_proj = tmp_path / "empty_proj"
        empty_proj.mkdir()
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
                str(empty_proj),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_qa_invalid_threshold(self) -> None:
        """qa with non-float threshold exits with error."""
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
                "not_a_valid_float",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code != 0


class TestCLIYouTubeUnknownSubcommand:
    """Verify error behavior on invalid subcommands."""

    def test_unknown_subcommand_exits_code_2(self) -> None:
        """Invoking unknown subcommand exits with code 2."""
        with patch.object(
            sys, "argv", ["veraxi-ymmp", "youtube", "unknown_subcmd"]
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2


@pytest.fixture
def mock_project_dir(tmp_path: Path) -> Path:
    """Create a fully valid mock project directory for pipeline run tests."""
    proj = tmp_path / "test_pipeline_project"
    proj.mkdir(parents=True, exist_ok=True)
    audio_dir = proj / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    wav_file = audio_dir / "001_Zundamon.wav"

    wav_file.write_bytes(
        b"RIFF"
        + struct.pack("<I", 36)
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, 48000, 96000, 2, 16)
        + b"data"
        + struct.pack("<I", 0)
    )

    script_data = [
        {"character": "ずんだもん", "text": "YouTube自動投稿のテストなのだ！"}
    ]
    (proj / "script.json").write_text(
        json.dumps(script_data, ensure_ascii=False), encoding="utf-8"
    )
    (proj / "final_video.mp4").write_bytes(b"\x00" * 2048)
    (proj / "thumbnail.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1024)
    return proj


class TestCLIRunYouTubeIntegration:
    """Verify end-to-end YouTube publishing automation integrated into 'veraxi-ymmp run'."""

    def test_run_upload_to_youtube_mock_end_to_end(
        self, mock_project_dir: Path
    ) -> None:
        """veraxi-ymmp run <project_dir> --upload-to-youtube --mock-upload uploads video, thumb, captions."""
        dummy_wav = mock_project_dir / "audio" / "001_Zundamon.wav"
        real_mock = MockYouTubeAdapter()

        with (
            patch("veraxi_ymmp.pipeline.MoviePyRenderer"),
            patch(
                "veraxi_ymmp.pipeline.generate_project_thumbnail",
                return_value=mock_project_dir / "thumbnail.png",
            ),
            patch("veraxi_ymmp.pipeline.YMMPCompiler.build_ir") as mock_build_ir,
            patch(
                "veraxi_ymmp.youtube_adapter.MockYouTubeAdapter",
                return_value=real_mock,
            ),
            patch.object(
                sys,
                "argv",
                [
                    "veraxi-ymmp",
                    "run",
                    str(mock_project_dir),
                    "--upload-to-youtube",
                    "--mock-upload",
                ],
            ),
        ):
            ir = TimelineIR(
                fps=60,
                total_frames=60,
                voice_clips=[
                    VoiceClip(
                        start_frame=0,
                        length=60,
                        character="ずんだもん",
                        text="YouTube自動投稿のテストなのだ！",
                        emotion="normal",
                        motion="none",
                        audio_path=dummy_wav,
                        hatsuon="ユーチューブジドウトウコウノテストナノダ",
                        subtitle_position="bottom_center",
                        subtitle_style="outlined",
                    )
                ],
            )
            mock_build_ir.return_value = (ir, [dummy_wav])

            main()

        # 1. Video was uploaded
        assert len(real_mock.uploaded_videos) == 1
        video_id = list(real_mock.uploaded_videos.keys())[0]
        video_path, meta = real_mock.uploaded_videos[video_id]
        assert video_path.name == "final_video.mp4"
        assert meta.title == "test_pipeline_project"
        assert meta.privacy_status == "private"

        # 2. Thumbnail was uploaded
        assert video_id in real_mock.uploaded_thumbnails
        assert real_mock.uploaded_thumbnails[video_id].name == "thumbnail.png"

        # 3. SRT captions were generated and uploaded
        srt_file = mock_project_dir / f"{mock_project_dir.name}.srt"
        assert srt_file.exists()
        assert "YouTube自動投稿のテストなのだ！" in srt_file.read_text(encoding="utf-8")
        assert len(real_mock.uploaded_captions) == 1
        assert real_mock.uploaded_captions[0]["video_id"] == video_id
        assert real_mock.uploaded_captions[0]["caption_path"] == srt_file

        # 4. Correct call sequence
        assert "upload_video:final_video.mp4" in real_mock.call_log
        assert f"upload_thumbnail:{video_id}" in real_mock.call_log
        assert f"upload_caption:{video_id}" in real_mock.call_log

    def test_run_upload_to_youtube_mock_scheduled(
        self, mock_project_dir: Path
    ) -> None:
        """veraxi-ymmp run <project_dir> --upload-to-youtube --mock-upload --publish-at succeeds with private status."""
        dummy_wav = mock_project_dir / "audio" / "001_Zundamon.wav"
        real_mock = MockYouTubeAdapter()
        scheduled_ts = "2026-10-25T15:00:00Z"

        with (
            patch("veraxi_ymmp.pipeline.MoviePyRenderer"),
            patch(
                "veraxi_ymmp.pipeline.generate_project_thumbnail",
                return_value=mock_project_dir / "thumbnail.png",
            ),
            patch("veraxi_ymmp.pipeline.YMMPCompiler.build_ir") as mock_build_ir,
            patch(
                "veraxi_ymmp.youtube_adapter.MockYouTubeAdapter",
                return_value=real_mock,
            ),
            patch.object(
                sys,
                "argv",
                [
                    "veraxi-ymmp",
                    "run",
                    str(mock_project_dir),
                    "--upload-to-youtube",
                    "--mock-upload",
                    "--publish-at",
                    scheduled_ts,
                    "--privacy",
                    "private",
                ],
            ),
        ):
            ir = TimelineIR(
                fps=60,
                total_frames=60,
                voice_clips=[
                    VoiceClip(
                        start_frame=0,
                        length=60,
                        character="ずんだもん",
                        text="YouTube自動投稿のテストなのだ！",
                        emotion="normal",
                        motion="none",
                        audio_path=dummy_wav,
                        hatsuon="ユーチューブジドウトウコウノテストナノダ",
                        subtitle_position="bottom_center",
                        subtitle_style="outlined",
                    )
                ],
            )
            mock_build_ir.return_value = (ir, [dummy_wav])

            main()

        assert len(real_mock.uploaded_videos) == 1
        video_id = list(real_mock.uploaded_videos.keys())[0]
        _, meta = real_mock.uploaded_videos[video_id]
        assert meta.publish_at == scheduled_ts
        assert meta.privacy_status == "private"

    def test_run_publish_at_with_non_private_status_exits_code_1(
        self, mock_project_dir: Path, capsys: Any
    ) -> None:
        """--publish-at with --privacy public exits with code 1 before pipeline execution."""
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "run",
                str(mock_project_dir),
                "--upload-to-youtube",
                "--mock-upload",
                "--publish-at",
                "2026-10-25T15:00:00Z",
                "--privacy",
                "public",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

        captured = capsys.readouterr()
        assert "YouTube requires privacy_status='private' for scheduled uploads" in captured.err

    def test_run_publish_at_with_unlisted_status_exits_code_1(
        self, mock_project_dir: Path, capsys: Any
    ) -> None:
        """--publish-at with --privacy unlisted exits with code 1 before pipeline execution."""
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "run",
                str(mock_project_dir),
                "--upload-to-youtube",
                "--mock-upload",
                "--publish-at",
                "2026-10-25T15:00:00Z",
                "--privacy",
                "unlisted",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

        captured = capsys.readouterr()
        assert "YouTube requires privacy_status='private' for scheduled uploads" in captured.err

    def test_run_invalid_publish_at_format_exits_code_1(
        self, mock_project_dir: Path, capsys: Any
    ) -> None:
        """Invalid --publish-at format exits with code 1 before pipeline execution."""
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "run",
                str(mock_project_dir),
                "--upload-to-youtube",
                "--mock-upload",
                "--publish-at",
                "not-an-iso-8601-timestamp",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

        captured = capsys.readouterr()
        assert "Invalid ISO-8601 publish_at format" in captured.err

    def test_run_missing_video_artifact_fails(
        self, mock_project_dir: Path, capsys: Any
    ) -> None:
        """When --upload-to-youtube is set and no video artifact exists, exits with code 1."""
        (mock_project_dir / "final_video.mp4").unlink()
        dummy_wav = mock_project_dir / "audio" / "001_Zundamon.wav"

        with (
            patch("veraxi_ymmp.pipeline.MoviePyRenderer"),
            patch(
                "veraxi_ymmp.pipeline.generate_project_thumbnail",
                return_value=mock_project_dir / "thumbnail.png",
            ),
            patch("veraxi_ymmp.pipeline.YMMPCompiler.build_ir") as mock_build_ir,
            patch.object(
                sys,
                "argv",
                [
                    "veraxi-ymmp",
                    "run",
                    str(mock_project_dir),
                    "--upload-to-youtube",
                    "--mock-upload",
                    "--no-qa",
                ],
            ),
        ):
            ir = TimelineIR(
                fps=60,
                total_frames=60,
                voice_clips=[
                    VoiceClip(
                        start_frame=0,
                        length=60,
                        character="ずんだもん",
                        text="テスト",
                        emotion="normal",
                        motion="none",
                        audio_path=dummy_wav,
                        hatsuon="テスト",
                        subtitle_position="bottom_center",
                        subtitle_style="outlined",
                    )
                ],
            )
            mock_build_ir.return_value = (ir, [dummy_wav])

            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

        captured = capsys.readouterr()
        assert "No video artifact found for YouTube upload" in captured.err

    def test_run_normalize_loudness_flag(
        self, mock_project_dir: Path
    ) -> None:
        """--normalize calls normalize_video_audio and uploads normalized video."""
        dummy_wav = mock_project_dir / "audio" / "001_Zundamon.wav"
        real_mock = MockYouTubeAdapter()
        norm_video = mock_project_dir / "final_video_normalized.mp4"
        norm_video.write_bytes(b"\x00" * 2048)

        with (
            patch("veraxi_ymmp.pipeline.MoviePyRenderer"),
            patch(
                "veraxi_ymmp.pipeline.generate_project_thumbnail",
                return_value=mock_project_dir / "thumbnail.png",
            ),
            patch("veraxi_ymmp.pipeline.YMMPCompiler.build_ir") as mock_build_ir,
            patch(
                "veraxi_ymmp.youtube_adapter.MockYouTubeAdapter",
                return_value=real_mock,
            ),
            patch(
                "veraxi_ymmp.audio_normalizer.normalize_video_audio",
                return_value=norm_video,
            ) as mock_norm,
            patch.object(
                sys,
                "argv",
                [
                    "veraxi-ymmp",
                    "run",
                    str(mock_project_dir),
                    "--upload-to-youtube",
                    "--mock-upload",
                    "--normalize",
                ],
            ),
        ):
            ir = TimelineIR(
                fps=60,
                total_frames=60,
                voice_clips=[
                    VoiceClip(
                        start_frame=0,
                        length=60,
                        character="ずんだもん",
                        text="テスト",
                        emotion="normal",
                        motion="none",
                        audio_path=dummy_wav,
                        hatsuon="テスト",
                        subtitle_position="bottom_center",
                        subtitle_style="outlined",
                    )
                ],
            )
            mock_build_ir.return_value = (ir, [dummy_wav])

            main()

        mock_norm.assert_called_once()
        assert len(real_mock.uploaded_videos) == 1
        video_id = list(real_mock.uploaded_videos.keys())[0]
        uploaded_path, _ = real_mock.uploaded_videos[video_id]
        assert uploaded_path.name == "final_video_normalized.mp4"

def test_youtube_auth_cli_parsing(capsys) -> None:
    from veraxi_ymmp.cli import main
    with patch("sys.argv", ["veraxi-ymmp", "youtube", "auth", "--client-secrets", "secrets.json", "--monetary"]):
        with patch("veraxi_ymmp.cli_youtube._cmd_youtube_auth") as mock_cmd:
            main()
            mock_cmd.assert_called_once()
            args = mock_cmd.call_args[0][0]
            assert args.client_secrets == "secrets.json"
            assert args.monetary is True
            assert args.no_browser is False

def test_youtube_stats_cli_parsing_json_csv_output(capsys) -> None:
    from veraxi_ymmp.cli import main
    with patch("sys.argv", ["veraxi-ymmp", "youtube", "stats", "--video-id", "vid1", "--video-id", "vid2", "--format", "json"]):
        with patch("veraxi_ymmp.cli_youtube._cmd_youtube_stats") as mock_cmd:
            main()
            mock_cmd.assert_called_once()
            args = mock_cmd.call_args[0][0]
            assert args.video_id == ["vid1", "vid2"]
            assert args.format == "json"

def test_youtube_channel_cli_parsing(capsys) -> None:
    from veraxi_ymmp.cli import main
    with patch("sys.argv", ["veraxi-ymmp", "youtube", "channel", "--mock"]):
        with patch("veraxi_ymmp.cli_youtube._cmd_youtube_channel") as mock_cmd:
            main()
            mock_cmd.assert_called_once()
            args = mock_cmd.call_args[0][0]
            assert args.mock is True
