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
    with open(filepath, 'r', encoding='utf-8') as f:
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

    items = template_data.get("Timeline", {}).get("Items", [])

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
