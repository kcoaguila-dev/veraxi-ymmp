import os
import pytest
from veraxi_ymmp.template import load_template, extract_character_templates

def test_extract_character_templates():
    fixture_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'sample_template.ymmp')
    template_data = load_template(fixture_path)

    char_templates = extract_character_templates(template_data)

    assert "ゆっくり霊夢" in char_templates
    assert "ゆっくり魔理沙" in char_templates

    assert char_templates["ゆっくり霊夢"]["voice"] is not None
    assert char_templates["ゆっくり霊夢"]["tachie"] is not None
    assert char_templates["ゆっくり魔理沙"]["voice"] is not None
    assert char_templates["ゆっくり魔理沙"]["tachie"] is not None

    assert char_templates["ゆっくり霊夢"]["voice"]["Serif"] == "こんばんは"
