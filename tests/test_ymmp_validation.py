"""
Automated QA tests for YMMP Timeline validation.
Guarantees that broken YMMP files (missing speech audio, invisible tachie, invalid layers,
empty VoiceCache, or unlinked lip-sync) are caught immediately and never passed to the user.
"""
import copy
import base64
import brotli
import pytest
from pathlib import Path
from veraxi_ymmp.validation import validate_ymmp_timeline, ValidationError


@pytest.fixture
def base_valid_ymmp():
    """Minimal valid YMMP timeline fixture."""
    test_wav = Path("tests/scratch_audio.wav").resolve()
    test_wav.parent.mkdir(parents=True, exist_ok=True)
    wav_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    test_wav.write_bytes(wav_bytes)

    vc_b64 = base64.b64encode(brotli.compress(wav_bytes)).decode('ascii')
    psd_path = str(Path.home() / "Pictures" / "ずんだもん立ち絵素材V3.2" / "坂本アヒル_ずんだもん立ち絵V3.2_全部入り版.psd.psd")

    return {
        "Characters": [
            {
                "Name": "ずんだもん",
                "TachieType": "YukkuriMovieMaker.Plugin.Tachie.Psd.PsdTachiePlugin, YukkuriMovieMaker.Plugin.Tachie.Psd, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null",
                "TachieCharacterParameter": {
                    "FilePath": psd_path,
                    "MouthSensitivity": 200.0
                },
                "TachieDefaultFaceParameter": {
                    "IsEnabled": True,
                    "FilePath": psd_path,
                    "EnableLayers": ["n153", "n89", "n88", "n83", "n97", "n95", "n148", "n140", "n115", "n21", "n15", "n12", "n4", "n1", "n0", "n109"],
                    "EnableLayerPaths": ["path1"]
                }
            }
        ],
        "Timeline": {
            "MaxLayer": 10,
            "Items": [
                {
                    "$type": "YukkuriMovieMaker.Project.Items.AudioItem, YukkuriMovieMaker",
                    "FilePath": str(test_wav),
                    "Layer": 3,
                    "Frame": 0,
                    "Length": 90,
                    "Volume": {"Values": [{"Value": 3.0}]}
                },
                {
                    "$type": "YukkuriMovieMaker.Project.Items.TachieItem, YukkuriMovieMaker",
                    "CharacterName": "ずんだもん",
                    "Layer": 6,
                    "Frame": 0,
                    "Length": 90,
                    "X": {"Values": [{"Value": 550.0}]},
                    "TachieItemParameter": {
                        "FilePath": psd_path,
                        "EnableLayers": ["n153", "n89", "n88", "n83", "n97", "n95", "n148", "n140", "n115", "n21", "n15", "n12", "n4", "n1", "n0", "n109"],
                        "EnableLayerPaths": ["path1"],
                        "IsHiddenWhenNoSpeech": False
                    }
                },
                {
                    "$type": "YukkuriMovieMaker.Project.Items.VoiceItem, YukkuriMovieMaker",
                    "CharacterName": "ずんだもん",
                    "Hatsuon": str(test_wav),
                    "FilePath": str(test_wav),
                    "VoiceCache": vc_b64,
                    "Layer": 9,
                    "Frame": 0,
                    "Length": 90,
                    "VoiceLength": "00:00:01.5000000",
                    "IsWaveformEnabled": True,
                    "Volume": {"Values": [{"Value": 100.0}]}
                }
            ]
        }
    }


def test_validation_passes_valid_data(base_valid_ymmp):
    res = validate_ymmp_timeline(base_valid_ymmp, expected_voice_count=1)
    assert res["status"] == "PASS"
    assert res["voice_items"] == 1
    assert res["tachie_items"] == 1


def test_validation_fails_on_empty_voice_items(base_valid_ymmp):
    # Remove VoiceItem
    base_valid_ymmp["Timeline"]["Items"] = [
        it for it in base_valid_ymmp["Timeline"]["Items"]
        if "VoiceItem" not in it.get("$type", "")
    ]
    with pytest.raises(ValidationError, match="No VoiceItems found in timeline"):
        validate_ymmp_timeline(base_valid_ymmp)


def test_validation_fails_on_empty_enable_layers(base_valid_ymmp):
    # Empty EnableLayers in TachieItem (the exact bug that caused invisible characters)
    for it in base_valid_ymmp["Timeline"]["Items"]:
        if "TachieItem" in it.get("$type", ""):
            it["TachieItemParameter"]["EnableLayers"] = []
    with pytest.raises(ValidationError, match="empty or invalid EnableLayers"):
        validate_ymmp_timeline(base_valid_ymmp)


def test_validation_fails_on_missing_audio_file(base_valid_ymmp):
    for it in base_valid_ymmp["Timeline"]["Items"]:
        if "VoiceItem" in it.get("$type", ""):
            it["Hatsuon"] = "C:/non/existent/audio_file.wav"
    with pytest.raises(ValidationError, match="must point to an existing audio file"):
        validate_ymmp_timeline(base_valid_ymmp)


def test_validation_fails_on_empty_voicecache(base_valid_ymmp):
    for it in base_valid_ymmp["Timeline"]["Items"]:
        if "VoiceItem" in it.get("$type", ""):
            it["VoiceCache"] = ""
    with pytest.raises(ValidationError, match="VoiceCache is empty"):
        validate_ymmp_timeline(base_valid_ymmp)


def test_validation_fails_on_corrupt_voicecache(base_valid_ymmp):
    for it in base_valid_ymmp["Timeline"]["Items"]:
        if "VoiceItem" in it.get("$type", ""):
            # Base64 of random non-compressed junk
            it["VoiceCache"] = base64.b64encode(b"not_brotli_garbage").decode('ascii')
    with pytest.raises(ValidationError, match="failed to decompress VoiceCache"):
        validate_ymmp_timeline(base_valid_ymmp)


def test_validation_fails_on_empty_voicelength_for_lipsync(base_valid_ymmp):
    for it in base_valid_ymmp["Timeline"]["Items"]:
        if "VoiceItem" in it.get("$type", ""):
            it["VoiceLength"] = "00:00:00"
    with pytest.raises(ValidationError, match="VoiceLength must match speech duration"):
        validate_ymmp_timeline(base_valid_ymmp)


def test_validation_fails_on_missing_mouth_animation_layer(base_valid_ymmp):
    # Omit mouth animation layer (n109 / n108) from TachieItem EnableLayers
    for it in base_valid_ymmp["Timeline"]["Items"]:
        if "TachieItem" in it.get("$type", ""):
            it["TachieItemParameter"]["EnableLayers"] = [
                lid for lid in it["TachieItemParameter"]["EnableLayers"]
                if lid not in ("n108", "n109")
            ]
    with pytest.raises(ValidationError, match="registered mouth animation layers"):
        validate_ymmp_timeline(base_valid_ymmp)


def test_validation_fails_on_low_mouth_sensitivity(base_valid_ymmp):
    # MouthSensitivity below 150.0 fails to reliably open mouth on speech volume
    for c in base_valid_ymmp["Characters"]:
        c["TachieCharacterParameter"]["MouthSensitivity"] = 100.0
    with pytest.raises(ValidationError, match="MouthSensitivity is 100.0"):
        validate_ymmp_timeline(base_valid_ymmp)


def test_validation_fails_when_face_item_missing_mouth_layer(base_valid_ymmp):
    # Add a TachieFaceItem with missing mouth animation layer (e.g. n121 '*むふ' instead of n109)
    psd_path = base_valid_ymmp["Characters"][0]["TachieCharacterParameter"]["FilePath"]
    base_valid_ymmp["Timeline"]["Items"].append({
        "$type": "YukkuriMovieMaker.Project.Items.TachieFaceItem, YukkuriMovieMaker",
        "CharacterName": "ずんだもん",
        "Layer": 7,
        "Frame": 0,
        "Length": 90,
        "TachieFaceParameter": {
            "IsEnabled": True,
            "FilePath": psd_path,
            "EnableLayers": ["n153", "n89", "n88", "n147", "n121"],  # Missing n109!
            "EyeAnimation": "Default",
            "MouthAnimation": "Default"
        }
    })
    with pytest.raises(ValidationError, match="GetActiveMouthAnimations will return empty"):
        validate_ymmp_timeline(base_valid_ymmp)


def test_validation_fails_on_missing_tachie_type(base_valid_ymmp):
    # If TachieType is missing or doesn't mention PsdTachiePlugin, YMM4 cannot load the character tachie
    base_valid_ymmp["Characters"][0]["TachieType"] = None
    with pytest.raises(ValidationError, match="TachieType is 'None'"):
        validate_ymmp_timeline(base_valid_ymmp)


def test_validation_fails_on_missing_enable_layer_paths(base_valid_ymmp):
    # If EnableLayerPaths is missing from TachieItem, YMM4 fails to locate PSD tree nodes
    for it in base_valid_ymmp["Timeline"]["Items"]:
        if "TachieItem" in it.get("$type", ""):
            it["TachieItemParameter"]["EnableLayerPaths"] = None
    with pytest.raises(ValidationError, match="missing or empty EnableLayerPaths"):
        validate_ymmp_timeline(base_valid_ymmp)


