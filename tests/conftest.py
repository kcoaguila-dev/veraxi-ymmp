import pytest
import json
from pathlib import Path

@pytest.fixture
def dummy_psd(tmp_path: Path) -> Path:
    """Provides a dummy PSD file."""
    psd_path = tmp_path / "dummy_tachie.psd"
    # Minimal content, validation just checks .exists() and .endswith(".psd")
    psd_path.write_text("8BPS dummy content")
    return psd_path

@pytest.fixture
def dummy_wav(tmp_path: Path) -> Path:
    """Provides a dummy WAV file."""
    wav_path = tmp_path / "dummy_audio.wav"
    wav_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    wav_path.write_bytes(wav_bytes)
    return wav_path

@pytest.fixture
def dummy_png(tmp_path: Path) -> Path:
    """Provides a dummy PNG file."""
    png_path = tmp_path / "dummy_image.png"
    # 1x1 transparent PNG
    png_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\x0d\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")
    return png_path

@pytest.fixture
def fake_project(tmp_path: Path, dummy_psd: Path, dummy_wav: Path, dummy_png: Path) -> Path:
    proj_dir = tmp_path / "fake_project"
    proj_dir.mkdir(exist_ok=True)

    ymmp_data = {
        "Timeline": {
            "VideoInfo": {"FPS": 60, "Hz": 48000},
            "Items": [
                {
                    "$type": "YukkuriMovieMaker.Project.Items.VoiceItem, YukkuriMovieMaker",
                    "CharacterName": "ずんだもん",
                    "Layer": 2,
                    "Frame": 0,
                    "Length": 60
                },
                {
                    "$type": "YukkuriMovieMaker.Project.Items.VoiceItem, YukkuriMovieMaker",
                    "CharacterName": "四国めたん",
                    "Layer": 2,
                    "Frame": 0,
                    "Length": 60
                }
            ]
        },
        "Characters": [
            {"Name": "ずんだもん", "TachieCharacterParameter": {"FilePath": str(dummy_psd)}, "TachieType": "YukkuriMovieMaker.Plugin.Tachie.Psd.PsdTachiePlugin"},
            {"Name": "四国めたん", "TachieCharacterParameter": {"FilePath": str(dummy_psd)}, "TachieType": "YukkuriMovieMaker.Plugin.Tachie.Psd.PsdTachiePlugin"}
        ]
    }
    (proj_dir / "template.ymmp").write_text(json.dumps(ymmp_data, ensure_ascii=False))

    script_data = [
        {
            "character": "ずんだもん",
            "text": "Hello world",
            "emotion": "normal",
            "motion": "none",
            "audio_path": str(dummy_wav.resolve())
        },
        {
            "character": "四国めたん",
            "text": "Goodbye world",
            "emotion": "sad",
            "motion": "none",
            "audio_path": str(dummy_wav.resolve())
        },
        {
            "character": "ずんだもん",
            "text": "Hello again",
            "emotion": "normal",
            "motion": "none",
            "audio_path": str(dummy_wav.resolve())
        }
    ]

    (proj_dir / "script.json").write_text(json.dumps(script_data, ensure_ascii=False))
    (proj_dir / "thumbnail.png").write_bytes(dummy_png.read_bytes())

    return proj_dir




@pytest.fixture
def dummy_psd(tmp_path: Path) -> Path:
    """Provides a dummy PSD file for validation tests that require an existing file."""
    psd = tmp_path / "test.psd"
    psd.write_text("dummy psd content")
    return psd
