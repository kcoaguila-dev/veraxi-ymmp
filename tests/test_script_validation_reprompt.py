import json
from pathlib import Path
import pytest
from veraxi_ymmp.cli import _cmd_validate

def test_script_validation_reprompt(capsys, tmp_path):
    # Create an invalid script
    bad_script_path = tmp_path / "bad_script.json"
    bad_script_path.write_text(json.dumps([
        {
            "character": "zundamon",
            "text": "This text is well over forty characters long and should definitely trigger the length validation error during the script validation.",
            "emotion": "happy",
            "motion": "none",
            "bgm": None,
            "sfx": None,
            "image": None
        },
        {
            "character": "metan",
            "text": "Valid text",
            "emotion": "super_happy",
            "motion": "none",
            "bgm": None,
            "sfx": None,
            "image": None
        }
    ]), encoding="utf-8")

    # We expect sys.exit(1) to be raised on validation error
    with pytest.raises(SystemExit) as e:
        _cmd_validate([str(bad_script_path)])

    assert e.value.code == 1

    out, err = capsys.readouterr()

    assert "================ LLM RE-PROMPT BLOCK (COPY & PASTE TO AI) ================" in out
    assert "Cut #0 (zundamon): Exceeds 40 characters" in out
    assert "Cut #1 (metan): Invalid emotion 'super_happy'." in out
    assert "Please fix these specific entries while preserving the rest of the script, and return the complete corrected JSON block." in out
