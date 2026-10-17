"""
Unit test suite for newly extracted Clean Architecture components:
1. CharacterPSDRegistry:
   - PSD path resolution with and without env overrides (VERAXI_ZUNDA_PSD, VERAXI_METAN_PSD, VERAXI_PSD_DIR)
   - Mouth layers query for Zundamon, Metan, and unknown characters
   - Face layers and paths across emotions and mouth states (is_open=True vs False)
   - Spatial layout with and without B-roll
   - Open-Closed Principle dynamic character registration with CharacterPSDConfig
2. veraxi_ymmp.typography:
   - wrap_japanese with short/long text, Kinsoku Shori punctuation rules, and 2-line balancing
   - get_char_color for known, unknown, and custom fallback colors
   - calculate_speech_plate_geometry and draw_rounded_speech_bubble
3. YMMPCompiler public API:
   - Independent invocation of build_ir and render_ymmp
   - Standalone TimelineIR rendering
   - Equivalence between compile facade and decoupled build_ir + render_ymmp pipeline
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from PIL import Image

from veraxi_ymmp.compiler import CompilationResult, YMMPCompiler
from veraxi_ymmp.ir import (
    CharacterClip,
    DynamicAudioClip,
    DynamicImageClip,
    GlobalClip,
    TimelineIR,
    VoiceClip,
)
from veraxi_ymmp.psd_registry import CharacterPSDConfig, CharacterPSDRegistry
from veraxi_ymmp.typography import (
    CHAR_COLORS,
    DEFAULT_CHAR_COLOR,
    SpeechPlateGeometry,
    calculate_speech_plate_geometry,
    draw_rounded_speech_bubble,
    get_char_color,
    wrap_japanese,
)


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def sample_template_path() -> Path:
    """Returns absolute path to sample YMM4 template fixture."""
    path = Path(__file__).parent / "fixtures" / "sample_template.ymmp"
    assert path.exists(), f"Fixture missing: {path}"
    return path


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clears all character PSD environment variable overrides."""
    monkeypatch.delenv("VERAXI_ZUNDA_PSD", raising=False)
    monkeypatch.delenv("ZUNDAMON_PSD_PATH", raising=False)
    monkeypatch.delenv("VERAXI_METAN_PSD", raising=False)
    monkeypatch.delenv("VERAXI_PSD_DIR", raising=False)


# ==============================================================================
# 1. CharacterPSDRegistry Tests
# ==============================================================================


class TestCharacterPSDRegistry:
    """Tests for CharacterPSDRegistry and CharacterPSDConfig."""

    def test_resolve_psd_path_env_overrides(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test PSD path resolution with environment variable overrides."""
        zunda_custom = (tmp_path / "custom_zunda.psd").resolve()
        metan_custom = (tmp_path / "custom_metan.psd").resolve()

        monkeypatch.setenv("VERAXI_ZUNDA_PSD", str(zunda_custom))
        monkeypatch.setenv("VERAXI_METAN_PSD", str(metan_custom))

        # Zundamon aliases
        assert CharacterPSDRegistry.resolve_psd_path("ずんだもん") == zunda_custom
        assert CharacterPSDRegistry.resolve_psd_path("zundamon") == zunda_custom
        assert CharacterPSDRegistry.resolve_psd_path("ZUNDA") == zunda_custom

        # Metan aliases
        assert CharacterPSDRegistry.resolve_psd_path("四国めたん") == metan_custom
        assert CharacterPSDRegistry.resolve_psd_path("metan") == metan_custom
        assert CharacterPSDRegistry.resolve_psd_path("METAN") == metan_custom

    def test_resolve_psd_path_fallback_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test fallback to legacy ZUNDAMON_PSD_PATH when VERAXI_ZUNDA_PSD is absent."""
        monkeypatch.delenv("VERAXI_ZUNDA_PSD", raising=False)
        fallback_zunda = (tmp_path / "legacy_zunda.psd").resolve()
        monkeypatch.setenv("ZUNDAMON_PSD_PATH", str(fallback_zunda))

        assert CharacterPSDRegistry.resolve_psd_path("ずんだもん") == fallback_zunda

    def test_resolve_psd_path_without_env_overrides(self, clean_env: None) -> None:
        """Test default PSD path resolution without environment variable overrides."""
        zunda_path = CharacterPSDRegistry.resolve_psd_path("ずんだもん")
        metan_path = CharacterPSDRegistry.resolve_psd_path("四国めたん")
        unknown_path = CharacterPSDRegistry.resolve_psd_path("unknown_actor.psd")

        # Must end with the respective canonical filename
        assert zunda_path.name == "坂本アヒル_ずんだもん立ち絵V3.2_全部入り版.psd.psd"
        assert metan_path.name == "四国めたん立ち絵素材2.1.psd"
        assert unknown_path.name == "unknown_actor.psd"

    def test_resolve_psd_path_with_psd_dir(self, clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test VERAXI_PSD_DIR base directory override."""
        psd_dir = tmp_path / "custom_psd_dir"
        psd_dir.mkdir()
        target_file = psd_dir / "坂本アヒル_ずんだもん立ち絵V3.2_全部入り版.psd.psd"
        target_file.touch()

        monkeypatch.setenv("VERAXI_PSD_DIR", str(psd_dir))
        resolved = CharacterPSDRegistry.resolve_psd_path("ずんだもん")
        assert resolved == target_file.resolve()

    def test_get_mouth_layers(self) -> None:
        """Test get_mouth_layers for Zundamon, Metan, and unknown characters."""
        registry = CharacterPSDRegistry()

        # Classmethod calls
        assert CharacterPSDRegistry.get_mouth_layers("ずんだもん") == {"n108", "n109"}
        assert CharacterPSDRegistry.get_mouth_layers("zunda") == {"n108", "n109"}
        assert CharacterPSDRegistry.get_mouth_layers("四国めたん") == {"n47", "n48"}
        assert CharacterPSDRegistry.get_mouth_layers("metan") == {"n47", "n48"}
        assert CharacterPSDRegistry.get_mouth_layers("春日部つむぎ") == set()
        assert CharacterPSDRegistry.get_mouth_layers("unknown") == set()
        assert CharacterPSDRegistry.get_mouth_layers("") == set()

        # Instance method calls
        assert registry.get_mouth_layers("ずんだもん") == {"n108", "n109"}
        assert registry.get_mouth_layers("四国めたん") == {"n47", "n48"}

    @pytest.mark.parametrize("emotion,expected_layers", [
        ("normal", ["n147", "n139"]),
        ("happy", ["n147", "n121"]),
        ("angry", ["n144", "n139"]),
        ("sad", ["n142", "n139"]),
        ("surprised", ["n145", "n132"]),
    ])
    def test_zunda_face_layers_and_paths_emotions(self, emotion: str, expected_layers: List[str]) -> None:
        """Test Zundamon face layers across all 5 emotions."""
        registry = CharacterPSDRegistry()
        layers_open, _ = registry.get_face_layers_and_paths("ずんだもん", emotion=emotion, is_open=True)
        layers_closed, _ = registry.get_face_layers_and_paths("ずんだもん", emotion=emotion, is_open=False)

        for expected in expected_layers:
            assert expected in layers_open
            assert expected in layers_closed

        # Verify mouth layer differentiation
        assert layers_open[-1] == "n108"  # mouth open
        assert layers_closed[-1] == "n109"  # mouth closed

    @pytest.mark.parametrize("emotion,expected_eyebrow", [
        ("normal", "n78"),
        ("happy", "n78"),
        ("angry", "n76"),
        ("sad", "n75"),
        ("surprised", "n78"),
    ])
    def test_metan_face_layers_and_paths_emotions(self, emotion: str, expected_eyebrow: str) -> None:
        """Test Metan face layers across all 5 emotions."""
        registry = CharacterPSDRegistry()
        layers_open, _ = registry.get_face_layers_and_paths("四国めたん", emotion=emotion, is_open=True)
        layers_closed, _ = registry.get_face_layers_and_paths("四国めたん", emotion=emotion, is_open=False)

        assert expected_eyebrow in layers_open
        assert expected_eyebrow in layers_closed

        # Verify mouth layer differentiation
        assert layers_open[-1] == "n48"  # mouth open (わあー)
        assert layers_closed[-1] == "n47"  # mouth closed (ほほえみ)

    def test_face_layers_vowel_parameter(self) -> None:
        """Test mouth state derivation from vowel string when is_open is not explicitly passed."""
        registry = CharacterPSDRegistry()

        # vowel="a" -> open
        layers_a, _ = registry.get_face_layers_and_paths("ずんだもん", emotion="normal", vowel="a")
        assert layers_a[-1] == "n108"

        # vowel="silent" -> closed
        layers_silent, _ = registry.get_face_layers_and_paths("ずんだもん", emotion="normal", vowel="silent")
        assert layers_silent[-1] == "n109"

    def test_get_spatial_layout_with_and_without_broll(self) -> None:
        """Test spatial layout coordinates and zoom with and without B-roll."""
        registry = CharacterPSDRegistry()

        # Zundamon
        zunda_broll = registry.get_spatial_layout("ずんだもん", has_broll=True)
        assert zunda_broll == {"x": 650.0, "y": 220.0, "zoom": 55.0, "layer": 6}

        zunda_no_broll = registry.get_spatial_layout("ずんだもん", has_broll=False)
        assert zunda_no_broll == {"x": 550.0, "y": 220.0, "zoom": 70.0, "layer": 6}

        # Metan
        metan_broll = registry.get_spatial_layout("四国めたん", has_broll=True)
        assert metan_broll == {"x": 650.0, "y": 300.0, "zoom": 48.0, "layer": 4}

        metan_no_broll = registry.get_spatial_layout("四国めたん", has_broll=False)
        assert metan_no_broll == {"x": -550.0, "y": 300.0, "zoom": 62.0, "layer": 4}

    def test_register_character_open_closed_principle(self, tmp_path: Path) -> None:
        """Test registering a custom character adhering to the Open-Closed Principle."""
        registry = CharacterPSDRegistry()

        custom_psd = tmp_path / "custom_actor.psd"
        custom_cfg = CharacterPSDConfig(
            name="custom_tsumugi",
            psd_path=custom_psd,
            base_layers=["base_01", "base_02"],
            base_paths=["\\path_01\\", "\\path_02\\"],
            mouth_open_layer="mouth_open",
            mouth_open_path="\\mouth\\open\\",
            mouth_closed_layer="mouth_closed",
            mouth_closed_path="\\mouth\\closed\\",
            face_layer=15,
            tachie_layer=7,
            font_color="#FFFFFFFF",
            style_color="#FF123456",
            style_id=99,
            layout_with_broll={"x": 700.0, "y": 250.0, "zoom": 50.0},
            layout_without_broll={"x": -600.0, "y": 250.0, "zoom": 60.0},
            emotion_rules={
                "happy": (["emo_happy"], ["\\emo\\happy\\"]),
                "angry": (["emo_angry"], ["\\emo\\angry\\"]),
            },
        )

        registry.register_character(custom_cfg)

        # Basic properties
        assert registry.get_psd_path("custom_tsumugi") == custom_psd
        assert registry.get_base_layers("custom_tsumugi") == ["base_01", "base_02"]
        assert registry.get_base_paths("custom_tsumugi") == ["\\path_01\\", "\\path_02\\"]
        assert registry.get_face_layer("custom_tsumugi") == 15
        assert registry.get_tachie_layer("custom_tsumugi") == 7
        assert registry.get_style_id("custom_tsumugi") == 99
        assert registry.get_style_color("custom_tsumugi") == "#FF123456"
        assert registry.get_font_color("custom_tsumugi") == "#FFFFFFFF"

        # Spatial layout
        assert registry.get_spatial_layout("custom_tsumugi", has_broll=True) == {
            "x": 700.0, "y": 250.0, "zoom": 50.0, "layer": 7
        }
        assert registry.get_spatial_layout("custom_tsumugi", has_broll=False) == {
            "x": -600.0, "y": 250.0, "zoom": 60.0, "layer": 7
        }

        # Emotion & mouth states
        layers_happy_open, paths_happy_open = registry.get_face_layers_and_paths(
            "custom_tsumugi", emotion="happy", is_open=True
        )
        assert layers_happy_open == ["base_01", "base_02", "emo_happy", "mouth_open"]
        assert paths_happy_open == ["\\path_01\\", "\\path_02\\", "\\emo\\happy\\", "\\mouth\\open\\"]

        layers_happy_closed, paths_happy_closed = registry.get_face_layers_and_paths(
            "custom_tsumugi", emotion="happy", is_open=False
        )
        assert layers_happy_closed == ["base_01", "base_02", "emo_happy", "mouth_closed"]
        assert paths_happy_closed == ["\\path_01\\", "\\path_02\\", "\\emo\\happy\\", "\\mouth\\closed\\"]

        # Unconfigured emotion falls back cleanly without crashing
        layers_unknown, _ = registry.get_face_layers_and_paths(
            "custom_tsumugi", emotion="unknown_emotion", is_open=False
        )
        assert layers_unknown == ["base_01", "base_02", "mouth_closed"]


# ==============================================================================
# 2. veraxi_ymmp.typography Tests
# ==============================================================================


class TestTypography:
    """Tests for Japanese typography, color registry, and speech plate rendering."""

    def test_wrap_japanese_empty_and_short_text(self) -> None:
        """Test that empty or short text within width constraint is returned unchanged."""
        assert wrap_japanese("") == ""
        assert wrap_japanese("短いテキスト", width=20) == "短いテキスト"
        assert wrap_japanese("12345", width=5) == "12345"

    def test_wrap_japanese_long_text_greedy(self) -> None:
        """Test multi-line greedy wrapping for text longer than 2 lines."""
        text = "AIの進化により、2024年は100ドル以上の利益が5000億円に達し、市場全体が大きく成長しました！"
        wrapped = wrap_japanese(text, width=12)

        lines = wrapped.split("\n")
        assert len(lines) >= 3
        # Tokens should not be split awkwardly
        assert "100ドル" in wrapped
        assert "5000億円" in wrapped

    def test_wrap_japanese_kinsoku_shori(self) -> None:
        """Test Japanese Kinsoku Shori punctuation rules (forbidden line starts and ends)."""
        text = "AIの進化により、2024年は100ドル以上の利益が5000億円に達した！"
        wrapped = wrap_japanese(text, width=12)
        lines = wrapped.split("\n")

        forbidden_starts = set("！!？?。、…・ー)」』％%")
        forbidden_ends = set("「『（(")

        for line in lines[1:]:
            assert line[0] not in forbidden_starts, f"Line starts with forbidden punct: '{line}'"

        for line in lines[:-1]:
            assert line[-1] not in forbidden_ends, f"Line ends with forbidden open bracket: '{line}'"

    def test_wrap_japanese_two_line_balancing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test 2-line length balancing when text fits in 2 lines."""
        mock_parser = MagicMock()
        mock_parser.parse.return_value = ["明日の", "天気は", "晴れ時々", "曇りです"]
        monkeypatch.setattr("veraxi_ymmp.typography._budoux_parser", mock_parser)

        text = "明日の天気は晴れ時々曇りです"  # 14 chars, width=10 -> fits in 2 lines (<= 20)
        wrapped = wrap_japanese(text, width=10)

        assert "\n" in wrapped
        lines = wrapped.split("\n")
        assert len(lines) == 2
        # Optimal balanced split: "明日の天気は" (6) and "晴れ時々曇りです" (8) -> diff 2
        assert lines[0] == "明日の天気は"
        assert lines[1] == "晴れ時々曇りです"

    def test_get_char_color(self) -> None:
        """Test character theme RGBA color retrieval and fallbacks."""
        # Known characters
        assert get_char_color("ずんだもん") == CHAR_COLORS["ずんだもん"]
        assert get_char_color("ずんだもん") == (34, 197, 94, 255)
        assert get_char_color("四国めたん") == CHAR_COLORS["四国めたん"]
        assert get_char_color("春日部つむぎ") == CHAR_COLORS["春日部つむぎ"]

        # Unknown character default slate color
        assert get_char_color("未知のキャラクター") == DEFAULT_CHAR_COLOR
        assert get_char_color("未知のキャラクター") == (100, 116, 139, 255)

        # Custom fallback with 3-tuple (RGB -> RGBA)
        assert get_char_color("未知のキャラクター", default=(255, 0, 0)) == (255, 0, 0, 255)

        # Custom fallback with 4-tuple (RGBA)
        assert get_char_color("未知のキャラクター", default=(0, 255, 0, 128)) == (0, 255, 0, 128)

    def test_calculate_speech_plate_geometry(self) -> None:
        """Test speech bubble plate geometry calculation."""
        text = "テスト発話メッセージです。"
        geom = calculate_speech_plate_geometry(
            text=text,
            font_size=52,
            canvas_w=1920,
            canvas_h=360,
            wrap_width=20,
        )

        assert isinstance(geom, SpeechPlateGeometry)
        assert geom.box_w >= 480  # min_box_w
        assert geom.box_w <= 1600  # max_box_w
        assert geom.box_h >= 136  # min_box_h

        # Centered horizontally
        assert geom.box_x == pytest.approx((1920 - geom.box_w) / 2)

        # Centered vertically by default
        assert geom.box_y == pytest.approx((360 - geom.box_h) / 2)

    def test_calculate_speech_plate_geometry_bottom_margin(self) -> None:
        """Test speech plate vertical positioning when bottom_margin is specified."""
        text = "下部マージン指定テスト"
        bottom_margin = 40
        geom = calculate_speech_plate_geometry(
            text=text,
            canvas_w=1920,
            canvas_h=360,
            bottom_margin=bottom_margin,
        )

        assert geom.box_y == pytest.approx(360 - geom.box_h - bottom_margin)

    def test_calculate_speech_plate_geometry_auto_scale_down(self) -> None:
        """Test that auto_scale_down reduces font size when text is exceptionally wide."""
        long_unbroken = "非常に長い文章" * 15
        geom_scaled = calculate_speech_plate_geometry(
            text=long_unbroken,
            font_size=52,
            wrap_width=50,
            auto_scale_down=True,
        )
        assert isinstance(geom_scaled, SpeechPlateGeometry)
        assert geom_scaled.box_w <= 1600

    def test_draw_rounded_speech_bubble(self) -> None:
        """Test rendering rounded speech bubble with and without text."""
        text = "描画テスト発話"
        geom = calculate_speech_plate_geometry(text, canvas_w=1920, canvas_h=360)

        # Render with text and 4-tuple border color
        img_with_text = draw_rounded_speech_bubble(
            canvas_size=(1920, 360),
            geometry=geom,
            border_color=(34, 197, 94, 255),
            draw_text=True,
        )
        assert isinstance(img_with_text, Image.Image)
        assert img_with_text.size == (1920, 360)
        assert img_with_text.mode == "RGBA"

        # Check non-empty canvas
        extrema = img_with_text.getextrema()
        assert extrema[3][1] > 0, "Rendered plate image should contain non-transparent pixels"

        # Render without text and 3-tuple border color
        img_no_text = draw_rounded_speech_bubble(
            canvas_size=(1920, 360),
            geometry=geom,
            border_color=(236, 72, 153),
            draw_text=False,
        )
        assert isinstance(img_no_text, Image.Image)
        assert img_no_text.size == (1920, 360)


# ==============================================================================
# 3. YMMPCompiler Public API Tests (build_ir and render_ymmp)
# ==============================================================================


class TestYMMPCompilerPublicAPI:
    """Tests for YMMPCompiler decoupled public methods (build_ir and render_ymmp)."""

    def test_build_ir_and_render_ymmp_independently(
        self,
        sample_template_path: Path,
        tmp_path: Path,
    ) -> None:
        """Test calling compiler.build_ir and compiler.render_ymmp independently."""
        compiler = YMMPCompiler(template_path=sample_template_path)
        script: List[Dict[str, Any]] = [
            {"character": "ゆっくり霊夢", "text": "独立したIR構築テストです。"},
            {"character": "ゆっくり魔理沙", "text": "レンダラーのテストだぜ！"},
        ]

        audio_dir = tmp_path / "audio"
        output_file = tmp_path / "independent_result.ymmp"

        # Step 1: Independently build IR
        timeline_ir, audio_files = compiler.build_ir(script, audio_dir=audio_dir)

        assert isinstance(timeline_ir, TimelineIR)
        assert len(timeline_ir.voice_clips) == 2
        assert timeline_ir.voice_clips[0].character == "ゆっくり霊夢"
        assert timeline_ir.voice_clips[0].text == "独立したIR構築テストです。"
        assert timeline_ir.voice_clips[1].character == "ゆっくり魔理沙"
        assert timeline_ir.total_frames > 0
        assert len(timeline_ir.character_clips) == 2

        # Step 2: Independently render YMMP from IR
        result = compiler.render_ymmp(
            timeline_ir=timeline_ir,
            output_path=output_file,
            script_len=len(script),
            audio_files=audio_files,
        )

        assert isinstance(result, CompilationResult)
        assert result.output_path == output_file
        assert output_file.exists()
        assert result.voice_item_count == 2
        assert result.total_frames == timeline_ir.total_frames

        # Verify output project JSON content
        with open(output_file, "r", encoding="utf-8") as f:
            project_data = json.load(f)

        assert "Timeline" in project_data
        items = project_data["Timeline"]["Items"]
        voice_items = [i for i in items if "VoiceItem" in i.get("$type", "")]
        assert len(voice_items) == 2
        assert voice_items[0]["CharacterName"] == "ゆっくり霊夢"
        assert voice_items[1]["CharacterName"] == "ゆっくり魔理沙"

    def test_render_ymmp_from_standalone_ir(
        self,
        sample_template_path: Path,
        tmp_path: Path,
    ) -> None:
        """Test calling compiler.render_ymmp on a hand-constructed TimelineIR without build_ir."""
        compiler = YMMPCompiler(template_path=sample_template_path)
        output_file = tmp_path / "from_standalone_ir.ymmp"

        standalone_ir = TimelineIR(
            fps=30,
            total_frames=180,
            voice_clips=[
                VoiceClip(
                    start_frame=0,
                    length=90,
                    character="ゆっくり霊夢",
                    text="直接作成したVoiceClipです。",
                    emotion="normal",
                    motion="none",
                    audio_path=None,
                    hatsuon="チョクセツサクセイシタ",
                    subtitle_position="bottom",
                    subtitle_style="default",
                ),
                VoiceClip(
                    start_frame=90,
                    length=90,
                    character="ゆっくり魔理沙",
                    text="直接作成した魔理沙のClipだぜ。",
                    emotion="normal",
                    motion="none",
                    audio_path=None,
                    hatsuon="チョクセツサクセイシタマリサ",
                    subtitle_position="bottom",
                    subtitle_style="default",
                ),
            ],
            character_clips=[
                CharacterClip(start_frame=0, length=180, character="ゆっくり霊夢", position="left"),
                CharacterClip(start_frame=0, length=180, character="ゆっくり魔理沙", position="right"),
            ],
            template_data=compiler.template_data,
        )

        result = compiler.render_ymmp(standalone_ir, output_path=output_file)

        assert isinstance(result, CompilationResult)
        assert result.output_path.exists()
        assert result.voice_item_count == 2
        assert result.total_frames == 180

        with open(output_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data["Timeline"]["Items"]) >= 2

    def test_build_ir_with_broll_and_bgm(
        self,
        sample_template_path: Path,
        tmp_path: Path,
    ) -> None:
        """Test build_ir handling of BGM and image entries."""
        compiler = YMMPCompiler(template_path=sample_template_path)

        dummy_bgm = tmp_path / "bgm.mp3"
        dummy_bgm.touch()

        dummy_img = tmp_path / "broll.png"
        dummy_img.touch()

        script: List[Dict[str, Any]] = [
            {"type": "bgm", "path": str(dummy_bgm), "volume": 20},
            {
                "character": "ゆっくり霊夢",
                "text": "Bロール画像を背景に話します。",
                "image": str(dummy_img),
            },
        ]

        timeline_ir, _ = compiler.build_ir(script, audio_dir=tmp_path / "audio")

        assert len(timeline_ir.dynamic_audio_clips) == 1
        assert timeline_ir.dynamic_audio_clips[0].audio_path == dummy_bgm.resolve()
        assert timeline_ir.dynamic_audio_clips[0].volume == pytest.approx(0.2)

        assert len(timeline_ir.dynamic_image_clips) == 1
        assert timeline_ir.dynamic_image_clips[0].image_path == dummy_img.resolve()

    def test_compiler_compile_facade_matches_independent_calls(
        self,
        sample_template_path: Path,
        tmp_path: Path,
    ) -> None:
        """Test that compile facade produces identical output to calling build_ir + render_ymmp."""
        compiler = YMMPCompiler(template_path=sample_template_path)
        script: List[Dict[str, Any]] = [
            {"character": "ゆっくり霊夢", "text": "こんにちは世界。"},
            {"character": "ゆっくり魔理沙", "text": "ハローワールド！"},
        ]

        facade_out = tmp_path / "facade.ymmp"
        decoupled_out = tmp_path / "decoupled.ymmp"

        # 1. Facade call
        res_facade = compiler.compile(script, facade_out)

        # 2. Decoupled calls
        ir, audio_files = compiler.build_ir(script, audio_dir=tmp_path / "audio")
        res_decoupled = compiler.render_ymmp(
            ir,
            decoupled_out,
            script_len=len(script),
            audio_files=audio_files,
        )

        assert res_facade.item_count == res_decoupled.item_count
        assert res_facade.voice_item_count == res_decoupled.voice_item_count
        assert res_facade.tachie_item_count == res_decoupled.tachie_item_count
        assert res_facade.total_frames == res_decoupled.total_frames

        with open(facade_out, "r", encoding="utf-8") as f1, open(decoupled_out, "r", encoding="utf-8") as f2:
            data1 = json.load(f1)
            data2 = json.load(f2)

        # Timeline items should match in count and key types
        items1 = data1["Timeline"]["Items"]
        items2 = data2["Timeline"]["Items"]
        assert len(items1) == len(items2)
        for i1, i2 in zip(items1, items2):
            assert i1["$type"] == i2["$type"]
            assert i1["Frame"] == i2["Frame"]
            assert i1["Length"] == i2["Length"]
