from pathlib import Path
import pytest
from veraxi_ymmp.validation import (
    ValidationError,
    sanitize_filename,
    validate_output_path,
    validate_ymmp_schema,
)


def test_validate_output_path_safe(tmp_path: Path):
    base_dir = tmp_path
    safe_path = tmp_path / "subdir" / "output.ymmp"

    # Should not raise
    resolved = validate_output_path(safe_path, base_dir)
    assert resolved == safe_path.resolve()


def test_validate_output_path_unsafe(tmp_path: Path):
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    unsafe_path = base_dir / ".." / "outside.ymmp"

    with pytest.raises((ValueError, ValidationError), match="escapes base directory|Path traversal detected"):
        validate_output_path(unsafe_path, base_dir)


def test_validate_output_path_unsafe_absolute_outside_base_dir(tmp_path: Path):
    base_dir = tmp_path / "sandbox"
    base_dir.mkdir()
    outside_abs = (tmp_path / "other_folder" / "evil.ymmp").resolve()

    with pytest.raises((ValueError, ValidationError), match="escapes base directory|Path traversal detected|outside"):
        validate_output_path(outside_abs, base_dir)


def test_sanitize_filename():
    assert sanitize_filename("safe_name.wav") == "safe_name.wav"
    assert sanitize_filename("bad/name.wav") == "badname.wav"
    assert sanitize_filename("bad\\name.wav") == "badname.wav"
    assert sanitize_filename("bad:name.wav") == "badname.wav"
    assert sanitize_filename("bad*name?.wav") == "badname.wav"
    assert sanitize_filename('bad"name".wav') == "badname.wav"
    assert sanitize_filename("bad<name>.wav") == "badname.wav"
    assert sanitize_filename("bad|name.wav") == "badname.wav"
    assert sanitize_filename("bad\0name.wav") == "badname.wav"


def test_validate_ymmp_schema_valid():
    data = {
        "Timeline": {
            "Items": [
                {
                    "Style": "Border",
                    "WordWrap": "Wrap",
                    "BasePoint": "CenterBottom",
                    "Blend": "Normal",
                    "X": {"AnimationType": "なし"},
                }
            ]
        }
    }
    # Should not raise
    validate_ymmp_schema(data)


def test_validate_ymmp_schema_invalid_enum():
    bad_data = {
        "Timeline": {
            "Items": [
                {
                    "Style": "InvalidStyleValue",
                    "WordWrap": "Wrap",
                }
            ]
        }
    }
    with pytest.raises(ValueError, match="YMM4 Enum Validation Failure"):
        validate_ymmp_schema(bad_data)
