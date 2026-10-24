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

@pytest.fixture(autouse=True)
def mock_ymmp_timeline_validation(monkeypatch):
    """Bypass disk file checks during timeline unit and CLI tests."""
    import os
    current_test = os.environ.get("PYTEST_CURRENT_TEST", "")
    if "test_ymmp_validation" in current_test or "test_subtitle_safe_zone" in current_test:
        return

    dummy_result = {
        "status": "PASS",
        "voice_count": 1,
        "tachie_count": 1,
        "plate_count": 0,
        "bgm_count": 0,
    }
    monkeypatch.setattr(
        "veraxi_ymmp.ymmp_renderer.validate_ymmp_timeline",
        lambda *args, **kwargs: dummy_result,
    )
    monkeypatch.setattr(
        "veraxi_ymmp.validation.validate_ymmp_timeline",
        lambda *args, **kwargs: dummy_result,
    )
    monkeypatch.setattr(
        "veraxi_ymmp.compiler.validate_ymmp_timeline",
        lambda *args, **kwargs: dummy_result,
    )
    monkeypatch.setattr(
        "veraxi_ymmp.pipeline.validate_ymmp_timeline",
        lambda *args, **kwargs: dummy_result,
    )

@pytest.fixture(autouse=True)
def mock_ymmp_timeline_validation(monkeypatch):
    """Bypass disk file checks during timeline unit and CLI tests."""
    import os
    current_test = os.environ.get("PYTEST_CURRENT_TEST", "")
    if "test_ymmp_validation" in current_test or "test_subtitle_safe_zone" in current_test:
        return

    dummy_result = {
        "status": "PASS",
        "voice_count": 1,
        "tachie_count": 1,
        "plate_count": 0,
        "bgm_count": 0,
    }

    try:
        monkeypatch.setattr(
            "veraxi_ymmp.ymmp_renderer.validate_ymmp_timeline",
            lambda *args, **kwargs: dummy_result,
        )
    except AttributeError:
        pass

    try:
        monkeypatch.setattr(
            "veraxi_ymmp.validation.validate_ymmp_timeline",
            lambda *args, **kwargs: dummy_result,
        )
    except AttributeError:
        pass

    try:
        monkeypatch.setattr(
            "veraxi_ymmp.compiler.validate_ymmp_timeline",
            lambda *args, **kwargs: dummy_result,
        )
    except AttributeError:
        pass

    try:
        monkeypatch.setattr(
            "veraxi_ymmp.pipeline.validate_ymmp_timeline",
            lambda *args, **kwargs: dummy_result,
        )
    except AttributeError:
        pass
