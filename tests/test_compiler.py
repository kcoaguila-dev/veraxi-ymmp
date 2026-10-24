import copy
from veraxi_ymmp.compiler import YMMPCompiler
from veraxi_ymmp.voicevox import VoicevoxClient
from unittest.mock import Mock
import os
import json
from pathlib import Path
import pytest


import pytest
@pytest.fixture(autouse=True)
def mock_ymmp_timeline_validation(monkeypatch):
    """Bypass disk file checks (PSDs/WAVs) during compiler unit tests.
    YMMPCompiler translation and timeline AST logic are under test here;
    strict timeline file validation is tested in test_ymmp_validation.py.
    """
    dummy_result = {
        "status": "PASS",
        "voice_count": 1,
        "tachie_count": 1,
        "plate_count": 0,
        "bgm_count": 0,
    }
    monkeypatch.setattr(
        "veraxi_ymmp.validation.validate_ymmp_timeline",
        lambda *args, **kwargs: dummy_result,
    )






def test_compile(tmp_path):
    template_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_template.ymmp")
    script_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_script.json")
    output_path = tmp_path / "output.ymmp"

    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)

    compiler = YMMPCompiler(template_path)

    # Check that original template data isn't modified
    original_template_data = copy.deepcopy(compiler.template_data)

    compiler.compile(script, str(output_path))

    # Assert deep copy isolated mutations
    assert compiler.template_data == original_template_data

    with open(output_path, "r", encoding="utf-8") as f:
        output_data = json.load(f)

    assert "Timeline" in output_data
    assert "Items" in output_data["Timeline"]

    items = output_data["Timeline"]["Items"]

    # 3 voice items + 2 tachie items = 5 items total
    assert len(items) == 5

    # Verify the sequence of frames
    voice_items = [i for i in items if "VoiceItem" in i.get("$type", "")]
    assert len(voice_items) == 3

    assert voice_items[0]["Serif"] == "こんにちは"
    assert voice_items[0]["Hatsuon"] == compiler.hatsuon.convert("こんにちは")
    assert voice_items[0]["Frame"] == 0
    assert voice_items[0]["Length"] == max(30, len("こんにちは") * 5)

    assert voice_items[1]["Serif"] == "こんばんは"
    assert voice_items[1]["Hatsuon"] == compiler.hatsuon.convert("こんばんは")
    assert voice_items[1]["Frame"] == voice_items[0]["Length"]
    assert voice_items[1]["Length"] == max(30, len("こんばんは") * 5)

    assert voice_items[2]["Serif"] == "今日はいい天気ですね"
    assert voice_items[2]["Frame"] == voice_items[0]["Length"] + voice_items[1]["Length"]

    for v_item in voice_items:
        assert v_item.get("IsWaveformEnabled") is True

    # Missing character handling
    script_with_missing_char = [{"character": "ゆっくり妖夢", "text": "みょん"}]
    with pytest.raises(ValueError):
        compiler.compile(script_with_missing_char, str(tmp_path / "output2.ymmp"))


def test_compile_tachie_filtering(tmp_path):
    template_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_template.ymmp")
    output_path = tmp_path / "output_tachie.ymmp"

    # Template has 2 characters (霊夢 and 魔理沙), script only uses 1 (霊夢)
    script_one_char = [{"character": "ゆっくり霊夢", "text": "こんにちは"}]

    compiler = YMMPCompiler(template_path)
    compiler.compile(script_one_char, str(output_path))

    with open(output_path, "r", encoding="utf-8") as f:
        output_data = json.load(f)

    items = output_data["Timeline"]["Items"]
    tachie_items = [i for i in items if "TachieItem" in i.get("$type", "")]

    # Should only contain 1 TachieItem for 霊夢, the one for 魔理沙 should be filtered out
    assert len(tachie_items) == 1
    assert tachie_items[0]["CharacterName"] == "ゆっくり霊夢"


def test_compile_tts(tmp_path):
    template_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_template.ymmp")
    output_path = tmp_path / "output_tts.ymmp"

    script = [
        {"character": "ゆっくり霊夢", "text": "こんにちは"},
        {"character": "ゆっくり魔理沙", "text": "こんばんは"},
    ]

    mock_client = Mock(spec=VoicevoxClient)
    mock_client.is_available.return_value = True
    # 2.0 seconds duration * 60 FPS (from template) = 120 frames
    mock_client.synthesize.return_value = (b"fake_wav", 2.0, {})

    speaker_map = {"ゆっくり霊夢": 10}

    compiler = YMMPCompiler(
        template_path=template_path,
        voicevox_client=mock_client,
        speaker_map=speaker_map,
        default_speaker_id=3,
    )

    compiler.compile(script, str(output_path))

    with open(output_path, "r", encoding="utf-8") as f:
        output_data = json.load(f)

    voice_items = [i for i in output_data["Timeline"]["Items"] if "VoiceItem" in i.get("$type", "")]
    audio_items = [i for i in output_data["Timeline"]["Items"] if "AudioItem" in i.get("$type", "")]
    text_items = [i for i in output_data["Timeline"]["Items"] if "TextItem" in i.get("$type", "")]

    assert len(voice_items) == 2
    assert len(audio_items) == 2
    assert len(text_items) == 0
    assert voice_items[0]["Length"] == 120
    assert voice_items[1]["Length"] == 120
    assert audio_items[0]["Frame"] == voice_items[0]["Frame"]
    assert audio_items[0]["Length"] == voice_items[0]["Length"]
    assert audio_items[0]["FilePath"] == str(
        (output_path.parent / "audio" / "000_ゆっくり霊夢.wav").resolve()
    )
    assert voice_items[0]["Volume"]["Values"][0]["Value"] == 0.0

    # Assert synthesized audio was saved correctly
    audio_dir = output_path.parent / "audio"
    assert (audio_dir / "000_ゆっくり霊夢.wav").exists()
    assert (audio_dir / "001_ゆっくり魔理沙.wav").exists()

    # Assert proper speaker routing
    assert mock_client.synthesize.call_count == 2
    mock_client.synthesize.assert_any_call("こんにちは", 10)
    mock_client.synthesize.assert_any_call("こんばんは", 3)


def test_compile_director_script(tmp_path):
    template_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_template.ymmp")
    output_path = tmp_path / "output_director.ymmp"

    script = [
        {
            "character": "ゆっくり霊夢",
            "text": "こんにちは",
            "emotion": "happy",
            "motion": "jump",
            "bgm": "theme.mp3",
            "sfx": "bang.wav",
            "image": None,
        }
    ]

    compiler = YMMPCompiler(template_path)
    original_template_data = copy.deepcopy(compiler.template_data)

    result = compiler.compile(script, str(output_path))

    assert compiler.template_data == original_template_data
    assert len(result.warnings) == 4  # it should match
    assert any("Emotion 'happy'" in w for w in result.warnings)
    assert any("Motion 'jump'" in w for w in result.warnings)
    assert any("BGM not found: theme.mp3" in w for w in result.warnings)
    assert any("SFX not found: bang.wav" in w for w in result.warnings)


def test_compile_tts_unavailable(tmp_path):
    template_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_template.ymmp")
    output_path = tmp_path / "output_unavailable.ymmp"

    script = [{"character": "ゆっくり霊夢", "text": "こんにちは"}]

    mock_client = Mock(spec=VoicevoxClient)
    mock_client.is_available.return_value = False
    mock_client.base_url = "http://localhost:50021"

    compiler = YMMPCompiler(template_path=template_path, voicevox_client=mock_client)

    with pytest.raises(RuntimeError, match="TTS Backend not reachable"):
        compiler.compile(script, str(output_path))


def test_coalesce_consecutive_images_and_tachie(tmp_path):
    template_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_template.ymmp")
    compiler = YMMPCompiler(template_path)

    # 1. Setup dummy images
    img1 = tmp_path / "chart1.png"
    img2 = tmp_path / "chart2.png"
    img1.write_bytes(b"dummy image 1")
    img2.write_bytes(b"dummy image 2")

    # Script with consecutive lines using the same image, then switching to a new image, then without image
    script = [
        {"character": "ずんだもん", "text": "一行目なのだ", "image": str(img1)},
        {"character": "ずんだもん", "text": "二行目なのだ", "image": str(img1)},
        {"character": "四国めたん", "text": "三行目ですわ", "image": str(img2)},
        {"character": "四国めたん", "text": "四行目ですわ"},
        {"character": "ずんだもん", "text": "五行目なのだ"},
    ]

    # Verify IR level B-roll DynamicImageClip coalescing in _build_ir
    audio_dir = tmp_path / "audio"
    timeline_ir, _ = compiler._build_ir(script, audio_dir)

    # Consecutive script lines with the same image produce a single coalesced DynamicImageClip
    # with length equal to the sum of consecutive lines' lengths.
    # Switching to a different image creates a new clip.
    assert len(timeline_ir.dynamic_image_clips) == 2

    # First clip: coalesced from lines 0 and 1
    clip0 = timeline_ir.dynamic_image_clips[0]
    expected_coalesced_len = timeline_ir.voice_clips[0].length + timeline_ir.voice_clips[1].length
    assert clip0.image_path.resolve() == img1.resolve()
    assert clip0.start_frame == 0
    assert clip0.length == expected_coalesced_len

    # Second clip: separate clip for line 2
    clip1 = timeline_ir.dynamic_image_clips[1]
    assert clip1.image_path.resolve() == img2.resolve()
    assert clip1.start_frame == expected_coalesced_len
    assert clip1.length == timeline_ir.voice_clips[2].length

    # Verify render level coalescing of TachieItem in _render_psd_ymmp
    output_path = tmp_path / "output_coalesce.ymmp"
    compiler.compile(script, str(output_path))

    with open(output_path, "r", encoding="utf-8") as f:
        output_data = json.load(f)

    items = output_data["Timeline"]["Items"]

    # Layer 1 ImageItems match the 2 dynamic image clips
    l1_items = [i for i in items if i.get("Layer") == 1 and "ImageItem" in i.get("$type", "")]
    assert len(l1_items) == 2
    assert l1_items[0]["Length"] == expected_coalesced_len
    assert l1_items[1]["Length"] == timeline_ir.voice_clips[2].length

    # Tachie items on Layer 4 and Layer 6
    l4_items = [i for i in items if i.get("Layer") == 4 and "TachieItem" in i.get("$type", "")]
    l6_items = [i for i in items if i.get("Layer") == 6 and "TachieItem" in i.get("$type", "")]

    # Layer 4 (四国めたん):
    # - Line 2 has B-roll, 四国めたん is speaking: placed at X=650, Y=280, Zoom=55
    # - Lines 3 & 4 have no B-roll: 四国めたん placed at X=-550, Y=250, Zoom=70
    #   Lines 3 and 4 have identical spatial state -> coalesced into a single TachieItem!
    assert len(l4_items) == 2
    assert l4_items[0]["Length"] == timeline_ir.voice_clips[2].length
    assert (
        l4_items[1]["Length"]
        == timeline_ir.voice_clips[3].length + timeline_ir.voice_clips[4].length
    )
    assert l4_items[1]["Frame"] == timeline_ir.voice_clips[3].start_frame

    # Layer 6 (ずんだもん):
    # - Lines 0 & 1 have B-roll, ずんだもん is speaking: placed at X=650, Y=280, Zoom=55
    #   Both lines have identical spatial state -> coalesced into a single TachieItem!
    # - Lines 3 & 4 have no B-roll: ずんだもん placed at X=550, Y=250, Zoom=70
    #   Both lines have identical spatial state -> coalesced into a single TachieItem!
    assert len(l6_items) == 2
    assert (
        l6_items[0]["Length"]
        == timeline_ir.voice_clips[0].length + timeline_ir.voice_clips[1].length
    )
    assert (
        l6_items[1]["Length"]
        == timeline_ir.voice_clips[3].length + timeline_ir.voice_clips[4].length
    )
    assert l6_items[1]["Frame"] == timeline_ir.voice_clips[3].start_frame

    # Verify zero back-to-back duplicate items on Layer 1, 4, 6
    for layer_num, layer_items in [(1, l1_items), (4, l4_items), (6, l6_items)]:
        for idx in range(len(layer_items) - 1):
            curr = layer_items[idx]
            nxt = layer_items[idx + 1]
            if curr["Frame"] + curr["Length"] == nxt["Frame"]:
                if "TachieItem" in curr.get("$type", ""):
                    same_char = curr.get("CharacterName") == nxt.get("CharacterName")
                    same_x = curr["X"]["Values"][0]["Value"] == nxt["X"]["Values"][0]["Value"]
                    same_y = curr["Y"]["Values"][0]["Value"] == nxt["Y"]["Values"][0]["Value"]
                    same_z = curr["Zoom"]["Values"][0]["Value"] == nxt["Zoom"]["Values"][0]["Value"]
                    assert not (same_char and same_x and same_y and same_z), (
                        f"Found uncoalesced back-to-back TachieItem on Layer {layer_num}: {curr} and {nxt}"
                    )
                elif "ImageItem" in curr.get("$type", ""):
                    assert curr.get("FilePath") != nxt.get("FilePath"), (
                        f"Found uncoalesced back-to-back ImageItem on Layer {layer_num}: {curr} and {nxt}"
                    )


def test_compile_discovers_existing_audio_without_tts(tmp_path: Path):
    template_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_template.ymmp")
    output_path = tmp_path / "ymmp" / "final_video.ymmp"
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(parents=True)

    wav_bytes = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    (audio_dir / "000_ずんだもん.wav").write_bytes(wav_bytes)

    script = [{"character": "ずんだもん", "text": "テスト音声なのだ"}]

    compiler = YMMPCompiler(template_path)
    res = compiler.compile(script, str(output_path), audio_dir=str(audio_dir))

    assert len(res.audio_files) == 1
    assert res.audio_files[0] == audio_dir / "000_ずんだもん.wav"

    with open(output_path, "r", encoding="utf-8") as f:
        output_data = json.load(f)

    from veraxi_ymmp.validation import validate_ymmp_timeline

    v_res = validate_ymmp_timeline(output_data, expected_voice_count=1, require_audio=True)
    assert v_res["status"] == "PASS"
