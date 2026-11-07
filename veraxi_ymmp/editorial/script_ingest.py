"""Parser and compiler converting raw Markdown dialogue into validated DirectorScriptEntry JSON."""
from __future__ import annotations

import re
from typing import List, Dict, Any, Optional
from veraxi_ymmp.core.script import (
    DirectorScriptEntry,
    validate_director_script,
    CharacterPosition,
    Emotion,
    Motion,
)

SPEAKER_ALIASES: Dict[str, str] = {
    # Zundamon aliases
    "zundamon": "ずんだもん",
    "ずんだもん": "ずんだもん",
    "zunda": "ずんだもん",
    # Metan aliases
    "metan": "四国めたん",
    "四国めたん": "四国めたん",
    "めたん": "四国めたん",
    # Tsumugi aliases
    "tsumugi": "春日部つむぎ",
    "春日部つむぎ": "春日部つむぎ",
    "つむぎ": "春日部つむぎ",
}

DEFAULT_POSITIONS: Dict[str, CharacterPosition] = {
    "四国めたん": "left",
    "ずんだもん": "right",
    "春日部つむぎ": "right",
}

LINE_SPLIT_PUNCTUATION = re.compile(r"([。！？\?!])")


def normalize_speaker(raw_name: str) -> Optional[str]:
    """Normalize raw speaker name to official Japanese character name."""
    cleaned = raw_name.strip().strip("[]*:").lower()
    return SPEAKER_ALIASES.get(cleaned)


def detect_emotion(text: str) -> Emotion:
    """Heuristic emotion detector from sentence endings and punctuation."""
    if "！？" in text or "?!" in text or "ええっ" in text or "はぁ" in text:
        return "surprised"
    if "のだー" in text or "やった" in text or "すごい" in text:
        return "excited"
    if "おめでたい" in text or "愚か" in text or "ふふ" in text:
        return "smug"
    if "まずい" in text or "どうしよう" in text:
        return "scared"
    if "許せない" in text or "怒" in text:
        return "angry"
    return "normal"


def split_text_to_char_limit(text: str, max_chars: int = 38) -> List[str]:
    """Split text into cuts <= max_chars, breaking naturally on punctuation."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    # Split preserving punctuation delimiters
    parts = LINE_SPLIT_PUNCTUATION.split(text)
    reconstructed: List[str] = []
    current = ""

    for part in parts:
        if not part:
            continue
        if LINE_SPLIT_PUNCTUATION.match(part):
            current += part
            reconstructed.append(current)
            current = ""
        else:
            if current:
                reconstructed.append(current)
            current = part
    if current:
        reconstructed.append(current)

    # Combine parts into chunks of <= max_chars
    chunks: List[str] = []
    accum = ""
    for r in reconstructed:
        if len(accum) + len(r) <= max_chars:
            accum += r
        else:
            if accum:
                chunks.append(accum)
            accum = r
    if accum:
        chunks.append(accum)

    # Fallback hard cut if any single chunk exceeds max_chars
    final_chunks: List[str] = []
    for chunk in chunks:
        while len(chunk) > max_chars:
            final_chunks.append(chunk[:max_chars])
            chunk = chunk[max_chars:]
        if chunk:
            final_chunks.append(chunk)

    return final_chunks


def parse_markdown_dialogue(markdown_content: str) -> List[DirectorScriptEntry]:
    """Parse markdown dialogue lines into validated DirectorScriptEntry list."""
    pattern = re.compile(
        r"^(?:\d+[\.\)]\s*)?(?:[-*]\s*)?\[?(?:\*\*)?([a-zA-Z\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]+)(?:\*\*)?\]?\s*[:：]\s*(.+)$"
    )

    raw_cuts: List[Dict[str, Any]] = []

    for line in markdown_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("|") or line.startswith("```"):
            continue

        match = pattern.match(line)
        if not match:
            continue

        speaker_raw, text_raw = match.group(1), match.group(2)
        speaker = normalize_speaker(speaker_raw)
        if not speaker:
            continue

        # Split text if it exceeds 38 chars
        sub_texts = split_text_to_char_limit(text_raw, max_chars=38)

        for sub_text in sub_texts:
            cut_idx = len(raw_cuts)
            emotion = detect_emotion(sub_text)
            motion: Motion = "nod" if emotion in {"excited", "surprised"} else "none"

            entry: Dict[str, Any] = {
                "character": speaker,
                "text": sub_text,
                "emotion": emotion,
                "motion": motion,
                "bgm": None,
                "sfx": None,
                "image": None if cut_idx < 3 else None,  # Cold open hook protection
                "character_position": DEFAULT_POSITIONS.get(speaker, "left"),
                "subtitle_position": "bottom_center",
                "subtitle_style": "outlined",
            }
            raw_cuts.append(entry)

    # Validate output schema against domain invariants
    validated = validate_director_script(raw_cuts)
    return validated
