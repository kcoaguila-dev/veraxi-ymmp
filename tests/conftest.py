from pathlib import Path
import pytest


@pytest.fixture
def fake_project(tmp_path: Path) -> Path:
    proj_dir = tmp_path / "test_fake_project"
    proj_dir.mkdir()

    script_json = proj_dir / "script.json"
    script_json.write_text('[{"character": "ずんだもん", "text": "テスト"}]', encoding="utf-8")

    audio_dir = proj_dir / "audio"
    audio_dir.mkdir()
    dummy_wav = audio_dir / "001_Zundamon.wav"
    dummy_wav.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")

    return proj_dir
