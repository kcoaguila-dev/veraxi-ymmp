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
from dataclasses import dataclass
from .voicevox import VoicevoxClient, VoicevoxError, TTSBackend
from .config import CompilerConfig
from .constants import DEFAULT_FPS, FRAMES_PER_CHAR, MIN_LENGTH_FRAMES
from .utils import resolve_path, ensure_path
from .cache import TTSCache
from .validation import validate_output_path, sanitize_filename
from .logging import logger

if TYPE_CHECKING:
    from pathlib import Path

@dataclass
class CompilationResult:
    """Result of a compilation process."""
    output_path: "Path"
    item_count: int
    voice_item_count: int
    tachie_item_count: int
    total_frames: int
    total_duration_seconds: float
    audio_files: List["Path"]
    warnings: List[str]
    errors: List[str]


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
        default_speaker_id: int = 3,
        hatsuon_converter: Optional[Hatsuon] = None,
        tts_backend: Optional[TTSBackend] = None,
        config: Optional[CompilerConfig] = None
    ):
        self.template_path = ensure_path(template_path)
        self.template_data = load_template(str(self.template_path))
        self.character_templates = extract_character_templates(self.template_data)
        self.hatsuon = hatsuon_converter or Hatsuon()
        self.tts_backend = tts_backend or voicevox_client
        self.voicevox_client = voicevox_client  # for backward compatibility checks

        # Merge backwards-compatible config
        if config is None:
            self.config = CompilerConfig(
                default_speaker_id=default_speaker_id,
                speaker_map=speaker_map or {},
                use_tts=self.tts_backend is not None
            )
        else:
            self.config = config

        self.cache = TTSCache(enabled=self.config.use_cache, cache_dir=self.config.cache_dir)
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def compile(
        self,
        script: List[ScriptEntry],
        output_path: Union[str, "Path"],
        use_bom: bool = False
    ) -> CompilationResult:
        self.warnings = []
        self.errors = []

        output_data = copy.deepcopy(self.template_data)
        items: List[Dict[str, Any]] = []

        if self.config.use_tts and self.tts_backend and not self.tts_backend.is_available():
            raise RuntimeError("TTS Backend not reachable - is it running?")

        current_frame = 0

        resolved_output = resolve_path(output_path)
        # Ensure output is within the current working directory to prevent path traversal
        resolved_output = validate_output_path(resolved_output)

        output_dir = resolved_output.parent
        audio_dir = output_dir / "audio"

        fps = self._get_fps()
        audio_files: List["Path"] = []

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

            audio_path = None
            if self.config.use_tts and self.tts_backend:
                length, audio_path = self._synthesize_audio(idx, char_name, text, audio_dir)
                if audio_path:
                    audio_files.append(audio_path)
            else:
                length = self._calculate_placeholder_length(text)

            new_item["Length"] = length
            new_item["VoiceCache"] = ""

            items.append(new_item)
            current_frame += length

        total_length = current_frame
        used_characters = set(line["character"] for line in script if "character" in line)
        tachie_items = self._add_tachie_items(used_characters, total_length)
        items.extend(tachie_items)

        output_data["Timeline"]["Items"] = items
        output_data["Timeline"]["Length"] = total_length

        self._write_output(output_data, resolved_output, use_bom)

        return CompilationResult(
            output_path=resolved_output,
            item_count=len(items),
            voice_item_count=len(script),
            tachie_item_count=len(tachie_items),
            total_frames=total_length,
            total_duration_seconds=total_length / fps if fps else 0.0,
            audio_files=audio_files,
            warnings=self.warnings,
            errors=self.errors
        )

    def _get_fps(self) -> int:
        return self.template_data.get("Timeline", {}).get("VideoInfo", {}).get("FPS", self.config.fps)

    def _convert_hatsuon(self, text: str) -> str:
        try:
            return self.hatsuon.convert(text)
        except HatsuonError as e:
            msg = f"Hatsuon conversion failed: {e}. Using original text."
            logger.warning(msg)
            self.warnings.append(msg)
            return text

    def _synthesize_audio(self, idx: int, char_name: str, text: str, audio_dir: "Path") -> Tuple[int, Optional["Path"]]:
        speaker_id = self.config.speaker_map.get(char_name, self.config.default_speaker_id)
        
        cached = self.cache.get(text, speaker_id)
        if cached:
            wav_bytes, duration = cached
        else:
            try:
                wav_bytes, duration = self.tts_backend.synthesize(text, speaker_id)
                self.cache.set(text, speaker_id, wav_bytes, duration)
            except Exception as e:
                raise RuntimeError(f"Synthesis failed for '{char_name}' on line '{text}': {e}")

        audio_dir.mkdir(parents=True, exist_ok=True)
        safe_char_name = sanitize_filename(char_name)
        audio_filename = f"{idx:03d}_{safe_char_name}.wav"
        audio_path = audio_dir / audio_filename

        with open(audio_path, "wb") as f:
            f.write(wav_bytes)

        return round(duration * self._get_fps()), audio_path

    def _calculate_placeholder_length(self, text: str) -> int:
        return max(self.config.min_length_frames, len(text) * self.config.frames_per_char)

    def _add_tachie_items(self, used_characters: set[str], total_length: int) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        
        for char_name, templates in self.character_templates.items():
            if char_name in used_characters and templates["tachie"] is not None:
                tachie_item = copy.deepcopy(templates["tachie"])
                tachie_item["Frame"] = 0
                tachie_item["Length"] = total_length
                result.append(tachie_item)
        
        return result

    def _write_output(self, output_data: Dict[str, Any], output_path: "Path", use_bom: bool) -> None:
        mode = 'w'
        encoding = 'utf-8-sig' if use_bom else 'utf-8'
        with open(output_path, mode, encoding=encoding) as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
