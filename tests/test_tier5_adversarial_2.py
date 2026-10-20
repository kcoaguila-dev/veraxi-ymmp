"""Tier 5 Adversarial Coverage Hardening: CLI & End-to-End Stress Testing.

White-box stress tests verifying:
1. CLI parameter & argument parsing adversarial stress (missing subcommands, invalid choices,
   unsupported flags, missing required options).
2. Boundary thresholds for retention QA (0.0, 1.0, negative, tiny, NaN, infinity).
3. Malformed and edge-case project configurations (non-existent, file-as-dir, missing script,
   corrupted JSON, invalid schema, empty timeline, missing templates).
4. Output directory auto-creation and security sanitization (deeply nested directories,
   pre-existing file collision, path traversal prevention, Windows invalid character cleansing).
5. Machine-parseable JSON and Markdown serialization robustness (round-trip fidelity, Japanese
   Unicode/emojis, pipe escaping, extreme text truncation, multiline sanitization).
6. Upload and status CLI operational edge cases (mock failure injection, unexpected adapter exceptions,
   production mode without credentials).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from veraxi_ymmp.cli import main
from veraxi_ymmp.ir import (
    CutRetentionMetric,
    RetentionDropoffPoint,
    VideoPublishMetadata,
    VideoRetentionReport,
)
from veraxi_ymmp.retention_qa import RetentionCorrelationEngine


@pytest.fixture
def dummy_video(tmp_path: Path) -> Path:
    """Create a minimal video file for CLI upload testing."""
    video = tmp_path / "sample_video.mp4"
    video.write_bytes(b"\x00" * 1024)
    return video


@pytest.fixture
def dummy_thumbnail(tmp_path: Path) -> Path:
    """Create a minimal PNG thumbnail file."""
    thumb = tmp_path / "sample_thumb.png"
    thumb.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 512)
    return thumb


@pytest.fixture
def minimal_project(tmp_path: Path) -> Path:
    """Create a minimal valid project directory with script.json."""
    proj = tmp_path / "minimal_project"
    proj.mkdir(parents=True, exist_ok=True)
    script_data = [
        {
            "character": "ずんだもん",
            "emotion": "happy",
            "text": "テストなのだ！",
        },
        {
            "character": "四国めたん",
            "emotion": "normal",
            "text": "テストですわ。",
        },
    ]
    (proj / "script.json").write_text(
        json.dumps(script_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return proj


# ============================================================================
# 1. CLI Parameter & Argument Parsing Adversarial Stress
# ============================================================================


class TestCLIAdversarialArguments:
    """Adversarial stress testing on CLI subcommands and parameter parsing."""

    def test_youtube_missing_subcommand_exits_code_2(self, capsys: Any) -> None:
        """Invoking 'veraxi-ymmp youtube' without subcommands prints help and exits 2."""
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2

    def test_youtube_invalid_subcommand_exits_code_2(self) -> None:
        """Invoking unknown subcommand exits with code 2."""
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "destroy"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2

    def test_youtube_unexpected_flags_exits_code_2(self) -> None:
        """Invoking top-level youtube with unknown flag exits 2."""
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "--nonexistent-flag"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2

    def test_upload_missing_video_path_exits_code_2(self) -> None:
        """'youtube upload' without video path exits with code 2."""
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "upload"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2

    def test_upload_invalid_privacy_choice_exits_code_2(self, dummy_video: Path) -> None:
        """'youtube upload' with unsupported privacy choice exits 2."""
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "upload",
                str(dummy_video),
                "--privacy",
                "confidential",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2

    def test_status_missing_video_id_exits_code_2(self) -> None:
        """'youtube status' without video_id exits 2."""
        with patch.object(sys, "argv", ["veraxi-ymmp", "youtube", "status"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2

    def test_qa_missing_video_id_exits_code_2(self, minimal_project: Path) -> None:
        """'youtube qa' without --video-id exits with code 2."""
        with patch.object(
            sys,
            "argv",
            ["veraxi-ymmp", "youtube", "qa", "--project", str(minimal_project)],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2

    def test_qa_missing_project_exits_code_2(self) -> None:
        """'youtube qa' without --project exits with code 2."""
        with patch.object(
            sys,
            "argv",
            ["veraxi-ymmp", "youtube", "qa", "--video-id", "test_video_123"],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2

    def test_qa_invalid_string_threshold_exits_code_2(
        self, minimal_project: Path
    ) -> None:
        """'youtube qa' with non-float string threshold exits with code 2."""
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
                str(minimal_project),
                "--threshold",
                "invalid_threshold_str",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2

    def test_qa_invalid_percent_threshold_exits_code_2(
        self, minimal_project: Path
    ) -> None:
        """'youtube qa' with '5%' string threshold exits with code 2."""
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
                str(minimal_project),
                "--threshold",
                "5%",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2


# ============================================================================
# 2. Boundary Thresholds for Retention QA Telemetry
# ============================================================================


class TestCLIAdversarialBoundaryThresholds:
    """Stress-testing threshold boundary conditions in retention QA."""

    def test_qa_threshold_zero_boundary(
        self, minimal_project: Path, tmp_path: Path
    ) -> None:
        """Threshold 0.0 captures every point where retention drops."""
        out_dir = tmp_path / "qa_zero_threshold"
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "qa",
                "--video-id",
                "zero_thresh_vid",
                "--project",
                str(minimal_project),
                "--output",
                str(out_dir),
                "--threshold",
                "0.0",
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

        report_file = out_dir / "zero_thresh_vid_report.json"
        assert report_file.exists()
        data = json.loads(report_file.read_text(encoding="utf-8"))
        assert data["dropoff_threshold"] == 0.0
        assert len(data["dropoff_points"]) > 0

    def test_qa_threshold_one_boundary_no_drops(
        self, minimal_project: Path, tmp_path: Path
    ) -> None:
        """Threshold 1.0 yields 0 dropoff points for normal retention curves."""
        out_dir = tmp_path / "qa_one_threshold"
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "qa",
                "--video-id",
                "one_thresh_vid",
                "--project",
                str(minimal_project),
                "--output",
                str(out_dir),
                "--threshold",
                "1.0",
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

        report_file = out_dir / "one_thresh_vid_report.json"
        assert report_file.exists()
        data = json.loads(report_file.read_text(encoding="utf-8"))
        assert data["dropoff_threshold"] == 1.0
        assert len(data["dropoff_points"]) == 0

    def test_qa_threshold_tiny_boundary(
        self, minimal_project: Path, tmp_path: Path
    ) -> None:
        """Threshold 0.0001 processes cleanly and detects subtle drops."""
        out_dir = tmp_path / "qa_tiny_threshold"
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "qa",
                "--video-id",
                "tiny_thresh_vid",
                "--project",
                str(minimal_project),
                "--output",
                str(out_dir),
                "--threshold",
                "0.0001",
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

        report_file = out_dir / "tiny_thresh_vid_report.json"
        assert report_file.exists()

    def test_qa_threshold_nan_handled_gracefully(
        self, minimal_project: Path, tmp_path: Path
    ) -> None:
        """Threshold 'nan' parses to float('nan'), runs without unhandled crash."""
        out_dir = tmp_path / "qa_nan_threshold"
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "qa",
                "--video-id",
                "nan_thresh_vid",
                "--project",
                str(minimal_project),
                "--output",
                str(out_dir),
                "--threshold",
                "nan",
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

        report_file = out_dir / "nan_thresh_vid_report.json"
        assert report_file.exists()
        md_file = out_dir / "nan_thresh_vid_report.md"
        assert md_file.exists()
        md_content = md_file.read_text(encoding="utf-8")
        assert "Drop-off Threshold" in md_content

    def test_qa_threshold_infinity_handled_gracefully(
        self, minimal_project: Path, tmp_path: Path
    ) -> None:
        """Threshold 'inf' yields 0 dropoff points without crashing."""
        out_dir = tmp_path / "qa_inf_threshold"
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "qa",
                "--video-id",
                "inf_thresh_vid",
                "--project",
                str(minimal_project),
                "--output",
                str(out_dir),
                "--threshold",
                "inf",
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

        report_file = out_dir / "inf_thresh_vid_report.json"
        assert report_file.exists()
        data = json.loads(report_file.read_text(encoding="utf-8"))
        assert len(data["dropoff_points"]) == 0

    def test_qa_threshold_negative_boundary(
        self, minimal_project: Path, tmp_path: Path
    ) -> None:
        """Negative threshold '--threshold=-0.05' is parsed and processed."""
        out_dir = tmp_path / "qa_neg_threshold"
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "qa",
                "--video-id",
                "neg_thresh_vid",
                "--project",
                str(minimal_project),
                "--output",
                str(out_dir),
                "--threshold=-0.05",
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

        report_file = out_dir / "neg_thresh_vid_report.json"
        assert report_file.exists()


# ============================================================================
# 3. Malformed and Edge-Case Project Configurations
# ============================================================================


class TestCLIAdversarialProjectConfigs:
    """Stress-testing invalid, missing, or malformed project configurations."""

    def test_qa_nonexistent_project_path_exits_1(self, tmp_path: Path) -> None:
        """Nonexistent project directory logs error and exits 1."""
        ghost_path = tmp_path / "ghost_project_dir"
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
                str(ghost_path),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_qa_project_path_is_file_not_dir_exits_1(self, tmp_path: Path) -> None:
        """Passing a file instead of a directory as --project exits 1."""
        file_path = tmp_path / "file_instead_of_dir.txt"
        file_path.write_text("not a directory", encoding="utf-8")
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
                str(file_path),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_qa_project_missing_script_json_exits_1(self, tmp_path: Path) -> None:
        """Project directory without script.json exits 1."""
        empty_dir = tmp_path / "empty_dir"
        empty_dir.mkdir()
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
                str(empty_dir),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_qa_malformed_json_script_exits_1(self, tmp_path: Path) -> None:
        """Corrupted JSON in script.json fails pipeline and exits 1 cleanly."""
        corrupt_proj = tmp_path / "corrupt_proj"
        corrupt_proj.mkdir()
        (corrupt_proj / "script.json").write_text(
            "{this is not valid json syntax", encoding="utf-8"
        )
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
                str(corrupt_proj),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_qa_invalid_schema_script_exits_1(self, tmp_path: Path) -> None:
        """Valid JSON but invalid script structure fails pipeline and exits 1."""
        bad_schema_proj = tmp_path / "bad_schema_proj"
        bad_schema_proj.mkdir()
        (bad_schema_proj / "script.json").write_text(
            json.dumps({"timeline": "not_an_array_of_cuts"}), encoding="utf-8"
        )
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
                str(bad_schema_proj),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_qa_empty_script_timeline_succeeds_gracefully(
        self, tmp_path: Path
    ) -> None:
        """Empty script array '[]' compiles to 0 cuts and exits 0 with nominal report."""
        empty_script_proj = tmp_path / "empty_script_proj"
        empty_script_proj.mkdir()
        (empty_script_proj / "script.json").write_text("[]", encoding="utf-8")
        out_dir = tmp_path / "empty_script_out"
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "qa",
                "--video-id",
                "empty_vid",
                "--project",
                str(empty_script_proj),
                "--output",
                str(out_dir),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

        report_file = out_dir / "empty_vid_report.json"
        assert report_file.exists()
        data = json.loads(report_file.read_text(encoding="utf-8"))
        assert data["total_cuts"] == 0
        assert data["cut_metrics"] == []

    def test_qa_missing_all_template_candidates_exits_1(
        self, minimal_project: Path
    ) -> None:
        """When no YMM4 template is found across all fallback candidates, exits 1."""
        with patch("pathlib.Path.exists", autospec=True) as mock_exists:
            # Allow project_path and script_path to exist, but simulate template paths not existing
            def side_effect(p_self: Path) -> bool:
                p_str = str(p_self).replace("\\", "/")
                if "template" in p_str:
                    return False
                return True

            mock_exists.side_effect = side_effect

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
                    str(minimal_project),
                    "--mock",
                ],
            ):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 1


# ============================================================================
# 4. Output Directory Auto-Creation and Security Sanitization
# ============================================================================


class TestCLIAdversarialOutputDirectoryHandling:
    """Stress-testing report directory generation and path sanitization."""

    def test_qa_auto_creates_deeply_nested_output_directory(
        self, minimal_project: Path, tmp_path: Path
    ) -> None:
        """Deeply nested non-existent directory is recursively created."""
        deep_dir = (
            tmp_path / "deep_1" / "nested_2" / "level_3" / "sub_4" / "reports_out"
        )
        assert not deep_dir.exists()

        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "qa",
                "--video-id",
                "nested_vid",
                "--project",
                str(minimal_project),
                "--output",
                str(deep_dir),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

        assert deep_dir.exists()
        assert (deep_dir / "nested_vid_report.json").exists()
        assert (deep_dir / "nested_vid_report.md").exists()

    def test_qa_default_output_creates_project_qa_reports(
        self, minimal_project: Path
    ) -> None:
        """Omitting --output automatically creates <project>/qa_reports."""
        default_dir = minimal_project / "qa_reports"
        assert not default_dir.exists()

        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "qa",
                "--video-id",
                "default_out_vid",
                "--project",
                str(minimal_project),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

        assert default_dir.exists()
        assert (default_dir / "default_out_vid_report.json").exists()
        assert (default_dir / "default_out_vid_report.md").exists()

    def test_qa_output_dir_is_existing_file_fails_cleanly_exits_1(
        self, minimal_project: Path, tmp_path: Path
    ) -> None:
        """When --output points to a file, mkdir fails and CLI exits 1 cleanly."""
        blocker = tmp_path / "already_a_file.txt"
        blocker.write_text("I am a file", encoding="utf-8")

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
                str(minimal_project),
                "--output",
                str(blocker),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_save_reports_path_traversal_sanitization(self, tmp_path: Path) -> None:
        """Video ID with path traversal sequences is sanitized to prevent directory escape."""
        engine = RetentionCorrelationEngine()
        report = VideoRetentionReport(
            video_id="../../../etc/passwd",
            video_title="Traversal Attack Test",
            total_duration_sec=10.0,
            total_cuts=1,
            retention_score=80.0,
            average_view_percentage=80.0,
            dropoff_threshold=0.05,
            dropoff_points=[],
            cut_metrics=[],
            summary_verdict="NOMINAL",
            editorial_recommendations=[],
        )
        json_file, md_file = engine.save_reports(report, tmp_path)
        assert json_file.parent == tmp_path
        assert md_file.parent == tmp_path
        assert ".." not in json_file.name
        assert json_file.name.endswith("_report.json")
        assert json_file.exists()

    def test_save_reports_windows_invalid_filename_characters(
        self, tmp_path: Path
    ) -> None:
        """Video ID with Windows invalid characters (:*?\"<>|) is sanitized cleanly."""
        engine = RetentionCorrelationEngine()
        report = VideoRetentionReport(
            video_id='vid:123*456?789<0>|bar"baz',
            video_title="Invalid Windows Chars Test",
            total_duration_sec=15.0,
            total_cuts=2,
            retention_score=75.0,
            average_view_percentage=75.0,
            dropoff_threshold=0.05,
            dropoff_points=[],
            cut_metrics=[],
            summary_verdict="NOMINAL",
            editorial_recommendations=[],
        )
        json_file, md_file = engine.save_reports(report, tmp_path)
        assert json_file.exists()
        assert md_file.exists()
        # Verify forbidden characters were replaced with underscore
        for char in ':*?"<>|':
            assert char not in json_file.name

    def test_save_reports_empty_and_whitespace_video_id(self, tmp_path: Path) -> None:
        """Empty video ID falls back to 'retention_qa_report' filename."""
        engine = RetentionCorrelationEngine()
        report = VideoRetentionReport(
            video_id="",
            video_title="Empty ID Test",
            total_duration_sec=5.0,
            total_cuts=0,
            retention_score=0.0,
            average_view_percentage=0.0,
            dropoff_threshold=0.05,
            dropoff_points=[],
            cut_metrics=[],
            summary_verdict="NOMINAL",
            editorial_recommendations=[],
        )
        json_file, md_file = engine.save_reports(report, tmp_path)
        assert json_file.name == "retention_qa_report.json"
        assert md_file.name == "retention_qa_report.md"


# ============================================================================
# 5. Machine-Parseable JSON & Markdown Serialization Robustness
# ============================================================================


class TestReportSerializationStressAndRoundTrip:
    """Stress-testing report serialization, escaping, and formatting."""

    def test_json_round_trip_preserves_all_attributes(self) -> None:
        """Verify full round-trip serialization between domain entity and JSON."""
        engine = RetentionCorrelationEngine()
        drop = RetentionDropoffPoint(
            timestamp_sec=12.5,
            elapsed_ratio=0.25,
            retention_before=0.85,
            retention_after=0.72,
            drop_magnitude=0.13,
            cut_index=3,
            speaker="ずんだもん",
            subtitle_text="ここで急な難解用語を話してしまったのだ…",
            emotion="surprised",
            broll_image="slide_01.png",
            issue_type="PACING_OR_FATIGUE",
            recommendation="カット #3: フックを再構築してください。",
        )
        cut_metric = CutRetentionMetric(
            cut_index=3,
            speaker="ずんだもん",
            text="ここで急な難解用語を話してしまったのだ…",
            start_sec=10.0,
            end_sec=14.0,
            start_retention=0.85,
            end_retention=0.72,
            retention_change=-0.13,
            broll_image="slide_01.png",
        )
        report = VideoRetentionReport(
            video_id="round_trip_vid",
            video_title="Round Trip Verification",
            total_duration_sec=50.0,
            total_cuts=10,
            retention_score=72.5,
            average_view_percentage=65.2,
            dropoff_threshold=0.05,
            dropoff_points=[drop],
            cut_metrics=[cut_metric],
            summary_verdict="NEEDS_OPTIMIZATION",
            editorial_recommendations=["改善を推奨します。"],
        )

        rendered_json = engine.render_json(report)
        parsed = json.loads(rendered_json)

        assert parsed["video_id"] == "round_trip_vid"
        assert parsed["total_cuts"] == 10
        assert parsed["retention_score"] == 72.5
        assert len(parsed["dropoff_points"]) == 1
        assert parsed["dropoff_points"][0]["speaker"] == "ずんだもん"
        assert parsed["dropoff_points"][0]["drop_magnitude"] == 0.13
        assert len(parsed["cut_metrics"]) == 1
        assert parsed["cut_metrics"][0]["retention_change"] == -0.13

    def test_json_unicode_japanese_and_emoji_fidelity(self) -> None:
        """Verify Japanese characters and emojis are not Unicode-escaped or corrupted."""
        engine = RetentionCorrelationEngine()
        jp_text = "「はい、まさにその通りなのだ！🚀💥」"
        drop = RetentionDropoffPoint(
            timestamp_sec=5.0,
            elapsed_ratio=0.1,
            retention_before=0.9,
            retention_after=0.8,
            drop_magnitude=0.1,
            cut_index=1,
            speaker="四国めたん",
            subtitle_text=jp_text,
            emotion="normal",
            broll_image=None,
        )
        report = VideoRetentionReport(
            video_id="unicode_vid_🇯🇵",
            video_title="日本語タイトルと絵文字 🎉",
            total_duration_sec=30.0,
            total_cuts=1,
            retention_score=80.0,
            average_view_percentage=80.0,
            dropoff_threshold=0.05,
            dropoff_points=[drop],
            cut_metrics=[],
            summary_verdict="NOMINAL",
            editorial_recommendations=[f"注意点: {jp_text}"],
        )

        rendered = engine.render_json(report)
        # Should contain actual UTF-8 characters, not '\u306f\u3044'
        assert jp_text in rendered
        assert "日本語タイトルと絵文字 🎉" in rendered

    def test_markdown_escaping_pipe_characters_in_subtitles_and_recommendations(
        self,
    ) -> None:
        """Pipes in subtitle text and recommendations are properly escaped with \\|."""
        engine = RetentionCorrelationEngine()
        drop = RetentionDropoffPoint(
            timestamp_sec=8.0,
            elapsed_ratio=0.2,
            retention_before=0.85,
            retention_after=0.75,
            drop_magnitude=0.10,
            cut_index=0,
            speaker="ずんだもん",
            subtitle_text="選択肢A | 選択肢B | 選択肢C",
            emotion="happy",
            broll_image="broll_test.png",
            recommendation="条件A | 条件B を確認すること",
        )
        cut = CutRetentionMetric(
            cut_index=0,
            speaker="ずんだもん",
            text="選択肢A | 選択肢B | 選択肢C",
            start_sec=0.0,
            end_sec=8.0,
            start_retention=0.85,
            end_retention=0.75,
            retention_change=-0.10,
            broll_image=None,
        )
        report = VideoRetentionReport(
            video_id="pipe_vid",
            video_title="Pipe Escaping Test",
            total_duration_sec=10.0,
            total_cuts=1,
            retention_score=75.0,
            average_view_percentage=75.0,
            dropoff_threshold=0.05,
            dropoff_points=[drop],
            cut_metrics=[cut],
            summary_verdict="NEEDS_OPTIMIZATION",
            editorial_recommendations=["注意: | パイプ検証"],
        )

        md = engine.render_markdown(report)
        # Assert escaped pipes exist in table data rows
        assert "\\|" in md
        # Table rows should not have unescaped column ruptures
        for line in md.splitlines():
            if line.startswith("| 8.0s"):
                # Dropoff table has 7 columns: | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
                # With leading and trailing pipes, splitting on unescaped pipe (not \|) gives 8 parts
                unescaped_pipes = [
                    idx for idx, c in enumerate(line) if c == "|" and (idx == 0 or line[idx - 1] != "\\")
                ]
                assert len(unescaped_pipes) == 8, f"Table row has broken pipe alignment: {line}"

    def test_markdown_pipes_in_speaker_and_slide_rupture_table_columns(self) -> None:
        """Adversarial stress test: speaker or slide containing '|' ruptures Markdown columns."""
        engine = RetentionCorrelationEngine()
        drop = RetentionDropoffPoint(
            timestamp_sec=8.0,
            elapsed_ratio=0.2,
            retention_before=0.85,
            retention_after=0.75,
            drop_magnitude=0.10,
            cut_index=0,
            speaker="ずんだもん | ナレーター",  # Speaker with pipe
            subtitle_text="セリフなのだ",
            emotion="happy",
            broll_image="slide|01.png",  # Slide with pipe
            recommendation="レコメンド",
        )
        report = VideoRetentionReport(
            video_id="pipe_rupture_vid",
            video_title="Rupture Test",
            total_duration_sec=10.0,
            total_cuts=1,
            retention_score=75.0,
            average_view_percentage=75.0,
            dropoff_threshold=0.05,
            dropoff_points=[drop],
            cut_metrics=[],
            summary_verdict="NOMINAL",
            editorial_recommendations=[],
        )
        md = engine.render_markdown(report)
        for line in md.splitlines():
            if line.startswith("| 8.0s"):
                unescaped_pipes = [
                    idx for idx, c in enumerate(line) if c == "|" and (idx == 0 or line[idx - 1] != "\\")
                ]
                # If properly escaped, exactly 8 column boundary pipes exist.
                # Currently fails with >8 because speaker and slide are unescaped.
                assert len(unescaped_pipes) == 8

    def test_markdown_truncates_extremely_long_subtitle_text(self) -> None:
        """5,000-character subtitle text is truncated in markdown table to prevent table blowup."""
        engine = RetentionCorrelationEngine()
        giant_text = "あ" * 5000
        drop = RetentionDropoffPoint(
            timestamp_sec=20.0,
            elapsed_ratio=0.5,
            retention_before=0.8,
            retention_after=0.68,
            drop_magnitude=0.12,
            cut_index=5,
            speaker="ずんだもん",
            subtitle_text=giant_text,
            emotion="normal",
            broll_image=None,
            recommendation="長文セリフを分割してください。",
        )
        cut = CutRetentionMetric(
            cut_index=5,
            speaker="ずんだもん",
            text=giant_text,
            start_sec=15.0,
            end_sec=25.0,
            start_retention=0.8,
            end_retention=0.68,
            retention_change=-0.12,
            broll_image=None,
        )
        report = VideoRetentionReport(
            video_id="giant_text_vid",
            video_title="Giant Text Test",
            total_duration_sec=40.0,
            total_cuts=1,
            retention_score=68.0,
            average_view_percentage=68.0,
            dropoff_threshold=0.05,
            dropoff_points=[drop],
            cut_metrics=[cut],
            summary_verdict="NEEDS_OPTIMIZATION",
            editorial_recommendations=[],
        )

        md = engine.render_markdown(report)
        assert giant_text not in md  # Giant text must NOT be present un-truncated
        assert "..." in md

    def test_markdown_sanitizes_newlines_in_table_cells(self) -> None:
        """Multiline subtitles with \r\n and \n do not break markdown table into multiple rows."""
        engine = RetentionCorrelationEngine()
        multiline_text = "1行目\r\n2行目\n3行目\n4行目"
        drop = RetentionDropoffPoint(
            timestamp_sec=10.0,
            elapsed_ratio=0.3,
            retention_before=0.85,
            retention_after=0.75,
            drop_magnitude=0.10,
            cut_index=2,
            speaker="四国めたん",
            subtitle_text=multiline_text,
            emotion="normal",
            broll_image=None,
            recommendation="改行入り\nレコメンド",
        )
        report = VideoRetentionReport(
            video_id="multiline_vid",
            video_title="Multiline Sanitization Test",
            total_duration_sec=30.0,
            total_cuts=1,
            retention_score=75.0,
            average_view_percentage=75.0,
            dropoff_threshold=0.05,
            dropoff_points=[drop],
            cut_metrics=[],
            summary_verdict="NOMINAL",
            editorial_recommendations=[],
        )

        md = engine.render_markdown(report)
        lines = md.splitlines()
        # Find table section
        table_lines = [line for line in lines if line.startswith("| 10.0s")]
        assert len(table_lines) == 1, "Multiline text broke table row across multiple lines!"
        assert "\n" not in table_lines[0]
        assert "\r" not in table_lines[0]

    def test_markdown_with_empty_report_zero_cuts_zero_drops(self) -> None:
        """Report with 0 cuts and 0 drops displays clear fallback notices."""
        engine = RetentionCorrelationEngine()
        report = VideoRetentionReport(
            video_id="empty_report",
            video_title="Empty Report",
            total_duration_sec=0.0,
            total_cuts=0,
            retention_score=0.0,
            average_view_percentage=0.0,
            dropoff_threshold=0.05,
            dropoff_points=[],
            cut_metrics=[],
            summary_verdict="NOMINAL",
            editorial_recommendations=["データなし"],
        )

        md = engine.render_markdown(report)
        assert "*(No retention cliff drop-offs detected exceeding threshold)*" in md
        assert "*(No dialogue cuts in timeline)*" in md

    def test_markdown_all_summary_verdicts(self) -> None:
        """Verify bold verdict formatting across all standard verdict types."""
        engine = RetentionCorrelationEngine()
        for verdict in [
            "EXCELLENT",
            "NOMINAL",
            "ATTENTION_REQUIRED",
            "NEEDS_OPTIMIZATION",
        ]:
            report = VideoRetentionReport(
                video_id="verdict_vid",
                video_title="",
                total_duration_sec=10.0,
                total_cuts=1,
                retention_score=85.0,
                average_view_percentage=85.0,
                dropoff_threshold=0.05,
                dropoff_points=[],
                cut_metrics=[],
                summary_verdict=verdict,
                editorial_recommendations=[],
            )
            md = engine.render_markdown(report)
            assert f"**{verdict}**" in md


# ============================================================================
# 6. Upload and Status CLI Operational Edge Cases
# ============================================================================


class TestCLIAdversarialUploadAndStatus:
    """Stress-testing upload and status operational error paths."""

    def test_upload_nonexistent_video_exits_1(self, tmp_path: Path) -> None:
        """Nonexistent video file logs error and exits 1."""
        ghost = tmp_path / "nonexistent.mp4"
        with patch.object(
            sys,
            "argv",
            ["veraxi-ymmp", "youtube", "upload", str(ghost), "--mock"],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_upload_directory_instead_of_file_fails_cleanly(
        self, tmp_path: Path
    ) -> None:
        """Passing a directory instead of a video file should fail with exit code 1."""
        dir_as_video = tmp_path / "dir_video"
        dir_as_video.mkdir()
        with patch.object(
            sys,
            "argv",
            ["veraxi-ymmp", "youtube", "upload", str(dir_as_video), "--mock"],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_upload_directory_as_thumbnail_fails_cleanly(
        self, dummy_video: Path, tmp_path: Path
    ) -> None:
        """Passing a directory instead of a thumbnail file should fail with exit code 1."""
        dir_as_thumb = tmp_path / "dir_thumb"
        dir_as_thumb.mkdir()
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "upload",
                str(dummy_video),
                "--thumbnail",
                str(dir_as_thumb),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_upload_nonexistent_thumbnail_exits_1(
        self, dummy_video: Path, tmp_path: Path
    ) -> None:
        """Nonexistent thumbnail file logs error and exits 1."""
        ghost_thumb = tmp_path / "ghost_thumb.png"
        with patch.object(
            sys,
            "argv",
            [
                "veraxi-ymmp",
                "youtube",
                "upload",
                str(dummy_video),
                "--thumbnail",
                str(ghost_thumb),
                "--mock",
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_upload_tags_adversarial_parsing(
        self, dummy_video: Path
    ) -> None:
        """Tags with whitespace, redundant commas, and Unicode are parsed cleanly."""
        captured_metadata = []

        def mock_upload(video_p: Path, meta: VideoPublishMetadata, **kwargs: Any) -> Any:
            captured_metadata.append(meta)
            from veraxi_ymmp.ports import UploadResult
            return UploadResult(
                video_id="mock_test_id",
                url="https://youtu.be/mock_test_id",
                status="uploaded",
            )

        with patch(
            "veraxi_ymmp.youtube_adapter.MockYouTubeAdapter.upload_video",
            side_effect=mock_upload,
        ):
            with patch.object(
                sys,
                "argv",
                [
                    "veraxi-ymmp",
                    "youtube",
                    "upload",
                    str(dummy_video),
                    "--tags",
                    "  ずんだもん ,  , YouTube  ,  Python 3  ,  ",
                    "--mock",
                ],
            ):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 0

        assert len(captured_metadata) == 1
        assert captured_metadata[0].tags == ["ずんだもん", "YouTube", "Python 3"]

    def test_upload_mock_simulated_failure_exits_1(self, dummy_video: Path) -> None:
        """When mock adapter returns status='failed', CLI exits 1."""
        with patch(
            "veraxi_ymmp.youtube_adapter.MockYouTubeAdapter.upload_video"
        ) as mock_up:
            from veraxi_ymmp.ports import UploadResult
            mock_up.return_value = UploadResult(
                video_id="",
                url="",
                status="failed",
                error_message="Simulated quota exceeded",
            )
            with patch.object(
                sys,
                "argv",
                ["veraxi-ymmp", "youtube", "upload", str(dummy_video), "--mock"],
            ):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 1

    def test_upload_adapter_unexpected_exception_exits_1(
        self, dummy_video: Path
    ) -> None:
        """When adapter upload raises unexpected Exception, CLI catches and exits 1."""
        with patch(
            "veraxi_ymmp.youtube_adapter.MockYouTubeAdapter.upload_video",
            side_effect=ConnectionResetError("Socket reset by peer"),
        ):
            with patch.object(
                sys,
                "argv",
                ["veraxi-ymmp", "youtube", "upload", str(dummy_video), "--mock"],
            ):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 1

    def test_upload_production_mode_without_credentials_exits_1(
        self, dummy_video: Path
    ) -> None:
        """Running upload without --mock in offline environment fails initialization and exits 1."""
        with patch.object(
            sys,
            "argv",
            ["veraxi-ymmp", "youtube", "upload", str(dummy_video)],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_status_production_mode_without_credentials_exits_1(self) -> None:
        """Running status without --mock in offline environment fails and exits 1."""
        with patch.object(
            sys,
            "argv",
            ["veraxi-ymmp", "youtube", "status", "test_video_live"],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
