"""
Unit Test Suite for Audience Retention QA Feedback Loop & Correlation Engine.

Tests:
1. Exact timestamp and frame calculations.
2. Attribution to active dialogue cuts (speaker, text, emotion, cut index) and B-roll visuals.
3. Cliff drop detection (>5%) and cut-level cumulative loss telemetry.
4. Retention score clamping and summary verdicts (EXCELLENT, NOMINAL, ATTENTION_REQUIRED, NEEDS_OPTIMIZATION).
5. Editorial recommendations generation (cognitive overload, static visual, pacing).
6. Structured JSON and Markdown report rendering, Path safety, and file persistence.
7. Boundary conditions: empty curve, 0 cuts, replay ratios > 1.0, unsorted curves, zero duration.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from veraxi_ymmp.ir import (
    DynamicImageClip,
    TimelineIR,
    VoiceClip,
)
from veraxi_ymmp.retention_qa import RetentionCorrelationEngine


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_timeline(tmp_path: Path) -> TimelineIR:
    """
    Constructs a 3-cut, 60-second TimelineIR at 30 FPS (1800 frames total).
    Includes 2 B-roll image slides.
    """
    fps = 30
    total_frames = 1800  # 60.0s

    # Cut 0: 0.0s - 15.0s (frames 0 - 450)
    vc0 = VoiceClip(
        start_frame=0,
        length=450,
        character="ずんだもん",
        text="コストコの安さの秘密を知っているのだ？",
        emotion="smile",
        motion="none",
        audio_path=tmp_path / "audio_0.wav",
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
        emotion="normal",
        motion="none",
        audio_path=tmp_path / "audio_1.wav",
        hatsuon="ソレワ...",
        subtitle_position="CenterBottom",
        subtitle_style="default",
    )

    # Cut 2: 35.0s - 55.0s (frames 1050 - 1650), leaving a 5-second trailing outro gap
    vc2 = VoiceClip(
        start_frame=1050,
        length=600,
        character="ずんだもん",
        text="利益のほとんどが年会費から出ているのだ！",
        emotion="surprise",
        motion="jump",
        audio_path=tmp_path / "audio_2.wav",
        hatsuon="リエキノ...",
        subtitle_position="CenterBottom",
        subtitle_style="default",
    )

    # Slide 0: frames 0 - 600 (0.0s - 20.0s)
    broll0 = DynamicImageClip(
        start_frame=0,
        length=600,
        image_path=tmp_path / "costco_entrance.png",
        is_background=False,
    )

    # Slide 1: frames 600 - 1800 (20.0s - 60.0s)
    broll1 = DynamicImageClip(
        start_frame=600,
        length=1200,
        image_path=tmp_path / "membership_chart.png",
        is_background=False,
    )

    # Background image (should be ignored in B-roll attribution)
    bg = DynamicImageClip(
        start_frame=0,
        length=1800,
        image_path=tmp_path / "classroom_bg.png",
        is_background=True,
    )

    return TimelineIR(
        fps=fps,
        total_frames=total_frames,
        voice_clips=[vc0, vc1, vc2],
        dynamic_image_clips=[broll0, broll1, bg],
    )


# ---------------------------------------------------------------------------
# 1. Exact Timestamp & Frame Calculation Tests
# ---------------------------------------------------------------------------
class TestExactTimelineMapping:
    """Tests mathematical alignment: t = r * T, F = round(r * total_frames)."""

    def test_timestamp_and_frame_precision(self, mock_timeline: TimelineIR) -> None:
        engine = RetentionCorrelationEngine()
        # 60s total, drop at ratio 0.25 (15.0s, frame 450)
        curve = [(0.0, 1.0), (0.24, 0.95), (0.25, 0.85)]
        report = engine.correlate(mock_timeline, curve)

        assert len(report.dropoff_points) == 1
        drop = report.dropoff_points[0]
        assert drop.elapsed_ratio == 0.25
        assert pytest.approx(drop.timestamp_sec, 0.01) == 15.0
        assert drop.cut_index == 1

    def test_fractional_fps_calculations(self, tmp_path: Path) -> None:
        """Verifies correlation under 24 fps and 60 fps timeline configurations."""
        fps = 60
        total_frames = 1800  # 30.0s
        vc = VoiceClip(0, 1800, "ずんだもん", "60fpsテスト", "normal", "none", tmp_path / "a.wav", "", "CB", "d")
        ir = TimelineIR(fps=fps, total_frames=total_frames, voice_clips=[vc])

        engine = RetentionCorrelationEngine()
        # Drop at 0.50 (15.0s)
        curve = [(0.0, 1.0), (0.49, 0.90), (0.50, 0.70)]
        report = engine.correlate(ir, curve)

        assert len(report.dropoff_points) == 1
        assert pytest.approx(report.dropoff_points[0].timestamp_sec, 0.01) == 15.0


# ---------------------------------------------------------------------------
# 2. Attribution to Speaker, Text, Emotion, Cut Index & B-Roll
# ---------------------------------------------------------------------------
class TestCutAndVisualAttribution:
    """Tests attributing drops to active VoiceClip and DynamicImageClip."""

    def test_attribution_to_first_cut(self, mock_timeline: TimelineIR) -> None:
        engine = RetentionCorrelationEngine()
        # Drop at 5% of video (3.0s, frame 90) -> in Cut 0 (ずんだもん)
        curve = [(0.0, 1.0), (0.04, 0.98), (0.05, 0.88)]
        report = engine.correlate(mock_timeline, curve)

        assert len(report.dropoff_points) == 1
        drop = report.dropoff_points[0]
        assert drop.cut_index == 0
        assert drop.speaker == "ずんだもん"
        assert "安さの秘密" in drop.subtitle_text
        assert drop.emotion == "smile"
        assert drop.broll_image == "costco_entrance.png"

    def test_attribution_to_second_cut_and_slide(self, mock_timeline: TimelineIR) -> None:
        engine = RetentionCorrelationEngine()
        # Drop at 40% of video (24.0s, frame 720) -> in Cut 1 (四国めたん) and Slide 1
        curve = [(0.0, 1.0), (0.39, 0.95), (0.40, 0.80)]
        report = engine.correlate(mock_timeline, curve)

        assert len(report.dropoff_points) == 1
        drop = report.dropoff_points[0]
        assert drop.cut_index == 1
        assert drop.speaker == "四国めたん"
        assert "年会費ビジネスモデル" in drop.subtitle_text
        assert drop.emotion == "normal"
        assert drop.broll_image == "membership_chart.png"

    def test_fallback_attribution_in_trailing_gap(self, mock_timeline: TimelineIR) -> None:
        """Drop in trailing outro gap (57.0s, after cut 2 ends at 55.0s) maps to cut 2."""
        engine = RetentionCorrelationEngine()
        # Ratio 0.95 (57.0s, frame 1710, beyond cut 2 end_frame 1650)
        curve = [(0.0, 1.0), (0.94, 0.85), (0.95, 0.70)]
        report = engine.correlate(mock_timeline, curve)

        assert len(report.dropoff_points) == 1
        drop = report.dropoff_points[0]
        assert drop.cut_index == 2
        assert drop.speaker == "ずんだもん"

    def test_ignores_background_images_for_broll(self, tmp_path: Path) -> None:
        """Verifies DynamicImageClip with is_background=True is never attributed as B-roll."""
        vc = VoiceClip(0, 300, "ずんだもん", "テスト", "normal", "none", tmp_path / "a.wav", "", "CB", "d")
        bg = DynamicImageClip(0, 300, tmp_path / "bg.png", is_background=True)
        ir = TimelineIR(fps=30, total_frames=300, voice_clips=[vc], dynamic_image_clips=[bg])

        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.4, 0.95), (0.5, 0.80)]
        report = engine.correlate(ir, curve)

        assert len(report.dropoff_points) == 1
        assert report.dropoff_points[0].broll_image is None


# ---------------------------------------------------------------------------
# 3. Dual Drop-Off Detection & Deduplication Tests
# ---------------------------------------------------------------------------
class TestDropoffDetection:
    """Tests point-level cliff drop (>5%) and cumulative cut loss detection."""

    def test_single_cliff_drop_detection(self, mock_timeline: TimelineIR) -> None:
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.2, 0.95), (0.25, 0.80), (0.5, 0.78)]
        report = engine.correlate(mock_timeline, curve)

        assert len(report.dropoff_points) == 1
        drop = report.dropoff_points[0]
        assert pytest.approx(drop.drop_magnitude, 0.01) == 0.15
        assert drop.retention_before == 0.95
        assert drop.retention_after == 0.80

    def test_sub_threshold_drop_is_ignored(self, mock_timeline: TimelineIR) -> None:
        """Drop of 4% (0.04) under default threshold 0.05 is not flagged."""
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.2, 0.96), (0.4, 0.92), (0.6, 0.88)]
        report = engine.correlate(mock_timeline, curve)
        assert len(report.dropoff_points) == 0

    def test_custom_threshold_filtering(self, mock_timeline: TimelineIR) -> None:
        engine = RetentionCorrelationEngine()
        # Drops: 8% at 0.3, 16% at 0.7
        curve = [(0.0, 1.0), (0.29, 0.95), (0.30, 0.87), (0.69, 0.85), (0.70, 0.69)]

        # Threshold 0.10: only 16% drop should be reported
        report = engine.correlate(mock_timeline, curve, threshold=0.10)
        assert len(report.dropoff_points) == 1
        assert pytest.approx(report.dropoff_points[0].drop_magnitude, 0.01) == 0.16

    def test_terminal_outro_drop_excluded(self, mock_timeline: TimelineIR) -> None:
        """Drop occurring at r = 1.0 (end of video) is excluded from cliff drops."""
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.9, 0.98), (1.0, 0.50)]  # 48% drop at terminal end
        report = engine.correlate(mock_timeline, curve)
        assert len(report.dropoff_points) == 0

    def test_cut_level_cumulative_metrics(self, mock_timeline: TimelineIR) -> None:
        """Verifies start, end, and change retention calculation for each cut."""
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.5, 0.8), (1.0, 0.6)]
        report = engine.correlate(mock_timeline, curve)

        assert len(report.cut_metrics) == 3
        # Cut 0: 0.0 to 15.0s (ratio 0.0 to 0.25). R(0.0)=1.0, R(0.25)=0.9
        assert pytest.approx(report.cut_metrics[0].start_retention, 0.01) == 1.0
        assert pytest.approx(report.cut_metrics[0].end_retention, 0.01) == 0.9
        assert pytest.approx(report.cut_metrics[0].retention_change, 0.01) == -0.1


# ---------------------------------------------------------------------------
# 4. Retention Score & Verdicts
# ---------------------------------------------------------------------------
class TestRetentionScoreAndVerdict:
    """Tests score clamping [0, 100] and summary verdicts."""

    def test_excellent_verdict(self, mock_timeline: TimelineIR) -> None:
        engine = RetentionCorrelationEngine()
        # Flat high curve: 0 drops, avg = 95%
        curve = [(0.0, 1.0), (0.5, 0.95), (1.0, 0.90)]
        report = engine.correlate(mock_timeline, curve)
        assert report.summary_verdict == "EXCELLENT"
        assert report.retention_score >= 90.0

    def test_nominal_verdict(self, mock_timeline: TimelineIR) -> None:
        engine = RetentionCorrelationEngine()
        # Flat curve with low average (60%), 0 cliff drops
        curve = [(0.0, 0.65), (0.5, 0.60), (1.0, 0.55)]
        report = engine.correlate(mock_timeline, curve)
        assert report.summary_verdict == "NOMINAL"

    def test_attention_required_verdict(self, mock_timeline: TimelineIR) -> None:
        engine = RetentionCorrelationEngine()
        # 1 moderate drop (7%)
        curve = [(0.0, 1.0), (0.3, 0.95), (0.35, 0.88), (1.0, 0.85)]
        report = engine.correlate(mock_timeline, curve)
        assert report.summary_verdict == "ATTENTION_REQUIRED"

    def test_needs_optimization_verdict_severe_drop(self, mock_timeline: TimelineIR) -> None:
        engine = RetentionCorrelationEngine()
        # 1 severe drop (15% >= 10%)
        curve = [(0.0, 1.0), (0.3, 0.95), (0.35, 0.80), (1.0, 0.75)]
        report = engine.correlate(mock_timeline, curve)
        assert report.summary_verdict == "NEEDS_OPTIMIZATION"

    def test_score_clamped_to_zero(self, mock_timeline: TimelineIR) -> None:
        engine = RetentionCorrelationEngine()
        # Very low average (5%) with 3 severe drops -> raw score = 5 - 30 = -25 -> clamps to 0.0
        curve = [
            (0.0, 0.15),
            (0.1, 0.08),  # 7% drop in cut 0
            (0.3, 0.06),
            (0.4, 0.00),  # 6% drop in cut 1
            (0.6, 0.00),
            (0.7, 0.00),
            (1.0, 0.00),
        ]
        report = engine.correlate(mock_timeline, curve)
        assert report.retention_score == 0.0


# ---------------------------------------------------------------------------
# 5. Editorial Recommendations Tests
# ---------------------------------------------------------------------------
class TestEditorialRecommendations:
    """Tests actionable feedback formulation."""

    def test_long_dialogue_cognitive_overload_alert(self, tmp_path: Path) -> None:
        long_text = "これは非常に長い説明文であり40文字を大幅に超過しているため視聴者が疲弊して離脱する可能性が高いテキストです。"
        vc = VoiceClip(0, 300, "四国めたん", long_text, "normal", "none", tmp_path / "a.wav", "", "CB", "d")
        ir = TimelineIR(fps=30, total_frames=300, voice_clips=[vc])

        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.4, 0.95), (0.5, 0.80)]
        report = engine.correlate(ir, curve)

        assert len(report.dropoff_points) == 1
        assert report.dropoff_points[0].issue_type == "COGNITIVE_OVERLOAD_LONG_TEXT"
        assert any("分割" in rec or "文字数" in rec for rec in report.editorial_recommendations)

    def test_static_visual_fatigue_alert(self, tmp_path: Path) -> None:
        short_text = "短いテキストなのだ。"
        vc = VoiceClip(0, 300, "ずんだもん", short_text, "normal", "none", tmp_path / "a.wav", "", "CB", "d")
        # No B-roll image clips
        ir = TimelineIR(fps=30, total_frames=300, voice_clips=[vc], dynamic_image_clips=[])

        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.4, 0.95), (0.5, 0.87)]  # 8% drop
        report = engine.correlate(ir, curve)

        assert len(report.dropoff_points) == 1
        assert report.dropoff_points[0].issue_type == "STATIC_VISUAL_FATIGUE"
        assert any("Bロール" in rec or "スライド" in rec for rec in report.editorial_recommendations)

    def test_nominal_recommendation_when_no_drops(self, mock_timeline: TimelineIR) -> None:
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (1.0, 0.98)]
        report = engine.correlate(mock_timeline, curve)
        assert len(report.editorial_recommendations) >= 1
        assert "良好" in report.editorial_recommendations[0]


# ---------------------------------------------------------------------------
# 6. JSON & Markdown Rendering & File Persistence
# ---------------------------------------------------------------------------
class TestReportRenderingAndPersistence:
    """Tests render_json, render_markdown, and save_reports."""

    def test_render_json_path_serialization_safety(self, mock_timeline: TimelineIR) -> None:
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.2, 0.95), (0.25, 0.80)]
        report = engine.correlate(mock_timeline, curve, video_id="test_json_safety")

        # Verify JSON dump is valid and parseable
        json_str = engine.render_json(report)
        data = json.loads(json_str)

        assert data["video_id"] == "test_json_safety"
        assert isinstance(data["dropoff_points"], list)
        assert isinstance(data["cut_metrics"], list)
        assert len(data["dropoff_points"]) == 1

    def test_render_markdown_editorial_scorecard(self, mock_timeline: TimelineIR) -> None:
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.2, 0.95), (0.25, 0.80)]
        report = engine.correlate(mock_timeline, curve, video_title="コストコ徹底解説")

        md_str = engine.render_markdown(report)
        assert "# Retention QA Report: コストコ徹底解説" in md_str
        assert "## Executive Summary" in md_str
        assert "## Retention Drop-Off Analysis" in md_str
        assert "| Timestamp |" in md_str
        assert "## Cut-Level Progression" in md_str
        assert "## Editorial Recommendations" in md_str

    def test_save_reports_creates_files(self, mock_timeline: TimelineIR, tmp_path: Path) -> None:
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (1.0, 0.85)]
        report = engine.correlate(mock_timeline, curve, video_id="vid_persisted")

        target_dir = tmp_path / "qa_outputs" / "2026"
        assert not target_dir.exists()

        json_path, md_path = engine.save_reports(report, target_dir)
        assert target_dir.exists()
        assert json_path.is_file()
        assert md_path.is_file()
        assert json_path.name.endswith(".json")
        assert md_path.name.endswith(".md")
        assert len(json_path.read_text(encoding="utf-8")) > 50
        assert len(md_path.read_text(encoding="utf-8")) > 50


# ---------------------------------------------------------------------------
# 7. Edge Cases & Boundary Conditions
# ---------------------------------------------------------------------------
class TestBoundaryAndEdgeCases:
    """Tests empty curves, 0 cuts, replay ratios > 1.0, and zero duration."""

    def test_empty_retention_curve(self, mock_timeline: TimelineIR) -> None:
        engine = RetentionCorrelationEngine()
        report = engine.correlate(mock_timeline, [])

        assert report.total_cuts == 3
        assert len(report.dropoff_points) == 0
        assert report.retention_score == 0.0
        assert report.average_view_percentage == 0.0
        assert report.summary_verdict == "NOMINAL"

    def test_zero_cuts_timeline(self) -> None:
        ir = TimelineIR(fps=30, total_frames=900, voice_clips=[])
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.0), (0.5, 0.70)]
        report = engine.correlate(ir, curve)

        assert report.total_cuts == 0
        assert len(report.cut_metrics) == 0
        assert len(report.dropoff_points) == 1
        assert report.dropoff_points[0].speaker == "Unknown"

    def test_replay_curve_watch_ratio_exceeding_one(self, mock_timeline: TimelineIR) -> None:
        """Audience watch ratios > 1.0 (replays) are processed without crashing."""
        engine = RetentionCorrelationEngine()
        curve = [(0.0, 1.2), (0.3, 1.1), (0.35, 0.85), (1.0, 0.70)]
        report = engine.correlate(mock_timeline, curve)

        assert len(report.dropoff_points) >= 1
        assert report.average_view_percentage > 70.0

    def test_unsorted_curve_input(self, mock_timeline: TimelineIR) -> None:
        """Unsorted points in retention curve are sorted internally before correlation."""
        engine = RetentionCorrelationEngine()
        unsorted_curve = [(0.5, 0.8), (0.0, 1.0), (1.0, 0.6), (0.2, 0.9)]
        report = engine.correlate(mock_timeline, unsorted_curve)

        assert report.average_view_percentage > 0.0
        assert len(report.cut_metrics) == 3

    def test_zero_duration_timeline(self) -> None:
        ir = TimelineIR(fps=30, total_frames=0, voice_clips=[])
        engine = RetentionCorrelationEngine()
        report = engine.correlate(ir, [(0.0, 1.0), (1.0, 0.8)])

        assert report.total_duration_sec == 0.0
        assert report.total_cuts == 0
