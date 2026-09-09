"""
Native script generation module for veraxi-ymmp.

Provides utilities to convert a script JSON (list of dialogue entries) into
YMM4's native script-import text format.

Limitation:
YMM4's native script text format does not support emotion or expression tags per line.
If an "emotion" key is present in a script entry, it is silently ignored by this module.
A future separate stage should be used to apply emotions directly against the resulting .ymmp.
"""

import re
from typing import Any


def json_to_native_script(script: list[dict[str, Any]]) -> str:
    """
    Convert a script JSON array into YMM4's native script text format.

    The format outputs:
    CharacterName「DialogueText」

    Rules applied:
    - One line per entry.
    - If the dialogue text contains a literal 「 or 」 character, it is escaped as \「 / \」.
    - If the dialogue text contains literal newlines, they are preserved within the text.
    - Empty characters or empty text raise a ValueError.
    - "emotion" keys are silently ignored.
    - Entries starting with '#' are emitted as normal dialogue, but may be parsed as comments
      by YMM4. Manual verification is required.

    Args:
        script: A list of dictionaries, each containing 'character' and 'text'.

    Returns:
        The formatted script as a single string.

    Raises:
        ValueError: If script is not a list, if an entry is missing 'character' or 'text',
                    or if either field is an empty string.
    """
    if not isinstance(script, list):
        raise ValueError("Script must be a list of dictionaries")

    output_lines = []

    for idx, entry in enumerate(script):
        if not isinstance(entry, dict):
            raise ValueError(f"Script entry at index {idx} is not a dictionary")

        if "character" not in entry or "text" not in entry:
            raise ValueError(f"Script entry at index {idx} must contain 'character' and 'text'")

        character = entry["character"]
        text = entry["text"]

        if not character or str(character).strip() == "":
            raise ValueError(f"Script entry at index {idx} has an empty 'character' value")
        if not text or str(text).strip() == "":
            raise ValueError(f"Script entry at index {idx} has an empty 'text' value")

        character = str(character)
        text = str(text)

        # Escape 「 and 」 if not already escaped
        # Use regex negative lookbehind to check if not preceded by a backslash
        text = re.sub(r'(?<!\\)「', r'\「', text)
        text = re.sub(r'(?<!\\)」', r'\」', text)

        output_lines.append(f"{character}「{text}」")

    return "\n".join(output_lines)
