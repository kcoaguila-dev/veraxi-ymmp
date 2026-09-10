import pytest
from veraxi_ymmp.script import (
    validate_writer_script,
    validate_director_script,
    validate_director_against_writer
)

def test_validate_writer_script_valid():
    data = [
        {"character": "A", "text": "Hello"},
        {"character": "B", "text": "World"}
    ]
    result = validate_writer_script(data)
    assert len(result) == 2
    assert result[0]["character"] == "A"
    assert result[0]["text"] == "Hello"

def test_validate_writer_script_invalid():
    with pytest.raises(ValueError, match="Writer script must be a JSON array"):
        validate_writer_script({})

    with pytest.raises(ValueError, match="must contain at least 'character' and 'text'"):
        validate_writer_script([{"character": "A"}])

    # Should NOT raise, legacy scripts can have extra fields
    res = validate_writer_script([{"character": "A", "text": "Hello", "extra": "field"}])
    assert len(res) == 1
    assert res[0]["character"] == "A"

    with pytest.raises(ValueError, match="'character' must be a non-empty string"):
        validate_writer_script([{"character": "", "text": "Hello"}])

def test_validate_director_script_valid():
    data = [
        {
            "character": "A",
            "text": "Hello",
            "emotion": "happy",
            "motion": "jump",
            "bgm": "theme.mp3",
            "sfx": None
        }
    ]
    result = validate_director_script(data)
    assert len(result) == 1
    assert result[0]["emotion"] == "happy"
    assert result[0]["motion"] == "jump"
    assert result[0]["bgm"] == "theme.mp3"
    assert result[0]["sfx"] is None

def test_validate_director_script_invalid():
    with pytest.raises(ValueError, match="Director script must be a JSON array"):
        validate_director_script({})

    # Missing fields
    with pytest.raises(ValueError, match="must contain exactly"):
        validate_director_script([{"character": "A", "text": "Hello"}])

    # Invalid emotion types and values
    for bad_emotion in ["weird", 123, [], {}, None]:
        invalid_emotion = [{
            "character": "A", "text": "Hello", "emotion": bad_emotion,
            "motion": "none", "bgm": None, "sfx": None
        }]
        with pytest.raises(ValueError, match="'emotion' must be one of"):
            validate_director_script(invalid_emotion)

    # Invalid motion types and values
    for bad_motion in ["dance", 123, [], {}, None]:
        invalid_motion = [{
            "character": "A", "text": "Hello", "emotion": "neutral",
            "motion": bad_motion, "bgm": None, "sfx": None
        }]
        with pytest.raises(ValueError, match="'motion' must be one of"):
            validate_director_script(invalid_motion)

    # Invalid bgm (empty string)
    empty_bgm = [{
        "character": "A", "text": "Hello", "emotion": "neutral",
        "motion": "none", "bgm": "", "sfx": None
    }]
    with pytest.raises(ValueError, match="'bgm' must be null or a non-empty string"):
        validate_director_script(empty_bgm)


def test_validate_director_against_writer():
    writer = [
        {"character": "A", "text": "Hello"},
        {"character": "B", "text": "World"}
    ]
    director = [
        {
            "character": "A", "text": "Hello", "emotion": "neutral",
            "motion": "none", "bgm": None, "sfx": None
        },
        {
            "character": "B", "text": "World", "emotion": "happy",
            "motion": "jump", "bgm": None, "sfx": None
        }
    ]

    # Should not raise
    validate_director_against_writer(director, writer)

    # Mismatched length
    with pytest.raises(ValueError, match="Script length mismatch"):
        validate_director_against_writer(director[:1], writer)

    # Character changed
    bad_char = [dict(d) for d in director]
    bad_char[0]["character"] = "C"
    with pytest.raises(ValueError, match="Character mismatch at entry 0"):
        validate_director_against_writer(bad_char, writer)

    # Text changed
    bad_text = [dict(d) for d in director]
    bad_text[1]["text"] = "Worlds"
    with pytest.raises(ValueError, match="Text mismatch at entry 1"):
        validate_director_against_writer(bad_text, writer)
