"""
YMM4 project compiler for generating dialogue timelines.

This module provides the main compilation logic for generating .ymmp files
from scripts and templates. It handles:
- Loading and processing templates
- Generating voice items with proper timing
- Integrating with VOICEVOX for TTS
- Managing tachie (character) items
"""

from __future__ import annotations

import copy
import json
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from .template import load_template, extract_character_templates
from .hatsuon import Hatsuon, HatsuonError
from .voicevox import VoicevoxClient, VoicevoxError

if TYPE_CHECKING:
    from pathlib import Path


class CompilerError(Exception):
    """Exception raised when compilation fails."""
    pass


# Type alias for script entries
ScriptEntry = Dict[str, str]


class YMMPCompiler:
    """
    Compiler for generating YMM4 .ymmp dialogue timelines.
    
    Takes a template file and a script (list of character/text pairs) and generates
    a complete .ymmp file with properly timed voice items and tachie items.
    """
    
    def __init__(
        self,
        template_path: Union[str, "Path"],
        voicevox_client: Optional[VoicevoxClient] = None,
        speaker_map: Optional[Dict[str, int]] = None,
        default_speaker_id: int = 3
    ):
        self.template_path = str(template_path)
        self.template_data = load_template(self.template_path)
        self.character_templates = extract_character_templates(self.template_data)
        self.hatsuon = Hatsuon()
        self.voicevox_client = voicevox_client
        self.speaker_map = speaker_map or {}
        self.default_speaker_id = default_speaker_id

    def compile(
        self,
        script: List[ScriptEntry],
        output_path: Union[str, "Path"],
        use_bom: bool = False
    ) -> None:
        output_data = copy.deepcopy(self.template_data)
        items: List[Dict[str, Any]] = []

        if self.voicevox_client and not self.voicevox_client.is_available():
            raise RuntimeError(
                f"VOICEVOX server not reachable at {self.voicevox_client.base_url} "
                "- is it running?"
            )

        current_frame = 0
        output_dir = os.path.dirname(os.path.abspath(str(output_path)))
        audio_dir = os.path.join(output_dir, "audio")

        fps = self._get_fps()

        for idx, line in enumerate(script):
            char_name = line.get("character")
            text = line.get("text")
            
            if not char_name or not text:
                raise ValueError(f"Invalid script entry at index {idx}: missing character or text")

            if char_name not in self.character_templates:
                raise ValueError(f"Missing template for character: {char_name}")

            template_item = self.character_templates[char_name]["voice"]
            if template_item is None:
                raise ValueError(f"No voice template found for character: {char_name}")

            new_item = copy.deepcopy(template_item)

            new_item["Serif"] = text
            new_item["Hatsuon"] = self._convert_hatsuon(text)
            new_item["Frame"] = current_frame

            if self.voicevox_client:
                length = self._synthesize_audio(idx, char_name, text, audio_dir)
            else:
                length = self._calculate_placeholder_length(text)

            new_item["Length"] = length
            new_item["VoiceCache"] = ""

            items.append(new_item)
            current_frame += length

        total_length = current_frame
        used_characters = set(line["character"] for line in script)
        items.extend(self._add_tachie_items(used_characters, total_length))

        output_data["Timeline"]["Items"] = items
        output_data["Timeline"]["Length"] = total_length

        self._write_output(output_data, output_path, use_bom)

    def _get_fps(self) -> int:
        return self.template_data.get("Timeline", {}).get("VideoInfo", {}).get("FPS", 60)

    def _convert_hatsuon(self, text: str) -> str:
        try:
            return self.hatsuon.convert(text)
        except HatsuonError as e:
            import warnings
            warnings.warn(f"Hatsuon conversion failed: {e}. Using original text.")
            return text

    def _synthesize_audio(self, idx: int, char_name: str, text: str, audio_dir: str) -> int:
        speaker_id = self.speaker_map.get(char_name, self.default_speaker_id)
        
        try:
            wav_bytes, duration = self.voicevox_client.synthesize(text, speaker_id)
        except VoicevoxError as e:
            raise RuntimeError(f"Synthesis failed for '{char_name}' on line '{text}': {e}")

        os.makedirs(audio_dir, exist_ok=True)
        audio_filename = f"{idx:03d}_{char_name}.wav"
        audio_path = os.path.join(audio_dir, audio_filename)

        with open(audio_path, "wb") as f:
            f.write(wav_bytes)

        return round(duration * self._get_fps())

    def _calculate_placeholder_length(self, text: str) -> int:
        frames_per_char = 5
        min_length = 30
        return max(min_length, len(text) * frames_per_char)

    def _add_tachie_items(self, used_characters: set[str], total_length: int) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        
        for char_name, templates in self.character_templates.items():
            if char_name in used_characters and templates["tachie"] is not None:
                tachie_item = copy.deepcopy(templates["tachie"])
                tachie_item["Frame"] = 0
                tachie_item["Length"] = total_length
                result.append(tachie_item)
        
        return result

    def _write_output(self, output_data: Dict[str, Any], output_path: Union[str, "Path"], use_bom: bool) -> None:
        mode = 'w'
        encoding = 'utf-8-sig' if use_bom else 'utf-8'
        with open(str(output_path), mode, encoding=encoding) as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
