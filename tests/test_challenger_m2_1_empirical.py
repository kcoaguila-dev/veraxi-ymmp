"""Empirical and adversarial test suite for Milestone 2 deliverables.

Author: challenger_2_m2_1
Scope:
- R1: Pipeline Run Integration (ProjectPipeline.run, veraxi-ymmp run, mock upload, video discovery, loudness normalization).
- R2: Caption & Subtitle Auto-Ingestion (SRT generation on disk, upload_caption to VideoPublisher).
- R3: Scheduled Publishing & Metadata Guardrails (ISO-8601 format validation, privacy_status enforcement).
- R4: Error handling, edge cases, and Clean Architecture invariants.
"""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from veraxi_ymmp.cli import main
from veraxi_ymmp.ir import TimelineIR, VoiceClip
from veraxi_ymmp.pipeline import ProjectPipeline
from veraxi_ymmp.srt_generator import _format_srt_time, generate_srt
from veraxi_ymmp.youtube_adapter import MockYouTubeAdapter


def _create_minimal_wav(path: Path) -> Path:
    """Create a 48kHz mono 16-bit PCM WAV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        b"RIFF"
        + struct.pack("<I", 36)
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, 48000, 96000, 2, 16)
        + b"data"
        + struct.pack("<I", 0)
    )
    path.write_bytes(header)
    return path


def _make_voice_clip(
    start_frame: int,
    length: int,
    character: str,
    text: str,
    audio_path: Optional[Path] = None,
    emotion: str = "normal",
    motion: str = "none",
    hatsuon: str = "テスト",
    subtitle_position: str = "bottom_center",
    subtitle_style: str = "outlined",
) -> VoiceClip:
    """Helper to instantiate valid VoiceClip dataclass with all required fields."""
    return VoiceClip(
        start_frame=start_frame,
        length=length,
        character=character,
        text=text,
        emotion=emotion,
        motion=motion,
        audio_path=audio_path,
        hatsuon=hatsuon,
        subtitle_position=subtitle_position,
        subtitle_style=subtitle_style,
    )


@pytest.fixture
def project_factory(tmp_path: Path):
    """Fixture to build customizable mock project structures for testing."""

    def _make_project(
        name: str = "empirical_m2_proj",
        with_final_video: bool = True,
        with_qa_video: bool = False,
        with_thumbnail: bool = True,
        script_entries: Optional[List[Dict[str, str]]] = None,
    ) -> Path:
        proj = tmp_path / name
        proj.mkdir(parents=True, exist_ok=True)
        audio_dir = proj / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        # WAV audio
        wav_path = audio_dir / "001_Zundamon.wav"
        _create_minimal_wav(wav_path)

        # Script
        entries = script_entries or [
            {"character": "ずんだもん", "text": "YouTube自動投稿の検証なのだ！"},
            {"character": "四国めたん", "text": "字幕とスケジュール投稿も完璧ですわ！"},
        ]
        (proj / "script.json").write_text(
            json.dumps(entries, ensure_ascii=False), encoding="utf-8"
        )

        # Video artifacts
        if with_final_video:
            (proj / "final_video.mp4").write_bytes(b"\x00" * 4096)
        if with_qa_video:
            (proj / "qa_test.mp4").write_bytes(b"\x00" * 2048)

        # Thumbnail
        if with_thumbnail:
            (proj / "thumbnail.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1024)

        return proj

    return _make_project


# =============================================================================
# Test Group 1: ProjectPipeline.run Empirical Integration & Discovery
# =============================================================================


class TestPipelineRunEmpiricalIntegration:
    """Empirical verification of ProjectPipeline.run coordinating upload, thumbnail, and captions."""

    def test_pipeline_run_mock_upload_end_to_end(self, project_factory: Any) -> None:
        """Pipeline successfully uploads final_video.mp4, thumbnail.png, and creates .srt caption file on disk."""
        proj_dir = project_factory(name="proj_e2e_nominal")
        dummy_wav = proj_dir / "audio" / "001_Zundamon.wav"
        mock_pub = MockYouTubeAdapter()

        pipeline = ProjectPipeline(use_tts=False)

        with (
            patch("veraxi_ymmp.pipeline.MoviePyRenderer"),
            patch(
                "veraxi_ymmp.pipeline.generate_project_thumbnail",
                return_value=proj_dir / "thumbnail.png",
            ),
            patch("veraxi_ymmp.pipeline.YMMPCompiler.build_ir") as mock_build_ir,
        ):
            ir = TimelineIR(
                fps=60,
                total_frames=120,
                voice_clips=[
                    _make_voice_clip(
                        start_frame=0,
                        length=60,
                        character="ずんだもん",
                        text="YouTube自動投稿の検証なのだ！",
                        audio_path=dummy_wav,
                    ),
                    _make_voice_clip(
                        start_frame=60,
                        length=60,
                        character="四国めたん",
                        text="字幕とスケジュール投稿も完璧ですわ！",
                        audio_path=dummy_wav,
                    ),
                ],
            )
            mock_build_ir.return_value = (ir, [dummy_wav])

            result = pipeline.run(
                project_path=proj_dir,
                do_premiere=False,
                do_ymmp=False,
                do_qa=False,
                do_thumbnail=False,
                upload_to_youtube=True,
                mock_upload=True,
                publisher=mock_pub,
            )

        # 1. Pipeline result checks
        assert result.success is True, f"Pipeline errors: {result.errors}"
        assert result.upload_result is not None
        assert result.upload_result.status in ("completed", "uploaded")
        assert result.upload_result.video_id != ""
        assert result.upload_result.thumbnail_uploaded is True

        # 2. SRT file created on disk
        srt_file = proj_dir / f"{proj_dir.name}.srt"
        assert srt_file.exists(), f"Expected SRT file at {srt_file}"
        assert result.srt_path == srt_file
        srt_content = srt_file.read_text(encoding="utf-8")
        assert "1\n00:00:00,000 --> 00:00:01,000\nYouTube自動投稿の検証なのだ！" in srt_content
        assert "2\n00:00:01,000 --> 00:00:02,000\n字幕とスケジュール投稿も完璧ですわ！" in srt_content

        # 3. Mock publisher calls and states
        vid_id = result.upload_result.video_id
        assert vid_id in mock_pub.uploaded_videos
        uploaded_video_path, uploaded_meta = mock_pub.uploaded_videos[vid_id]
        assert uploaded_video_path == proj_dir / "final_video.mp4"
        assert uploaded_meta.title == "proj_e2e_nominal"
        assert uploaded_meta.privacy_status == "private"

        assert vid_id in mock_pub.uploaded_thumbnails
        assert mock_pub.uploaded_thumbnails[vid_id] == proj_dir / "thumbnail.png"

        assert len(mock_pub.uploaded_captions) == 1
        cap_entry = mock_pub.uploaded_captions[0]
        assert cap_entry["video_id"] == vid_id
        assert cap_entry["caption_path"] == srt_file
        assert cap_entry["language"] == "ja"
        assert cap_entry["name"] == "Japanese"

        # 4. Invariant call order: video -> thumbnail -> caption
        assert mock_pub.call_log == [
            "upload_video:final_video.mp4",
            f"upload_thumbnail:{vid_id}",
            f"upload_caption:{vid_id}",
        ]

    def test_pipeline_run_falls_back_to_qa_video_when_final_video_absent(
        self, project_factory: Any
    ) -> None:
        """When final_video.mp4 is missing and do_qa=True, target_video falls back to qa_test.mp4."""
        proj_dir = project_factory(
            name="proj_fallback_qa",
            with_final_video=False,
            with_qa_video=True,
        )
        dummy_wav = proj_dir / "audio" / "001_Zundamon.wav"
        mock_pub = MockYouTubeAdapter()

        pipeline = ProjectPipeline(use_tts=False)

        with (
            patch("veraxi_ymmp.pipeline.MoviePyRenderer"),
            patch("veraxi_ymmp.pipeline.YMMPCompiler.build_ir") as mock_build_ir,
        ):
            ir = TimelineIR(
                fps=60,
                total_frames=60,
                voice_clips=[_make_voice_clip(0, 60, "ずんだもん", "QAテストなのだ", dummy_wav)],
            )
            mock_build_ir.return_value = (ir, [dummy_wav])

            result = pipeline.run(
                project_path=proj_dir,
                do_premiere=False,
                do_ymmp=False,
                do_qa=True,
                do_thumbnail=False,
                upload_to_youtube=True,
                mock_upload=True,
                publisher=mock_pub,
            )

        assert result.success is True, f"Errors: {result.errors}"
        vid_id = list(mock_pub.uploaded_videos.keys())[0]
        uploaded_video_path, _ = mock_pub.uploaded_videos[vid_id]
        assert uploaded_video_path.name == "qa_test.mp4"
        assert "upload_video:qa_test.mp4" in mock_pub.call_log

    def test_pipeline_run_fails_gracefully_when_no_video_artifact_exists(
        self, project_factory: Any
    ) -> None:
        """When neither final_video.mp4 nor qa_test.mp4 exists, pipeline fails with explicit error."""
        proj_dir = project_factory(
            name="proj_no_video",
            with_final_video=False,
            with_qa_video=False,
        )
        mock_pub = MockYouTubeAdapter()
        pipeline = ProjectPipeline(use_tts=False)

        with (
            patch("veraxi_ymmp.pipeline.MoviePyRenderer"),
            patch("veraxi_ymmp.pipeline.YMMPCompiler.build_ir") as mock_build_ir,
        ):
            ir = TimelineIR(fps=60, total_frames=60, voice_clips=[])
            mock_build_ir.return_value = (ir, [])

            result = pipeline.run(
                project_path=proj_dir,
                do_premiere=False,
                do_ymmp=False,
                do_qa=False,
                do_thumbnail=False,
                upload_to_youtube=True,
                mock_upload=True,
                publisher=mock_pub,
            )

        assert result.success is False
        assert any("No video artifact found for YouTube upload" in err for err in result.errors)
        assert len(mock_pub.uploaded_videos) == 0

    def test_pipeline_run_without_thumbnail_proceeds_with_video_and_captions(
        self, project_factory: Any
    ) -> None:
        """When thumbnail is absent, upload_video and upload_caption still execute."""
        proj_dir = project_factory(
            name="proj_no_thumb",
            with_final_video=True,
            with_thumbnail=False,
        )
        dummy_wav = proj_dir / "audio" / "001_Zundamon.wav"
        mock_pub = MockYouTubeAdapter()
        pipeline = ProjectPipeline(use_tts=False)

        with (
            patch("veraxi_ymmp.pipeline.MoviePyRenderer"),
            patch("veraxi_ymmp.pipeline.YMMPCompiler.build_ir") as mock_build_ir,
        ):
            ir = TimelineIR(
                fps=60,
                total_frames=60,
                voice_clips=[
                    _make_voice_clip(
                        start_frame=0,
                        length=60,
                        character="ずんだもん",
                        text="サムネイルなしでも投稿できるのだ！",
                        audio_path=dummy_wav,
                    )
                ],
            )
            mock_build_ir.return_value = (ir, [dummy_wav])

            result = pipeline.run(
                project_path=proj_dir,
                do_premiere=False,
                do_ymmp=False,
                do_qa=False,
                do_thumbnail=False,
                upload_to_youtube=True,
                mock_upload=True,
                publisher=mock_pub,
            )

        assert result.success is True
        vid_id = result.upload_result.video_id
        assert vid_id in mock_pub.uploaded_videos
        assert vid_id not in mock_pub.uploaded_thumbnails
        assert len(mock_pub.uploaded_captions) == 1
        assert mock_pub.call_log == [
            "upload_video:final_video.mp4",
            f"upload_caption:{vid_id}",
        ]


    def test_pipeline_run_loudness_normalization_invoked(
        self, project_factory: Any
    ) -> None:
        """normalize_loudness=True passes target -14.0 LUFS and uploads the normalized file."""
        proj_dir = project_factory(name="proj_norm")
        dummy_wav = proj_dir / "audio" / "001_Zundamon.wav"
        mock_pub = MockYouTubeAdapter()
        pipeline = ProjectPipeline(use_tts=False)

        norm_file = proj_dir / "final_video_normalized.mp4"
        norm_file.write_bytes(b"\x00" * 3000)

        with (
            patch("veraxi_ymmp.pipeline.MoviePyRenderer"),
            patch("veraxi_ymmp.pipeline.YMMPCompiler.build_ir") as mock_build_ir,
            patch(
                "veraxi_ymmp.audio_normalizer.normalize_video_audio",
                return_value=norm_file,
            ) as mock_norm,
        ):
            ir = TimelineIR(fps=60, total_frames=60, voice_clips=[])
            mock_build_ir.return_value = (ir, [dummy_wav])

            result = pipeline.run(
                project_path=proj_dir,
                do_premiere=False,
                do_ymmp=False,
                do_qa=False,
                do_thumbnail=False,
                upload_to_youtube=True,
                mock_upload=True,
                normalize_loudness=True,
                publisher=mock_pub,
            )

        assert result.success is True
        mock_norm.assert_called_once_with(
            proj_dir / "final_video.mp4",
            proj_dir / "final_video_normalized.mp4",
            target_i=-14.0,
        )
        vid_id = list(mock_pub.uploaded_videos.keys())[0]
        uploaded_video_path, _ = mock_pub.uploaded_videos[vid_id]
        assert uploaded_video_path == norm_file


# =============================================================================
# Test Group 2: SRT Generation Precision and SubRip Standard Conformance
# =============================================================================


class TestSRTGenerationAdversarial:
    """Stress test SRT timestamp formatting and SubRip output structure."""

    @pytest.mark.parametrize(
        "seconds,expected_srt_time",
        [
            (0.0, "00:00:00,000"),
            (0.001, "00:00:00,001"),
            (0.9994, "00:00:00,999"),
            (0.9999, "00:00:00,999"),  # Clamping protection against 1000ms rollover
            (1.0, "00:00:01,000"),
            (59.999, "00:00:59,999"),
            (60.0, "00:01:00,000"),
            (3599.999, "00:59:59,999"),
            (3600.0, "01:00:00,000"),
            (3661.123, "01:01:01,123"),
            (-10.5, "00:00:00,000"),  # Negative timestamp safety
        ],
    )
    def test_srt_time_formatter_precision(self, seconds: float, expected_srt_time: str) -> None:
        assert _format_srt_time(seconds) == expected_srt_time

    def test_generate_srt_multiple_clips_and_japanese_characters(self, tmp_path: Path) -> None:
        out_srt = tmp_path / "test_japanese.srt"
        ir = TimelineIR(
            fps=30,
            total_frames=300,
            voice_clips=[
                _make_voice_clip(
                    start_frame=0,
                    length=45,  # 0.0s to 1.5s
                    character="ずんだもん",
                    text="『こんにちは！』",
                ),
                _make_voice_clip(
                    start_frame=45,
                    length=75,  # 1.5s to 4.0s
                    character="四国めたん",
                    text="「ご機嫌麗しゅうございますわ。」",
                ),
                _make_voice_clip(
                    start_frame=150,
                    length=90,  # 5.0s to 8.0s
                    character="ずんだもん",
                    text="YouTube Data API v3 & SRT連携テストなのだ！",
                ),
            ],
        )

        res_path = generate_srt(ir, out_srt)
        assert res_path.exists()
        lines = out_srt.read_text(encoding="utf-8").strip().split("\n\n")
        assert len(lines) == 3

        block1 = lines[0].split("\n")
        assert block1[0] == "1"
        assert block1[1] == "00:00:00,000 --> 00:00:01,500"
        assert block1[2] == "『こんにちは！』"

        block2 = lines[1].split("\n")
        assert block2[0] == "2"
        assert block2[1] == "00:00:01,500 --> 00:00:04,000"
        assert block2[2] == "「ご機嫌麗しゅうございますわ。」"

        block3 = lines[2].split("\n")
        assert block3[0] == "3"
        assert block3[1] == "00:00:05,000 --> 00:00:08,000"
        assert block3[2] == "YouTube Data API v3 & SRT連携テストなのだ！"


# =============================================================================
# Test Group 3: CLI 'veraxi-ymmp run' End-to-End & Scheduling Guardrails
# =============================================================================


class TestCLIRunAdversarial:
    """Stress test 'veraxi-ymmp run' CLI command line flags, schedules, and exit codes."""

    @pytest.mark.parametrize(
        "valid_iso_ts",
        [
            "2026-11-20T10:00:00Z",
            "2026-11-20T19:00:00+09:00",
            "2026-11-20T05:00:00-05:00",
            "2026-11-20T10:00:00.000Z",
            "2026-11-20T15:30:00+05:30",
        ],
    )
    def test_cli_run_scheduled_valid_iso_formats(
        self, project_factory: Any, valid_iso_ts: str
    ) -> None:
        """Valid ISO-8601 publish_at timestamps with private visibility pass CLI validation."""
        proj_dir = project_factory(name=f"proj_cli_{valid_iso_ts.replace(':', '_')}")
        dummy_wav = proj_dir / "audio" / "001_Zundamon.wav"
        mock_pub = MockYouTubeAdapter()

        with (
            patch("veraxi_ymmp.pipeline.MoviePyRenderer"),
            patch(
                "veraxi_ymmp.pipeline.generate_project_thumbnail",
                return_value=proj_dir / "thumbnail.png",
            ),
            patch("veraxi_ymmp.pipeline.YMMPCompiler.build_ir") as mock_build_ir,
            patch(
                "veraxi_ymmp.youtube_adapter.MockYouTubeAdapter",
                return_value=mock_pub,
            ),
            patch.object(
                sys,
                "argv",
                [
                    "veraxi-ymmp",
                    "run",
                    str(proj_dir),
                    "--upload-to-youtube",
                    "--mock-upload",
                    "--publish-at",
                    valid_iso_ts,
                    "--privacy",
                    "private",
                ],
            ),
        ):
            ir = TimelineIR(
                fps=60,
                total_frames=60,
                voice_clips=[
                    _make_voice_clip(
                        0,
                        60,
                        "ずんだもん",
                        "スケジュール投稿なのだ！",
                        dummy_wav,
                    )
                ],
            )
            mock_build_ir.return_value = (ir, [dummy_wav])

            main()

        assert len(mock_pub.uploaded_videos) == 1
        vid_id = list(mock_pub.uploaded_videos.keys())[0]
        _, meta = mock_pub.uploaded_videos[vid_id]
        assert meta.publish_at == valid_iso_ts
        assert meta.privacy_status == "private"


    @pytest.mark.parametrize(
        "invalid_privacy",
        ["public", "unlisted"],
    )
    def test_cli_run_publish_at_with_non_private_exits_code_1(
        self, project_factory: Any, invalid_privacy: str, capsys: Any
    ) -> None:
        """CLI immediately rejects scheduled uploads if privacy is not 'private'."""
        proj_dir = project_factory(name="proj_invalid_privacy")

        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "run",
                str(proj_dir),
                "--upload-to-youtube",
                "--mock-upload",
                "--publish-at",
                "2026-11-20T10:00:00Z",
                "--privacy",
                invalid_privacy,
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "YouTube requires privacy_status='private' for scheduled uploads" in captured.err

    @pytest.mark.parametrize(
        "bad_iso_ts",
        [
            "tomorrow at 3pm",
            "2026/11/20 10:00:00",
            "2026-11-35T10:00:00Z",
            "not-a-date",
            "2026-02-30T12:00:00Z",
        ],
    )
    def test_cli_run_publish_at_with_invalid_iso_format_exits_code_1(
        self, project_factory: Any, bad_iso_ts: str, capsys: Any
    ) -> None:
        """CLI immediately rejects invalid ISO-8601 publish_at strings."""
        proj_dir = project_factory(name="proj_bad_iso")

        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "run",
                str(proj_dir),
                "--upload-to-youtube",
                "--mock-upload",
                "--publish-at",
                bad_iso_ts,
                "--privacy",
                "private",
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Invalid ISO-8601 publish_at format" in captured.err


# =============================================================================
# Test Group 4: Direct Pipeline Scheduling & Validation Invariants
# =============================================================================


class TestPipelineRunDirectSchedulingValidation:
    """Verify that ProjectPipeline.run directly validates scheduling invariants."""

    def test_pipeline_direct_invalid_privacy_schedule_records_error(
        self, project_factory: Any
    ) -> None:
        """Calling ProjectPipeline.run directly with publish_at and public privacy fails and records error."""
        proj_dir = project_factory(name="proj_direct_sched_invalid")
        dummy_wav = proj_dir / "audio" / "001_Zundamon.wav"
        pipeline = ProjectPipeline(use_tts=False)

        with (
            patch("veraxi_ymmp.pipeline.MoviePyRenderer"),
            patch("veraxi_ymmp.pipeline.YMMPCompiler.build_ir") as mock_build_ir,
        ):
            ir = TimelineIR(fps=60, total_frames=60, voice_clips=[])
            mock_build_ir.return_value = (ir, [dummy_wav])

            result = pipeline.run(
                project_path=proj_dir,
                do_premiere=False,
                do_ymmp=False,
                do_qa=False,
                do_thumbnail=False,
                upload_to_youtube=True,
                mock_upload=True,
                publish_at="2026-11-20T10:00:00Z",
                privacy_status="public",
            )

        assert result.success is False
        assert any("YouTube requires privacy_status='private'" in err for err in result.errors)

    def test_pipeline_direct_invalid_iso_format_records_error(
        self, project_factory: Any
    ) -> None:
        """Calling ProjectPipeline.run directly with non-ISO string fails and records error."""
        proj_dir = project_factory(name="proj_direct_sched_bad_iso")
        dummy_wav = proj_dir / "audio" / "001_Zundamon.wav"
        pipeline = ProjectPipeline(use_tts=False)

        with (
            patch("veraxi_ymmp.pipeline.MoviePyRenderer"),
            patch("veraxi_ymmp.pipeline.YMMPCompiler.build_ir") as mock_build_ir,
        ):
            ir = TimelineIR(fps=60, total_frames=60, voice_clips=[])
            mock_build_ir.return_value = (ir, [dummy_wav])

            result = pipeline.run(
                project_path=proj_dir,
                do_premiere=False,
                do_ymmp=False,
                do_qa=False,
                do_thumbnail=False,
                upload_to_youtube=True,
                mock_upload=True,
                publish_at="invalid-iso-timestamp",
                privacy_status="private",
            )

        assert result.success is False
        assert any("Invalid ISO-8601 publish_at format" in err for err in result.errors)
