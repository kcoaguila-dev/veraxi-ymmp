"""
Models and validation logic for the two-stage script pipeline.
"""

from typing import Any, List, Literal, Optional, TypedDict

Emotion = Literal["neutral", "happy", "angry", "sad", "surprised", "confused", "scared", "excited", "disgusted", "smug", "crying", "blushing"]
Motion = Literal["none", "jump", "shake", "nod"]
CharacterPosition = Literal["left", "center", "right"]
SubtitlePosition = Literal["top_center", "center", "bottom_center"]
SubtitleStyle = Literal["default", "outlined"]

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

    valid_emotions = {"neutral", "happy", "angry", "sad", "surprised", "confused", "scared", "excited", "disgusted", "smug", "crying", "blushing"}
    valid_motions = {"none", "jump", "shake", "nod"}
    required_keys = {"character", "text", "emotion", "motion", "bgm", "sfx", "image"}
    optional_keys = {"character_position", "subtitle_position", "subtitle_style"}
    expected_keys = required_keys | optional_keys
    valid_character_positions = {"left", "center", "right"}
    valid_subtitle_positions = {"top_center", "center", "bottom_center"}
    valid_subtitle_styles = {"default", "outlined"}

    validated: List[DirectorScriptEntry] = []
    for idx, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"Entry {idx} must be an object")

        if not required_keys.issubset(entry.keys()) or not set(entry.keys()).issubset(expected_keys):
            raise ValueError(f"Entry {idx} must contain exactly the supported Director fields {expected_keys}")

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

        if not isinstance(character_position, str) or character_position not in valid_character_positions:
            raise ValueError(f"Entry {idx} 'character_position' must be one of {valid_character_positions}")

        if not isinstance(subtitle_position, str) or subtitle_position not in valid_subtitle_positions:
            raise ValueError(f"Entry {idx} 'subtitle_position' must be one of {valid_subtitle_positions}")

        if not isinstance(subtitle_style, str) or subtitle_style not in valid_subtitle_styles:
            raise ValueError(f"Entry {idx} 'subtitle_style' must be one of {valid_subtitle_styles}")

        validated.append({
            "character": char,
            "text": text,
            "emotion": emotion,  # type: ignore
            "motion": motion,    # type: ignore
            "bgm": bgm,
            "sfx": sfx,
            "image": image,
            "character_position": character_position,  # type: ignore
            "subtitle_position": subtitle_position,  # type: ignore
            "subtitle_style": subtitle_style  # type: ignore
        })

    return validated


def validate_director_against_writer(director_script: List[DirectorScriptEntry], writer_script: List[WriterScriptEntry]) -> None:
    """
    Ensures the director script preserves the exact factual text and character sequence from the writer script.
    """
    if len(director_script) != len(writer_script):
        raise ValueError(f"Script length mismatch: Director has {len(director_script)} entries, Writer has {len(writer_script)}")

    for idx, (dir_entry, writ_entry) in enumerate(zip(director_script, writer_script)):
        if dir_entry["character"] != writ_entry["character"]:
            raise ValueError(f"Character mismatch at entry {idx}: Director changed '{writ_entry['character']}' to '{dir_entry['character']}'")

        if dir_entry["text"] != writ_entry["text"]:
            raise ValueError(f"Text mismatch at entry {idx}: Director changed '{writ_entry['text']}' to '{dir_entry['text']}'")
