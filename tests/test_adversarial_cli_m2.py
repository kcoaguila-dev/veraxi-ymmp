"""Adversarial stress test suite for Milestone 2 CLI guardrails and YouTube publishing.

Tests boundary conditions, attack scenarios, and combined flags for:
1. Invalid ISO-8601 publish_at strings
2. Non-private scheduled publish privacy statuses
3. Missing project directories, missing script.json, and missing video artifacts
4. Combined CLI flags (no-thumbnail, normalize loudness fallback, schedule without upload, live without creds)
5. YouTube upload subcommand guardrails parity
"""

import json
import os
import sys
import wave
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from veraxi_ymmp.cli import main
from veraxi_ymmp.ir import TimelineIR, VoiceClip
from veraxi_ymmp.youtube_adapter import MockYouTubeAdapter


@pytest.fixture
def stress_project_dir(tmp_path: Path) -> Path:
    """Create a minimal valid project directory with video and audio."""
    proj = tmp_path / "stress_project"
    proj.mkdir()
    audio_dir = proj / "audio"
    audio_dir.mkdir()

    # Generate valid 100ms PCM WAV
    wav_path = audio_dir / "001_Zundamon.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(b"\x00\x00" * 2400)

    # Valid script.json
    script_data = [
        {
            "character": "ずんだもん",
            "text": "境界値ストレステストなのだ！",
            "emotion": "normal",
        }
    ]
    (proj / "script.json").write_text(
        json.dumps(script_data, ensure_ascii=False), encoding="utf-8"
    )

    # Video artifact
    video_path = proj / "final_video.mp4"
    video_path.write_bytes(b"\x00" * 4096)

    # Thumbnail artifact
    thumb_path = proj / "thumbnail.png"
    thumb_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    return proj


# =====================================================================
# Dimension 1: Adversarial ISO-8601 Publish-At Strings
# =====================================================================

class TestAdversarialISOStrings:
    """Stress tests on datetime parsing and boundary formats."""

    @pytest.mark.parametrize(
        "invalid_iso",
        [
            "",
            "   ",
            "not-a-date",
            "2026-13-45",
            "2026-02-30T10:00:00Z",
            "2026-10-25T25:00:00Z",
            "2026/10/25T15:00:00Z",
            "2026-10-25T15:00:00Z_trailing_garbage",
            "1761404400",
            "yesterday",
            "2026-10-25T15:00:00+99:99",
        ],
    )
    def test_run_rejects_adversarial_iso_strings(
        self, stress_project_dir: Path, invalid_iso: str, capsys: Any
    ) -> None:
        """Every invalid or malformed ISO string must exit with code 1 before pipeline executes."""
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "run",
                str(stress_project_dir),
                "--upload-to-youtube",
                "--mock-upload",
                "--publish-at",
                invalid_iso,
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

        captured = capsys.readouterr()
        assert "Invalid ISO-8601 publish_at format" in captured.err

    @pytest.mark.parametrize(
        "valid_iso",
        [
            "2026-10-25T15:00:00Z",
            "2026-10-25T15:00:00+00:00",
            "2026-10-25T15:00:00+09:00",
            "2026-10-25T15:00:00-05:00",
            "2026-10-25T15:00:00.123456Z",
        ],
    )
    def test_run_accepts_valid_iso_variations(
        self, stress_project_dir: Path, valid_iso: str
    ) -> None:
        """Standard-compliant ISO-8601 variations with timezone offsets are accepted."""
        dummy_wav = stress_project_dir / "audio" / "001_Zundamon.wav"
        real_mock = MockYouTubeAdapter()

        with (
            patch("veraxi_ymmp.pipeline.MoviePyRenderer"),
            patch(
                "veraxi_ymmp.pipeline.generate_project_thumbnail",
                return_value=stress_project_dir / "thumbnail.png",
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
                    str(stress_project_dir),
                    "--upload-to-youtube",
                    "--mock-upload",
                    "--publish-at",
                    valid_iso,
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

        assert len(real_mock.uploaded_videos) == 1
        video_id = list(real_mock.uploaded_videos.keys())[0]
        _, meta = real_mock.uploaded_videos[video_id]
        assert meta.publish_at == valid_iso


# =====================================================================
# Dimension 2: Adversarial Privacy Status with Scheduled Publish
# =====================================================================

class TestAdversarialPrivacyStatus:
    """Stress tests on YouTube scheduling privacy status constraints."""

    @pytest.mark.parametrize("disallowed_privacy", ["public", "unlisted"])
    def test_run_rejects_non_private_scheduled_upload(
        self, stress_project_dir: Path, disallowed_privacy: str, capsys: Any
    ) -> None:
        """YouTube strictly prohibits public or unlisted status with publishAt."""
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "run",
                str(stress_project_dir),
                "--upload-to-youtube",
                "--mock-upload",
                "--publish-at",
                "2026-10-25T15:00:00Z",
                "--privacy",
                disallowed_privacy,
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

        captured = capsys.readouterr()
        assert "YouTube requires privacy_status='private' for scheduled uploads" in captured.err

    def test_run_rejects_invalid_privacy_choice(
        self, stress_project_dir: Path, capsys: Any
    ) -> None:
        """Arbitrary privacy choice like 'secret' is blocked at argparse parsing level with exit code 2."""
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "run",
                str(stress_project_dir),
                "--privacy",
                "secret",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2


# =====================================================================
# Dimension 3: Missing Directories, Missing Scripts, Missing Artifacts
# =====================================================================

class TestAdversarialMissingFiles:
    """Stress tests on filesystem boundary conditions."""

    def test_run_nonexistent_project_directory(self, capsys: Any) -> None:
        """Non-existent project dir path exits with code 1 and descriptive error."""
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "run",
                "nonexistent_project_dir_totally_fake",
                "--upload-to-youtube",
                "--mock-upload",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

        captured = capsys.readouterr()
        assert "does not exist" in captured.err

    def test_run_empty_project_directory_missing_script(
        self, tmp_path: Path, capsys: Any
    ) -> None:
        """Existing directory with missing script.json exits with code 1."""
        empty_dir = tmp_path / "empty_dir"
        empty_dir.mkdir()

        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "run",
                str(empty_dir),
                "--upload-to-youtube",
                "--mock-upload",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

        captured = capsys.readouterr()
        assert "No script.json found" in captured.err

    def test_run_missing_video_artifacts_fails_gracefully(
        self, stress_project_dir: Path, capsys: Any
    ) -> None:
        """When neither final_video.mp4 nor qa_test.mp4 exists, fails cleanly with code 1."""
        (stress_project_dir / "final_video.mp4").unlink()
        dummy_wav = stress_project_dir / "audio" / "001_Zundamon.wav"

        with (
            patch("veraxi_ymmp.pipeline.MoviePyRenderer"),
            patch(
                "veraxi_ymmp.pipeline.generate_project_thumbnail",
                return_value=stress_project_dir / "thumbnail.png",
            ),
            patch("veraxi_ymmp.pipeline.YMMPCompiler.build_ir") as mock_build_ir,
            patch.object(
                sys,
                "argv",
                [
                    "veraxi-ymmp",
                    "run",
                    str(stress_project_dir),
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


# =====================================================================
# Dimension 4: Adversarial Combined Flags
# =====================================================================

class TestAdversarialCombinedFlags:
    """Stress tests on interactions between multiple CLI options."""

    def test_combined_no_thumbnail_with_upload(
        self, stress_project_dir: Path
    ) -> None:
        """--no-thumbnail with --upload-to-youtube uploads video & caption, skipping thumbnail."""
        (stress_project_dir / "thumbnail.png").unlink()
        dummy_wav = stress_project_dir / "audio" / "001_Zundamon.wav"
        real_mock = MockYouTubeAdapter()

        with (
            patch("veraxi_ymmp.pipeline.MoviePyRenderer"),
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
                    str(stress_project_dir),
                    "--upload-to-youtube",
                    "--mock-upload",
                    "--no-thumbnail",
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

        assert len(real_mock.uploaded_videos) == 1
        video_id = list(real_mock.uploaded_videos.keys())[0]
        # Video uploaded
        assert "upload_video:final_video.mp4" in real_mock.call_log
        # Caption uploaded
        assert f"upload_caption:{video_id}" in real_mock.call_log
        # Thumbnail NOT uploaded
        assert f"upload_thumbnail:{video_id}" not in real_mock.call_log

    def test_combined_publish_at_without_upload_flag_validates(
        self, stress_project_dir: Path, capsys: Any
    ) -> None:
        """Passing --publish-at with --privacy public even without --upload-to-youtube is caught immediately."""
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "run",
                str(stress_project_dir),
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

    def test_combined_normalization_failure_falls_back_gracefully(
        self, stress_project_dir: Path
    ) -> None:
        """When --normalize loudness fails, it logs warning and falls back to original video."""
        dummy_wav = stress_project_dir / "audio" / "001_Zundamon.wav"
        real_mock = MockYouTubeAdapter()

        with (
            patch("veraxi_ymmp.pipeline.MoviePyRenderer"),
            patch(
                "veraxi_ymmp.pipeline.generate_project_thumbnail",
                return_value=stress_project_dir / "thumbnail.png",
            ),
            patch("veraxi_ymmp.pipeline.YMMPCompiler.build_ir") as mock_build_ir,
            patch(
                "veraxi_ymmp.youtube_adapter.MockYouTubeAdapter",
                return_value=real_mock,
            ),
            patch(
                "veraxi_ymmp.audio_normalizer.normalize_video_audio",
                side_effect=RuntimeError("FFmpeg normalization error simulation"),
            ),
            patch.object(
                sys,
                "argv",
                [
                    "veraxi-ymmp",
                    "run",
                    str(stress_project_dir),
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

        # Fallback to original final_video.mp4
        assert len(real_mock.uploaded_videos) == 1
        video_id = list(real_mock.uploaded_videos.keys())[0]
        uploaded_path, _ = real_mock.uploaded_videos[video_id]
        assert uploaded_path.name == "final_video.mp4"

    def test_combined_live_upload_without_credentials_fails_gracefully(
        self, stress_project_dir: Path, capsys: Any
    ) -> None:
        """Running --upload-to-youtube without mock mode and without credentials fails with clean error code 1."""
        dummy_wav = stress_project_dir / "audio" / "001_Zundamon.wav"

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("veraxi_ymmp.pipeline.MoviePyRenderer"),
            patch(
                "veraxi_ymmp.pipeline.generate_project_thumbnail",
                return_value=stress_project_dir / "thumbnail.png",
            ),
            patch("veraxi_ymmp.pipeline.YMMPCompiler.build_ir") as mock_build_ir,
            patch.object(
                sys,
                "argv",
                [
                    "veraxi-ymmp",
                    "run",
                    str(stress_project_dir),
                    "--upload-to-youtube",
                    # Note: No --mock-upload
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
        assert "Failed during YouTube upload" in captured.err
