from typing import Dict, Any
from .constants import DEFAULT_SPEAKER_MAP

def get_director_script_schema() -> Dict[str, Any]:
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "character": {
                    "type": "string",
                    "description": "The character speaking.",
                    "enum": list(DEFAULT_SPEAKER_MAP.keys())
                },
                "text": {
                    "type": "string",
                    "description": "The dialogue text. Limit to 35-40 characters per cut."
                },
                "emotion": {
                    "type": "string",
                    "enum": [
                        "normal", "neutral", "happy", "angry", "sad", "surprised",
                        "confused", "scared", "excited", "disgusted", "smug", "crying", "blushing"
                    ],
                    "default": "neutral"
                },
                "motion": {
                    "type": "string",
                    "enum": ["none", "jump", "nod"],
                    "default": "none"
                },
                "bgm": {
                    "type": ["string", "null"],
                    "default": None
                },
                "sfx": {
                    "type": ["string", "null"],
                    "default": None
                },
                "image": {
                    "type": ["string", "null"],
                    "default": None
                },
                "character_position": {
                    "type": "string",
                    "enum": ["left", "center", "right"],
                    "default": "center"
                },
                "subtitle_position": {
                    "type": "string",
                    "enum": ["top_center", "center", "bottom_center"],
                    "default": "bottom_center"
                },
                "subtitle_style": {
                    "type": "string",
                    "enum": ["default", "outlined"],
                    "default": "outlined"
                }
            },
            "required": ["character", "text", "emotion", "motion", "bgm", "sfx", "image"]
        }
    }
