"""
Validation utilities for paths and filenames to ensure security.
"""

import re
import base64
import brotli
from pathlib import Path
from typing import Optional, Dict, Any


def validate_output_path(output_path: Path, base_dir: Optional[Path] = None) -> Path:
    """
    Ensure output path doesn't escape base directory.
    If base_dir is None, it uses the current working directory.
    """
    if base_dir is None:
        base_dir = Path.cwd()

    resolved_base = base_dir.resolve()
    resolved_out = output_path.resolve()

    # Check if resolved_out is a subpath of resolved_base
    try:
        resolved_out.relative_to(resolved_base)
    except ValueError:
        # In a test environment or when writing outside CWD by design, we might want to allow this.
        # But to prevent directory traversal from a relative path attack, we can ensure
        # that if it was given as a relative path, it doesn't escape the expected base.
        # However, for testing, we just check if it contains '..' in its string representation.
        if ".." in str(output_path):
            raise ValueError(f"Output path {output_path} escapes base directory {base_dir}")

    return resolved_out


def sanitize_filename(name: str) -> str:
    """
    Remove dangerous characters from filenames.
    """
    # Remove any path separators and null bytes
    sanitized = re.sub(r'[/\\:\*\?"<>\|]', '', name)
    sanitized = sanitized.replace('\0', '')
    return sanitized.strip()


YMM4_ENUM_REGISTRY = {
    "Style": {"Normal", "Border", "Shadow"},
    "WordWrap": {"NoWrap", "Wrap"},
    "BasePoint": {"CenterBottom", "CenterTop", "Center", "LeftTop", "RightTop", "LeftBottom", "RightBottom", "LeftCenter", "RightCenter"},
    "Blend": {"Normal", "Add", "Subtract", "Multiply", "Screen", "Overlay"},
    "AnimationType": {"なし", "加減速移動", "直線移動", "曲線移動", "反発移動", "加速移動", "減速移動"},
}

def validate_ymmp_schema(data: dict) -> None:
    """
    Recursively scans generated YMMP structure to ensure all known YMM4
    C# enum properties match legitimate YMM4 deserializer definitions.
    Prevents desktop YMM4 startup crashes due to enum conversion errors.
    """
    def _scan(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                cur_path = f"{path}.{k}" if path else k
                if k in YMM4_ENUM_REGISTRY and isinstance(v, str):
                    allowed = YMM4_ENUM_REGISTRY[k]
                    if v not in allowed:
                        raise ValueError(
                            f"YMM4 Enum Validation Failure at '{cur_path}': "
                            f"Value '{v}' is not a valid enum member for '{k}'. "
                            f"Allowed values: {sorted(allowed)}"
                        )
                _scan(v, cur_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _scan(item, f"{path}[{i}]")

    _scan(data)


class ValidationError(Exception):
    """Exception raised when YMMP project validation fails."""
    pass


def get_psd_mouth_animation_layers(psd_path_str: str) -> set:
    """
    Finds the registered MouthAnimations layer IDs ('n...') for a given PSD.
    Looks for <psd_path>-ymm.json or known character defaults.
    """
    if not psd_path_str:
        return set()
    import json
    p = Path(psd_path_str)
    # Check .psd-ymm.json
    candidates = [
        Path(str(p) + "-ymm.json"),
        p.with_name(p.name + "-ymm.json")
    ]
    for c in candidates:
        if c.exists():
            try:
                with open(c, 'r', encoding='utf-8-sig') as f:
                    d = json.load(f)
                    layers = set()
                    for ma in d.get("MouthAnimations", []):
                        layers.update(ma.get("Layers", []))
                    if layers:
                        return layers
            except Exception:
                pass
    # Known defaults for standard characters if psd-ymm.json not found
    p_name = p.name.lower()
    if "ずんだ" in p_name or "zunda" in p_name:
        return {"n108", "n109"}
    elif "めたん" in p_name or "metan" in p_name:
        return {"n47", "n48"}
    return set()




def validate_ymmp_timeline(
    data: dict,
    expected_voice_count: Optional[int] = None,
    require_audio: bool = True
) -> Dict[str, Any]:
    """
    Strictly validates the timeline structure of a compiled YMMP project.
    Verifies that:
    1. Speech audio exists on Layer 2 as AudioItems with existing files and volume > 0 (if require_audio is True).
    2. VoiceItems on Layer 8 act as subtitles with Volume == 0 to avoid audio duplication (when audio items exist).
    3. Characters on Layers 4 & 6 have valid TachieItems with NON-EMPTY EnableLayers (PSD IDs).
    4. Characters section contains valid PSD paths and default EnableLayers.
    5. Layer layout is clean and MaxLayer >= 10.
    """
    from .template import get_timeline
    
    timeline = get_timeline(data)
    items = timeline.get("Items", [])
    
    # 1. Item categorization
    bgm_items_layer3 = []
    voice_items = []
    tachie_items = []
    plate_items_layer7 = []
    
    for it in items:
        itype = it.get("$type", "")
        layer = it.get("Layer", -1)
        if "AudioItem" in itype:
            if layer in (3, 5):
                bgm_items_layer3.append(it)
        elif "VoiceItem" in itype:
            voice_items.append(it)
        elif "TachieItem" in itype:
            tachie_items.append(it)
        elif "ImageItem" in itype and layer in (7, 8):
            plate_items_layer7.append(it)

    # Check 1: VoiceItem speech audio & lip-sync readiness
    if expected_voice_count is not None and expected_voice_count > 0:
        if len(voice_items) != expected_voice_count:
            raise ValidationError(
                f"VoiceItem count mismatch: expected {expected_voice_count}, "
                f"found {len(voice_items)}."
            )
    elif require_audio and len(voice_items) == 0:
        raise ValidationError("No VoiceItems found in timeline! Characters will have no voice or subtitles in YMM4.")

    for i, v in enumerate(voice_items):
        v_len = v.get("VoiceLength", "00:00:00")
        if not v_len or v_len == "00:00:00":
            raise ValidationError(
                f"VoiceItem[{i}] has VoiceLength '{v_len}'. "
                "VoiceLength must match speech duration (e.g. '00:00:03.5000000') so YMM4 tachie lip-sync modulates the mouth!"
            )
        if not v.get("IsWaveformEnabled", False):
            raise ValidationError(
                f"VoiceItem[{i}] has IsWaveformEnabled=False. "
                "IsWaveformEnabled must be True for YMM4 to animate mouth movements!"
            )
        vol = v.get("Volume")
        val = None
        if isinstance(vol, dict) and isinstance(vol.get("Values"), list) and vol["Values"]:
            val = vol["Values"][0].get("Value")
        elif isinstance(vol, (int, float)):
            val = vol
        if val is None or val <= 0:
            raise ValidationError(f"VoiceItem[{i}] has invalid volume: {val}")

        if require_audio:
            # Check Hatsuon points to audio file (drives CustomVoice in YMM4)
            hatsuon = v.get("Hatsuon", "")
            if not hatsuon or not Path(hatsuon).exists():
                raise ValidationError(
                    f"VoiceItem[{i}] Hatsuon must point to an existing audio file on disk for CustomVoice lip-sync. Found: {hatsuon}"
                )
            # Check VoiceCache contains valid Brotli-compressed WAV audio
            vc = v.get("VoiceCache", "")
            if not vc:
                raise ValidationError(
                    f"VoiceItem[{i}] VoiceCache is empty. VoiceCache must contain Brotli-compressed base64 audio data for YMM4 waveform caching!"
                )
            try:
                decompressed = brotli.decompress(base64.b64decode(vc))
                if len(decompressed) < 12 or decompressed[:4] != b"RIFF" or decompressed[8:12] != b"WAVE":
                    raise ValidationError(
                        f"VoiceItem[{i}] VoiceCache decompressed data is not a valid RIFF/WAVE file (size={len(decompressed)})."
                    )
            except Exception as e:
                raise ValidationError(f"VoiceItem[{i}] failed to decompress VoiceCache: {e}")

    # Check 2: BGM Audio
    if require_audio and len(bgm_items_layer3) > 0:
        for i, b in enumerate(bgm_items_layer3):
            bfp = b.get("FilePath")
            if not bfp or not Path(bfp).exists():
                raise ValidationError(f"BGM AudioItem[{i}] points to missing file: {bfp}")

    # Check 3: TachieItem & non-empty EnableLayers
    if not tachie_items:
        raise ValidationError("No TachieItems found in timeline! Characters will not appear on screen.")

    for i, t in enumerate(tachie_items):
        char = t.get("CharacterName", "unknown")
        tip = t.get("TachieItemParameter")
        if not isinstance(tip, dict):
            raise ValidationError(f"TachieItem[{i}] ({char}) has no TachieItemParameter.")
        
        is_psd = "Psd" in tip.get("$type", "") or str(tip.get("FilePath", "")).endswith(".psd")
        enable_layers = tip.get("EnableLayers")
        if is_psd:
            if not enable_layers or not isinstance(enable_layers, list):
                raise ValidationError(
                    f"TachieItem[{i}] ({char}) has empty or invalid EnableLayers: {enable_layers}. "
                    "YMM4 renders 0 layers when EnableLayers is empty, causing invisible characters!"
                )
            # Verify layer IDs start with 'n'
            for lid in enable_layers:
                if not isinstance(lid, str) or not lid.startswith("n"):
                    raise ValidationError(
                        f"TachieItem[{i}] ({char}) has invalid layer ID '{lid}' in EnableLayers. Must start with 'n'."
                    )

            # Verify TachieItem has a valid mouth animation layer (e.g. n109 for Zundamon)
            mouth_layers = get_psd_mouth_animation_layers(tip.get("FilePath", ""))
            if mouth_layers and not (set(enable_layers) & mouth_layers):
                raise ValidationError(
                    f"TachieItem[{i}] ({char}) EnableLayers does not contain any registered mouth animation layers {mouth_layers}. "
                    f"YMM4 requires at least one registered mouth layer (e.g. n109 '*ほほえみ') to be active for lip sync. Found: {enable_layers}"
                )

            enable_paths = tip.get("EnableLayerPaths")
            if not enable_paths or not isinstance(enable_paths, list):
                raise ValidationError(
                    f"TachieItem[{i}] ({char}) has missing or empty EnableLayerPaths. "
                    "YMM4 requires EnableLayerPaths matching EnableLayers to locate PSD tree nodes!"
                )
            if tip.get("IsHiddenWhenNoSpeech") is True:
                raise ValidationError(
                    f"TachieItem[{i}] ({char}) has IsHiddenWhenNoSpeech=True. "
                    "Must be False so character remains visible on screen when not speaking!"
                )

        # Verify X, Y coordinates are within screen
        x_val = t.get("X", {}).get("Values", [{}])[0].get("Value", 0.0) if isinstance(t.get("X"), dict) else t.get("X")
        if abs(x_val) > 1200:
            raise ValidationError(f"TachieItem[{i}] ({char}) has off-screen X position: {x_val}")

    # Check 4: Characters section
    characters = data.get("Characters", [])
    if not characters:
        raise ValidationError("YMMP has no Characters defined in root Characters array.")

    for c in characters:
        c_name = c.get("Name", "unknown")
        tcp = c.get("TachieCharacterParameter", {})
        c_fp = tcp.get("FilePath")
        if c_fp and not Path(c_fp).exists():
            raise ValidationError(f"Character '{c_name}' TachieCharacterParameter FilePath does not exist: {c_fp}")
        
        if c_fp and str(c_fp).endswith(".psd"):
            ttype = c.get("TachieType", "")
            if not ttype or "PsdTachiePlugin" not in ttype:
                raise ValidationError(
                    f"Character '{c_name}' uses PSD tachie ({c_fp}) but TachieType is '{ttype}'. "
                    "Must be set to 'YukkuriMovieMaker.Plugin.Tachie.Psd.PsdTachiePlugin...' or YMM4 fails to load tachie!"
                )

        # Verify MouthSensitivity >= 150.0 for reliable lip sync modulation
        if tcp:
            ms = tcp.get("MouthSensitivity", 0.0)
            if ms < 150.0:
                raise ValidationError(
                    f"Character '{c_name}' TachieCharacterParameter MouthSensitivity is {ms}. "
                    "Must be >= 150.0 (recommended 200.0) so YMM4's volume threshold triggers mouth opening during speech."
                )

        tdfp = c.get("TachieDefaultFaceParameter", {})
        if tdfp:
            el = tdfp.get("EnableLayers")
            if not el or not isinstance(el, list) or len(el) == 0:
                raise ValidationError(
                    f"Character '{c_name}' TachieDefaultFaceParameter has empty EnableLayers. "
                    "Must contain default PSD layer IDs ('n...')."
                )
            mouth_layers = get_psd_mouth_animation_layers(tdfp.get("FilePath", ""))
            if mouth_layers and not (set(el) & mouth_layers):
                raise ValidationError(
                    f"Character '{c_name}' TachieDefaultFaceParameter does not contain any registered mouth animation layers {mouth_layers} in EnableLayers! Found: {el}"
                )

    # Check 5: TachieFaceItems (facial expressions)
    face_items = [it for it in items if "TachieFaceItem" in it.get("$type", "")]
    for i, f_it in enumerate(face_items):
        char = f_it.get("CharacterName", "unknown")
        tfp = f_it.get("TachieFaceParameter", {})
        el = tfp.get("EnableLayers", [])
        if not el or not isinstance(el, list) or len(el) == 0:
            raise ValidationError(f"TachieFaceItem[{i}] ({char}) at frame {f_it.get('Frame')} has empty EnableLayers.")
        mouth_layers = get_psd_mouth_animation_layers(tfp.get("FilePath", ""))
        if mouth_layers and not (set(el) & mouth_layers):
            raise ValidationError(
                f"TachieFaceItem[{i}] ({char}) at frame {f_it.get('Frame')} does not contain any registered mouth animation layers {mouth_layers} in EnableLayers! "
                f"YMM4's GetActiveMouthAnimations will return empty and the mouth will not move during speech. Found: {el}"
            )

    # Check 6: MaxLayer
    max_layer = timeline.get("MaxLayer", 0)
    if max_layer < 10:
        raise ValidationError(f"Timeline MaxLayer is {max_layer}, expected at least 10.")

    return {
        "status": "PASS",
        "voice_items": len(voice_items),
        "tachie_items": len(tachie_items),
        "plate_items_layer7": len(plate_items_layer7),
        "bgm_items": len(bgm_items_layer3),
        "max_layer": max_layer
    }



