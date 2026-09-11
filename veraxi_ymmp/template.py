"""
Template loading and processing for YMM4 project files.

This module handles loading .ymmp template files and extracting character-specific
templates for VoiceItems and TachieItems.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, TypedDict


class CharacterTemplates(TypedDict):
    """Type definition for character template structure."""
    voice: Optional[Dict[str, Any]]
    tachie: Optional[Dict[str, Any]]


def get_timeline(template_data: Dict[str, Any]) -> Dict[str, Any]:
    """Return the first timeline for both supported YMM4 project layouts."""
    if isinstance(template_data.get("Timeline"), dict):
        return template_data["Timeline"]
    timelines = template_data.get("Timelines")
    if isinstance(timelines, list) and timelines and isinstance(timelines[0], dict):
        return timelines[0]
    raise ValueError("Template does not contain a supported Timeline or Timelines section")


def load_template(filepath: str) -> Dict[str, Any]:
    """
    Load a YMM4 template file.

    Args:
        filepath: Path to the .ymmp template file.

    Returns:
        Parsed JSON data from the template file.

    Raises:
        FileNotFoundError: If the template file doesn't exist.
        json.JSONDecodeError: If the template file contains invalid JSON.
        UnicodeDecodeError: If the template file is not UTF-8 encoded.
    """
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        return json.load(f)


def extract_character_templates(template_data: Dict[str, Any]) -> Dict[str, CharacterTemplates]:
    """
    Extracts the first VoiceItem and TachieItem for each character from template.

    Scans the template for character definitions in both the Characters section
    and the Timeline Items section. Builds a mapping of character names to their
    voice and tachie templates.

    Args:
        template_data: Loaded template JSON data.

    Returns:
        Dictionary mapping character names to {"voice": item, "tachie": item}.
        Voice or tachie will be None if not found in the template.
    """
    character_templates: Dict[str, CharacterTemplates] = {}

    # First, check if there's a Characters section
    if "Characters" in template_data:
        for char in template_data["Characters"]:
            name = char.get("Name")
            if name:
                character_templates[name] = {"voice": None, "tachie": None}

    items = get_timeline(template_data).get("Items", [])

    for item in items:
        item_type = item.get("$type", "")
        char_name = item.get("CharacterName")

        if not char_name:
            continue

        if char_name not in character_templates:
            character_templates[char_name] = {"voice": None, "tachie": None}

        if "VoiceItem" in item_type and character_templates[char_name]["voice"] is None:
            character_templates[char_name]["voice"] = item

        if "TachieItem" in item_type and character_templates[char_name]["tachie"] is None:
            character_templates[char_name]["tachie"] = item

    return character_templates


def extract_text_template(template_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return the first standalone TextItem used for generated subtitles."""
    for item in get_timeline(template_data).get("Items", []):
        if "TextItem" in item.get("$type", ""):
            return item
    return None


def extract_face_templates(template_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Extract face templates mapping character -> emotion -> item.
    Supports explicit metadata via the Remark field (e.g. 'emotion:happy')
    and falls back to PSD layer heuristics.
    """
    result: Dict[str, Dict[str, Any]] = {}
    for item in get_timeline(template_data).get("Items", []):
        if "TachieFaceItem" not in item.get("$type", ""):
            continue
            
        char_name = item.get("CharacterName")
        if not char_name:
            continue
            
        if char_name not in result:
            result[char_name] = {}
            
        remark = item.get("Remark", "")
        if remark.startswith("emotion:"):
            emotion = remark.split(":", 1)[1].strip()
            result[char_name].setdefault(emotion, item)
            continue
            
        parameter = item.get("TachieFaceParameter") or {}
        paths = " ".join(parameter.get("EnableLayerPaths", []))
        if "涙" in paths or "青ざめ" in paths:
            result[char_name].setdefault("sad", item)
        elif "うわー" in paths or "上がり眉" in paths:
            result[char_name].setdefault("surprised", item)
        elif "むふ" in paths:
            result[char_name].setdefault("happy", item)
        elif "怒り眉2" in paths or "ジト目" in paths:
            result[char_name].setdefault("angry", item)
    return result
