"""
Models and validation logic for the two-stage script pipeline.
"""

import logging
import re
from typing import Any, Dict, List, Literal, Optional, TypedDict

logger = logging.getLogger(__name__)

Emotion = Literal[
    "normal",
    "neutral",
    "happy",
    "angry",
    "sad",
    "surprised",
    "confused",
    "scared",
    "excited",
    "disgusted",
    "smug",
    "crying",
    "blushing",
]
Motion = Literal["none", "jump", "nod"]
CharacterPosition = Literal["left", "center", "right"]
SubtitlePosition = Literal["top_center", "center", "bottom_center"]
SubtitleStyle = Literal["default", "outlined"]

VALID_EMOTIONS = {
    "normal",
    "neutral",
    "happy",
    "angry",
    "sad",
    "surprised",
    "confused",
    "scared",
    "excited",
    "disgusted",
    "smug",
    "crying",
    "blushing",
}
VALID_MOTIONS = {"none", "jump", "nod"}
VALID_CHARACTER_POSITIONS = {"left", "center", "right"}
VALID_SUBTITLE_POSITIONS = {"top_center", "center", "bottom_center"}
VALID_SUBTITLE_STYLES = {"default", "outlined"}


class WriterScriptEntry(TypedDict):
    """Factual dialogue entry from the writer."""

    character: str
    text: str


class DirectorScriptEntry(TypedDict):
    """Validated director script entry including metadata."""

    character: str
    text: str
    emotion: Emotion
    motion: Motion
    bgm: Optional[str]
    sfx: Optional[str]
    image: Optional[str]
    character_position: CharacterPosition
    subtitle_position: SubtitlePosition
    subtitle_style: SubtitleStyle


def validate_writer_script(data: Any) -> List[WriterScriptEntry]:
    """
    Validates that the input data conforms to the WriterScriptEntry schema.
    """
    if not isinstance(data, list):
        raise ValueError("Writer script must be a JSON array of objects")

    validated: List[WriterScriptEntry] = []
    for idx, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"Entry {idx} must be an object")

        if "character" not in entry or "text" not in entry:
            raise ValueError(f"Entry {idx} must contain at least 'character' and 'text' fields")

        char = entry["character"]
        text = entry["text"]

        if not isinstance(char, str) or not char.strip():
            raise ValueError(f"Entry {idx} 'character' must be a non-empty string")

        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Entry {idx} 'text' must be a non-empty string")

        validated.append({"character": char, "text": text})

    return validated


def validate_director_script(data: Any) -> List[DirectorScriptEntry]:
    """
    Validates that the input data conforms to the DirectorScriptEntry schema.
    """
    if not isinstance(data, list):
        raise ValueError("Director script must be a JSON array of objects")

    valid_emotions = VALID_EMOTIONS
    valid_motions = VALID_MOTIONS
    required_keys = {"character", "text", "emotion", "motion", "bgm", "sfx", "image"}
    optional_keys = {"character_position", "subtitle_position", "subtitle_style"}
    expected_keys = required_keys | optional_keys
    valid_character_positions = VALID_CHARACTER_POSITIONS
    valid_subtitle_positions = VALID_SUBTITLE_POSITIONS
    valid_subtitle_styles = VALID_SUBTITLE_STYLES

    validated: List[DirectorScriptEntry] = []
    for idx, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"Entry {idx} must be an object")

        if not required_keys.issubset(entry.keys()) or not set(entry.keys()).issubset(
            expected_keys
        ):
            raise ValueError(
                f"Entry {idx} must contain exactly the supported Director fields {expected_keys}"
            )

        char = entry["character"]
        text = entry["text"]
        emotion = entry["emotion"]
        motion = entry["motion"]
        bgm = entry["bgm"]
        sfx = entry["sfx"]
        image = entry["image"]
        character_position = entry.get("character_position", "center")
        subtitle_position = entry.get("subtitle_position", "bottom_center")
        subtitle_style = entry.get("subtitle_style", "outlined")

        if not isinstance(char, str) or not char.strip():
            raise ValueError(f"Entry {idx} 'character' must be a non-empty string")

        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Entry {idx} 'text' must be a non-empty string")

        if not isinstance(emotion, str) or emotion not in valid_emotions:
            raise ValueError(f"Entry {idx} 'emotion' must be one of {valid_emotions}")

        if not isinstance(motion, str) or motion not in valid_motions:
            raise ValueError(f"Entry {idx} 'motion' must be one of {valid_motions}")

        if bgm is not None and (not isinstance(bgm, str) or not bgm.strip()):
            raise ValueError(f"Entry {idx} 'bgm' must be null or a non-empty string")

        if sfx is not None and (not isinstance(sfx, str) or not sfx.strip()):
            raise ValueError(f"Entry {idx} 'sfx' must be null or a non-empty string")

        if image is not None and (not isinstance(image, str) or not image.strip()):
            raise ValueError(f"Entry {idx} 'image' must be null or a non-empty string")

        if (
            not isinstance(character_position, str)
            or character_position not in valid_character_positions
        ):
            raise ValueError(
                f"Entry {idx} 'character_position' must be one of {valid_character_positions}"
            )

        if (
            not isinstance(subtitle_position, str)
            or subtitle_position not in valid_subtitle_positions
        ):
            raise ValueError(
                f"Entry {idx} 'subtitle_position' must be one of {valid_subtitle_positions}"
            )

        if not isinstance(subtitle_style, str) or subtitle_style not in valid_subtitle_styles:
            raise ValueError(f"Entry {idx} 'subtitle_style' must be one of {valid_subtitle_styles}")

        validated.append(
            {
                "character": char,
                "text": text,
                "emotion": emotion,  # type: ignore
                "motion": motion,  # type: ignore
                "bgm": bgm,
                "sfx": sfx,
                "image": image,
                "character_position": character_position,  # type: ignore
                "subtitle_position": subtitle_position,  # type: ignore
                "subtitle_style": subtitle_style,  # type: ignore
            }
        )

    return validated


def validate_production_script(data: Any) -> List[Dict[str, Any]]:
    """
    Validates production project scripts (such as projects/*/script.json) which may contain
    directive entries ({"type": "bgm" | "thumbnail", ...}), optional "bg" keys, and partial
    director staging fields, populating defaults for omitted staging fields on dialogue entries.
    """
    if not isinstance(data, list):
        raise ValueError("Production script must be a JSON array of objects")

    validated: List[Dict[str, Any]] = []
    for idx, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"Entry {idx} must be an object")

        if "type" in entry and "character" not in entry:
            directive_type = entry["type"]
            if not isinstance(directive_type, str) or not directive_type.strip():
                raise ValueError(f"Entry {idx} directive 'type' must be a non-empty string")
            validated.append(dict(entry))
            continue

        if "character" not in entry or "text" not in entry:
            raise ValueError(
                f"Entry {idx} must contain 'character' and 'text' fields (or a directive 'type')"
            )

        char = entry["character"]
        text = entry["text"]
        if not isinstance(char, str) or not char.strip():
            raise ValueError(f"Entry {idx} 'character' must be a non-empty string")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Entry {idx} 'text' must be a non-empty string")
        if len(text) > 45:
            logger.warning(
                f"Entry {idx} ({char}): text length {len(text)} exceeds recommended ceiling (<= 40 chars). "
                "Consider splitting into shorter cuts to prevent speech bubble crowding and reading fatigue."
            )

        emotion = entry.get("emotion", "neutral")
        motion = entry.get("motion", "none")
        bgm = entry.get("bgm", None)
        sfx = entry.get("sfx", None)
        image = entry.get("image", None)
        bg = entry.get("bg", None)
        character_position = entry.get("character_position", "center")
        subtitle_position = entry.get("subtitle_position", "bottom_center")
        subtitle_style = entry.get("subtitle_style", "outlined")

        if not isinstance(emotion, str) or emotion not in VALID_EMOTIONS:
            raise ValueError(f"Entry {idx} 'emotion' must be one of {VALID_EMOTIONS}")
        if not isinstance(motion, str) or motion not in VALID_MOTIONS:
            raise ValueError(f"Entry {idx} 'motion' must be one of {VALID_MOTIONS}")
        if bgm is not None and (not isinstance(bgm, str) or not bgm.strip()):
            raise ValueError(f"Entry {idx} 'bgm' must be null or a non-empty string")
        if sfx is not None and (not isinstance(sfx, str) or not sfx.strip()):
            raise ValueError(f"Entry {idx} 'sfx' must be null or a non-empty string")
        if image is not None and (not isinstance(image, str) or not image.strip()):
            raise ValueError(f"Entry {idx} 'image' must be null or a non-empty string")
        if bg is not None and (not isinstance(bg, str) or not bg.strip()):
            raise ValueError(f"Entry {idx} 'bg' must be null or a non-empty string")
        if (
            not isinstance(character_position, str)
            or character_position not in VALID_CHARACTER_POSITIONS
        ):
            raise ValueError(
                f"Entry {idx} 'character_position' must be one of {VALID_CHARACTER_POSITIONS}"
            )
        if (
            not isinstance(subtitle_position, str)
            or subtitle_position not in VALID_SUBTITLE_POSITIONS
        ):
            raise ValueError(
                f"Entry {idx} 'subtitle_position' must be one of {VALID_SUBTITLE_POSITIONS}"
            )
        if not isinstance(subtitle_style, str) or subtitle_style not in VALID_SUBTITLE_STYLES:
            raise ValueError(f"Entry {idx} 'subtitle_style' must be one of {VALID_SUBTITLE_STYLES}")

        normalized: Dict[str, Any] = dict(entry)
        normalized.update(
            {
                "character": char,
                "text": text,
                "emotion": emotion,
                "motion": motion,
                "bgm": bgm,
                "sfx": sfx,
                "image": image,
                "character_position": character_position,
                "subtitle_position": subtitle_position,
                "subtitle_style": subtitle_style,
            }
        )
        validated.append(normalized)

    return validated


def validate_director_against_writer(
    director_script: List[DirectorScriptEntry], writer_script: List[WriterScriptEntry]
) -> None:
    """
    Ensures the director script preserves the exact factual text and character sequence from the writer script.
    """
    if len(director_script) != len(writer_script):
        raise ValueError(
            f"Script length mismatch: Director has {len(director_script)} entries, Writer has {len(writer_script)}"
        )

    for idx, (dir_entry, writ_entry) in enumerate(zip(director_script, writer_script)):
        if dir_entry["character"] != writ_entry["character"]:
            raise ValueError(
                f"Character mismatch at entry {idx}: Director changed '{writ_entry['character']}' to '{dir_entry['character']}'"
            )

        if dir_entry["text"] != writ_entry["text"]:
            raise ValueError(
                f"Text mismatch at entry {idx}: Director changed '{writ_entry['text']}' to '{dir_entry['text']}'"
            )


def split_long_text(text: str, max_chars: int = 42) -> List[str]:
    """
    Splits long compound dialogue text into smaller, well-paced cuts (<= max_chars).
    Splits along sentence boundaries (。！？!?) first, then comma/clause boundaries if needed.
    """
    if len(text) <= max_chars:
        return [text]

    parts = [p.strip() for p in re.split(r"(?<=[。！？!?])\s*", text) if p.strip()]
    if len(parts) > 1:
        result: List[str] = []
        cur = ""
        for p in parts:
            if not cur:
                cur = p
            elif len(cur) + len(p) <= max_chars:
                cur += p
            else:
                result.append(cur)
                cur = p
        if cur:
            result.append(cur)
        return result

    comma_parts = [p.strip() for p in re.split(r"(?<=[、,])\s*", text) if p.strip()]
    if len(comma_parts) > 1:
        result = []
        cur = ""
        for p in comma_parts:
            if not cur:
                cur = p
            elif len(cur) + len(p) <= max_chars:
                cur += p
            else:
                result.append(cur)
                cur = p
        if cur:
            result.append(cur)
        return result

    return [text]


def split_long_script_entries(
    script: List[Dict[str, Any]], max_chars: int = 42
) -> List[Dict[str, Any]]:
    """
    Processes a script array and splits dialogue entries where text exceeds max_chars
    into multiple sequential cuts preserving speaker, emotion, and layout.
    B-roll images and SFX remain attached to their respective first cut.
    """
    new_script: List[Dict[str, Any]] = []
    for entry in script:
        if "text" not in entry or len(entry.get("text", "")) <= max_chars:
            new_script.append(dict(entry))
            continue

        text_parts = split_long_text(entry["text"], max_chars=max_chars)
        if len(text_parts) <= 1:
            new_script.append(dict(entry))
            continue

        for i, part in enumerate(text_parts):
            sub_entry = dict(entry)
            sub_entry["text"] = part
            if i > 0:
                sub_entry.pop("image", None)
                sub_entry.pop("sfx", None)
                if sub_entry.get("motion") == "jump":
                    sub_entry["motion"] = "none"
            new_script.append(sub_entry)

    return new_script
