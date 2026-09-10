import pytest
from veraxi_ymmp.validation import validate_output_path, sanitize_filename

def test_validate_output_path_safe(tmp_path):
    base_dir = tmp_path
    safe_path = tmp_path / "subdir" / "output.ymmp"

    # Should not raise
    resolved = validate_output_path(safe_path, base_dir)
    assert resolved == safe_path.resolve()

def test_validate_output_path_unsafe(tmp_path):
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    unsafe_path = base_dir / ".." / "outside.ymmp"

    with pytest.raises(ValueError, match="escapes base directory"):
        validate_output_path(unsafe_path, base_dir)

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
