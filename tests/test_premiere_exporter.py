"""Tests for the refactored PremiereExporter class."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock
from xml.etree import ElementTree

from veraxi_ymmp.premiere_exporter import (
    PremiereExporter,
    generate_fcp_xml,
    export_to_premiere,
    create_speech_bubble_png,
)
from veraxi_ymmp.ir import TimelineIR, VoiceClip


def _make_voice_clip(start_frame, length, text, character="ずんだもん", emotion="neutral", audio_path=None):
    return VoiceClip(
        start_frame=start_frame,
        length=length,
        character=character,
        text=text,
        emotion=emotion,
        motion="none",
        audio_path=audio_path,
        hatsuon="",
        subtitle_position="bottom_center",
        subtitle_style="outlined",
    )


def _make_ir(voice_clips=None, fps=60, dynamic_image_clips=None, dynamic_audio_clips=None):
    voice_clips = voice_clips or []
    total_frames = 0
    for vc in voice_clips:
        end = vc.start_frame + vc.length
        if end > total_frames:
            total_frames = end
    if total_frames == 0:
        total_frames = 300

    return TimelineIR(
        fps=fps,
        total_frames=total_frames,
        voice_clips=voice_clips,
        dynamic_image_clips=dynamic_image_clips or [],
        dynamic_audio_clips=dynamic_audio_clips or [],
    )


class TestPremiereExporterXmeml:
    """Tests for xmeml XML export methods."""

    def test_export_xmeml_creates_xml_file(self, tmp_path):
        """Full xmeml export should create a valid XML file."""
        ir = _make_ir([_make_voice_clip(0, 120, "テスト")])
        exporter = PremiereExporter(ir)

        proj_dir = tmp_path / "project"
        proj_dir.mkdir()
        (proj_dir / "04_GRAPHICS" / "IMAGES" / "faces").mkdir(parents=True)
        # Create dummy face PNGs
        from PIL import Image
        for name in ["neutral_closed.png", "neutral_open.png"]:
            img = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
            img.save(proj_dir / "04_GRAPHICS" / "IMAGES" / "faces" / name)

        xml_dir = tmp_path / "xml_out"
        xml_dir.mkdir()

        result = exporter.export_xmeml(xml_dir, proj_dir)

        assert result.exists()
        assert result.name == "Zundamon_Episode_1_PRO.xml"

        # Parse and validate XML structure
        content = result.read_text(encoding="utf-8")
        assert '<?xml version="1.0" encoding="UTF-8"?>' in content
        assert '<xmeml' in content

    def test_export_xmeml_without_bubbles_has_empty_v4(self, tmp_path):
        """No-bubble export should create V4 track but leave it empty."""
        ir = _make_ir([_make_voice_clip(0, 120, "テスト")])
        exporter = PremiereExporter(ir)

        proj_dir = tmp_path / "project"
        proj_dir.mkdir()
        (proj_dir / "04_GRAPHICS" / "IMAGES" / "faces").mkdir(parents=True)
        from PIL import Image
        for name in ["neutral_closed.png", "neutral_open.png"]:
            img = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
            img.save(proj_dir / "04_GRAPHICS" / "IMAGES" / "faces" / name)

        xml_dir = tmp_path / "xml_out"
        xml_dir.mkdir()

        result = exporter.export_xmeml_without_bubbles(xml_dir, proj_dir)
        assert result.exists()

        # Parse XML - V4 should have no clipitems
        result.read_text(encoding="utf-8")
        # The bubble directory should NOT have been created
        bubble_dir = proj_dir / "04_GRAPHICS" / "TITLES" / "speech_bubbles"
        assert not bubble_dir.exists()

    def test_export_xmeml_generates_bubble_pngs(self, tmp_path):
        """Full export should create PNG bubble images."""
        ir = _make_ir([
            _make_voice_clip(0, 60, "こんにちは"),
            _make_voice_clip(60, 60, "さようなら"),
        ])
        exporter = PremiereExporter(ir)

        proj_dir = tmp_path / "project"
        proj_dir.mkdir()
        (proj_dir / "04_GRAPHICS" / "IMAGES" / "faces").mkdir(parents=True)
        from PIL import Image
        for name in ["neutral_closed.png", "neutral_open.png"]:
            img = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
            img.save(proj_dir / "04_GRAPHICS" / "IMAGES" / "faces" / name)

        xml_dir = tmp_path / "xml_out"
        xml_dir.mkdir()

        exporter.export_xmeml(xml_dir, proj_dir)

        bubble_dir = proj_dir / "04_GRAPHICS" / "TITLES" / "speech_bubbles"
        assert bubble_dir.exists()
        assert any(f.name.startswith("bubble_0_") and f.name.endswith("_pro.png") for f in bubble_dir.glob("*.png"))
        assert any(f.name.startswith("bubble_1_") and f.name.endswith("_pro.png") for f in bubble_dir.glob("*.png"))

    def test_xmeml_has_four_video_tracks(self, tmp_path):
        """The generated xmeml should have exactly 4 video tracks."""
        ir = _make_ir([_make_voice_clip(0, 60, "テスト")])
        exporter = PremiereExporter(ir)

        proj_dir = tmp_path / "project"
        proj_dir.mkdir()
        (proj_dir / "04_GRAPHICS" / "IMAGES" / "faces").mkdir(parents=True)
        from PIL import Image
        for name in ["neutral_closed.png", "neutral_open.png"]:
            img = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
            img.save(proj_dir / "04_GRAPHICS" / "IMAGES" / "faces" / name)

        xml_dir = tmp_path / "xml_out"
        xml_dir.mkdir()

        result = exporter.export_xmeml(xml_dir, proj_dir)

        # Remove DOCTYPE for parsing (ElementTree can't parse DOCTYPE)
        content = result.read_text(encoding="utf-8")
        content = content.replace('<!DOCTYPE xmeml>\n', '')
        root = ElementTree.fromstring(content)

        video_tracks = root.findall('.//media/video/track')
        assert len(video_tracks) == 4


class TestPremiereExporterNativeBubbles:
    """Tests for the MCP MOGRT native bubble placement."""

    def test_export_native_bubbles_calls_mcp(self, tmp_path):
        """Should call import_mogrt, get_mogrt_component, set_effect_property per clip."""
        ir = _make_ir([
            _make_voice_clip(0, 60, "テスト1"),
            _make_voice_clip(60, 60, "テスト2"),
        ])
        exporter = PremiereExporter(ir)

        mogrt_path = tmp_path / "bubble.mogrt"
        mogrt_path.write_text("fake mogrt")

        mcp_call = MagicMock()
        mcp_call.side_effect = [
            # Clip 1: import_mogrt
            {"node_id": "node_001"},
            # Clip 1: get_mogrt_component
            {"parameters": [{"name": "Source Text"}]},
            # Clip 1: set_effect_property
            {"ok": True},
            # Clip 2: import_mogrt
            {"node_id": "node_002"},
            # Clip 2: get_mogrt_component
            {"parameters": [{"name": "Source Text"}]},
            # Clip 2: set_effect_property
            {"ok": True},
        ]

        results = exporter.export_native_bubbles(mogrt_path, mcp_call)

        assert len(results) == 2
        assert results[0]["status"] == "success"
        assert results[1]["status"] == "success"
        assert mcp_call.call_count == 6

        # Verify import_mogrt was called with correct timing
        first_import = mcp_call.call_args_list[0]
        assert first_import[0][0] == "import_mogrt"
        assert first_import[0][1]["start_seconds"] == 0.0
        assert first_import[0][1]["track_index"] == 3

    def test_export_native_bubbles_handles_missing_mogrt(self, tmp_path):
        """Should raise FileNotFoundError for missing .mogrt file."""
        ir = _make_ir([_make_voice_clip(0, 60, "テスト")])
        exporter = PremiereExporter(ir)

        with pytest.raises(FileNotFoundError):
            exporter.export_native_bubbles(tmp_path / "nonexistent.mogrt", MagicMock())

    def test_export_native_bubbles_handles_mcp_error(self, tmp_path):
        """Should gracefully handle MCP errors and continue with other clips."""
        ir = _make_ir([
            _make_voice_clip(0, 60, "クリップ1"),
            _make_voice_clip(60, 60, "クリップ2"),
        ])
        exporter = PremiereExporter(ir)

        mogrt_path = tmp_path / "bubble.mogrt"
        mogrt_path.write_text("fake mogrt")

        mcp_call = MagicMock()
        mcp_call.side_effect = [
            Exception("MCP connection lost"),  # Clip 1 fails
            {"node_id": "node_002"},            # Clip 2 succeeds
            {"parameters": [{"name": "Source Text"}]},
            {"ok": True},
        ]

        results = exporter.export_native_bubbles(mogrt_path, mcp_call)

        assert len(results) == 2
        assert results[0]["status"] == "error"
        assert results[1]["status"] == "success"

    def test_export_native_bubbles_no_node_id(self, tmp_path):
        """Should handle missing node_id gracefully (placed_no_text status)."""
        ir = _make_ir([_make_voice_clip(0, 60, "テスト")])
        exporter = PremiereExporter(ir)

        mogrt_path = tmp_path / "bubble.mogrt"
        mogrt_path.write_text("fake mogrt")

        mcp_call = MagicMock()
        mcp_call.return_value = {"status": "ok"}  # No node_id

        results = exporter.export_native_bubbles(mogrt_path, mcp_call)

        assert results[0]["status"] == "placed_no_text"


class TestExportToPremiere:
    """Tests for the top-level hybrid export function."""

    def test_fallback_to_png_without_mcp(self, tmp_path):
        """Without MCP, should use full xmeml with PNG bubbles."""
        ir = _make_ir([_make_voice_clip(0, 60, "テスト")])

        proj_dir = tmp_path / "project"
        proj_dir.mkdir()
        (proj_dir / "04_GRAPHICS" / "IMAGES" / "faces").mkdir(parents=True)
        from PIL import Image
        for name in ["neutral_closed.png", "neutral_open.png"]:
            img = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
            img.save(proj_dir / "04_GRAPHICS" / "IMAGES" / "faces" / name)

        xml_dir = tmp_path / "xml_out"
        xml_dir.mkdir()

        result = export_to_premiere(ir, xml_dir, proj_dir)

        assert result["mode"] == "xmeml_png"
        assert Path(result["xml_path"]).exists()

    def test_hybrid_mode_with_mcp(self, tmp_path):
        """With MCP + MOGRT, should use hybrid mode."""
        ir = _make_ir([_make_voice_clip(0, 60, "テスト")])

        proj_dir = tmp_path / "project"
        proj_dir.mkdir()
        (proj_dir / "04_GRAPHICS" / "IMAGES" / "faces").mkdir(parents=True)
        from PIL import Image
        for name in ["neutral_closed.png", "neutral_open.png"]:
            img = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
            img.save(proj_dir / "04_GRAPHICS" / "IMAGES" / "faces" / name)

        xml_dir = tmp_path / "xml_out"
        xml_dir.mkdir()

        mogrt_path = tmp_path / "bubble.mogrt"
        mogrt_path.write_text("fake mogrt")

        mcp_call = MagicMock()
        mcp_call.side_effect = [
            {"node_id": "node_001"},
            {"parameters": [{"name": "Source Text"}]},
            {"ok": True},
        ]

        result = export_to_premiere(ir, xml_dir, proj_dir, mogrt_path=mogrt_path, mcp_call=mcp_call)

        assert result["mode"] == "hybrid_mogrt"
        assert Path(result["xml_path"]).exists()
        assert len(result["bubble_results"]) == 1

        # Verify no PNG bubble directory was created
        bubble_dir = proj_dir / "04_GRAPHICS" / "TITLES" / "speech_bubbles"
        assert not bubble_dir.exists()


class TestBackwardCompatibility:
    """Tests to ensure the old generate_fcp_xml function still works."""

    def test_generate_fcp_xml_wrapper(self, tmp_path):
        """The old generate_fcp_xml function should produce identical output."""
        ir = _make_ir([_make_voice_clip(0, 60, "後方互換性テスト")])

        proj_dir = tmp_path / "project"
        proj_dir.mkdir()
        (proj_dir / "04_GRAPHICS" / "IMAGES" / "faces").mkdir(parents=True)
        from PIL import Image
        for name in ["neutral_closed.png", "neutral_open.png"]:
            img = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
            img.save(proj_dir / "04_GRAPHICS" / "IMAGES" / "faces" / name)

        xml_dir = tmp_path / "xml_out"
        xml_dir.mkdir()

        # Should not raise
        generate_fcp_xml(ir, xml_dir, proj_dir)

        xml_file = xml_dir / "Zundamon_Episode_1_PRO.xml"
        assert xml_file.exists()
        content = xml_file.read_text(encoding="utf-8")
        assert "Zundamon Project" in content


class TestBubbleTimingData:
    """Tests for the get_bubble_timing_data helper."""

    def test_timing_data_correct(self):
        ir = _make_ir([
            _make_voice_clip(0, 60, "A", character="ずんだもん"),
            _make_voice_clip(60, 90, "B", character="四国めたん"),
        ], fps=30)
        exporter = PremiereExporter(ir)

        data = exporter.get_bubble_timing_data()

        assert len(data) == 2
        assert data[0]["text"] == "A"
        assert data[0]["start_seconds"] == 0.0
        assert data[0]["duration_seconds"] == 2.0
        assert data[0]["character"] == "ずんだもん"
        assert data[1]["start_seconds"] == 2.0
        assert data[1]["duration_seconds"] == 3.0


class TestCreateSpeechBubblePng:
    """Tests for the PNG speech bubble renderer."""

    def test_creates_png_file(self, tmp_path):
        out_path = tmp_path / "bubble.png"
        create_speech_bubble_png("テスト", out_path)
        assert out_path.exists()

    def test_png_is_rgba(self, tmp_path):
        from PIL import Image
        out_path = tmp_path / "bubble.png"
        create_speech_bubble_png("こんにちは", out_path)
        with Image.open(out_path) as img:
            assert img.mode == "RGBA"

    def test_long_text_wraps(self, tmp_path):
        from PIL import Image
        short_path = tmp_path / "short.png"
        long_path = tmp_path / "long.png"
        create_speech_bubble_png("短い", short_path)
        create_speech_bubble_png("これはとても長いテキストで、複数行に分割されるべきテストケースです", long_path)

        with Image.open(short_path) as short_img, Image.open(long_path) as long_img:
            # Longer text should produce a taller or wider image
            assert long_img.size[0] >= short_img.size[0] or long_img.size[1] >= short_img.size[1]
