from __future__ import annotations
from .ir import TimelineIR, VoiceClip, CharacterClip, GlobalClip, DynamicImageClip, DynamicAudioClip
from pathlib import Path
"""
YMM4 project compiler for generating dialogue timelines.

This module provides the main compilation logic for generating .ymmp files
from scripts and templates. It handles:
- Loading and processing templates
- Generating voice items with proper timing
- Integrating with VOICEVOX for TTS
- Managing tachie (character) items
"""


import copy
import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from .template import (
    extract_character_templates,
    extract_face_templates,
    extract_text_template,
    get_timeline,
    load_template,
)
from .hatsuon import Hatsuon, HatsuonError
from dataclasses import dataclass
from .voicevox import VoicevoxClient, TTSBackend
from .config import CompilerConfig
from .utils import resolve_path, ensure_path
from .cache import TTSCache
from .validation import validate_output_path, sanitize_filename
from .logging import logger
from .script import WriterScriptEntry, DirectorScriptEntry

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
ScriptEntry = Union[WriterScriptEntry, DirectorScriptEntry, Dict[str, Any]]


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
        self.text_template = extract_text_template(self.template_data)
        self.face_templates = extract_face_templates(self.template_data)
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
        output_path: "Path",
        use_bom: bool = False
    ) -> CompilationResult:
        from pathlib import Path
        output_path = Path(output_path)
        self.warnings.clear()
        self.errors.clear()
        audio_dir = output_path.parent / "audio"
        timeline_ir, audio_files = self._build_ir(script, audio_dir)
        return self._render_ymmp(timeline_ir, output_path, use_bom, len(script), audio_files)

    def _build_ir(self, script: List[ScriptEntry], audio_dir: "Path") -> Tuple[TimelineIR, List["Path"]]:
        from .template import get_timeline
        fps = self._get_fps()
        current_frame = 0
        audio_files = []
        voice_clips = []
        character_positions = {}
        dynamic_image_clips = []
        dynamic_audio_clips = []
        active_bg = None

        for idx, line in enumerate(script):
            if line.get("type") == "bgm":
                # Resolve relative to project root
                path = audio_dir.parent.parent / line["path"]
                vol = line.get("volume", 15) / 100.0
                dynamic_audio_clips.append(DynamicAudioClip(audio_path=path, start_frame=0, length=-1, volume=vol))
                continue
                
            char_name = line.get("character")

            if "emotion" in line and line["emotion"] != "neutral":
                char_faces = self.face_templates.get(char_name, {})
                if line["emotion"] not in char_faces:
                    msg = f"Emotion '{line['emotion']}' for character '{char_name}' on entry {idx} is preserved but unsupported in generated YMMP."
                    self.warnings.append(msg)

            if "motion" in line and line["motion"] != "none":
                msg = f"Motion '{line['motion']}' on entry {idx} is preserved but unsupported in generated YMMP."
                self.warnings.append(msg)

            text = line.get("text", "")
            length = self._calculate_placeholder_length(text)

            bgm_name = line.get("bgm")
            if bgm_name and bgm_name != "none" and bgm_name != "":
                bgm_path = Path(bgm_name)
                if bgm_path.exists():
                    dynamic_audio_clips.append(DynamicAudioClip(
                        audio_path=bgm_path,
                        start_frame=current_frame,
                        length=-1 # Special marker for "entire video"
                    ))
                else:
                    msg = f"BGM not found: {bgm_name}"
                    logger.warning(msg)
                    self.warnings.append(msg)

            if line.get("sfx") is not None and line["sfx"] != "none" and line["sfx"] != "":
                sfx_path = Path(line["sfx"])
                if sfx_path.exists():
                    dynamic_audio_clips.append(DynamicAudioClip(
                        audio_path=sfx_path,
                        start_frame=current_frame,
                        length=30 # default sfx length 30 frames
                    ))
                else:
                    msg = f"SFX not found: {line['sfx']}"
                    logger.warning(msg)
                    self.warnings.append(msg)

            text = line.get("text", "")
            if not char_name:
                continue
                
            character_positions.setdefault(char_name, line.get("character_position", "center"))
            
            if char_name not in self.character_templates:
                # Dynamic fallback: clone the first available character template
                if not self.character_templates:
                    raise ValueError(f"No character templates available to clone for: {char_name}")
                base_char = list(self.character_templates.keys())[0]
                self.character_templates[char_name] = copy.deepcopy(self.character_templates[base_char])
                # Update the character name in the cloned templates
                for k, v in self.character_templates[char_name].items():
                    if v and isinstance(v, dict) and "CharacterName" in v:
                        v["CharacterName"] = char_name
                logger.info(f"Dynamically cloned template for {char_name} from {base_char}")

            if self.character_templates[char_name]["voice"] is None:
                raise ValueError(f"No voice template found for character: {char_name}")

            audio_path = None
            audio_query = None
            
            # Check for actual audio file to get accurate length
            if self.config.use_tts:
                audio_filename = f"{idx:03d}_{sanitize_filename(char_name)}.wav"
                audio_path = audio_dir / audio_filename
                
                # If the audio file already exists (e.g. from a previous run or cache)
                if audio_path.exists():
                    try:
                        import wave
                        with wave.open(str(audio_path), 'rb') as wav:
                            frames = wav.getnframes()
                            rate = wav.getframerate()
                            actual_duration = frames / float(rate)
                            length = int((actual_duration + 0.3) * fps) # Add 0.3s padding
                    except Exception as e:
                        logger.warning(f"Could not read wav length for {audio_filename}: {e}")

            if self.config.use_tts and self.tts_backend:
                if not self.tts_backend.is_available():
                    raise RuntimeError("TTS Backend not reachable")
                if not audio_path or not audio_path.exists():
                    length, audio_path, audio_query = self._synthesize_audio(idx, char_name, text, audio_dir)
                if audio_path and audio_path not in audio_files:
                    audio_files.append(audio_path)
            else:
                if not audio_path or not audio_path.exists():
                    length = self._calculate_placeholder_length(text)

            hatsuon = self._convert_hatsuon(text)

            voice_clips.append(VoiceClip(
                start_frame=current_frame,
                length=length,
                character=char_name,
                text=text,
                emotion=line.get("emotion", "neutral"),
                motion=line.get("motion", "none"),
                audio_path=audio_path,
                hatsuon=hatsuon,
                subtitle_position=line.get("subtitle_position", "bottom_center"),
                subtitle_style=line.get("subtitle_style", "outlined"),
                audio_query=audio_query
            ))

            def add_image_clip(img_name):
                from pathlib import Path
                img_path = Path("artifacts/.user_uploaded") / img_name
                if not img_path.exists():
                    img_path = Path(img_name)
                if not img_path.exists():
                    img_path = Path("artifacts") / img_name
                if img_path.exists():
                    dynamic_image_clips.append(DynamicImageClip(
                        image_path=img_path,
                        start_frame=current_frame,
                        length=length
                    ))
                else:
                    msg = f"Image not found: {img_name}"
                    logger.warning(msg)
                    self.warnings.append(msg)

            image_name = line.get("image")
            if image_name:
                add_image_clip(image_name)
                
            bg_name = line.get("bg")
            if bg_name:
                if active_bg:
                    active_bg.length = current_frame - active_bg.start_frame
                
                # We defer setting the length until it changes or the script ends
                active_bg = DynamicImageClip(
                    image_path=Path(bg_name), # Will be resolved later or we can resolve it now
                    start_frame=current_frame,
                    length=-1 
                )
                
                img_path = Path("artifacts/.user_uploaded") / bg_name
                if not img_path.exists(): img_path = Path(bg_name)
                if not img_path.exists(): img_path = Path("artifacts") / bg_name
                
                if img_path.exists():
                    active_bg.image_path = img_path
                    dynamic_image_clips.append(active_bg)
                else:
                    active_bg = None
                    msg = f"BG Image not found: {bg_name}"
                    logger.warning(msg)
                    self.warnings.append(msg)

            current_frame += length

        # active_bg remains with length=-1 so renderer knows to stretch it to total_duration

        total_frames = current_frame

        used_characters = set(c.character for c in voice_clips)
        character_clips = []
        for char_name in used_characters:
            character_clips.append(CharacterClip(
                start_frame=0,
                length=total_frames,
                character=char_name,
                position=character_positions.get(char_name, "center")
            ))

        global_clips = []
        for template_item in get_timeline(self.template_data).get("Items", []):
            type_str = template_item.get("$type", "")
            if "VoiceItem" not in type_str and "Tachie" not in type_str and "TextItem" not in type_str and "ImageItem" not in type_str and "AudioItem" not in type_str:
                global_clips.append(GlobalClip(
                    start_frame=0,
                    length=total_frames,
                    template_item=template_item
                ))

        return TimelineIR(
            fps=fps,
            total_frames=total_frames,
            voice_clips=voice_clips,
            character_clips=character_clips,
            global_clips=global_clips,
            dynamic_image_clips=dynamic_image_clips,
            dynamic_audio_clips=dynamic_audio_clips,
            template_data=self.template_data
        ), audio_files

    def _render_ymmp(
        self,
        timeline_ir: TimelineIR,
        output_path: "Path",
        use_bom: bool,
        script_len: int,
        audio_files: List["Path"]
    ) -> CompilationResult:
        import os
        import copy
        from .template import get_timeline
        
        output_data = copy.deepcopy(self.template_data)
        
        # Detect aspect ratio to support both Long-form (16:9) and Short-form (9:16)
        timeline = get_timeline(output_data)
        video_info = timeline.get("VideoInfo", {})
        width = video_info.get("Width", 1920)
        height = video_info.get("Height", 1080)
        is_vertical = height > width
        
        if is_vertical:
            # 9:16 layout (TikTok / Shorts)
            sub_y = 300.0
            sub_size = 100.0
            tachie_cfg = {"X": 0.0, "Y": 650.0, "Zoom": 80.0}
            broll_cfg = {"X": 0.0, "Y": -300.0, "Zoom": 120.0}
        else:
            # 16:9 layout (YouTube long-form)
            sub_y = 450.0
            sub_size = 80.0
            tachie_cfg = {"X": -650.0, "Y": 250.0, "Zoom": 65.0}
            broll_cfg = {"X": 350.0, "Y": -50.0, "Zoom": 80.0}

        # Autonomous configuration: Ensure huge readable subtitles at the bottom
        for char in output_data.get("Characters", []):
            char["FontSize"] = sub_size
            char["Y"] = sub_y
                
        # Store for _add_tachie_items and image items
        self.layout_cfg = {"tachie": tachie_cfg, "broll": broll_cfg}
                
        items = []

        for clip in timeline_ir.voice_clips:
            template_item = self.character_templates[clip.character]["voice"]
            new_item = copy.deepcopy(template_item)
            new_item["Layer"] = 2
            
            # Apply Japanese word wrapping to avoid text cutoff in YMM4
            from veraxi_ymmp.moviepy_renderer import wrap_japanese
            new_item["Serif"] = wrap_japanese(clip.text, width=24)
            
            new_item["Hatsuon"] = clip.hatsuon
            new_item["Frame"] = clip.start_frame
            new_item["Length"] = clip.length
            new_item["VoiceCache"] = ""
            
            # Autonomous configuration: Ensure huge readable subtitles at the bottom
            self._set_animated_value(new_item, "FontSize", 80.0)
            self._set_animated_value(new_item, "Y", 450.0)
            # Enable lip sync auto-generation
            new_item["IsWaveformEnabled"] = True

            if clip.audio_path:
                sec = clip.length / timeline_ir.fps
                hours = int(sec // 3600)
                mins = int((sec % 3600) // 60)
                secs = sec % 60
                new_item["VoiceLength"] = f"{hours:02d}:{mins:02d}:{secs:09.6f}0"
                new_item["FilePath"] = str(clip.audio_path.resolve())
                self._mute_voice_item(new_item)
                new_item["IsHidden"] = False
                
            # Add motion effects to VoiceItem (applies to character in YMM4)
            effects = new_item.get("VideoEffects", [])
            if clip.motion == "jump":
                effects.append({
                    "$type": "YukkuriMovieMaker.Project.Effects.JumpEffect, YukkuriMovieMaker",
                    "Span": 0.5,
                    "Height": 50.0
                })
            elif clip.motion == "shake":
                effects.append({
                    "$type": "YukkuriMovieMaker.Project.Effects.ShakeEffect, YukkuriMovieMaker",
                    "Amount": 20.0,
                    "Interval": 1.0
                })
            new_item["VideoEffects"] = effects

            if clip.audio_path:
                items.append(new_item)
                items.append(self._make_audio_item(new_item, clip.audio_path))
            else:
                items.append(new_item)

            pseudo_line = {
                "subtitle_position": clip.subtitle_position,
                "subtitle_style": clip.subtitle_style,
                "emotion": clip.emotion,
                "character": clip.character
            }

            # We DO NOT generate a separate TextItem anymore, so the white box JimakuStyle on the VoiceItem shows instead!

            face_item = self._make_face_item(pseudo_line, clip.start_frame, clip.length)
            if face_item is not None:
                items.append(face_item)

        tachie_items = self._add_tachie_items(
            set(c.character for c in timeline_ir.character_clips),
            timeline_ir.total_frames,
            {c.character: c.position for c in timeline_ir.character_clips}
        )
        items.extend(tachie_items)

        for clip in timeline_ir.dynamic_image_clips:
            is_bg = "bg" in str(clip.image_path).lower() or "room" in str(clip.image_path).lower() or "classroom" in str(clip.image_path).lower()
            
            # Dynamic zoom animation for non-bg images (B-roll)
            if not is_bg:
                zoom_val = broll_cfg["Zoom"]
                zoom_prop = {
                    "Values": [{"Value": 0.0}, {"Value": zoom_val}],
                    "Span": 0.2, # Pop in over 20% of duration (or 0.2s depending on YMM4 version, usually ratio or seconds)
                    "AnimationType": "Deceleration" # Smooth pop
                }
            else:
                zoom_prop = {
                    "Values": [{"Value": 100.0}],
                    "Span": 0.0,
                    "AnimationType": "None"
                }

            image_item = {
                "$type": "YukkuriMovieMaker.Project.Items.ImageItem, YukkuriMovieMaker",
                "FilePath": str(clip.image_path.resolve()),
                "X": {
                    "Values": [{"Value": 0.0 if is_bg else broll_cfg["X"]}],
                    "Span": 0.0,
                    "AnimationType": "None"
                },
                "Y": {
                    "Values": [{"Value": 0.0 if is_bg else broll_cfg["Y"]}],
                    "Span": 0.0,
                    "AnimationType": "None"
                },
                "Opacity": {"Values": [{"Value": 100.0}]},
                "Zoom": zoom_prop,
                "Rotation": {"Values": [{"Value": 0.0}]},
                "Blend": "Normal",
                "Layer": 0 if is_bg else 1,
                "Frame": clip.start_frame,
                "Length": clip.length,
                "VideoEffects": []
            }
                
            items.append(image_item)
            if not is_bg:
                pon_path = str(Path(__file__).parent.parent / "assets" / "sfx" / "pon.wav")
                items.append({
                    "$type": "YukkuriMovieMaker.Project.Items.AudioItem, YukkuriMovieMaker",
                    "FilePath": pon_path,
                    "Volume": {"Values": [{"Value": 40.0}]},
                    "Pan": {"Values": [{"Value": 0.0}]},
                    "PlaybackRate": 100.0,
                    "ContentOffset": "00:00:00",
                    "Frame": clip.start_frame,
                    "Length": 60,
                    "Layer": 11,
                    "Blend": "Normal",
                    "VideoEffects": []
                })

        for clip in timeline_ir.dynamic_audio_clips:
            if clip.length == -1: # BGM
                volume = 3.0 # Audio ducking!
            else:
                volume = 50.0

            length = timeline_ir.total_frames - clip.start_frame if clip.length == -1 else clip.length
            
            audio_item = {
                "$type": "YukkuriMovieMaker.Project.Items.AudioItem, YukkuriMovieMaker",
                "FilePath": str(clip.audio_path.resolve()),
                "Volume": {
                    "Values": [{"Value": volume}],
                    "Span": 0.0,
                    "AnimationType": "None"
                },
                "Pan": {"Values": [{"Value": 0.0}]},
                "PlaybackRate": 100.0,
                "Layer": 5,
                "Frame": clip.start_frame,
                "Length": length,
                "IsLooped": clip.length == -1
            }
            items.append(audio_item)

        for gc in timeline_ir.global_clips:
            preserved_item = copy.deepcopy(gc.template_item)
            if "Length" in preserved_item:
                preserved_item["Length"] = timeline_ir.total_frames
            items.append(preserved_item)

        timeline = get_timeline(output_data)
        timeline["Items"] = items
        timeline["Length"] = timeline_ir.total_frames

        # Deep replace the anonymized PSD path with the real one everywhere!
        psd_path = os.environ.get("ZUNDAMON_PSD_PATH")
        if psd_path:
            def _replace_psd(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if isinstance(v, str) and "YourUser" in v and ".psd" in v:
                            obj[k] = psd_path
                        else:
                            _replace_psd(v)
                elif isinstance(obj, list):
                    for i, v in enumerate(obj):
                        if isinstance(v, str) and "YourUser" in v and ".psd" in v:
                            obj[i] = psd_path
                        else:
                            _replace_psd(v)
            _replace_psd(output_data)

        self._write_output(output_data, output_path, use_bom)

        return CompilationResult(
            output_path=output_path,
            item_count=len(items),
            voice_item_count=script_len,
            tachie_item_count=len(tachie_items),
            total_frames=timeline_ir.total_frames,
            total_duration_seconds=timeline_ir.total_frames / timeline_ir.fps if timeline_ir.fps else 0.0,
            audio_files=audio_files,
            warnings=self.warnings,
            errors=self.errors
        )
    def _get_fps(self) -> int:
        return get_timeline(self.template_data).get("VideoInfo", {}).get("FPS", self.config.fps)

    def _convert_hatsuon(self, text: str) -> str:
        try:
            return self.hatsuon.convert(text)
        except HatsuonError as e:
            msg = f"Hatsuon conversion failed: {e}. Using original text."
            logger.warning(msg)
            self.warnings.append(msg)
            return text

    def _synthesize_audio(self, idx: int, char_name: str, text: str, audio_dir: "Path") -> Tuple[int, Optional["Path"], Optional[Dict[str, Any]]]:
        speaker_id = self.config.speaker_map.get(char_name, self.config.default_speaker_id)
        out_path = audio_dir / f"{idx:03d}_{char_name}.wav"
        
        if out_path.exists():
            import wave
            try:
                with wave.open(str(out_path), 'rb') as wav:
                    actual_duration = wav.getnframes() / float(wav.getframerate())
                    return int((actual_duration + 0.3) * self._get_fps()), out_path, None
            except Exception:
                return int(3.0 * self._get_fps()), out_path, None

        cached = self.cache.get(text, speaker_id)
        if cached:
            wav_bytes, duration = cached
            audio_query = None # Cache doesn't store audio_query yet
        else:
            try:
                wav_bytes, duration, audio_query = self.tts_backend.synthesize(text, speaker_id)
                self.cache.set(text, speaker_id, wav_bytes, duration)
            except Exception as e:
                raise RuntimeError(f"Synthesis failed for '{char_name}' on line '{text}': {e}")

        audio_dir.mkdir(parents=True, exist_ok=True)
        safe_char_name = sanitize_filename(char_name)
        audio_filename = f"{idx:03d}_{safe_char_name}.wav"
        audio_path = audio_dir / audio_filename

        with open(audio_path, 'wb') as f:
            f.write(wav_bytes)

        length = int(duration * self._get_fps())
        return length, audio_path, audio_query

    def _calculate_placeholder_length(self, text: str) -> int:
        return max(self.config.min_length_frames, len(text) * self.config.frames_per_char)

    def _mute_voice_item(self, voice_item: Dict[str, Any]) -> None:
        volume = voice_item.get("Volume")
        if isinstance(volume, dict) and isinstance(volume.get("Values"), list):
            for value in volume["Values"]:
                if isinstance(value, dict):
                    value["Value"] = 0.0
        elif volume is not None:
            voice_item["Volume"] = 0.0

    def _make_audio_item(self, voice_item: Dict[str, Any], audio_path: "Path") -> Dict[str, Any]:
        return {
            "$type": "YukkuriMovieMaker.Project.Items.AudioItem, YukkuriMovieMaker",
            "FilePath": str(audio_path.resolve()),
            "Frame": voice_item["Frame"],
            "Length": voice_item["Length"],
            "Layer": voice_item.get("Layer", 0) + 1,
            "PlaybackRate": 100.0,
            "ContentOffset": "00:00:00",
            "Volume": 100.0,
            "FadeIn": 0.0,
            "FadeOut": 0.0,
            "Pan": 0.0,
            "PlaybackRateAudioProcessingMode": "Resampling",
        }

    def _make_text_item(
        self,
        text: str,
        frame: int,
        length: int,
        line: ScriptEntry,
    ) -> Optional[Dict[str, Any]]:
        if self.text_template is None:
            return None
        text_item = copy.deepcopy(self.text_template)
        text_item["Text"] = text
        text_item["Frame"] = frame
        text_item["Length"] = length
        text_item["Layer"] = self._get_subtitle_layer()
        self._set_animated_value(text_item, "X", {"top_center": -480, "center": -480, "bottom_center": -480}[line.get("subtitle_position", "bottom_center")])
        self._set_animated_value(text_item, "Y", {"top_center": -420, "center": 0, "bottom_center": 420}[line.get("subtitle_position", "bottom_center")])
        if line.get("subtitle_style", "outlined") == "outlined":
            self._set_animated_value(text_item, "FontSize", 56.0)
        return text_item

    def _make_face_item(
        self,
        line: ScriptEntry,
        frame: int,
        length: int,
    ) -> Optional[Dict[str, Any]]:
        emotion = line.get("emotion", "neutral")
        char_name = line.get("character")
        if not char_name:
            return None
        char_faces = self.face_templates.get(char_name, {})
        template = char_faces.get(emotion)
        if template is None:
            return None
        face_item = copy.deepcopy(template)
        face_item["Layer"] = 1
        face_item["Frame"] = frame
        face_item["Length"] = length
        
        return face_item

    @staticmethod
    def _set_animated_value(item: Dict[str, Any], key: str, value: float) -> None:
        property_data = item.get(key)
        if isinstance(property_data, dict) and isinstance(property_data.get("Values"), list):
            if property_data["Values"] and isinstance(property_data["Values"][0], dict):
                property_data["Values"][0]["Value"] = value

    def _get_subtitle_layer(self) -> int:
        tachie_layers = [
            templates["tachie"].get("Layer", 0)
            for templates in self.character_templates.values()
            if templates["tachie"] is not None
        ]
        return max(tachie_layers, default=self.text_template.get("Layer", 0)) + 1

    def _add_tachie_items(
        self,
        used_characters: set[str],
        total_length: int,
        character_positions: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []

        for char_name, templates in self.character_templates.items():
            if char_name in used_characters and templates["tachie"] is not None:
                tachie_item = copy.deepcopy(templates["tachie"])
                tachie_item["Layer"] = 1
                tachie_item["Frame"] = 0
                tachie_item["Length"] = total_length
                
                # Zundamon style default based on Canvas detection
                default_x = self.layout_cfg["tachie"]["X"]
                pos = character_positions.get(char_name, "left")
                # If pos explicitly requested center, use 0. Otherwise use the layout configured X.
                # E.g. in 9:16 layout, X is already 0.0. In 16:9, it's -650.0.
                final_x = 0.0 if pos == "center" else default_x
                
                self._set_animated_value(tachie_item, "X", final_x)
                self._set_animated_value(tachie_item, "Y", self.layout_cfg["tachie"]["Y"])
                self._set_animated_value(tachie_item, "Zoom", self.layout_cfg["tachie"]["Zoom"])
                result.append(tachie_item)

        return result

    def _write_output(self, output_data: Dict[str, Any], output_path: "Path", use_bom: bool) -> None:
        mode = 'w'
        encoding = 'utf-8-sig' if use_bom else 'utf-8'
        with open(output_path, mode, encoding=encoding) as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
