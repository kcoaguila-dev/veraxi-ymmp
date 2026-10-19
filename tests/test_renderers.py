"""Unit tests for AfterEffectsRenderer and MoviePyRenderer speech bubble generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from veraxi_ymmp.ae_renderer import AfterEffectsRenderer
from veraxi_ymmp.ir import (
    DynamicImageClip,
    GlobalClip,
    TimelineIR,
    VoiceClip,
)
from veraxi_ymmp.moviepy_renderer import MoviePyRenderer, create_speech_bubble


def test_ae_renderer_requires_ir(tmp_path: Path) -> None:
    """AfterEffectsRenderer.render raises ValueError when TimelineIR is None."""
    renderer = AfterEffectsRenderer(None)
    with pytest.raises(ValueError, match="TimelineIR must be provided"):
        renderer.render(tmp_path / "out.jsx")


def test_ae_renderer_with_none_and_populated_audio_query(tmp_path: Path) -> None:
    """AfterEffectsRenderer.render handles VoiceClips with audio_query=None and populated audio_query, plus global_clips and dynamic_image_clips."""
    bg_audio = tmp_path / "bgm.ogg"
    bg_audio.write_bytes(b"ogg")
    broll_img = tmp_path / "slide1.png"
    broll_img.write_bytes(b"png")
    voice_wav = tmp_path / "000_zunda.wav"
    voice_wav.write_bytes(b"wav")

    vc_no_query = VoiceClip(
        start_frame=0,
        length=60,
        character="ずんだもん",
        text="クエリなしの発話",
        emotion="normal",
        motion="none",
        audio_path=None,
        hatsuon="クエリナシノハツワ",
        subtitle_position="bottom_center",
        subtitle_style="outlined",
        audio_query=None,
    )

    vc_with_query = VoiceClip(
        start_frame=60,
        length=60,
        character="ずんだもん",
        text="クエリありの発話",
        emotion="happy",
        motion="jump",
        audio_path=voice_wav,
        hatsuon="クエリアリノハツワ",
        subtitle_position="bottom_center",
        subtitle_style="outlined",
        audio_query={
            "accent_phrases": [
                {
                    "moras": [
                        {"text": "ク", "consonant": "k", "consonant_length": 0.05, "vowel": "u", "vowel_length": 0.1},
                        {"text": "エ", "consonant": None, "consonant_length": None, "vowel": "e", "vowel_length": 0.12},
                    ],
                    "pause_mora": {"text": "、", "vowel": "pau", "vowel_length": 0.15},
                }
            ]
        },
    )

    global_audio = GlobalClip(
        start_frame=0,
        length=120,
        file_path=str(bg_audio),
        item_type="AudioItem",
    )
    global_bg = GlobalClip(
        start_frame=0,
        length=120,
        template_item={"FilePath": str(broll_img)},
        item_type="ImageItem",
    )
    dyn_img = DynamicImageClip(
        start_frame=30,
        length=60,
        image_path=broll_img,
    )

    ir = TimelineIR(
        fps=60,
        total_frames=120,
        voice_clips=[vc_no_query, vc_with_query],
        global_clips=[global_audio, global_bg],
        dynamic_image_clips=[dyn_img],
    )

    out_jsx = tmp_path / "project.jsx"
    renderer = AfterEffectsRenderer(ir)
    res_path = renderer.render(out_jsx)

    assert res_path == out_jsx
    assert out_jsx.exists()
    content = out_jsx.read_text(encoding="utf-8")
    assert "Zundamon_Final" in content
    assert "rigMouth(psdItem);" in content
    assert "bgm.wav" in content  # .ogg converted to .wav in AE script
    assert "slide1.png" in content
    assert "クエリなしの発話" in content
    assert "クエリありの発話" in content
    assert "sliderProp.setValueAtTime(" in content


def test_moviepy_create_speech_bubble() -> None:
    """create_speech_bubble produces a timed MoviePy clip with RGBA frame data."""
    clip = create_speech_bubble("テスト吹き出し字幕なのだ！", duration=1.5, border_color=(34, 197, 94, 255))
    assert clip.duration == pytest.approx(1.5)
    frame_start = clip.get_frame(0.0)
    frame_mid = clip.get_frame(0.5)
    assert frame_start.ndim == 3
    assert frame_mid.shape[1] == 1920
    assert frame_mid.shape[0] == 360

    # Also verify MoviePyRenderer instantiation
    renderer = MoviePyRenderer()
    assert renderer.ir is None
