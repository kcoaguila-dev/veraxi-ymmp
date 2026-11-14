import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

from veraxi_ymmp.core.config import CompilerConfig
from veraxi_ymmp.core.ir import CameraShotIR, TimelineIR, VoiceClip
from veraxi_ymmp.app.ir_builder import (
    TimelineIRBuilder,
    _calculate_cut_padding,
    _resolve_camera_shot,
)
from veraxi_ymmp.core.ports import NullTTSBackend
from veraxi_ymmp.audio.sfx import (
    ensure_tactile_sfx_suite,
    generate_sub_bass_impact,
    generate_subtle_whoosh,
    generate_ui_snap,
)
from veraxi_ymmp.audio.voicevox import VoicevoxClient


def test_tactile_sfx_generation(tmp_path: Path) -> None:
    """Verify procedural tactile SFX generation produces valid 48kHz WAV audio."""
    whoosh_p = generate_subtle_whoosh(tmp_path / "whoosh.wav")
    impact_p = generate_sub_bass_impact(tmp_path / "impact.wav")
    snap_p = generate_ui_snap(tmp_path / "snap.wav")

    assert whoosh_p.exists()
    assert impact_p.exists()
    assert snap_p.exists()

    for p in (whoosh_p, impact_p, snap_p):
        with wave.open(str(p), "rb") as wav:
            assert wav.getframerate() == 48000
            assert wav.getnchannels() == 1
            assert wav.getsampwidth() == 2
            assert wav.getnframes() > 0

    sfx_suite = ensure_tactile_sfx_suite(tmp_path / "suite")
    assert "whoosh" in sfx_suite
    assert "impact" in sfx_suite
    assert "snap" in sfx_suite
    assert sfx_suite["whoosh"].exists()


def test_zero_gap_audio_padding_calculation() -> None:
    """Verify acoustic padding calculations for rapid ping-pong, micro-reactions, and comedic drops."""
    base_pad = 0.05
    punchline_pause = 0.25

    # 1. Micro-reaction cut (<= 12 characters) gets zero padding
    micro_entry = {"character": "ずんだもん", "text": "「はぁ！？」", "emotion": "surprised"}
    assert _calculate_cut_padding(micro_entry, None, base_pad, punchline_pause) == 0.0

    # 2. Comedic drop pause: Metan cold roast followed by Zundamon reaction
    metan_roast = {
        "character": "四国めたん",
        "text": "能天気ですわね。底値で狼狽売りする養分の鑑ですわ。",
        "emotion": "smug",
    }
    zunda_reaction = {
        "character": "ずんだもん",
        "text": "ボクの株、明日売っ払ってくるのだー！",
        "emotion": "scared",
    }
    assert _calculate_cut_padding(zunda_reaction, metan_roast, base_pad, punchline_pause) == 0.25

    # 3. Standard rapid ping-pong
    normal_entry = {
        "character": "四国めたん",
        "text": "決算書の実態をご覧ください。巨額の設備投資が利益を食い潰していますわ。",
        "emotion": "normal",
    }
    assert _calculate_cut_padding(normal_entry, None, base_pad, punchline_pause) == 0.05


def test_camera_shot_ir_resolution() -> None:
    """Verify CameraShotIR angles for cold open hook, shock punch-ins, roasts, and slides."""
    # 1. Opening hook cuts (cut_idx 0-1) focus onto speaker
    hook_entry = {"character": "ずんだもん", "text": "「AI銘柄を買えば全員大金持ち」…今すぐ逃げるのだ！"}
    shot_0 = _resolve_camera_shot(hook_entry, cut_idx=0, start_frame=0, length=120, has_slide=False)
    assert shot_0.shot_type == "focus_speaker"
    assert shot_0.zoom == 1.12
    assert shot_0.pan_x == 180.0

    # 2. Shock/Panic micro-reaction triggers punch-in close-up on Zundamon with camera shake
    shock_entry = {"character": "ずんだもん", "text": "ええっ、連日ニュースで最高値更新って大騒ぎしてるのだ！？", "emotion": "surprised"}
    shot_shock = _resolve_camera_shot(shock_entry, cut_idx=3, start_frame=300, length=90, has_slide=False)
    assert shot_shock.shot_type == "punch_in_reactor"
    assert shot_shock.zoom == 1.35
    assert shot_shock.shake_frames == 3
    assert shot_shock.pan_x == 280.0

    # 3. Sarcastic/Sadistic roast triggers focus on Metan
    roast_entry = {"character": "四国めたん", "text": "おめでたい頭ですわね。表向きの熱狂の裏で大口は真っ青ですわよ。", "emotion": "smug"}
    shot_roast = _resolve_camera_shot(roast_entry, cut_idx=4, start_frame=390, length=120, has_slide=False)
    assert shot_roast.shot_type == "focus_left"
    assert shot_roast.zoom == 1.22
    assert shot_roast.pan_x == -220.0

    # 4. Slide presentation cut
    slide_entry = {"character": "四国めたん", "text": "この設備投資の比較をご覧ください。"}
    shot_slide = _resolve_camera_shot(slide_entry, cut_idx=5, start_frame=510, length=150, has_slide=True)
    assert shot_slide.shot_type == "slide_focus"
    assert shot_slide.zoom == 1.04

    # 5. Default wide shot
    normal_entry = {"character": "四国めたん", "text": "それでは詳細を解説しますわ。", "emotion": "normal"}
    shot_wide = _resolve_camera_shot(normal_entry, cut_idx=6, start_frame=660, length=120, has_slide=False)
    assert shot_wide.shot_type == "wide"
    assert shot_wide.zoom == 1.0


def test_timeline_ir_builder_retention_integration(tmp_path: Path) -> None:
    """Verify TimelineIRBuilder emits camera shots, zero-gap padding, and sonic punctuation."""
    slide_img = tmp_path / "slide_01.png"
    slide_img.write_text("fake", encoding="utf-8")

    script = [
        {
            "character": "ずんだもん",
            "emotion": "excited",
            "text": "「AI戦争はマイクロソフトの完全勝利」…そう信じてる人は今すぐ逃げるのだ！",
            "image": None,
        },
        {
            "character": "四国めたん",
            "emotion": "smug",
            "text": "おめでたい頭ですわね。巨額設備投資で大赤字の危機ですわよ。",
            "image": str(slide_img),
        },
        {
            "character": "ずんだもん",
            "emotion": "surprised",
            "text": "「はぁ！？」",
            "image": None,
        },
    ]

    template_data = {
        "Timelines": [
            {
                "VideoInfo": {"FPS": 30},
                "Items": [],
            }
        ]
    }
    char_templates = {
        "ずんだもん": {"voice": {"$type": "VoiceItem"}},
        "四国めたん": {"voice": {"$type": "VoiceItem"}},
    }

    config = CompilerConfig(
        fps=30,
        inter_cut_padding_sec=0.05,
        punchline_pause_sec=0.25,
        enable_tactile_sfx=True,
    )
    builder = TimelineIRBuilder(
        template_data=template_data,
        character_templates=char_templates,
        face_templates={},
        config=config,
        tts_backend=NullTTSBackend(),
    )

    audio_dir = tmp_path / "audio"
    timeline_ir, _ = builder.build_ir(script, audio_dir=audio_dir)

    # Verify Camera Shots exist and align with cuts
    assert len(timeline_ir.camera_shots) == 3
    assert timeline_ir.camera_shots[0].shot_type == "focus_speaker"
    assert timeline_ir.camera_shots[1].shot_type == "slide_focus"
    assert timeline_ir.camera_shots[2].shot_type == "punch_in_reactor"

    # Verify Sonic Punctuation (whoosh on slide, impact on crisis keyword, snap on punch-in)
    assert len(timeline_ir.dynamic_audio_clips) >= 2
    sfx_paths = [str(ac.audio_path) for ac in timeline_ir.dynamic_audio_clips]
    assert any("whoosh" in p for p in sfx_paths)
    assert any("impact" in p or "snap" in p for p in sfx_paths)


def test_voicevox_speed_scale_and_silence_clamping() -> None:
    """Verify VoicevoxClient passes speedScale and clamps leading/trailing silence."""
    client = VoicevoxClient()

    mock_query = {
        "speedScale": 1.0,
        "prePhonemeLength": 0.10,
        "postPhonemeLength": 0.10,
        "accent_phrases": [],
    }

    with patch("requests.post") as mock_post:
        # 1. audio_query endpoint
        mock_res_query = MagicMock()
        mock_res_query.status_code = 200
        mock_res_query.json.return_value = mock_query

        # 2. synthesis endpoint
        mock_res_synth = MagicMock()
        mock_res_synth.status_code = 200
        import io
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            w.writeframes(b"\x00\x00")
        mock_res_synth.content = buf.getvalue()

        mock_post.side_effect = [mock_res_query, mock_res_synth]

        _, _, aq = client.synthesize("テストなのだ", speaker_id=3, speed_scale=1.18, clamp_silence=True)

        assert aq["speedScale"] == 1.18
        assert aq["prePhonemeLength"] == 0.06
        assert aq["postPhonemeLength"] == 0.06


def test_moviepy_virtual_camera_frame_render(tmp_path: Path) -> None:
    """Verify MoviePyRenderer executes virtual camera zoom and crops cleanly."""
    from PIL import Image
    from veraxi_ymmp.exporters.moviepy_renderer import MoviePyRenderer

    ir = TimelineIR(
        fps=30,
        total_frames=60,
        voice_clips=[
            VoiceClip(
                start_frame=0,
                length=60,
                character="ずんだもん",
                text="カメラテストなのだ！",
                emotion="surprised",
                motion="none",
                audio_path=None,
                hatsuon="カメラテストなのだ",
                subtitle_position="bottom_center",
                subtitle_style="outlined",
            )
        ],
        camera_shots=[
            CameraShotIR(
                start_frame=0,
                length=60,
                shot_type="punch_in_reactor",
                zoom=1.35,
                pan_x=280.0,
                pan_y=30.0,
                shake_frames=3,
            )
        ],
    )

    renderer = MoviePyRenderer(timeline_ir=ir, fast_qa_duration=1.0)
    out_frame = tmp_path / "camera_qa_frame.png"
    renderer.save_frame_at(t=0.5, output_path=str(out_frame))

    assert out_frame.exists()
    img = Image.open(out_frame)
    assert img.size == (1920, 1080)



def test_premiere_audio_track_separation(tmp_path: Path) -> None:
    """Verify PremiereExporter maps A1: BGM, A2: SFX (finite duration), and A3+: Voices."""
    import xml.etree.ElementTree as ET
    from veraxi_ymmp.core.ir import DynamicAudioClip
    from veraxi_ymmp.exporters.premiere_exporter import PremiereExporter

    sfx_wav = tmp_path / "snap.wav"
    sfx_wav.write_bytes(b"RIFF....WAVE")
    bgm_wav = tmp_path / "bgm.wav"
    bgm_wav.write_bytes(b"RIFF....WAVE")
    voice_wav1 = tmp_path / "v1.wav"
    voice_wav1.write_bytes(b"RIFF....WAVE")
    voice_wav2 = tmp_path / "v2.wav"
    voice_wav2.write_bytes(b"RIFF....WAVE")

    ir = TimelineIR(
        fps=30,
        total_frames=300,
        voice_clips=[
            VoiceClip(
                start_frame=0,
                length=60,
                character="ずんだもん",
                text="ボクなのだ！",
                emotion="normal",
                motion="none",
                audio_path=voice_wav1,
                hatsuon="ボクなのだ",
                subtitle_position="bottom_center",
                subtitle_style="outlined",
            ),
            VoiceClip(
                start_frame=60,
                length=90,
                character="四国めたん",
                text="めたんですわ。",
                emotion="smug",
                motion="none",
                audio_path=voice_wav2,
                hatsuon="めたんですわ",
                subtitle_position="bottom_center",
                subtitle_style="outlined",
            ),
        ],
        dynamic_audio_clips=[
            DynamicAudioClip(
                audio_path=bgm_wav,
                start_frame=0,
                length=-1,  # BGM
                volume=0.15,
            ),
            DynamicAudioClip(
                audio_path=sfx_wav,
                start_frame=60,
                length=15,  # SFX (0.5s)
                volume=0.30,
            ),
        ],
    )

    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    (proj_dir / "04_GRAPHICS" / "IMAGES" / "faces").mkdir(parents=True)
    from PIL import Image
    for name in ["neutral_closed.png", "neutral_open.png"]:
        img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        img.save(proj_dir / "04_GRAPHICS" / "IMAGES" / "faces" / name)

    xml_dir = tmp_path / "xml_out"
    xml_dir.mkdir()

    exporter = PremiereExporter(ir)
    xml_file = exporter.export_xmeml_without_bubbles(xml_dir, proj_dir)

    content = xml_file.read_text(encoding="utf-8").replace("<!DOCTYPE xmeml>\n", "")
    root = ET.fromstring(content)

    audio_tracks = root.findall(".//media/audio/track")
    # A1: BGM, A2: SFX, A3: Zundamon, A4: Metan
    assert len(audio_tracks) == 4

    # Track A1 (BGM)
    a1_clips = audio_tracks[0].findall("clipitem")
    assert len(a1_clips) == 1
    assert a1_clips[0].find("name").text == "BGM"
    # total_frames includes 2.0s tail padding: 300 + 2*30 = 360
    assert a1_clips[0].find("duration").text == "360"
    assert a1_clips[0].find("start").text == "0"
    assert a1_clips[0].find("end").text == "360"

    # Track A2 (SFX)
    a2_clips = audio_tracks[1].findall("clipitem")
    assert len(a2_clips) == 1
    assert a2_clips[0].find("name").text == "SFX"
    assert a2_clips[0].find("start").text == "60"
    assert a2_clips[0].find("duration").text == "15"
    assert a2_clips[0].find("end").text == "75"

    # Track A3 (Zundamon Voice)
    a3_clips = audio_tracks[2].findall("clipitem")
    assert len(a3_clips) == 1
    assert "ずんだもん" in a3_clips[0].find("name").text
    assert a3_clips[0].find("start").text == "0"
    assert a3_clips[0].find("duration").text == "60"

    # Track A4 (Metan Voice)
    a4_clips = audio_tracks[3].findall("clipitem")
    assert len(a4_clips) == 1
    assert "四国めたん" in a4_clips[0].find("name").text
    assert a4_clips[0].find("start").text == "60"
    assert a4_clips[0].find("duration").text == "90"



def test_ymmp_sfx_non_overlapping_layers(tmp_path: Path) -> None:
    """Verify YMMPRenderer routes SFX to Layer 11+ with collision-free allocation and no duplicate BGM."""
    import json
    from veraxi_ymmp.core.ir import DynamicAudioClip
    from veraxi_ymmp.exporters.ymmp_renderer import YMMPRenderer

    sfx1 = tmp_path / "snap.wav"
    sfx1.write_bytes(b"RIFF....WAVE")
    sfx2 = tmp_path / "impact.wav"
    sfx2.write_bytes(b"RIFF....WAVE")
    bgm = tmp_path / "bgm.wav"
    bgm.write_bytes(b"RIFF....WAVE")

    template_data = {
        "Timelines": [
            {
                "VideoInfo": {"FPS": 30},
                "Items": [],
            }
        ]
    }

    ir = TimelineIR(
        fps=30,
        total_frames=120,
        voice_clips=[],
        dynamic_audio_clips=[
            DynamicAudioClip(audio_path=bgm, start_frame=0, length=-1, volume=0.10),
            # Two simultaneous SFX clips starting at frame 30
            DynamicAudioClip(audio_path=sfx1, start_frame=30, length=20, volume=0.25),
            DynamicAudioClip(audio_path=sfx2, start_frame=30, length=30, volume=0.35),
        ],
        template_data=template_data,
    )

    renderer = YMMPRenderer(template_data=template_data)
    out_ymmp = tmp_path / "output.ymmp"
    renderer.export(ir, out_ymmp)

    with open(out_ymmp, "r", encoding="utf-8") as f:
        data = json.load(f)

    from veraxi_ymmp.core.template import get_timeline
    items = get_timeline(data)["Items"]
    audio_items = [it for it in items if "AudioItem" in it.get("$type", "")]

    # BGM on Layer 3
    bgm_items = [it for it in audio_items if it.get("Layer") == 3]
    assert len(bgm_items) == 1
    assert bgm_items[0]["IsLooped"] is True

    # No AudioItems on Layer 5 (Layer 5 is reserved for Tsumugi character Tachie)
    layer5_items = [it for it in audio_items if it.get("Layer") == 5]
    assert len(layer5_items) == 0

    # SFX on Layer 11 and Layer 12 (collision-free allocation for simultaneous SFX)
    sfx_items = [it for it in audio_items if it.get("Layer", 0) >= 11]
    assert len(sfx_items) == 2
    layers = {it["Layer"] for it in sfx_items}
    assert 11 in layers
    assert 12 in layers


def test_staging_module_heuristics(tmp_path: Path) -> None:
    """Verify veraxi_ymmp.core.staging decoupled functions."""
    from veraxi_ymmp.core.staging import (
        calculate_cut_padding,
        detect_sfx_for_cut,
        detect_slide_sfx,
        resolve_camera_shot,
    )

    # 1. calculate_cut_padding
    assert calculate_cut_padding({"character": "ずんだもん", "text": "「はい！」"}, None, 0.05, 0.25) == 0.0

    # 2. resolve_camera_shot hook
    shot = resolve_camera_shot({"character": "ずんだもん", "text": "はじめ"}, cut_idx=0, start_frame=0, length=30, has_slide=False)
    assert shot.shot_type == "focus_speaker"

    # 3. detect_sfx_for_cut
    sfx_suite = {
        "snap": tmp_path / "snap.wav",
        "impact": tmp_path / "impact.wav",
        "whoosh": tmp_path / "whoosh.wav",
    }
    sfx_clips = detect_sfx_for_cut(
        entry={"text": "大赤字で危機なのだ！"},
        camera_shot=CameraShotIR(start_frame=0, length=30, shot_type="punch_in_reactor"),
        sfx_suite=sfx_suite,
        current_frame=15,
        fps=30,
    )
    assert len(sfx_clips) == 2  # snap (due to punch_in) + impact (due to 赤字/危機)

    # 4. detect_slide_sfx
    slide_clip = detect_slide_sfx(sfx_suite, current_frame=60, fps=30)
    assert slide_clip is not None
    assert slide_clip.audio_path == sfx_suite["whoosh"]
