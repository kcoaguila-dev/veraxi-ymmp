import json
import pytest
from unittest.mock import patch
from veraxi_ymmp.cli import _compile
from argparse import Namespace
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
        "sfx": None,
            "image": None
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
            "image": None,
        "extra_field": "unwanted"
    }])
    base_args.script = script_path

    with patch('sys.stderr', new=io.StringIO()) as fake_err:
        with pytest.raises(SystemExit) as excinfo:
            _compile(base_args)
        assert excinfo.value.code == 1
        assert "must contain exactly" in fake_err.getvalue()

def test_cli_director_script_never_falls_back(tmp_path, base_args):
    # A script with valid Writer fields but invalid Director metadata
    script_path = _create_temp_json(tmp_path, [{
        "character": "ゆっくり霊夢",
        "text": "こんにちは",
        "emotion": "superhappy" # Invalid emotion, triggering Director validation
        # Missing motion, bgm, sfx, which also triggers validation failure
    }])
    base_args.script = script_path

    with patch('sys.stderr', new=io.StringIO()) as fake_err:
        with pytest.raises(SystemExit) as excinfo:
            _compile(base_args)
        assert excinfo.value.code == 1
        err_msg = fake_err.getvalue()
        assert "Invalid director script schema" in err_msg
        assert "Invalid writer script schema" not in err_msg


def test_cli_valid_legacy_script(tmp_path, base_args):
    script_path = _create_temp_json(tmp_path, [{
        "character": "ゆっくり霊夢",
        "text": "こんにちは"
    }])
    base_args.script = script_path

    # Should compile without SystemExit
    _compile(base_args)
    assert (tmp_path / "output.ymmp").exists()

def test_cli_non_utf8_writer_script(tmp_path, base_args):
    script_path = _create_temp_json(tmp_path, [{
        "character": "ゆっくり霊夢",
        "text": "こんにちは",
        "emotion": "happy",
        "motion": "none",
        "bgm": None,
        "sfx": None,
            "image": None
    }])

    # Create non-UTF-8 writer script (e.g. Shift-JIS)
    writer_path = tmp_path / "writer.json"
    data = json.dumps([{"character": "ゆっくり霊夢", "text": "こんにちは"}], ensure_ascii=False)
    with open(writer_path, 'wb') as f:
        f.write(data.encode('shift-jis'))

    base_args.script = script_path
    base_args.writer_script = str(writer_path)

    with patch('sys.stderr', new=io.StringIO()) as fake_err:
        with pytest.raises(SystemExit) as excinfo:
            _compile(base_args)
        assert excinfo.value.code == 1
        assert "Error: Writer script file is not UTF-8 encoded:" in fake_err.getvalue()


def test_cli_subcommand_run(monkeypatch, tmp_path):
    from veraxi_ymmp.cli import main
    from veraxi_ymmp.pipeline import PipelineResult

    monkeypatch.setattr("sys.argv", ["veraxi-ymmp", "run", str(tmp_path), "--no-tts", "--qa-duration", "10"])
    fake_res = PipelineResult(project_dir=tmp_path, success=True)
    with patch("veraxi_ymmp.pipeline.ProjectPipeline.run", return_value=fake_res) as mock_run:
        main()
        assert mock_run.called
        assert mock_run.call_args.kwargs["qa_duration"] == 10.0


def test_cli_subcommand_normalize(monkeypatch, tmp_path):
    from veraxi_ymmp.cli import main

    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"mp4")
    monkeypatch.setattr("sys.argv", ["veraxi-ymmp", "normalize", str(dummy_video), "-p", "youtube"])
    with patch("veraxi_ymmp.audio_normalizer.normalize_video_audio", return_value=tmp_path / "video_youtube.mp4") as mock_norm:
        main()
        assert mock_norm.called


def test_cli_subcommand_broll(monkeypatch, tmp_path):
    from veraxi_ymmp.cli import main

    manifest = tmp_path / "broll_manifest.json"
    manifest.write_text("[]", encoding="utf-8")
    out_dir = tmp_path / "broll_out"
    monkeypatch.setattr("sys.argv", ["veraxi-ymmp", "broll", str(manifest), "-o", str(out_dir)])
    with patch("veraxi_ymmp.broll.render_from_manifest", return_value=[]) as mock_broll:
        main()
        assert mock_broll.called


def test_cli_subcommand_thumbnail(monkeypatch, tmp_path):
    from veraxi_ymmp.cli import main

    out_png = tmp_path / "thumb.png"
    monkeypatch.setattr("sys.argv", ["veraxi-ymmp", "thumbnail", str(tmp_path), "-o", str(out_png)])
    with patch("veraxi_ymmp.thumbnail.generate_project_thumbnail", return_value=out_png) as mock_thumb:
        main()
        assert mock_thumb.called
