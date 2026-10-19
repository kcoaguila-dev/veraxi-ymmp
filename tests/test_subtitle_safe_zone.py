"""
Automated QA tests for systematic subtitle and speech bubble plate safe zones.
Guarantees that speech bubble plates and subtitles maintain adequate space at the bottom
to prevent the bottom border from ever being clipped or touching the canvas edge.
"""

import base64
import brotli
from pathlib import Path
import pytest

from veraxi_ymmp.constants import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_SUBTITLE_BOTTOM_EDGE_Y,
    DEFAULT_SUBTITLE_SAFE_BOTTOM_MARGIN,
)
from veraxi_ymmp.moviepy_renderer import create_speech_bubble
from veraxi_ymmp.psd_registry import CharacterPSDRegistry
from veraxi_ymmp.subtitle_plate import create_speech_plate
from veraxi_ymmp.typography import (
    calculate_ymm4_subtitle_y,
)
from veraxi_ymmp.validation import ValidationError, validate_ymmp_timeline


@pytest.fixture
def base_valid_ymmp(tmp_path: Path):
    """Minimal valid YMMP timeline fixture."""
    test_wav = (tmp_path / "scratch_audio.wav").resolve()
    wav_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    test_wav.write_bytes(wav_bytes)

    vc_b64 = base64.b64encode(brotli.compress(wav_bytes)).decode('ascii')
    psd_path = str(CharacterPSDRegistry.resolve_psd_path("ずんだもん"))

    return {
        "Characters": [
            {
                "Name": "ずんだもん",
                "TachieType": "YukkuriMovieMaker.Plugin.Tachie.Psd.PsdTachiePlugin, YukkuriMovieMaker.Plugin.Tachie.Psd, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null",
                "TachieCharacterParameter": {
                    "FilePath": psd_path,
                    "MouthSensitivity": 200.0
                },
                "TachieDefaultFaceParameter": {
                    "IsEnabled": True,
                    "FilePath": psd_path,
                    "EnableLayers": ["n153", "n89", "n88", "n83", "n97", "n95", "n148", "n140", "n115", "n21", "n15", "n12", "n4", "n1", "n0", "n109"],
                    "EnableLayerPaths": ["path1"]
                }
            }
        ],
        "Timeline": {
            "MaxLayer": 10,
            "Items": [
                {
                    "$type": "YukkuriMovieMaker.Project.Items.AudioItem, YukkuriMovieMaker",
                    "FilePath": str(test_wav),
                    "Layer": 3,
                    "Frame": 0,
                    "Length": 90,
                    "Volume": {"Values": [{"Value": 3.0}]}
                },
                {
                    "$type": "YukkuriMovieMaker.Project.Items.TachieItem, YukkuriMovieMaker",
                    "CharacterName": "ずんだもん",
                    "Layer": 6,
                    "Frame": 0,
                    "Length": 90,
                    "X": {"Values": [{"Value": 550.0}]},
                    "TachieItemParameter": {
                        "FilePath": psd_path,
                        "EnableLayers": ["n153", "n89", "n88", "n83", "n97", "n95", "n148", "n140", "n115", "n21", "n15", "n12", "n4", "n1", "n0", "n109"],
                        "EnableLayerPaths": ["path1"],
                        "IsHiddenWhenNoSpeech": False
                    }
                },
                {
                    "$type": "YukkuriMovieMaker.Project.Items.VoiceItem, YukkuriMovieMaker",
                    "CharacterName": "ずんだもん",
                    "Hatsuon": "テスト",
                    "FilePath": str(test_wav),
                    "VoiceCache": vc_b64,
                    "Layer": 9,
                    "Frame": 0,
                    "Length": 90,
                    "VoiceLength": "00:00:01.5000000",
                    "IsWaveformEnabled": True,
                    "Volume": {"Values": [{"Value": 100.0}]}
                }
            ]
        }
    }


class TestSubtitleSafeZone:
    """Systematic architectural tests for subtitle and speech plate geometry."""

    def test_calculate_ymm4_subtitle_y_guarantees_bottom_safe_margin(self) -> None:
        """Verify that calculate_ymm4_subtitle_y returns DEFAULT_SUBTITLE_CENTER_Y and maintains >= 50px safe bottom margin."""
        y_center = calculate_ymm4_subtitle_y()
        assert y_center == 345.0

        for box_h in (136.0, 188.0, 288.0):
            bottom_edge_y = y_center + (box_h / 2.0)
            assert bottom_edge_y <= DEFAULT_SUBTITLE_BOTTOM_EDGE_Y
            distance_to_screen_bottom = (DEFAULT_CANVAS_HEIGHT / 2.0) - bottom_edge_y
            assert distance_to_screen_bottom >= DEFAULT_SUBTITLE_SAFE_BOTTOM_MARGIN

    def test_four_line_dialogue_prevents_bottom_clipping(self, tmp_path: Path) -> None:
        """
        Verify the exact 71-character 4-line dialogue from the user's defect report:
        'これまでの『AIと言えば何でも買われる熱狂』は終わり、年間数千億ドルもの巨額投資に対する回収、つまりROIが厳格に問われる時代になりました。'
        The speech bubble plate must maintain >= 50px safe space at the bottom.
        """
        text = (
            "これまでの『AIと言えば何でも買われる熱狂』は終わり、"
            "年間数千億ドルもの巨額投資に対する回収、つまりROIが厳格に問われる時代になりました。"
        )
        out_plate = tmp_path / "plate_test_long.png"
        res = create_speech_plate(text, "四国めたん", out_plate)

        assert out_plate.exists()
        assert res.box_h >= 220.0  # Taller multi-line box
        # Bottom edge of the box in YMM4 centered space: center_y + box_h/2
        plate_bottom_y = res.center_y + (res.box_h / 2.0)
        assert plate_bottom_y <= 490.0

        # Margin from the bottom edge of the 1080p canvas (+540.0)
        distance_to_screen_bottom = 540.0 - plate_bottom_y
        assert distance_to_screen_bottom >= 50.0, (
            f"Distance to screen bottom is {distance_to_screen_bottom}px, "
            "must be >= 50px so border and shadow are fully visible!"
        )

    def test_moviepy_bubble_layout_y_anchors_to_safe_bottom(self) -> None:
        """Verify MoviePy preview bubble positions bottom at 1030 (1080 - 50)."""
        text_2line = "その通りですわ。そして第2の本質は、『AI相場の第2章』への突入です。"
        clip = create_speech_bubble(text_2line, duration=2.0)
        layout_y = getattr(clip, "layout_y", None)
        assert layout_y is not None
        geom = getattr(clip, "geom", None)
        assert geom is not None
        bottom_on_screen = layout_y + geom.box_y + geom.box_h
        assert bottom_on_screen == pytest.approx(1030.0, abs=2.0)

    def test_validation_rejects_clipped_speech_plates(self, base_valid_ymmp: dict) -> None:
        """Verify validate_ymmp_timeline catches plate items placed too low (Y > 445.0)."""
        # Inject an invalid plate item with Y = 460.0 (too low, would clip)
        base_valid_ymmp["Timeline"]["Items"].append(
            {
                "$type": "YukkuriMovieMaker.Project.Items.ImageItem, YukkuriMovieMaker",
                "FilePath": "plate.png",
                "Layer": 8,
                "Frame": 0,
                "Length": 90,
                "X": {"Values": [{"Value": 0.0}]},
                "Y": {"Values": [{"Value": 460.0}]},
            }
        )
        with pytest.raises(ValidationError, match="must maintain at least 45-50px safe distance"):
            validate_ymmp_timeline(base_valid_ymmp)

    def test_ymm4_voice_y_offset_balances_vertical_padding(self) -> None:
        """Verify calculate_ymm4_voice_y_offset maintains concentric 0.0 offset with CenterCenter BasePoint."""
        from veraxi_ymmp.typography import calculate_ymm4_voice_y_offset

        assert calculate_ymm4_voice_y_offset(line_count=1, font_size=44.0) == 0.0
        assert calculate_ymm4_voice_y_offset(line_count=2, font_size=44.0) == 0.0
        assert calculate_ymm4_voice_y_offset(line_count=3, font_size=36.0) == 0.0
        assert calculate_ymm4_voice_y_offset(line_count=4, font_size=32.0) == 0.0

    def test_speech_plate_result_includes_voice_y(self, tmp_path: Path) -> None:
        """Verify create_speech_plate returns voice_y matching plate center_y exactly."""
        # 1-line test
        t1 = "こんにちは、四国めたんですわ。"
        res1 = create_speech_plate(t1, "四国めたん", tmp_path / "p1.png")
        assert res1.voice_y == res1.center_y

        # 3-line test
        t3 = (
            "初心者は一体何を理解して\n"
            "投資すればいいのか、\n"
            "さっぱりわからないのだ！"
        )
        res3 = create_speech_plate(t3, "ずんだもん", tmp_path / "p3.png")
        assert res3.voice_y == res3.center_y

        # 4-line test
        t4 = (
            "これまでの『AIと言えば何でも買われる熱狂』は終わり、"
            "年間数千億ドルもの巨額投資に対する回収、つまりROIが厳格に問われる時代になりました。"
        )
        res4 = create_speech_plate(t4, "四国めたん", tmp_path / "p4.png")
        assert res4.voice_y == res4.center_y

    def test_validation_enforces_concentric_subtitle_and_plate_alignment(
        self, base_valid_ymmp: dict
    ) -> None:
        """Verify validate_ymmp_timeline catches invalid JimakuVisibility or non-concentric Y."""
        # Inject plate on Layer 8 and voice on Layer 9
        base_valid_ymmp["Timeline"]["Items"].append(
            {
                "$type": "YukkuriMovieMaker.Project.Items.ImageItem, YukkuriMovieMaker",
                "FilePath": "plate.png",
                "Layer": 8,
                "Frame": 0,
                "Length": 90,
                "X": {"Values": [{"Value": 0.0}]},
                "Y": {"Values": [{"Value": 345.0}]},
            }
        )
        voice_item = [
            it for it in base_valid_ymmp["Timeline"]["Items"]
            if "VoiceItem" in it.get("$type", "")
        ][0]
        voice_item["Y"] = {"Values": [{"Value": 345.0}]}
        voice_item["JimakuVisibility"] = "InvalidMode"

        # Must reject invalid JimakuVisibility
        with pytest.raises(ValidationError, match="Must be 'UseCharacterSetting'"):
            validate_ymmp_timeline(base_valid_ymmp, require_audio=False)

        # Must reject Custom mode to prevent chalkboard text detachment
        voice_item["JimakuVisibility"] = "Custom"
        with pytest.raises(ValidationError, match="Must be 'UseCharacterSetting'"):
            validate_ymmp_timeline(base_valid_ymmp, require_audio=False)

        # Must reject non-concentric Y with UseCharacterSetting if character Y doesn't match plate
        voice_item["JimakuVisibility"] = "UseCharacterSetting"
        base_valid_ymmp["Characters"][0]["Y"] = {"Values": [{"Value": 400.0}]}
        with pytest.raises(ValidationError, match="must be concentric"):
            validate_ymmp_timeline(base_valid_ymmp, require_audio=False)

        # Passes when UseCharacterSetting and Character.Y matches Plate
        base_valid_ymmp["Characters"][0]["Y"] = {"Values": [{"Value": 345.0}]}
        res = validate_ymmp_timeline(base_valid_ymmp, require_audio=False)
        assert res["status"] == "PASS"
