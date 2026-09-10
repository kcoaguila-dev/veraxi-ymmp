import json
import pytest
from unittest.mock import patch
from veraxi_ymmp.cli import _compile
from argparse import Namespace
import sys
import io

def _create_temp_json(tmp_path, data, name="script.json"):
    path = tmp_path / name
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    return str(path)

@pytest.fixture
def base_args(tmp_path):
    import os
    template = os.path.join(os.path.dirname(__file__), 'fixtures', 'sample_template.ymmp')

    return Namespace(
        template=str(template),
        output=str(tmp_path / "output.ymmp"),
        writer_script=None,
        use_tts=False,
        speaker_map=None,
        bom=False,
        use_async=False,
        quiet=False,
        verbose=False,
        voicevox_url="http://localhost:50021",
        default_speaker=3
    )

def test_cli_invalid_emotion(tmp_path, base_args):
    script_path = _create_temp_json(tmp_path, [{
        "character": "ゆっくり霊夢",
        "text": "こんにちは",
        "emotion": "superhappy",
        "motion": "none",
        "bgm": None,
        "sfx": None
    }])
    base_args.script = script_path

    with patch('sys.stderr', new=io.StringIO()) as fake_err:
        with pytest.raises(SystemExit) as excinfo:
            _compile(base_args)
        assert excinfo.value.code == 1
        assert "Invalid director script schema: Entry 0 'emotion' must be one of" in fake_err.getvalue()

def test_cli_missing_metadata(tmp_path, base_args):
    script_path = _create_temp_json(tmp_path, [{
        "character": "ゆっくり霊夢",
        "text": "こんにちは",
        "emotion": "happy"
        # missing motion, bgm, sfx
    }])
    base_args.script = script_path

    with patch('sys.stderr', new=io.StringIO()) as fake_err:
        with pytest.raises(SystemExit) as excinfo:
            _compile(base_args)
        assert excinfo.value.code == 1
        assert "must contain exactly" in fake_err.getvalue()

def test_cli_unknown_metadata(tmp_path, base_args):
    script_path = _create_temp_json(tmp_path, [{
        "character": "ゆっくり霊夢",
        "text": "こんにちは",
        "emotion": "happy",
        "motion": "none",
        "bgm": None,
        "sfx": None,
        "extra_field": "unwanted"
    }])
    base_args.script = script_path

    with patch('sys.stderr', new=io.StringIO()) as fake_err:
        with pytest.raises(SystemExit) as excinfo:
            _compile(base_args)
        assert excinfo.value.code == 1
        assert "must contain exactly" in fake_err.getvalue()

def test_cli_valid_legacy_script(tmp_path, base_args):
    script_path = _create_temp_json(tmp_path, [{
        "character": "ゆっくり霊夢",
        "text": "こんにちは"
    }])
    base_args.script = script_path

    # Should compile without SystemExit
    _compile(base_args)
    assert (tmp_path / "output.ymmp").exists()
