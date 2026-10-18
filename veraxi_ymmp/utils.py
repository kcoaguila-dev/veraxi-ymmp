"""
Utility functions for veraxi-ymmp.
"""

import re
from pathlib import Path
from typing import Union


def ensure_path(path: Union[str, Path]) -> Path:
    """Convert string to Path if necessary."""
    return Path(path) if isinstance(path, str) else path


def resolve_path(path: Union[str, Path]) -> Path:
    """Convert to Path and resolve to absolute path."""
    return ensure_path(path).resolve()


def normalize_japanese_typography(text: str) -> str:
    """
    Normalizes Japanese script typography according to standard digital editorial rules:
    - Normalizes awkward counter idioms (e.g. 3条件/３条件 -> 3つの条件)
    - Converts full-width alphanumeric characters (０-９, Ａ-Ｚ, ａ-ｚ) to standard half-width ASCII
    - Normalizes full-width percent sign (％ -> %)
    - Removes artificial whitespace between Japanese kana/kanji and ASCII words/numbers
    """
    if not text:
        return ""

    # Standardize phrasing to natural Japanese idiom
    t = text.replace("3条件", "3つの条件").replace("３条件", "3つの条件")

    # Full-width alphanumeric & symbols to standard half-width ASCII
    def _to_half(m: re.Match[str]) -> str:
        c = m.group(0)
        code = ord(c)
        if 0xFF10 <= code <= 0xFF19:  # 0-9
            return chr(code - 0xFF10 + 0x30)
        elif 0xFF21 <= code <= 0xFF3A:  # A-Z
            return chr(code - 0xFF21 + 0x41)
        elif 0xFF41 <= code <= 0xFF5A:  # a-z
            return chr(code - 0xFF41 + 0x61)
        elif code == 0xFF05:  # ％
            return "%"
        return c

    t = re.sub(r"[０-９Ａ-Ｚａ-ｚ％]", _to_half, t)

    # Clean up artificial whitespace between Japanese characters and numbers/Latin words
    t = re.sub(r"([ぁ-んァ-ヶ一-龥])\s+([A-Za-z0-9])", r"\1\2", t)
    t = re.sub(r"([A-Za-z0-9])\s+([ぁ-んァ-ヶ一-龥])", r"\1\2", t)
    return t
