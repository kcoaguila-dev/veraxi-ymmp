"""
YMM4 Project Renderer for Veraxi YMMP.

Renders TimelineIR intermediate representations into compliant .ymmp project files.
Supports:
- PSD-based character rendering using CharacterPSDRegistry
- Native Brotli-compressed VoiceCache generation
- LipSyncFrames generation from phonetic vowel/consonant queries
- Speech plate image generation and positioning
- Multi-character side-by-side positioning and B-roll dynamic layout adaptation
- Legacy template-based rendering for standard YMM4 templates
"""

from __future__ import annotations

import base64
import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Union, cast

import brotli

from .constants import DEFAULT_BG_IMAGE_PATH, DEFAULT_BGM_CANDIDATES, DEFAULT_SUBTITLE_CENTER_Y
from .ir import TimelineIR
from .phonetics import build_ymm4_lipsync_frames, extract_phonetic_blocks
from .ports import ExportResult
from .psd_registry import CharacterPSDRegistry
from .script import DirectorScriptEntry, WriterScriptEntry
from .subtitle_plate import create_speech_plate
from .template import get_timeline
from .typography import wrap_japanese
from .utils import normalize_japanese_typography

if TYPE_CHECKING:
    pass

ScriptEntry = Union[WriterScriptEntry, DirectorScriptEntry, Dict[str, Any]]


def _anim_val(val: float, span: float = 0.0, anim_type: str = "なし") -> Dict[str, Any]:
    """Create a standard YMM4 animated property dictionary."""
    return {"Values": [{"Value": val}], "Span": span, "AnimationType": anim_type}


def _format_voice_duration(sec: float) -> str:
    """Format duration in seconds into YMM4 TimeSpan string (HH:MM:SS.fffffff)."""
    hours = int(sec // 3600)
    mins = int((sec % 3600) // 60)
    secs = sec % 60
    return f"{hours:02d}:{mins:02d}:{secs:09.6f}0"


def _is_background_clip(ic: Any) -> bool:
    """Return True if a dynamic image clip is a background rather than B-roll."""
    if getattr(ic, "is_background", False) or getattr(ic, "is_bg", False):
        return True
    p_str = str(getattr(ic, "image_path", "")).lower()
    return any(
        k in p_str
        for k in (
            "assets/bg",
            "assets\\bg",
            "classroom",
            "room",
            "living_room",
            "washitsu",
            "clean_classroom",
        )
    )


def _get_vertical_broll_zoom(img_path: Union[str, Path]) -> float:
    """Calculate optimal YMM4 zoom for a B-roll image on a 1080x1920 vertical canvas."""
    try:
        from PIL import Image
        with Image.open(img_path) as im:
            w = im.size[0]
            if w > 1080:
                return round((1080.0 / float(w)) * 100.0, 2)
    except Exception:
        pass
    return 100.0


def _build_image_item(
    file_path: Union[str, Path],
    frame: int,
    length: int,
    layer: int,
    x: float = 0.0,
    y: float = 0.0,
    zoom: Union[float, Dict[str, Any]] = 100.0,
    animated_opacity_rot: bool = False,
) -> Dict[str, Any]:
    """Construct a YMM4 ImageItem dictionary."""
    zoom_dict = zoom if isinstance(zoom, dict) else _anim_val(zoom)
    opacity_dict = _anim_val(100.0) if animated_opacity_rot else {"Values": [{"Value": 100.0}]}
    rot_dict = _anim_val(0.0) if animated_opacity_rot else {"Values": [{"Value": 0.0}]}
    return {
        "$type": "YukkuriMovieMaker.Project.Items.ImageItem, YukkuriMovieMaker",
        "FilePath": str(file_path),
        "X": _anim_val(x),
        "Y": _anim_val(y),
        "Opacity": opacity_dict,
        "Zoom": zoom_dict,
        "Rotation": rot_dict,
        "Blend": "Normal",
        "Layer": layer,
        "Frame": frame,
        "Length": length,
        "VideoEffects": [],
    }


@dataclass
class CompilationResult:
    """Result of a compilation process."""

    output_path: Path
    item_count: int
    voice_item_count: int
    tachie_item_count: int
    total_frames: int
    total_duration_seconds: float
    audio_files: List[Path]
    warnings: List[str]
    errors: List[str]


class YMMPRenderer:
    """
    Renders TimelineIR representations into valid YMM4 .ymmp project files.
    """

    def __init__(
        self,
        template_data: Dict[str, Any],
        character_templates: Optional[Dict[str, Any]] = None,
        text_template: Optional[Dict[str, Any]] = None,
        face_templates: Optional[Dict[str, Any]] = None,
        psd_registry: Optional[CharacterPSDRegistry] = None,
        layout_cfg: Optional[Dict[str, Any]] = None,
        warnings: Optional[List[str]] = None,
        errors: Optional[List[str]] = None,
    ) -> None:
        self.template_data = template_data
        self.character_templates = character_templates or {}
        self.text_template = text_template
        self.face_templates = face_templates or {}
        self.psd_registry = psd_registry or CharacterPSDRegistry.get_default()
        self.layout_cfg = layout_cfg or {
            "tachie": {"X": -650.0, "Y": 250.0, "Zoom": 65.0},
            "broll": {"X": 350.0, "Y": -50.0, "Zoom": 80.0},
        }
        self.warnings = warnings if warnings is not None else []
        self.errors = errors if errors is not None else []

    def render(
        self,
        timeline_ir: TimelineIR,
        output_path: Path,
        use_bom: bool = False,
        script_len: Optional[int] = None,
        audio_files: Optional[List[Path]] = None,
    ) -> CompilationResult:
        """Renders TimelineIR to output_path. Automatically selects PSD vs template rendering."""
        output_path = Path(output_path)
        output_data = copy.deepcopy(self.template_data)
        audio_files = audio_files or []

        effective_script_len = (
            script_len if script_len is not None else len(timeline_ir.voice_clips)
        )

        is_psd_project = any(
            "ずんだ" in c.character or "めたん" in c.character for c in timeline_ir.voice_clips
        ) or any("Psd" in str(c) for c in output_data.get("Characters", []))
        render_fn = self.render_psd if is_psd_project else self.render_template
        return render_fn(
            timeline_ir=timeline_ir,
            output_path=output_path,
            use_bom=use_bom,
            script_len=effective_script_len,
            audio_files=audio_files,
            output_data=output_data,
        )

    def _build_psd_voice_item(
        self,
        clip: Any,
        txt: str,
        psd_p: Path,
        face_layers: List[str],
        face_paths: List[str],
        fps: int,
        font_size: float = 40.0,
        y: float = DEFAULT_SUBTITLE_CENTER_Y,
    ) -> Dict[str, Any]:
        """Build a PSD-backed VoiceItem with Brotli VoiceCache and native LipSyncFrames."""
        char, a_path = clip.character, clip.audio_path
        clip_dur = clip.length / fps if fps else 1.0
        voice_cache_b64, voice_len_str = "", "00:00:01.0000000"
        if a_path and a_path.exists():
            raw_bytes = a_path.read_bytes()
            voice_cache_b64 = base64.b64encode(brotli.compress(raw_bytes, quality=4)).decode(
                "ascii"
            )
            voice_len_str = _format_voice_duration(clip_dur)

        reg = self.psd_registry
        return {
            "$type": "YukkuriMovieMaker.Project.Items.VoiceItem, YukkuriMovieMaker",
            "IsWaveformEnabled": True,
            "CharacterName": char,
            "Serif": wrap_japanese(txt, width=20),
            "Decorations": [],
            "Hatsuon": clip.hatsuon if clip.hatsuon else txt,
            "Pronounce": None,
            "LipSyncFrames": build_ymm4_lipsync_frames(clip.audio_query, clip_dur),
            "FilePath": str(a_path.resolve()) if a_path else "",
            "VoiceLength": voice_len_str,
            "VoiceCache": voice_cache_b64,
            "VoiceParameter": {
                "$type": "YukkuriMovieMaker.Voice.VOICEVOXVoiceParameter, YukkuriMovieMaker",
                "StyleID": reg.get_style_id(char),
                "MorphingStyleID": -1,
                "MorphingRate": 50.0,
                "Speed": 100,
                "Pitch": 100.0,
                "Intonation": 100.0,
                "PrePhonemeLength": 0.1,
                "PostPhonemeLength": 0.1,
                "PauseLengthScale": 100.0,
            },
            "TachieFaceParameter": {
                "$type": "YukkuriMovieMaker.Plugin.Tachie.Psd.PsdTachieFaceParameter, YukkuriMovieMaker.Plugin.Tachie.Psd",
                "IsEnabled": True,
                "FilePath": str(psd_p),
                "EnableLayers": face_layers,
                "EnableLayerPaths": face_paths,
                "EyeAnimation": "Default",
                "MouthAnimation": "VowelLipSyncPriority",
            },
            "TachieFaceEffects": [],
            "Volume": _anim_val(100.0),
            "Pan": _anim_val(0.0),
            "PlaybackRate": 100.0,
            "PlaybackRate2": _anim_val(100.0),
            "ContentOffset": "00:00:00",
            "Layer": 9,
            "Frame": clip.start_frame,
            "Length": clip.length,
            "JimakuVisibility": "UseCharacterSetting",
            "X": _anim_val(0.0),
            "Y": _anim_val(y),
            "JimakuX": _anim_val(0.0),
            "JimakuY": _anim_val(y),
            "BasePoint": "CenterCenter",
            "Font": "メイリオ",
            "FontSize": _anim_val(font_size),
            "FontColor": reg.get_font_color(char),
            "Style": "Normal",
            "StyleColor": reg.get_style_color(char),
            "Bold": True,
            "LineHeight2": _anim_val(100.0),
            "LetterSpacing2": _anim_val(0.0),
            "WordWrap": "NoWrap",
            "MaxWidth": _anim_val(1600.0),
            "VideoEffects": [],
        }

    def render_psd(
        self,
        timeline_ir: TimelineIR,
        output_path: Path,
        use_bom: bool = False,
        script_len: Optional[int] = None,
        audio_files: Optional[List[Path]] = None,
        output_data: Optional[Dict[str, Any]] = None,
    ) -> CompilationResult:
        """Renders a PSD-based project using CharacterPSDRegistry."""
        output_path = Path(output_path)
        if output_data is None:
            output_data = copy.deepcopy(self.template_data)
        audio_files = audio_files or []
        timeline = get_timeline(output_data)
        video_info = timeline.get("VideoInfo", {})
        is_vertical = bool(video_info.get("Height", 1080) > video_info.get("Width", 1920))
        registry = self.psd_registry

        all_char_names = ["ずんだもん", "四国めたん", "春日部つむぎ"]
        for c in timeline_ir.voice_clips:
            if c.character not in all_char_names:
                all_char_names.append(c.character)
        output_data["Characters"] = [
            registry.create_character_definition(name, is_vertical=is_vertical) for name in all_char_names
        ]

        plates_dir = output_path.parent / "plates"
        plates_dir.mkdir(parents=True, exist_ok=True)
        items: List[Dict[str, Any]] = []

        # 1. Spoken Lines: Face, Plate, Voice
        for clip in timeline_ir.voice_clips:
            char, frm, lng, emo = clip.character, clip.start_frame, clip.length, clip.emotion
            txt = normalize_japanese_typography(clip.text)
            face_layer = registry.get_face_layer(char)
            psd_p = registry.get_psd_path(char)
            face_layers_key, face_paths_key = registry.get_face_layers_and_paths(
                char, emo, is_open=True
            )

            clip_dur = lng / timeline_ir.fps if timeline_ir.fps else 1.0
            phonetic_blocks = extract_phonetic_blocks(
                clip.audio_query, clip_dur, fps=timeline_ir.fps
            )
            cur_f = frm
            for b_idx, (_, b_e, is_open) in enumerate(phonetic_blocks):
                b_end_f = (
                    frm + lng
                    if b_idx == len(phonetic_blocks) - 1
                    else min(frm + lng, frm + int(round(b_e * timeline_ir.fps)))
                )
                b_len = b_end_f - cur_f
                if b_len > 0:
                    f_layers, f_paths = registry.get_face_layers_and_paths(
                        char, emo, is_open=is_open
                    )
                    items.append(
                        {
                            "$type": "YukkuriMovieMaker.Project.Items.TachieFaceItem, YukkuriMovieMaker",
                            "CharacterName": char,
                            "TachieFaceParameter": {
                                "$type": "YukkuriMovieMaker.Plugin.Tachie.Psd.PsdTachieFaceParameter, YukkuriMovieMaker.Plugin.Tachie.Psd",
                                "IsEnabled": True,
                                "FilePath": str(psd_p),
                                "EnableLayers": f_layers,
                                "EnableLayerPaths": f_paths,
                                "EyeAnimation": "Default",
                                "MouthAnimation": "AlwaysOpen" if is_open else "AlwaysClose",
                            },
                            "Layer": face_layer,
                            "Frame": cur_f,
                            "Length": b_len,
                            "Remark": f"{emo}_{'open' if is_open else 'closed'}",
                        }
                    )
                    cur_f = b_end_f

            plate_file = plates_dir / f"plate_{frm}_{char}.png"
            plate_res = create_speech_plate(
                txt,
                char,
                plate_file,
                canvas_w=1080 if is_vertical else 1920,
                bottom_safe_margin=330.0 if is_vertical else 50.0,
                canvas_total_h=1920 if is_vertical else 1080,
            )
            center_y = getattr(plate_res, "center_y", DEFAULT_SUBTITLE_CENTER_Y)
            voice_y = getattr(plate_res, "voice_y", center_y)
            items.append(
                _build_image_item(
                    plate_file.resolve(), frm, lng, layer=8, y=center_y, animated_opacity_rot=True
                )
            )
            items.append(
                self._build_psd_voice_item(
                    clip,
                    txt,
                    psd_p,
                    face_layers_key,
                    face_paths_key,
                    timeline_ir.fps,
                    font_size=plate_res.font_size,
                    y=voice_y,
                )
            )

        # 2. Tachie Characters (L4 & L6) - Coalesce contiguous spans with identical spatial layout
        broll_intervals = [
            (img.start_frame, img.start_frame + img.length)
            for img in timeline_ir.dynamic_image_clips
            if not _is_background_clip(img) and img.length > 0
        ]
        active_tachie_by_layer: Dict[int, Dict[str, Any]] = {}

        def add_or_coalesce_tachie(char_name: str, has_broll: bool, frm: int, lng: int) -> None:
            layout = registry.get_spatial_layout(char_name, has_broll=has_broll, is_vertical=is_vertical)
            t_layer, x_val, y_val, zoom_val = (
                layout["layer"],
                layout["x"],
                layout["y"],
                layout["zoom"],
            )
            prev = active_tachie_by_layer.get(t_layer)
            if (
                prev is not None
                and prev.get("CharacterName") == char_name
                and prev["Frame"] + prev["Length"] == frm
                and prev["X"]["Values"][0]["Value"] == x_val
                and prev["Y"]["Values"][0]["Value"] == y_val
                and prev["Zoom"]["Values"][0]["Value"] == zoom_val
            ):
                prev["Length"] += lng
                return

            new_tachie = {
                "$type": "YukkuriMovieMaker.Project.Items.TachieItem, YukkuriMovieMaker",
                "CharacterName": char_name,
                "TachieItemParameter": {
                    "$type": "YukkuriMovieMaker.Plugin.Tachie.Psd.PsdTachieItemParameter, YukkuriMovieMaker.Plugin.Tachie.Psd",
                    "FilePath": str(registry.get_psd_path(char_name)),
                    "EnableLayers": registry.get_base_layers(char_name),
                    "EnableLayerPaths": registry.get_base_paths(char_name),
                    "IsHiddenWhenNoSpeech": False,
                },
                "X": _anim_val(x_val),
                "Y": _anim_val(y_val),
                "Zoom": _anim_val(zoom_val),
                "Opacity": _anim_val(100.0),
                "Rotation": _anim_val(0.0),
                "Blend": "Normal",
                "PlaybackRate2": _anim_val(100.0),
                "FadeIn": 0.0,
                "FadeOut": 0.0,
                "Group": 0,
                "KeyFrames": {"Frames": [], "Count": 0},
                "IsLocked": False,
                "IsHidden": False,
                "Layer": t_layer,
                "Frame": frm,
                "Length": lng,
                "VideoEffects": [],
            }
            items.append(new_tachie)
            active_tachie_by_layer[t_layer] = new_tachie

        for clip in timeline_ir.voice_clips:
            frm, lng = clip.start_frame, clip.length
            has_broll = any(s <= frm < e or s < frm + lng <= e for s, e in broll_intervals)
            for c_name in [clip.character] if (has_broll and not is_vertical) else list(dict.fromkeys([c.character for c in timeline_ir.voice_clips])):
                add_or_coalesce_tachie(c_name, has_broll, frm, lng)

        # 3. Layer 0: Background ImageItem
        bg_clips = [img for img in timeline_ir.dynamic_image_clips if _is_background_clip(img)]
        if bg_clips:
            for bg_clip in bg_clips:
                bg_len = (
                    timeline_ir.total_frames - bg_clip.start_frame
                    if bg_clip.length <= 0
                    else bg_clip.length
                )
                items.append(
                    _build_image_item(
                        bg_clip.image_path.resolve(),
                        bg_clip.start_frame,
                        bg_len,
                        layer=0,
                        zoom=187.5,
                    )
                )
        else:
            bg_candidate = Path(DEFAULT_BG_IMAGE_PATH).resolve()
            for gc in timeline_ir.global_clips:
                ti = gc.template_item or {}
                file_p = gc.file_path or ti.get("FilePath")
                if file_p and any(k in file_p.lower() for k in ("bg", "room", "classroom")):
                    bg_candidate = Path(file_p).resolve()
            items.append(
                _build_image_item(bg_candidate, 0, timeline_ir.total_frames, layer=0, zoom=187.5)
            )

        # 4. Layer 1: B-Roll Images (Strictly exclude background clips and non-positive lengths)
        for d_img_clip in timeline_ir.dynamic_image_clips:
            if _is_background_clip(d_img_clip) or d_img_clip.length <= 0:
                continue
            b_y = -540.0 if is_vertical else 0.0
            b_zoom = _get_vertical_broll_zoom(d_img_clip.image_path) if is_vertical else 100.0
            items.append(
                _build_image_item(
                    d_img_clip.image_path.resolve(),
                    d_img_clip.start_frame,
                    d_img_clip.length,
                    layer=1,
                    y=b_y,
                    zoom=b_zoom,
                )
            )

        # 5. Layer 3: BGM AudioItem
        bgm_path = Path(DEFAULT_BGM_CANDIDATES[0]).resolve()
        for cand in DEFAULT_BGM_CANDIDATES:
            cand_p = Path(cand).resolve()
            if cand_p.exists():
                bgm_path = cand_p
                break
        for d_audio_clip in timeline_ir.dynamic_audio_clips:
            if d_audio_clip.length == -1 or "bgm" in str(d_audio_clip.audio_path).lower():
                bgm_path = d_audio_clip.audio_path.resolve()
        items.append(
            {
                "$type": "YukkuriMovieMaker.Project.Items.AudioItem, YukkuriMovieMaker",
                "FilePath": str(bgm_path),
                "Volume": _anim_val(3.0),
                "Pan": {"Values": [{"Value": 0.0}]},
                "PlaybackRate": 100.0,
                "Layer": 3,
                "Frame": 0,
                "Length": timeline_ir.total_frames,
                "IsLooped": True,
            }
        )

        tl = get_timeline(output_data)
        tl["Items"], tl["Length"], tl["MaxLayer"] = items, timeline_ir.total_frames, 12
        plates_layer7_or_8 = [it for it in items if "ImageItem" in it.get("$type", "") and it.get("Layer") in (7, 8)]
        if plates_layer7_or_8:
            first_p_y = plates_layer7_or_8[0]["Y"]["Values"][0]["Value"]
            for ch in output_data.get("Characters", []):
                ch["Y"] = {"Values": [{"Value": first_p_y}], "Span": 0.0, "AnimationType": "なし"}
        self._write_output(output_data, output_path, use_bom)

        has_voice_audio = bool(audio_files) or any(
            bool(c.audio_path and c.audio_path.exists()) for c in timeline_ir.voice_clips
        )
        if has_voice_audio:
            from .validation import validate_ymmp_timeline

            validate_ymmp_timeline(
                output_data,
                expected_voice_count=len(timeline_ir.voice_clips),
                require_audio=True,
            )

        tachie_count = sum(1 for i in items if "TachieItem" in i.get("$type", ""))
        return CompilationResult(
            output_path=output_path,
            item_count=len(items),
            voice_item_count=len(timeline_ir.voice_clips),
            tachie_item_count=tachie_count,
            total_frames=timeline_ir.total_frames,
            total_duration_seconds=timeline_ir.total_frames / timeline_ir.fps
            if timeline_ir.fps
            else 0.0,
            audio_files=audio_files,
            warnings=self.warnings,
            errors=self.errors,
        )

    def render_template(
        self,
        timeline_ir: TimelineIR,
        output_path: Path,
        use_bom: bool = False,
        script_len: Optional[int] = None,
        audio_files: Optional[List[Path]] = None,
        output_data: Optional[Dict[str, Any]] = None,
    ) -> CompilationResult:
        """Renders a non-PSD template project using character template cloning."""
        output_path = Path(output_path)
        if output_data is None:
            output_data = copy.deepcopy(self.template_data)
        audio_files = audio_files or []
        timeline = get_timeline(output_data)
        video_info = timeline.get("VideoInfo", {})
        is_vertical = bool(video_info.get("Height", 1080) > video_info.get("Width", 1920))
        effective_script_len = (
            script_len if script_len is not None else len(timeline_ir.voice_clips)
        )

        if is_vertical:
            sub_y, sub_size = 300.0, 100.0
            tachie_cfg = {"X": 0.0, "Y": 650.0, "Zoom": 80.0}
            broll_cfg = {"X": 0.0, "Y": -300.0, "Zoom": 120.0}
        else:
            sub_y, sub_size = 450.0, 80.0
            tachie_cfg = {"X": -650.0, "Y": 250.0, "Zoom": 65.0}
            broll_cfg = {"X": 350.0, "Y": -50.0, "Zoom": 80.0}

        for char in output_data.get("Characters", []):
            char["FontSize"], char["Y"] = sub_size, sub_y

        self.layout_cfg = {"tachie": tachie_cfg, "broll": broll_cfg}
        items: List[Dict[str, Any]] = []

        for clip in timeline_ir.voice_clips:
            new_item = copy.deepcopy(self.character_templates[clip.character]["voice"])
            new_item["Layer"] = 2
            new_item["Serif"] = wrap_japanese(clip.text, width=20)
            new_item["Hatsuon"] = clip.hatsuon
            new_item["Frame"] = clip.start_frame
            new_item["Length"] = clip.length
            new_item["VoiceCache"] = ""

            self._set_animated_value(new_item, "FontSize", 80.0)
            self._set_animated_value(new_item, "Y", 450.0)
            new_item["IsWaveformEnabled"] = True

            if clip.audio_path:
                sec = clip.length / timeline_ir.fps if timeline_ir.fps else 1.0
                new_item["VoiceLength"] = _format_voice_duration(sec)
                new_item["FilePath"] = str(clip.audio_path.resolve())
                self._mute_voice_item(new_item)
                new_item["IsHidden"] = False

            effects = new_item.get("VideoEffects", [])
            if clip.motion == "jump":
                effects.append(
                    {
                        "$type": "YukkuriMovieMaker.Project.Effects.JumpEffect, YukkuriMovieMaker",
                        "Span": 0.5,
                        "Height": 50.0,
                    }
                )
            elif clip.motion == "shake":
                effects.append(
                    {
                        "$type": "YukkuriMovieMaker.Project.Effects.ShakeEffect, YukkuriMovieMaker",
                        "Amount": 20.0,
                        "Interval": 1.0,
                    }
                )
            new_item["VideoEffects"] = effects

            items.append(new_item)
            if clip.audio_path:
                items.append(self._make_audio_item(new_item, clip.audio_path))

            pseudo_line = {
                "subtitle_position": clip.subtitle_position,
                "subtitle_style": clip.subtitle_style,
                "emotion": clip.emotion,
                "character": clip.character,
            }
            face_item = self._make_face_item(pseudo_line, clip.start_frame, clip.length)
            if face_item is not None:
                items.append(face_item)

        tachie_items = self._add_tachie_items(
            set(c.character for c in timeline_ir.character_clips),
            timeline_ir.total_frames,
            {c.character: c.position for c in timeline_ir.character_clips},
        )
        items.extend(tachie_items)

        for d_img_clip in timeline_ir.dynamic_image_clips:
            is_bg = _is_background_clip(d_img_clip)
            if not is_bg and d_img_clip.length <= 0:
                continue
            clip_len = (
                timeline_ir.total_frames - d_img_clip.start_frame
                if d_img_clip.length <= 0
                else d_img_clip.length
            )
            zoom_prop: Union[float, Dict[str, Any]] = (
                187.5
                if is_bg
                else {
                    "Values": [{"Value": 0.0}, {"Value": broll_cfg["Zoom"]}],
                    "Span": 0.2,
                    "AnimationType": "加減速移動",
                }
            )
            items.append(
                _build_image_item(
                    d_img_clip.image_path.resolve(),
                    d_img_clip.start_frame,
                    clip_len,
                    layer=0 if is_bg else 1,
                    x=0.0 if is_bg else broll_cfg["X"],
                    y=0.0 if is_bg else broll_cfg["Y"],
                    zoom=zoom_prop,
                )
            )


        for d_audio_clip in timeline_ir.dynamic_audio_clips:
            is_looped = d_audio_clip.length == -1
            volume = 3.0 if is_looped else 50.0
            length = (
                timeline_ir.total_frames - d_audio_clip.start_frame
                if is_looped
                else d_audio_clip.length
            )
            items.append(
                {
                    "$type": "YukkuriMovieMaker.Project.Items.AudioItem, YukkuriMovieMaker",
                    "FilePath": str(d_audio_clip.audio_path.resolve()),
                    "Volume": _anim_val(volume),
                    "Pan": {"Values": [{"Value": 0.0}]},
                    "PlaybackRate": 100.0,
                    "Layer": 5,
                    "Frame": d_audio_clip.start_frame,
                    "Length": length,
                    "IsLooped": is_looped,
                }
            )

        for gc in timeline_ir.global_clips:
            preserved_item = copy.deepcopy(gc.template_item)
            if "Length" in preserved_item:
                preserved_item["Length"] = timeline_ir.total_frames
            items.append(preserved_item)

        timeline = get_timeline(output_data)
        timeline["Items"], timeline["Length"] = items, timeline_ir.total_frames

        psd_path = os.environ.get("ZUNDAMON_PSD_PATH") or os.environ.get("VERAXI_ZUNDA_PSD")
        if psd_path:

            def _replace_psd(obj: Any) -> None:
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
            voice_item_count=effective_script_len,
            tachie_item_count=len(tachie_items),
            total_frames=timeline_ir.total_frames,
            total_duration_seconds=timeline_ir.total_frames / timeline_ir.fps
            if timeline_ir.fps
            else 0.0,
            audio_files=audio_files,
            warnings=self.warnings,
            errors=self.errors,
        )

    def _mute_voice_item(self, voice_item: Dict[str, Any]) -> None:
        """Mutes a VoiceItem when paired with an external AudioItem."""
        volume = voice_item.get("Volume")
        if isinstance(volume, dict) and isinstance(volume.get("Values"), list):
            for value in volume["Values"]:
                if isinstance(value, dict):
                    value["Value"] = 0.0
        elif volume is not None:
            voice_item["Volume"] = 0.0

    def _make_audio_item(self, voice_item: Dict[str, Any], audio_path: Path) -> Dict[str, Any]:
        """Creates an AudioItem matching the VoiceItem's timing."""
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
        self, text: str, frame: int, length: int, line: ScriptEntry
    ) -> Optional[Dict[str, Any]]:
        """Creates a subtitle TextItem from the text template."""
        if self.text_template is None:
            return None
        text_item = copy.deepcopy(self.text_template)
        text_item["Text"], text_item["Frame"], text_item["Length"] = text, frame, length
        text_item["Layer"] = self._get_subtitle_layer()
        sub_pos = str(line.get("subtitle_position", "bottom_center"))
        x_map: Dict[str, float] = {"top_center": -480.0, "center": -480.0, "bottom_center": -480.0}
        y_map: Dict[str, float] = {"top_center": -420.0, "center": 0.0, "bottom_center": 420.0}
        self._set_animated_value(text_item, "X", x_map.get(sub_pos, -480.0))
        self._set_animated_value(text_item, "Y", y_map.get(sub_pos, 420.0))
        if line.get("subtitle_style", "outlined") == "outlined":
            self._set_animated_value(text_item, "FontSize", 56.0)
        return text_item

    def _make_face_item(
        self, line: ScriptEntry, frame: int, length: int
    ) -> Optional[Dict[str, Any]]:
        """Creates a facial expression item from face templates."""
        emotion = line.get("emotion", "neutral")
        char_name = line.get("character")
        if not char_name:
            return None
        template = self.face_templates.get(char_name, {}).get(emotion)
        if template is None:
            return None
        face_item = cast(Dict[str, Any], copy.deepcopy(template))
        face_item["Layer"], face_item["Frame"], face_item["Length"] = 1, frame, length
        return face_item

    @staticmethod
    def _set_animated_value(item: Dict[str, Any], key: str, value: float) -> None:
        """Sets an animated value property on a YMM4 item."""
        property_data = item.get(key)
        if isinstance(property_data, dict) and isinstance(property_data.get("Values"), list):
            if property_data["Values"] and isinstance(property_data["Values"][0], dict):
                property_data["Values"][0]["Value"] = value

    def _get_subtitle_layer(self) -> int:
        """Calculates subtitle layer above all tachie items."""
        tachie_layers = [
            templates["tachie"].get("Layer", 0)
            for templates in self.character_templates.values()
            if templates["tachie"] is not None
        ]
        default_layer = self.text_template.get("Layer", 0) if self.text_template else 0
        return max(tachie_layers, default=default_layer) + 1

    def _add_tachie_items(
        self, used_characters: Set[str], total_length: int, character_positions: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """Adds template-based tachie items for all speaking characters."""
        result: List[Dict[str, Any]] = []
        for char_name, templates in self.character_templates.items():
            if char_name in used_characters and templates["tachie"] is not None:
                tachie_item = copy.deepcopy(templates["tachie"])
                tachie_item["Layer"], tachie_item["Frame"], tachie_item["Length"] = (
                    1,
                    0,
                    total_length,
                )
                pos = character_positions.get(char_name, "left")
                final_x = 0.0 if pos == "center" else self.layout_cfg["tachie"]["X"]
                self._set_animated_value(tachie_item, "X", final_x)
                self._set_animated_value(tachie_item, "Y", self.layout_cfg["tachie"]["Y"])
                self._set_animated_value(tachie_item, "Zoom", self.layout_cfg["tachie"]["Zoom"])
                result.append(tachie_item)
        return result

    @staticmethod
    def _write_output(output_data: Dict[str, Any], output_path: Path, use_bom: bool) -> None:
        """Writes project JSON to disk with optional UTF-8 BOM after schema validation."""
        from .validation import validate_ymmp_schema

        validate_ymmp_schema(output_data)
        encoding = "utf-8-sig" if use_bom else "utf-8"
        with open(output_path, "w", encoding=encoding) as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)

    def export(
        self, ir: TimelineIR, output_path: Path, options: Optional[Dict[str, Any]] = None
    ) -> ExportResult:
        """Export TimelineIR to YMM4 .ymmp project format."""
        opts = options or {}
        out_p = Path(output_path)
        comp_res = self.render(
            timeline_ir=ir,
            output_path=out_p,
            use_bom=opts.get("use_bom", False),
            script_len=opts.get("script_len", None),
            audio_files=opts.get("audio_files", None),
        )
        artifacts = [out_p] + (comp_res.audio_files if comp_res.audio_files else [])
        return ExportResult(
            target_format="ymmp",
            output_path=out_p,
            artifacts=artifacts,
            metadata={
                "item_count": comp_res.item_count,
                "voice_item_count": comp_res.voice_item_count,
                "tachie_item_count": comp_res.tachie_item_count,
                "total_frames": comp_res.total_frames,
                "total_duration_seconds": comp_res.total_duration_seconds,
                "warnings": comp_res.warnings,
                "errors": comp_res.errors,
            },
        )
