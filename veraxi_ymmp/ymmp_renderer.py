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

from .constants import DEFAULT_BG_IMAGE_PATH, DEFAULT_BGM_CANDIDATES
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
        """
        Renders TimelineIR to output_path. Automatically selects PSD vs template rendering.
        """
        output_path = Path(output_path)
        output_data = copy.deepcopy(self.template_data)
        audio_files = audio_files or []
        effective_script_len = script_len if script_len is not None else len(timeline_ir.voice_clips)

        is_psd_project = (
            any("ずんだ" in c.character or "めたん" in c.character for c in timeline_ir.voice_clips)
            or any("Psd" in str(c) for c in output_data.get("Characters", []))
        )
        if is_psd_project:
            return self.render_psd(
                timeline_ir=timeline_ir,
                output_path=output_path,
                use_bom=use_bom,
                script_len=effective_script_len,
                audio_files=audio_files,
                output_data=output_data,
            )
        return self.render_template(
            timeline_ir=timeline_ir,
            output_path=output_path,
            use_bom=use_bom,
            script_len=effective_script_len,
            audio_files=audio_files,
            output_data=output_data,
        )

    def render_psd(
        self,
        timeline_ir: TimelineIR,
        output_path: Path,
        use_bom: bool = False,
        script_len: Optional[int] = None,
        audio_files: Optional[List[Path]] = None,
        output_data: Optional[Dict[str, Any]] = None,
    ) -> CompilationResult:
        """
        Renders a PSD-based project using CharacterPSDRegistry.
        """
        output_path = Path(output_path)
        if output_data is None:
            output_data = copy.deepcopy(self.template_data)
        audio_files = audio_files or []
        registry = self.psd_registry

        # Setup characters
        output_data["Characters"] = [
            registry.create_character_definition("ずんだもん"),
            registry.create_character_definition("四国めたん"),
        ]

        plates_dir = output_path.parent / "plates"
        plates_dir.mkdir(parents=True, exist_ok=True)

        items: List[Dict[str, Any]] = []

        # 1. Spoken Lines: Face, Plate, Voice
        for clip in timeline_ir.voice_clips:
            char = clip.character
            frm = clip.start_frame
            lng = clip.length
            txt = normalize_japanese_typography(clip.text)
            emo = clip.emotion
            a_path = clip.audio_path
            face_layer = registry.get_face_layer(char)
            psd_p = registry.get_psd_path(char)

            face_layers_key, face_paths_key = registry.get_face_layers_and_paths(
                char, emo, is_open=True
            )

            # Face items sliced by 2-state phonetic blocks
            clip_dur = lng / timeline_ir.fps if timeline_ir.fps else 1.0
            phonetic_blocks = extract_phonetic_blocks(clip.audio_query, clip_dur, fps=timeline_ir.fps)
            cur_f = frm
            for b_idx, (b_s, b_e, is_open) in enumerate(phonetic_blocks):
                if b_idx == len(phonetic_blocks) - 1:
                    b_end_f = frm + lng
                else:
                    b_end_f = min(frm + lng, frm + int(round(b_e * timeline_ir.fps)))
                b_len = b_end_f - cur_f
                if b_len > 0:
                    f_layers, f_paths = registry.get_face_layers_and_paths(
                        char, emo, is_open=is_open
                    )
                    items.append({
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
                    })
                    cur_f = b_end_f

            # Plate item (L8)
            plate_file = plates_dir / f"plate_{frm}_{char}.png"
            create_speech_plate(txt, char, plate_file)
            items.append({
                "$type": "YukkuriMovieMaker.Project.Items.ImageItem, YukkuriMovieMaker",
                "FilePath": str(plate_file.resolve()),
                "X": {"Values": [{"Value": 0.0}], "Span": 0.0, "AnimationType": "なし"},
                "Y": {"Values": [{"Value": 418.0}], "Span": 0.0, "AnimationType": "なし"},
                "Opacity": {"Values": [{"Value": 100.0}], "Span": 0.0, "AnimationType": "なし"},
                "Zoom": {"Values": [{"Value": 100.0}], "Span": 0.0, "AnimationType": "なし"},
                "Rotation": {"Values": [{"Value": 0.0}], "Span": 0.0, "AnimationType": "なし"},
                "Blend": "Normal",
                "Layer": 8,
                "Frame": frm,
                "Length": lng,
                "VideoEffects": [],
            })

            # VoiceItem (L9) with Brotli VoiceCache and native LipSyncFrames
            voice_cache_b64 = ""
            voice_len_str = "00:00:01.0000000"
            if a_path and a_path.exists():
                raw_bytes = a_path.read_bytes()
                voice_cache_b64 = base64.b64encode(brotli.compress(raw_bytes, quality=4)).decode("ascii")
                sec = lng / timeline_ir.fps if timeline_ir.fps else 1.0
                hours = int(sec // 3600)
                mins = int((sec % 3600) // 60)
                secs = sec % 60
                voice_len_str = f"{hours:02d}:{mins:02d}:{secs:09.6f}0"

            lipsync_frames = build_ymm4_lipsync_frames(clip.audio_query, clip_dur)

            items.append({
                "$type": "YukkuriMovieMaker.Project.Items.VoiceItem, YukkuriMovieMaker",
                "IsWaveformEnabled": True,
                "CharacterName": char,
                "Serif": wrap_japanese(txt, width=20),
                "Decorations": [],
                "Hatsuon": clip.hatsuon if clip.hatsuon else txt,
                "Pronounce": None,
                "LipSyncFrames": lipsync_frames,
                "FilePath": str(a_path.resolve()) if a_path else "",
                "VoiceLength": voice_len_str,
                "VoiceCache": voice_cache_b64,
                "VoiceParameter": {
                    "$type": "YukkuriMovieMaker.Voice.VOICEVOXVoiceParameter, YukkuriMovieMaker",
                    "StyleID": registry.get_style_id(char),
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
                    "EnableLayers": face_layers_key,
                    "EnableLayerPaths": face_paths_key,
                    "EyeAnimation": "Default",
                    "MouthAnimation": "VowelLipSyncPriority",
                },
                "TachieFaceEffects": [],
                "Volume": {"Values": [{"Value": 100.0}], "Span": 0.0, "AnimationType": "なし"},
                "Pan": {"Values": [{"Value": 0.0}], "Span": 0.0, "AnimationType": "なし"},
                "PlaybackRate": 100.0,
                "PlaybackRate2": {"Values": [{"Value": 100.0}], "Span": 0.0, "AnimationType": "なし"},
                "ContentOffset": "00:00:00",
                "Layer": 9,
                "Frame": frm,
                "Length": lng,
                "JimakuVisibility": "UseCharacterSetting",
                "X": {"Values": [{"Value": 0.0}], "Span": 0.0, "AnimationType": "なし"},
                "Y": {"Values": [{"Value": 418.0}], "Span": 0.0, "AnimationType": "なし"},
                "BasePoint": "CenterCenter",
                "Font": "メイリオ",
                "FontSize": {"Values": [{"Value": 44.0}], "Span": 0.0, "AnimationType": "なし"},
                "FontColor": registry.get_font_color(char),
                "Style": "Normal",
                "StyleColor": registry.get_style_color(char),
                "Bold": True,
                "LineHeight2": {"Values": [{"Value": 100.0}], "Span": 0.0, "AnimationType": "なし"},
                "LetterSpacing2": {"Values": [{"Value": 0.0}], "Span": 0.0, "AnimationType": "なし"},
                "WordWrap": "NoWrap",
                "MaxWidth": {"Values": [{"Value": 1600.0}], "Span": 0.0, "AnimationType": "なし"},
                "VideoEffects": [],
            })

        # 2. Tachie Characters (L4 & L6) - Coalesce contiguous spans with identical spatial layout
        broll_intervals = [
            (img.start_frame, img.start_frame + img.length)
            for img in timeline_ir.dynamic_image_clips
        ]
        active_tachie_by_layer: Dict[int, Dict[str, Any]] = {}

        def add_or_coalesce_tachie(
            char_name: str,
            t_layer: int,
            t_psd: Path,
            t_layers: List[str],
            t_paths: List[str],
            x_val: float,
            y_val: float,
            zoom_val: float,
            frm: int,
            lng: int,
        ) -> None:
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
                    "FilePath": str(t_psd),
                    "EnableLayers": t_layers,
                    "EnableLayerPaths": t_paths,
                    "IsHiddenWhenNoSpeech": False,
                },
                "X": {"Values": [{"Value": x_val}], "Span": 0.0, "AnimationType": "なし"},
                "Y": {"Values": [{"Value": y_val}], "Span": 0.0, "AnimationType": "なし"},
                "Zoom": {"Values": [{"Value": zoom_val}], "Span": 0.0, "AnimationType": "なし"},
                "Opacity": {"Values": [{"Value": 100.0}], "Span": 0.0, "AnimationType": "なし"},
                "Rotation": {"Values": [{"Value": 0.0}], "Span": 0.0, "AnimationType": "なし"},
                "Blend": "Normal",
                "PlaybackRate2": {"Values": [{"Value": 100.0}], "Span": 0.0, "AnimationType": "なし"},
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
            char = clip.character
            frm = clip.start_frame
            lng = clip.length
            has_broll = any(s <= frm < e or s < frm + lng <= e for s, e in broll_intervals)
            if has_broll:
                layout = registry.get_spatial_layout(char, has_broll=True)
                add_or_coalesce_tachie(
                    char_name=char,
                    t_layer=layout["layer"],
                    t_psd=registry.get_psd_path(char),
                    t_layers=registry.get_base_layers(char),
                    t_paths=registry.get_base_paths(char),
                    x_val=layout["x"],
                    y_val=layout["y"],
                    zoom_val=layout["zoom"],
                    frm=frm,
                    lng=lng,
                )
            else:
                metan_layout = registry.get_spatial_layout("四国めたん", has_broll=False)
                add_or_coalesce_tachie(
                    char_name="四国めたん",
                    t_layer=metan_layout["layer"],
                    t_psd=registry.get_psd_path("四国めたん"),
                    t_layers=registry.get_base_layers("四国めたん"),
                    t_paths=registry.get_base_paths("四国めたん"),
                    x_val=metan_layout["x"],
                    y_val=metan_layout["y"],
                    zoom_val=metan_layout["zoom"],
                    frm=frm,
                    lng=lng,
                )
                zunda_layout = registry.get_spatial_layout("ずんだもん", has_broll=False)
                add_or_coalesce_tachie(
                    char_name="ずんだもん",
                    t_layer=zunda_layout["layer"],
                    t_psd=registry.get_psd_path("ずんだもん"),
                    t_layers=registry.get_base_layers("ずんだもん"),
                    t_paths=registry.get_base_paths("ずんだもん"),
                    x_val=zunda_layout["x"],
                    y_val=zunda_layout["y"],
                    zoom_val=zunda_layout["zoom"],
                    frm=frm,
                    lng=lng,
                )

        # 3. Layer 0: Background ImageItem
        bg_candidate = Path(DEFAULT_BG_IMAGE_PATH).resolve()
        for gc in timeline_ir.global_clips:
            ti = gc.template_item or {}
            file_p = gc.file_path or ti.get("FilePath")
            if file_p and (
                "bg" in file_p.lower()
                or "room" in file_p.lower()
                or "classroom" in file_p.lower()
            ):
                bg_candidate = Path(file_p).resolve()
        items.append({
            "$type": "YukkuriMovieMaker.Project.Items.ImageItem, YukkuriMovieMaker",
            "FilePath": str(bg_candidate),
            "X": {"Values": [{"Value": 0.0}], "Span": 0.0, "AnimationType": "なし"},
            "Y": {"Values": [{"Value": 0.0}], "Span": 0.0, "AnimationType": "なし"},
            "Opacity": {"Values": [{"Value": 100.0}]},
            "Zoom": {"Values": [{"Value": 187.5}], "Span": 0.0, "AnimationType": "なし"},
            "Rotation": {"Values": [{"Value": 0.0}]},
            "Blend": "Normal",
            "Layer": 0,
            "Frame": 0,
            "Length": timeline_ir.total_frames,
            "VideoEffects": [],
        })

        # 4. Layer 1: B-Roll Images
        for d_img_clip in timeline_ir.dynamic_image_clips:
            items.append({
                "$type": "YukkuriMovieMaker.Project.Items.ImageItem, YukkuriMovieMaker",
                "FilePath": str(d_img_clip.image_path.resolve()),
                "X": {"Values": [{"Value": 0.0}], "Span": 0.0, "AnimationType": "なし"},
                "Y": {"Values": [{"Value": 0.0}], "Span": 0.0, "AnimationType": "なし"},
                "Opacity": {"Values": [{"Value": 100.0}]},
                "Zoom": {"Values": [{"Value": 100.0}], "Span": 0.0, "AnimationType": "なし"},
                "Rotation": {"Values": [{"Value": 0.0}]},
                "Blend": "Normal",
                "Layer": 1,
                "Frame": d_img_clip.start_frame,
                "Length": d_img_clip.length,
                "VideoEffects": [],
            })

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
        items.append({
            "$type": "YukkuriMovieMaker.Project.Items.AudioItem, YukkuriMovieMaker",
            "FilePath": str(bgm_path),
            "Volume": {"Values": [{"Value": 3.0}], "Span": 0.0, "AnimationType": "なし"},
            "Pan": {"Values": [{"Value": 0.0}]},
            "PlaybackRate": 100.0,
            "Layer": 3,
            "Frame": 0,
            "Length": timeline_ir.total_frames,
            "IsLooped": True,
        })

        # Assemble and write
        tl = get_timeline(output_data)
        tl["Items"] = items
        tl["Length"] = timeline_ir.total_frames
        tl["MaxLayer"] = 12

        self._write_output(output_data, output_path, use_bom)

        tachie_count = len([i for i in items if "TachieItem" in i.get("$type", "")])
        return CompilationResult(
            output_path=output_path,
            item_count=len(items),
            voice_item_count=len(timeline_ir.voice_clips),
            tachie_item_count=tachie_count,
            total_frames=timeline_ir.total_frames,
            total_duration_seconds=(
                timeline_ir.total_frames / timeline_ir.fps if timeline_ir.fps else 0.0
            ),
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
        """
        Renders a non-PSD template project using character template cloning.
        """
        output_path = Path(output_path)
        if output_data is None:
            output_data = copy.deepcopy(self.template_data)
        audio_files = audio_files or []
        effective_script_len = script_len if script_len is not None else len(timeline_ir.voice_clips)

        timeline = get_timeline(output_data)
        video_info = timeline.get("VideoInfo", {})
        width = video_info.get("Width", 1920)
        height = video_info.get("Height", 1080)
        is_vertical = height > width

        if is_vertical:
            sub_y = 300.0
            sub_size = 100.0
            tachie_cfg = {"X": 0.0, "Y": 650.0, "Zoom": 80.0}
            broll_cfg = {"X": 0.0, "Y": -300.0, "Zoom": 120.0}
        else:
            sub_y = 450.0
            sub_size = 80.0
            tachie_cfg = {"X": -650.0, "Y": 250.0, "Zoom": 65.0}
            broll_cfg = {"X": 350.0, "Y": -50.0, "Zoom": 80.0}

        for char in output_data.get("Characters", []):
            char["FontSize"] = sub_size
            char["Y"] = sub_y

        self.layout_cfg = {"tachie": tachie_cfg, "broll": broll_cfg}

        items: List[Dict[str, Any]] = []

        for clip in timeline_ir.voice_clips:
            template_item = self.character_templates[clip.character]["voice"]
            new_item = copy.deepcopy(template_item)
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
                hours = int(sec // 3600)
                mins = int((sec % 3600) // 60)
                secs = sec % 60
                new_item["VoiceLength"] = f"{hours:02d}:{mins:02d}:{secs:09.6f}0"
                new_item["FilePath"] = str(clip.audio_path.resolve())
                self._mute_voice_item(new_item)
                new_item["IsHidden"] = False

            effects = new_item.get("VideoEffects", [])
            if clip.motion == "jump":
                effects.append({
                    "$type": "YukkuriMovieMaker.Project.Effects.JumpEffect, YukkuriMovieMaker",
                    "Span": 0.5,
                    "Height": 50.0,
                })
            elif clip.motion == "shake":
                effects.append({
                    "$type": "YukkuriMovieMaker.Project.Effects.ShakeEffect, YukkuriMovieMaker",
                    "Amount": 20.0,
                    "Interval": 1.0,
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
            is_bg = (
                "bg" in str(d_img_clip.image_path).lower()
                or "room" in str(d_img_clip.image_path).lower()
                or "classroom" in str(d_img_clip.image_path).lower()
            )

            if not is_bg:
                zoom_val = broll_cfg["Zoom"]
                zoom_prop = {
                    "Values": [{"Value": 0.0}, {"Value": zoom_val}],
                    "Span": 0.2,
                    "AnimationType": "加減速移動",
                }
            else:
                zoom_prop = {
                    "Values": [{"Value": 100.0}],
                    "Span": 0.0,
                    "AnimationType": "なし",
                }

            image_item: Dict[str, Any] = {
                "$type": "YukkuriMovieMaker.Project.Items.ImageItem, YukkuriMovieMaker",
                "FilePath": str(d_img_clip.image_path.resolve()),
                "X": {
                    "Values": [{"Value": 0.0 if is_bg else broll_cfg["X"]}],
                    "Span": 0.0,
                    "AnimationType": "なし",
                },
                "Y": {
                    "Values": [{"Value": 0.0 if is_bg else broll_cfg["Y"]}],
                    "Span": 0.0,
                    "AnimationType": "なし",
                },
                "Opacity": {"Values": [{"Value": 100.0}]},
                "Zoom": zoom_prop,
                "Rotation": {"Values": [{"Value": 0.0}]},
                "Blend": "Normal",
                "Layer": 0 if is_bg else 1,
                "Frame": d_img_clip.start_frame,
                "Length": d_img_clip.length,
                "VideoEffects": [],
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
                    "Frame": d_img_clip.start_frame,
                    "Length": 60,
                    "Layer": 11,
                    "Blend": "Normal",
                    "VideoEffects": [],
                })

        for d_audio_clip in timeline_ir.dynamic_audio_clips:
            if d_audio_clip.length == -1:
                volume = 3.0  # ducking
            else:
                volume = 50.0

            length = (
                timeline_ir.total_frames - d_audio_clip.start_frame
                if d_audio_clip.length == -1
                else d_audio_clip.length
            )

            audio_item = {
                "$type": "YukkuriMovieMaker.Project.Items.AudioItem, YukkuriMovieMaker",
                "FilePath": str(d_audio_clip.audio_path.resolve()),
                "Volume": {
                    "Values": [{"Value": volume}],
                    "Span": 0.0,
                    "AnimationType": "なし",
                },
                "Pan": {"Values": [{"Value": 0.0}]},
                "PlaybackRate": 100.0,
                "Layer": 5,
                "Frame": d_audio_clip.start_frame,
                "Length": length,
                "IsLooped": d_audio_clip.length == -1,
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

        # Deep replace anonymized PSD path if environment variable is set
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
            total_duration_seconds=(
                timeline_ir.total_frames / timeline_ir.fps if timeline_ir.fps else 0.0
            ),
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
        self,
        text: str,
        frame: int,
        length: int,
        line: ScriptEntry,
    ) -> Optional[Dict[str, Any]]:
        """Creates a subtitle TextItem from the text template."""
        if self.text_template is None:
            return None
        text_item = copy.deepcopy(self.text_template)
        text_item["Text"] = text
        text_item["Frame"] = frame
        text_item["Length"] = length
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
        self,
        line: ScriptEntry,
        frame: int,
        length: int,
    ) -> Optional[Dict[str, Any]]:
        """Creates a facial expression item from face templates."""
        emotion = line.get("emotion", "neutral")
        char_name = line.get("character")
        if not char_name:
            return None
        char_faces = self.face_templates.get(char_name, {})
        template = char_faces.get(emotion)
        if template is None:
            return None
        face_item = cast(Dict[str, Any], copy.deepcopy(template))
        face_item["Layer"] = 1
        face_item["Frame"] = frame
        face_item["Length"] = length
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
        self,
        used_characters: Set[str],
        total_length: int,
        character_positions: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """Adds template-based tachie items for all speaking characters."""
        result: List[Dict[str, Any]] = []

        for char_name, templates in self.character_templates.items():
            if char_name in used_characters and templates["tachie"] is not None:
                tachie_item = copy.deepcopy(templates["tachie"])
                tachie_item["Layer"] = 1
                tachie_item["Frame"] = 0
                tachie_item["Length"] = total_length

                default_x = self.layout_cfg["tachie"]["X"]
                pos = character_positions.get(char_name, "left")
                final_x = 0.0 if pos == "center" else default_x

                self._set_animated_value(tachie_item, "X", final_x)
                self._set_animated_value(tachie_item, "Y", self.layout_cfg["tachie"]["Y"])
                self._set_animated_value(tachie_item, "Zoom", self.layout_cfg["tachie"]["Zoom"])
                result.append(tachie_item)

        return result

    @staticmethod
    def _write_output(output_data: Dict[str, Any], output_path: Path, use_bom: bool) -> None:
        """Writes project JSON to disk with optional UTF-8 BOM."""
        encoding = "utf-8-sig" if use_bom else "utf-8"
        with open(output_path, "w", encoding=encoding) as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)

    def export(
        self,
        ir: TimelineIR,
        output_path: Path,
        options: Optional[Dict[str, Any]] = None,
    ) -> ExportResult:
        """Export TimelineIR to YMM4 .ymmp project format."""
        opts = options or {}
        use_bom = opts.get("use_bom", False)
        script_len = opts.get("script_len", None)
        audio_files = opts.get("audio_files", None)
        out_p = Path(output_path)
        comp_res = self.render(
            timeline_ir=ir,
            output_path=out_p,
            use_bom=use_bom,
            script_len=script_len,
            audio_files=audio_files,
        )
        artifacts = [out_p]
        if comp_res.audio_files:
            artifacts.extend(comp_res.audio_files)
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
