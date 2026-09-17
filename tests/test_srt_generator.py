"""Tests for SRT subtitle generator."""

import pytest
from pathlib import Path
from veraxi_ymmp.srt_generator import generate_srt, _format_srt_time
from veraxi_ymmp.ir import TimelineIR, VoiceClip


class TestFormatSrtTime:
    """Tests for the SRT timestamp formatter."""

    def test_zero(self):
        assert _format_srt_time(0.0) == "00:00:00,000"

    def test_simple_seconds(self):
        assert _format_srt_time(5.0) == "00:00:05,000"

    def test_with_milliseconds(self):
        assert _format_srt_time(1.5) == "00:00:01,500"

    def test_minutes(self):
        assert _format_srt_time(65.0) == "00:01:05,000"

    def test_hours(self):
        assert _format_srt_time(3661.123) == "01:01:01,123"

    def test_negative_clamped_to_zero(self):
        assert _format_srt_time(-5.0) == "00:00:00,000"

    def test_fractional_milliseconds(self):
        # 2.3456 seconds -> 2345.6ms -> rounded to 2346ms -> 02,346
        result = _format_srt_time(2.3456)
        assert result == "00:00:02,346"

    def test_near_boundary(self):
        # 59.999 seconds
        result = _format_srt_time(59.999)
        assert result == "00:00:59,999"


class TestGenerateSrt:
    """Tests for the main SRT generation function."""

    def _make_voice_clip(self, start_frame, length, text, character="ゆっくり霊夢"):
        return VoiceClip(
            start_frame=start_frame,
            length=length,
            character=character,
            text=text,
            emotion="neutral",
            motion="none",
            audio_path=None,
            hatsuon="",
            subtitle_position="bottom_center",
            subtitle_style="outlined",
        )

    def test_basic_srt_generation(self, tmp_path):
        ir = TimelineIR(
            fps=60,
            total_frames=300,
            voice_clips=[
                self._make_voice_clip(0, 120, "こんにちは"),
                self._make_voice_clip(120, 180, "今日はいい天気ですね"),
            ],
        )

        output = tmp_path / "test.srt"
        result = generate_srt(ir, output)

        assert result == output
        assert output.exists()

        content = output.read_text(encoding="utf-8")
        lines = content.strip().split("\n")

        # Entry 1
        assert lines[0] == "1"
        assert lines[1] == "00:00:00,000 --> 00:00:02,000"
        assert lines[2] == "こんにちは"

        # Entry 2
        assert lines[4] == "2"
        assert lines[5] == "00:00:02,000 --> 00:00:05,000"
        assert lines[6] == "今日はいい天気ですね"

    def test_empty_voice_clips(self, tmp_path):
        ir = TimelineIR(fps=30, total_frames=0, voice_clips=[])

        output = tmp_path / "empty.srt"
        generate_srt(ir, output)

        content = output.read_text(encoding="utf-8")
        assert content == ""

    def test_single_clip(self, tmp_path):
        ir = TimelineIR(
            fps=30,
            total_frames=90,
            voice_clips=[
                self._make_voice_clip(0, 90, "テスト"),
            ],
        )

        output = tmp_path / "single.srt"
        generate_srt(ir, output)

        content = output.read_text(encoding="utf-8")
        assert "1\n" in content
        assert "00:00:00,000 --> 00:00:03,000" in content
        assert "テスト" in content

    def test_utf8_encoding(self, tmp_path):
        ir = TimelineIR(
            fps=60,
            total_frames=120,
            voice_clips=[
                self._make_voice_clip(0, 60, "ずんだもんなのだ！"),
                self._make_voice_clip(60, 60, "四季映姫・ヤマザナドゥ"),
            ],
        )

        output = tmp_path / "unicode.srt"
        generate_srt(ir, output)

        content = output.read_text(encoding="utf-8")
        assert "ずんだもんなのだ！" in content
        assert "四季映姫・ヤマザナドゥ" in content

    def test_creates_parent_directories(self, tmp_path):
        output = tmp_path / "deep" / "nested" / "dir" / "subs.srt"
        ir = TimelineIR(
            fps=30,
            total_frames=30,
            voice_clips=[self._make_voice_clip(0, 30, "テスト")],
        )

        generate_srt(ir, output)
        assert output.exists()

    def test_timing_accuracy_at_30fps(self, tmp_path):
        """Verify frame-to-time conversion at 30fps."""
        ir = TimelineIR(
            fps=30,
            total_frames=150,
            voice_clips=[
                self._make_voice_clip(0, 30, "A"),      # 0s - 1s
                self._make_voice_clip(30, 45, "B"),      # 1s - 2.5s
                self._make_voice_clip(75, 75, "C"),      # 2.5s - 5s
            ],
        )

        output = tmp_path / "timing.srt"
        generate_srt(ir, output)

        content = output.read_text(encoding="utf-8")
        assert "00:00:00,000 --> 00:00:01,000" in content
        assert "00:00:01,000 --> 00:00:02,500" in content
        assert "00:00:02,500 --> 00:00:05,000" in content
