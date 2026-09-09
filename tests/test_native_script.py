import pytest
from veraxi_ymmp.native_script import json_to_native_script


def test_basic_serialization():
    script = [
        {"character": "Zundamon", "text": "Hello world!"},
        {"character": "Metan", "text": "This is a test."}
    ]
    expected = "Zundamon「Hello world!」\nMetan「This is a test.」"
    assert json_to_native_script(script) == expected

def test_escaping():
    script = [
        {"character": "A", "text": "He said 「yes」."},
        {"character": "B", "text": r"Already escaped \「and\」."}
    ]
    # '「' -> '\「'
    # '\「' remains '\「'
    expected = "A「He said \「yes\」.」\nB「Already escaped \「and\」.」"
    assert json_to_native_script(script) == expected

def test_multiline_dialogue():
    script = [
        {"character": "Zundamon", "text": "Line 1\nLine 2"}
    ]
    expected = "Zundamon「Line 1\nLine 2」"
    assert json_to_native_script(script) == expected

def test_comment_safety():
    # If a line starts with #, the native script format might parse it as a comment.
    # The current behavior just outputs it as CharacterName「Text」.
    # We test it to document the ambiguity.
    script = [
        {"character": "#CommentChar", "text": "This might be ignored by YMM4"}
    ]
    expected = "#CommentChar「This might be ignored by YMM4」"
    assert json_to_native_script(script) == expected

def test_emotion_key_ignored():
    script_with_emotion = [
        {"character": "A", "text": "Text", "emotion": "Happy"}
    ]
    script_without = [
        {"character": "A", "text": "Text"}
    ]
    assert json_to_native_script(script_with_emotion) == json_to_native_script(script_without)
    assert json_to_native_script(script_with_emotion) == "A「Text」"

def test_empty_character_or_text():
    with pytest.raises(ValueError, match="empty 'character' value"):
        json_to_native_script([{"character": "", "text": "Hello"}])

    with pytest.raises(ValueError, match="empty 'character' value"):
        json_to_native_script([{"character": "   ", "text": "Hello"}])

    with pytest.raises(ValueError, match="empty 'text' value"):
        json_to_native_script([{"character": "Zundamon", "text": ""}])

    with pytest.raises(ValueError, match="empty 'text' value"):
        json_to_native_script([{"character": "Zundamon", "text": "   "}])

def test_invalid_input_types():
    with pytest.raises(ValueError, match="must be a list"):
        json_to_native_script({"character": "A", "text": "B"})

    with pytest.raises(ValueError, match="not a dictionary"):
        json_to_native_script(["Not a dict"])

    with pytest.raises(ValueError, match="contain 'character' and 'text'"):
        json_to_native_script([{"character": "A"}])
