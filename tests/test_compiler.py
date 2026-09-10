import os
import json
import pytest
import copy
from veraxi_ymmp.compiler import YMMPCompiler
from veraxi_ymmp.voicevox import VoicevoxClient
from unittest.mock import Mock, patch

def test_compile(tmp_path):
    template_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'sample_template.ymmp')
    script_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'sample_script.json')
    output_path = tmp_path / "output.ymmp"

    with open(script_path, 'r', encoding='utf-8') as f:
        script = json.load(f)

    compiler = YMMPCompiler(template_path)

    # Check that original template data isn't modified
    original_template_data = copy.deepcopy(compiler.template_data)

    compiler.compile(script, str(output_path))

    # Assert deep copy isolated mutations
    assert compiler.template_data == original_template_data

    with open(output_path, 'r', encoding='utf-8') as f:
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

    # Ensure other fields aren't touched (full check)
    mutated_fields = {"Serif", "Hatsuon", "Frame", "Length", "VoiceCache"}

    for v_item in voice_items:
        char_name = v_item["CharacterName"]
        template_item = compiler.character_templates[char_name]["voice"]
        for key, template_value in template_item.items():
            if key not in mutated_fields:
                assert v_item[key] == template_value

    # Missing character handling
    script_with_missing_char = [
        { "character": "ゆっくり妖夢", "text": "みょん" }
    ]
    with pytest.raises(ValueError):
        compiler.compile(script_with_missing_char, str(tmp_path / "output2.ymmp"))


def test_compile_tachie_filtering(tmp_path):
    template_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'sample_template.ymmp')
    output_path = tmp_path / "output_tachie.ymmp"

    # Template has 2 characters (霊夢 and 魔理沙), script only uses 1 (霊夢)
    script_one_char = [
        { "character": "ゆっくり霊夢", "text": "こんにちは" }
    ]

    compiler = YMMPCompiler(template_path)
    compiler.compile(script_one_char, str(output_path))

    with open(output_path, 'r', encoding='utf-8') as f:
        output_data = json.load(f)

    items = output_data["Timeline"]["Items"]
    tachie_items = [i for i in items if "TachieItem" in i.get("$type", "")]

    # Should only contain 1 TachieItem for 霊夢, the one for 魔理沙 should be filtered out
    assert len(tachie_items) == 1
    assert tachie_items[0]["CharacterName"] == "ゆっくり霊夢"


def test_compile_tts(tmp_path):
    template_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'sample_template.ymmp')
    output_path = tmp_path / "output_tts.ymmp"

    script = [
        { "character": "ゆっくり霊夢", "text": "こんにちは" },
        { "character": "ゆっくり魔理沙", "text": "こんばんは" }
    ]

    mock_client = Mock(spec=VoicevoxClient)
    mock_client.is_available.return_value = True
    # 2.0 seconds duration * 60 FPS (from template) = 120 frames
    mock_client.synthesize.return_value = (b'fake_wav', 2.0)

    speaker_map = {"ゆっくり霊夢": 10}

    compiler = YMMPCompiler(
        template_path=template_path,
        voicevox_client=mock_client,
        speaker_map=speaker_map,
        default_speaker_id=3
    )

    compiler.compile(script, str(output_path))

    with open(output_path, 'r', encoding='utf-8') as f:
        output_data = json.load(f)

    voice_items = [i for i in output_data["Timeline"]["Items"] if "VoiceItem" in i.get("$type", "")]

    assert len(voice_items) == 2
    assert voice_items[0]["Length"] == 120
    assert voice_items[1]["Length"] == 120

    # Assert synthesized audio was saved correctly
    audio_dir = output_path.parent / "audio"
    assert (audio_dir / "000_ゆっくり霊夢.wav").exists()
    assert (audio_dir / "001_ゆっくり魔理沙.wav").exists()

    # Assert proper speaker routing
    assert mock_client.synthesize.call_count == 2
    mock_client.synthesize.assert_any_call("こんにちは", 10)
    mock_client.synthesize.assert_any_call("こんばんは", 3)


def test_compile_director_script(tmp_path):
    """Compile director metadata without mutating the source template."""
    template_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'sample_template.ymmp')
    output_path = tmp_path / "output_director.ymmp"

    script = [
        {
            "character": "ゆっくり霊夢",
            "text": "こんにちは",
            "emotion": "happy",
            "motion": "jump",
            "bgm": "theme.mp3",
            "sfx": "bang.wav"
        }
    ]

    compiler = YMMPCompiler(template_path)
    original_template_data = copy.deepcopy(compiler.template_data)

    result = compiler.compile(script, str(output_path))

    assert compiler.template_data == original_template_data
    assert len(result.warnings) == 4
    assert any("Emotion 'happy'" in w for w in result.warnings)
    assert any("Motion 'jump'" in w for w in result.warnings)
    assert any("BGM 'theme.mp3'" in w for w in result.warnings)
    assert any("SFX 'bang.wav'" in w for w in result.warnings)

def test_compile_tts_unavailable(tmp_path):
    template_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'sample_template.ymmp')
    output_path = tmp_path / "output_unavailable.ymmp"

    script = [
        { "character": "ゆっくり霊夢", "text": "こんにちは" }
    ]

    mock_client = Mock(spec=VoicevoxClient)
    mock_client.is_available.return_value = False
    mock_client.base_url = "http://localhost:50021"

    compiler = YMMPCompiler(template_path=template_path, voicevox_client=mock_client)

    with pytest.raises(RuntimeError, match="TTS Backend not reachable"):
        compiler.compile(script, str(output_path))
