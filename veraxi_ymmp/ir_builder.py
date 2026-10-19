"""
IR Builder for Veraxi YMMP.

Constructs TimelineIR intermediate representation from script entries, handling:
- Audio synthesis and caching (via VOICEVOX or TTS backend)
- Japanese typography normalization and phonetic pronunciation (Hatsuon) conversion
- BGM and SFX clip parsing and timing
- Dynamic fallback character template cloning
- Consecutive B-roll image clip coalescing
- Assembly of VoiceClip, CharacterClip, GlobalClip, and DynamicImage/AudioClip objects
"""

from __future__ import annotations

import copy
import json
import wave
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union, cast

from .cache import TTSCache
from .config import CompilerConfig
from .constants import KNOWN_CHARACTERS
from .hatsuon import Hatsuon, HatsuonError
from .ir import (
    CharacterClip,
    DynamicAudioClip,
    DynamicImageClip,
    GlobalClip,
    TimelineIR,
    VoiceClip,
)
from .logging import logger
from .phonetics import normalize_tts_text
from .script import DirectorScriptEntry, WriterScriptEntry
from .template import get_timeline
from .utils import normalize_japanese_typography
from .validation import sanitize_filename

try:
    from .ports import TTSBackend
except ImportError:
    from .voicevox import TTSBackend

if TYPE_CHECKING:
    pass

ScriptEntry = Union[WriterScriptEntry, DirectorScriptEntry, Dict[str, Any]]


def _create_dynamic_image_clip(
    image_path: Path,
    start_frame: int,
    length: int,
    is_background: bool = False,
) -> DynamicImageClip:
    """Create a DynamicImageClip with backward-compatible support for is_background."""
    try:
        return DynamicImageClip(
            image_path=image_path,
            start_frame=start_frame,
            length=length,
            is_background=is_background,
        )
    except TypeError:
        clip = DynamicImageClip(
            image_path=image_path,
            start_frame=start_frame,
            length=length,
        )
        setattr(clip, "is_background", is_background)
        return clip


class TimelineIRBuilder:
    """
    Builder responsible for translating raw script entries into a structured TimelineIR.
    """

    def __init__(
        self,
        template_data: Dict[str, Any],
        character_templates: Dict[str, Any],
        face_templates: Optional[Dict[str, Any]] = None,
        config: Optional[CompilerConfig] = None,
        tts_backend: Optional[TTSBackend] = None,
        cache: Optional[TTSCache] = None,
        hatsuon_converter: Optional[Hatsuon] = None,
        warnings: Optional[List[str]] = None,
        errors: Optional[List[str]] = None,
    ) -> None:
        self.template_data = template_data
        self.character_templates = dict(character_templates)
        self.face_templates = face_templates or {}
        self.config = config or CompilerConfig()
        self.tts_backend = tts_backend
        self.cache = cache or TTSCache(
            enabled=self.config.use_cache, cache_dir=self.config.cache_dir
        )
        self.hatsuon = hatsuon_converter or Hatsuon()
        self.warnings = warnings if warnings is not None else []
        self.errors = errors if errors is not None else []

    def get_fps(self) -> int:
        """Returns the frame rate from the template or configuration."""
        return cast(
            int, get_timeline(self.template_data).get("VideoInfo", {}).get("FPS", self.config.fps)
        )

    def convert_hatsuon(self, text: str) -> str:
        """Converts Japanese text into phonetic pronunciation string."""
        try:
            return self.hatsuon.convert(text)
        except HatsuonError as e:
            msg = f"Hatsuon conversion failed: {e}. Using original text."
            logger.warning(msg)
            self.warnings.append(msg)
            return text

    def calculate_placeholder_length(self, text: str) -> int:
        """Calculates placeholder duration in frames based on text length."""
        return max(self.config.min_length_frames, len(text) * self.config.frames_per_char)

    def synthesize_audio(
        self,
        idx: int,
        char_name: str,
        text: str,
        audio_dir: Path,
    ) -> Tuple[int, Optional[Path], Optional[Dict[str, Any]]]:
        """Synthesizes or retrieves cached audio for a script entry."""
        speaker_id = self.config.speaker_map.get(char_name, self.config.default_speaker_id)
        safe_char_name = sanitize_filename(char_name)
        out_path = audio_dir / f"{idx:03d}_{safe_char_name}.wav"
        query_path = audio_dir / f"{idx:03d}_{safe_char_name}.query.json"

        audio_query = None
        if query_path.exists():
            try:
                with open(query_path, "r", encoding="utf-8") as qf:
                    audio_query = json.load(qf)
            except Exception as exc:
                logger.debug(f"Failed to read cached audio query from {query_path}: {exc}")

        tts_text = normalize_tts_text(text)
        if out_path.exists():
            if (
                audio_query is None
                and self.tts_backend is not None
                and hasattr(self.tts_backend, "get_audio_query")
            ):
                try:
                    audio_query = self.tts_backend.get_audio_query(tts_text, speaker_id)
                    with open(query_path, "w", encoding="utf-8") as qf:
                        json.dump(audio_query, qf, ensure_ascii=False, indent=2)
                except Exception as exc:
                    logger.debug(f"Failed to fetch or write audio query for {out_path}: {exc}")
            try:
                with wave.open(str(out_path), "rb") as wav:
                    actual_duration = wav.getnframes() / float(wav.getframerate())
                    return int((actual_duration + 0.3) * self.get_fps()), out_path, audio_query
            except Exception as exc:
                logger.debug(f"Failed to read WAV duration from {out_path}: {exc}")
                return int(3.0 * self.get_fps()), out_path, audio_query

        cached = self.cache.get(tts_text, speaker_id)
        if cached:
            wav_bytes, duration = cached
            if (
                audio_query is None
                and self.tts_backend is not None
                and hasattr(self.tts_backend, "get_audio_query")
            ):
                try:
                    audio_query = self.tts_backend.get_audio_query(tts_text, speaker_id)
                except Exception as exc:
                    logger.debug(f"Failed to fetch audio query for cached entry {idx}: {exc}")
        else:
            if self.tts_backend is None:
                raise RuntimeError("TTS Backend not initialized")
            try:
                wav_bytes, duration, audio_query = self.tts_backend.synthesize(tts_text, speaker_id)
                self.cache.set(tts_text, speaker_id, wav_bytes, duration)
            except Exception as e:
                raise RuntimeError(f"Synthesis failed for '{char_name}' on line '{text}': {e}")

        audio_dir.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(wav_bytes)

        if audio_query:
            try:
                with open(query_path, "w", encoding="utf-8") as qf:
                    json.dump(audio_query, qf, ensure_ascii=False, indent=2)
            except Exception as exc:
                logger.debug(f"Failed to save audio query to {query_path}: {exc}")

        length = int(duration * self.get_fps())
        return length, out_path, audio_query

    def build_ir(
        self,
        script: List[ScriptEntry],
        audio_dir: Path,
    ) -> Tuple[TimelineIR, List[Path]]:
        """
        Builds the complete TimelineIR and returns the IR along with generated audio files.
        """
        fps = self.get_fps()
        current_frame = 0
        audio_files: List[Path] = []
        voice_clips: List[VoiceClip] = []
        character_positions: Dict[str, str] = {}
        dynamic_image_clips: List[DynamicImageClip] = []
        dynamic_audio_clips: List[DynamicAudioClip] = []
        active_bg: Optional[DynamicImageClip] = None

        for idx, line in enumerate(script):
            entry_dict: Dict[str, Any] = cast(Dict[str, Any], line)
            if entry_dict.get("type") == "bgm":
                raw_p = Path(str(entry_dict.get("path") or entry_dict.get("bgm", "")))
                if raw_p.exists():
                    path = raw_p.resolve()
                elif (Path.cwd() / raw_p).exists():
                    path = (Path.cwd() / raw_p).resolve()
                elif (audio_dir.parent / raw_p).exists():
                    path = (audio_dir.parent / raw_p).resolve()
                elif (audio_dir.parent.parent.parent / raw_p).exists():
                    path = (audio_dir.parent.parent.parent / raw_p).resolve()
                else:
                    path = raw_p.resolve()
                vol = float(entry_dict.get("volume", 15)) / 100.0
                dynamic_audio_clips.append(
                    DynamicAudioClip(audio_path=path, start_frame=0, length=-1, volume=vol)
                )
                continue

            char_name = str(entry_dict.get("character", ""))

            emo = entry_dict.get("emotion")
            if emo and emo != "neutral":
                char_faces = self.face_templates.get(char_name, {})
                if emo not in char_faces:
                    msg = (
                        f"Emotion '{emo}' for character '{char_name}' "
                        f"on entry {idx} is preserved but unsupported in generated YMMP."
                    )
                    self.warnings.append(msg)

            motion = entry_dict.get("motion")
            if motion and motion != "none":
                msg = f"Motion '{motion}' on entry {idx} is preserved but unsupported in generated YMMP."
                self.warnings.append(msg)

            text = str(entry_dict.get("text", ""))
            length = self.calculate_placeholder_length(text)

            bgm_name = entry_dict.get("bgm")
            if bgm_name and bgm_name != "none" and bgm_name != "":
                bgm_path = Path(str(bgm_name))
                if bgm_path.exists():
                    dynamic_audio_clips.append(
                        DynamicAudioClip(
                            audio_path=bgm_path,
                            start_frame=current_frame,
                            length=-1,  # Special marker for "entire video"
                        )
                    )
                else:
                    msg = f"BGM not found: {bgm_name}"
                    logger.warning(msg)
                    self.warnings.append(msg)

            sfx_val = entry_dict.get("sfx")
            if sfx_val is not None and sfx_val != "none" and sfx_val != "":
                sfx_path = Path(str(sfx_val))
                if sfx_path.exists():
                    dynamic_audio_clips.append(
                        DynamicAudioClip(
                            audio_path=sfx_path,
                            start_frame=current_frame,
                            length=30,  # default sfx length 30 frames
                        )
                    )
                else:
                    msg = f"SFX not found: {sfx_val}"
                    logger.warning(msg)
                    self.warnings.append(msg)

            text = normalize_japanese_typography(str(entry_dict.get("text", "")))
            if not char_name:
                continue

            character_positions.setdefault(
                char_name, str(entry_dict.get("character_position", "center"))
            )

            if char_name not in self.character_templates:
                # Dynamic fallback: clone the first available character template for known characters
                if char_name in self.config.speaker_map or char_name in KNOWN_CHARACTERS:
                    if not self.character_templates:
                        raise ValueError(
                            f"No character templates available to clone for: {char_name}"
                        )
                    base_char = list(self.character_templates.keys())[0]
                    self.character_templates[char_name] = copy.deepcopy(
                        self.character_templates[base_char]
                    )
                    for k, v in self.character_templates[char_name].items():
                        if v and isinstance(v, dict) and "CharacterName" in v:
                            v["CharacterName"] = char_name
                    logger.info(f"Dynamically cloned template for {char_name} from {base_char}")
                else:
                    raise ValueError(f"No character template found for character: {char_name}")

            if self.character_templates[char_name]["voice"] is None:
                raise ValueError(f"No voice template found for character: {char_name}")

            audio_path = None
            audio_query = None

            # Check for existing audio file in audio_dir to get accurate length and query
            audio_filename = f"{idx:03d}_{sanitize_filename(char_name)}.wav"
            query_filename = f"{idx:03d}_{sanitize_filename(char_name)}.query.json"
            candidate_audio = audio_dir / audio_filename
            candidate_query = audio_dir / query_filename

            if candidate_query.exists():
                try:
                    with open(candidate_query, "r", encoding="utf-8") as qf:
                        audio_query = json.load(qf)
                except Exception as e:
                    logger.warning(f"Failed to read query json for {audio_filename}: {e}")

            if candidate_audio.exists():
                audio_path = candidate_audio
                try:
                    with wave.open(str(audio_path), "rb") as wav:
                        frames = wav.getnframes()
                        rate = wav.getframerate()
                        actual_duration = frames / float(rate)
                        length = int((actual_duration + 0.3) * fps)  # Add 0.3s padding
                except Exception as e:
                    logger.warning(f"Could not read wav length for {audio_filename}: {e}")

            if self.config.use_tts and self.tts_backend:
                if not self.tts_backend.is_available():
                    raise RuntimeError("TTS Backend not reachable")
                if not audio_path or not audio_path.exists():
                    length, audio_path, audio_query = self.synthesize_audio(
                        idx, char_name, text, audio_dir
                    )
                elif audio_query is None:
                    try:
                        spk_id = self.config.speaker_map.get(
                            char_name, self.config.default_speaker_id
                        )
                        if hasattr(self.tts_backend, "get_audio_query"):
                            audio_query = self.tts_backend.get_audio_query(
                                normalize_tts_text(text), spk_id
                            )
                            query_path = (
                                audio_dir / f"{idx:03d}_{sanitize_filename(char_name)}.query.json"
                            )
                            with open(query_path, "w", encoding="utf-8") as qf:
                                json.dump(audio_query, qf, ensure_ascii=False, indent=2)
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch audio query for existing audio {audio_filename}: {e}"
                        )

            if audio_path and audio_path.exists():
                if audio_path not in audio_files:
                    audio_files.append(audio_path)
            else:
                length = self.calculate_placeholder_length(text)

            hatsuon = self.convert_hatsuon(text)

            voice_clips.append(
                VoiceClip(
                    start_frame=current_frame,
                    length=length,
                    character=char_name,
                    text=text,
                    emotion=str(entry_dict.get("emotion", "neutral")),
                    motion=str(entry_dict.get("motion", "none")),
                    audio_path=audio_path,
                    hatsuon=hatsuon,
                    subtitle_position=str(entry_dict.get("subtitle_position", "bottom_center")),
                    subtitle_style=str(entry_dict.get("subtitle_style", "outlined")),
                    audio_query=audio_query,
                )
            )

            def add_image_clip(img_name: str) -> None:
                img_path = Path("artifacts/.user_uploaded") / img_name
                if not img_path.exists():
                    img_path = Path(img_name)
                if not img_path.exists():
                    img_path = Path("artifacts") / img_name
                if not img_path.exists() and (audio_dir.parent / img_name).exists():
                    img_path = audio_dir.parent / img_name
                if not img_path.exists() and (audio_dir.parent / "broll" / img_name).exists():
                    img_path = audio_dir.parent / "broll" / img_name
                if img_path.exists():
                    resolved_img = img_path.resolve()
                    for prev_clip in reversed(dynamic_image_clips):
                        if prev_clip is active_bg or prev_clip.length == -1:
                            continue
                        if (
                            prev_clip.image_path.resolve() == resolved_img
                            and prev_clip.start_frame + prev_clip.length == current_frame
                        ):
                            prev_clip.length += length
                            return
                        if prev_clip.start_frame + prev_clip.length <= current_frame:
                            break
                    dynamic_image_clips.append(
                        _create_dynamic_image_clip(
                            image_path=img_path,
                            start_frame=current_frame,
                            length=length,
                            is_background=False,
                        )
                    )
                else:
                    msg = f"Image not found: {img_name}"
                    logger.warning(msg)
                    self.warnings.append(msg)

            image_name = entry_dict.get("image")
            if image_name:
                add_image_clip(str(image_name))

            bg_name = entry_dict.get("bg")
            if bg_name:
                bg_name_str = str(bg_name)
                if active_bg:
                    active_bg.length = current_frame - active_bg.start_frame

                img_path = Path("artifacts/.user_uploaded") / bg_name_str
                if not img_path.exists():
                    img_path = Path(bg_name_str)
                if not img_path.exists():
                    img_path = Path("artifacts") / bg_name_str
                if not img_path.exists() and (audio_dir.parent / bg_name_str).exists():
                    img_path = audio_dir.parent / bg_name_str
                if not img_path.exists() and (audio_dir.parent / "broll" / bg_name_str).exists():
                    img_path = audio_dir.parent / "broll" / bg_name_str

                if img_path.exists():
                    active_bg = _create_dynamic_image_clip(
                        image_path=img_path,
                        start_frame=current_frame,
                        length=-1,
                        is_background=True,
                    )
                    dynamic_image_clips.append(active_bg)
                else:
                    active_bg = None
                    msg = f"BG Image not found: {bg_name_str}"
                    logger.warning(msg)
                    self.warnings.append(msg)

            current_frame += length

        total_frames = current_frame
        if active_bg and active_bg.length <= 0:
            active_bg.length = total_frames - active_bg.start_frame

        used_characters = set(c.character for c in voice_clips)
        character_clips = []
        for char_name in used_characters:
            character_clips.append(
                CharacterClip(
                    start_frame=0,
                    length=total_frames,
                    character=char_name,
                    position=character_positions.get(char_name, "center"),
                )
            )

        global_clips = []
        for template_item in get_timeline(self.template_data).get("Items", []):
            type_str = template_item.get("$type", "")
            if (
                "VoiceItem" not in type_str
                and "Tachie" not in type_str
                and "TextItem" not in type_str
                and "ImageItem" not in type_str
                and "AudioItem" not in type_str
            ):
                global_clips.append(
                    GlobalClip(
                        start_frame=0,
                        length=total_frames,
                        template_item=template_item,
                    )
                )

        return (
            TimelineIR(
                fps=fps,
                total_frames=total_frames,
                voice_clips=voice_clips,
                character_clips=character_clips,
                global_clips=global_clips,
                dynamic_image_clips=dynamic_image_clips,
                dynamic_audio_clips=dynamic_audio_clips,
                template_data=self.template_data,
            ),
            audio_files,
        )
