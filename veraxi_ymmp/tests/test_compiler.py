import os
import json
import pytest
import copy
from veraxi_ymmp.compiler import YMMPCompiler

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

    # Ensure other fields aren't touched (check a few)
    assert voice_items[0]["VoiceFadeIn"] == 0.0
    assert voice_items[0]["Font"] == "けいふぉんと"

    # Missing character handling
    script_with_missing_char = [
        { "character": "ゆっくり妖夢", "text": "みょん" }
    ]
    with pytest.raises(ValueError):
        compiler.compile(script_with_missing_char, str(tmp_path / "output2.ymmp"))
