"""
Premiere Pro exporter for Zundamon video timelines.

Provides both xmeml XML export (with pre-rendered PNG speech bubbles)
and a hybrid path that uses native Premiere Essential Graphics via
MCP MOGRT templates when the bridge is available.

Export Strategies:
    - xmeml with PNGs: Self-contained, works offline with any NLE
    - Hybrid MCP+xmeml: xmeml for BG/audio/character, MCP MOGRT for editable bubbles
    - SRT fallback: Generate .srt for Premiere caption track import (see srt_generator.py)
"""

import os
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .ir import TimelineIR
from .logging import logger
from .phonetics import get_audio_reactive_intervals, resolve_lipsync_intervals
from .typography import (
    calculate_speech_plate_geometry,
    draw_rounded_speech_bubble,
    wrap_japanese,
)

_wrap_japanese = wrap_japanese

__all__ = [
    "PremiereExporter",
    "get_audio_reactive_intervals",
    "resolve_lipsync_intervals",
    "prettify",
    "create_speech_bubble_png",
]


def prettify(elem: Element) -> str:
    """Return a pretty-printed XML string for the Element."""
    rough_string = tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    xml_str = reparsed.toprettyxml(indent="  ")
    if xml_str.startswith("<?xml"):
        xml_str = xml_str.split("\n", 1)[1]
    header = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n'
    return header + xml_str


def create_speech_bubble_png(
    text: str,
    out_path: Union[str, Path],
    border_color: Tuple[int, int, int] = (46, 139, 87),
) -> None:
    """Pre-render a Zundamon-style speech bubble to a PNG file.

    Creates a white rounded-rectangle with a dynamic border,
    drop shadow, and Meiryo Japanese typography.
    """
    geom = calculate_speech_plate_geometry(
        text=text,
        font_size=52,
        canvas_w=1920,
        canvas_h=1080,
        wrap_width=22,
        spacing=12,
        auto_scale_down=True,
        bottom_margin=40,
    )
    img = draw_rounded_speech_bubble(
        canvas_size=(1920, 1080),
        geometry=geom,
        border_color=border_color,
        fill_color=(255, 255, 255, 245),
        border_width=12,
        corner_radius=25,
        shadow_offset=(6, 6),
        shadow_color=(0, 0, 0, 130),
        shadow_blur=8,
        draw_text=True,
        text_color=(30, 30, 30, 255),
        text_spacing=12,
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)



class PremiereExporter:
    """Exports a TimelineIR to Premiere Pro via xmeml XML and/or MCP bridge.

    Supports three export modes:
        - ``export_xmeml``: Full xmeml with pre-rendered PNG speech bubbles (V1-V4 + audio)
        - ``export_xmeml_without_bubbles``: xmeml for BG/character/audio only (V1-V3 + audio)
        - ``export_native_bubbles``: Places native MOGRT Essential Graphics via MCP

    The hybrid ``export_to_premiere`` convenience function selects the right
    combination based on MCP bridge availability.
    """

    def __init__(self, ir: TimelineIR):
        self.ir = ir
        self.fps = ir.fps

    # ------------------------------------------------------------------
    # xmeml building blocks (shared between full and no-bubble exports)
    # ------------------------------------------------------------------

    def _build_xmeml_root(self) -> Tuple[Element, List[Element], List[Element], int, List[str]]:
        """Build the xmeml root structure with sequence, tracks, and audio.

        Returns:
            Tuple of (root, video_tracks, audio_tracks, total_frames, unique_chars)
        """
        fps = self.fps
        total_frames = int(self.ir.total_frames + fps * 2.0)

        root = Element('xmeml', version="4")
        project = SubElement(root, 'project')
        SubElement(project, 'name').text = 'Zundamon Project'
        children = SubElement(project, 'children')

        import time
        seq = SubElement(children, 'sequence')
        SubElement(seq, 'name').text = f"Main Timeline {int(time.time())}"
        SubElement(seq, 'duration').text = str(total_frames)

        rate = SubElement(seq, 'rate')
        SubElement(rate, 'timebase').text = str(fps)
        SubElement(rate, 'ntsc').text = 'FALSE'

        media = SubElement(seq, 'media')
        video = SubElement(media, 'video')

        vformat = SubElement(video, 'format')
        sc = SubElement(vformat, 'samplecharacteristics')
        s_rate = SubElement(sc, 'rate')
        SubElement(s_rate, 'timebase').text = str(fps)
        SubElement(s_rate, 'ntsc').text = 'FALSE'
        SubElement(sc, 'width').text = '1920'
        SubElement(sc, 'height').text = '1080'
        SubElement(sc, 'pixelaspectratio').text = 'square'

        unique_chars = list(dict.fromkeys(vc.character for vc in self.ir.voice_clips))
        if not unique_chars:
            unique_chars = ["ずんだもん"]

        video_tracks = []
        video_tracks.append(SubElement(video, 'track'))  # V1: BG
        video_tracks.append(SubElement(video, 'track'))  # V2: B-Roll
        for _ in unique_chars:
            video_tracks.append(SubElement(video, 'track'))  # V3+: Characters
        video_tracks.append(SubElement(video, 'track'))  # V(Last): Speech Bubbles

        audio = SubElement(media, 'audio')
        SubElement(audio, 'numOutputChannels').text = '2'
        a_format = SubElement(audio, 'format')
        a_sc = SubElement(a_format, 'samplecharacteristics')
        SubElement(a_sc, 'depth').text = '16'
        SubElement(a_sc, 'samplerate').text = '48000'

        audio_tracks = []
        audio_tracks.append(SubElement(audio, 'track'))  # A1: BGM
        for _ in unique_chars:
            audio_tracks.append(SubElement(audio, 'track'))  # A2+: Voices

        return root, video_tracks, audio_tracks, total_frames, unique_chars

    def _create_clipitem(
        self,
        track: Element,
        file_path: Union[str, Path],
        start_frame: int,
        duration: int,
        item_id: str,
        name: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        x_offset: float = 0.0,
        y_offset: float = 0.0,
        scale: float = 100.0,
        fit_to_screen: bool = False,
    ) -> None:
        """Create a clipitem element on a video track."""
        import time
        unique_id = f"{item_id}_{int(time.time() * 1000)}"
        from PIL import Image
        if not file_path or duration <= 0:
            return
        try:
            with Image.open(file_path) as img_f:
                fw, fh = img_f.size
        except Exception:
            fw, fh = 1920, 1080

        if width is None:
            width = fw
        if height is None:
            height = fh

        if fit_to_screen:
            scale_x = 1920.0 / fw
            scale_y = 1080.0 / fh
            scale = max(scale_x, scale_y) * 100.0

        fps = self.fps
        clip = SubElement(track, 'clipitem', id=unique_id)
        SubElement(clip, 'name').text = name
        SubElement(clip, 'duration').text = str(duration)
        SubElement(clip, 'start').text = str(start_frame)
        SubElement(clip, 'end').text = str(start_frame + duration)
        SubElement(clip, 'in').text = "0"
        SubElement(clip, 'out').text = str(duration)

        file = SubElement(clip, 'file', id=f"file_{unique_id}")
        SubElement(file, 'name').text = Path(file_path).name
        SubElement(file, 'pathurl').text = f"file://localhost/{str(Path(file_path).absolute()).replace(os.sep, '/')}"

        f_rate = SubElement(file, 'rate')
        SubElement(f_rate, 'timebase').text = str(fps)
        SubElement(f_rate, 'ntsc').text = 'FALSE'

        media_elem = SubElement(file, 'media')
        v_elem = SubElement(media_elem, 'video')
        v_sc = SubElement(v_elem, 'samplecharacteristics')
        SubElement(v_sc, 'width').text = str(width)
        SubElement(v_sc, 'height').text = str(height)

        filter_elem = SubElement(clip, 'filter')
        eff = SubElement(filter_elem, 'effect')
        SubElement(eff, 'name').text = 'Basic Motion'
        SubElement(eff, 'effectid').text = 'basic'
        SubElement(eff, 'effectcategory').text = 'motion'
        SubElement(eff, 'effecttype').text = 'motion'
        SubElement(eff, 'mediatype').text = 'video'

        param_scale = SubElement(eff, 'parameter')
        SubElement(param_scale, 'parameterid').text = 'scale'
        SubElement(param_scale, 'name').text = 'Scale'
        SubElement(param_scale, 'value').text = str(scale)

        param_center = SubElement(eff, 'parameter')
        SubElement(param_center, 'parameterid').text = 'center'
        SubElement(param_center, 'name').text = 'Center'
        val = SubElement(param_center, 'value')
        SubElement(val, 'horiz').text = str(x_offset)
        SubElement(val, 'vert').text = str(y_offset)

    def _populate_backgrounds(self, v1_track: Element, v2_track: Element, total_frames: int) -> None:
        """Populate V1 (background) and V2 (B-roll) tracks."""
        for i, gc in enumerate(self.ir.global_clips):
            file_path = gc.file_path or (gc.template_item.get("FilePath") if gc.template_item else None)
            if file_path and gc.item_type != "AudioItem" and ("Volume" not in gc.template_item):
                dur = total_frames if gc.length in (-1, 0) else gc.length
                self._create_clipitem(v1_track, file_path, gc.start_frame, dur, f"global_bg_{i}", "Background", fit_to_screen=True)

        for i, bg in enumerate(self.ir.dynamic_image_clips):
            if "bg" in str(bg.image_path).lower() or "classroom" in str(bg.image_path).lower():
                dur = total_frames if bg.length == -1 else bg.length
                self._create_clipitem(v1_track, bg.image_path, bg.start_frame, dur, f"bg_{i}", "Background", fit_to_screen=True)
            else:
                # B-Roll (V2) Full-Screen 1920x1080 Presentation Slide
                self._create_clipitem(v2_track, bg.image_path, bg.start_frame, bg.length, f"broll_{i}", "B-Roll", fit_to_screen=True)

    def _populate_character_lipsync(self, char_tracks: list, unique_chars: list, proj_dir: Path, total_frames: int) -> None:
        import math
        import os
        fps = self.fps
        faces_dir = Path("assets/faces").absolute()

        # Pre-calculate x_offsets based on the number of characters
        num_chars = len(unique_chars)
        x_offsets = {}

        # YMM4 Convention: Zundamon is usually the reactor (Right), Metan is explainer (Left)
        # We sort characters so that Zundamon is always pushed to the right side
        def char_sort_key(c: str) -> int:
            # Lower score = Left, Higher score = Right
            convention = {
                "四国めたん": 0,
                "春日部つむぎ": 1,
                "ずんだもん": 10
            }
            return convention.get(c, 5)

        sorted_chars = sorted(unique_chars, key=char_sort_key)

        if num_chars == 1:
            x_offsets[sorted_chars[0]] = 0.0
        elif num_chars == 2:
            x_offsets[sorted_chars[0]] = -0.32 # Left (Metan)
            x_offsets[sorted_chars[1]] = 0.28  # Right (Zundamon, moved inward from 0.42)
        else:
            spacing = 0.8 / (num_chars - 1)
            for i, c in enumerate(sorted_chars):
                x_offsets[c] = -0.4 + (i * spacing)

        # We need to track the current frame for EACH character independently
        current_frames = {c: 0 for c in unique_chars}

        # Precalculate scales for characters
        from PIL import Image
        import time
        run_id = int(time.time())
        char_metrics = {}
        for char in unique_chars:
            src_dir = faces_dir / char
            if not src_dir.exists():
                src_dir = faces_dir
            dst_dir = proj_dir / f"faces_{run_id}" / char
            dst_dir.mkdir(parents=True, exist_ok=True)
            import shutil
            for img_file in src_dir.glob("*.png"):
                new_name = f"{img_file.stem}_{run_id}{img_file.suffix}"
                shutil.copy(img_file, dst_dir / new_name)

            char_faces_dir = dst_dir
            z_body = str(char_faces_dir / f"neutral_closed_{run_id}.png")
            if not os.path.exists(z_body):
                z_body = str(dst_dir.parent / f"neutral_closed_{run_id}.png")
            img_h = Image.open(z_body).size[1]
            target_scale = round((1250 / img_h) * 100, 2)
            base_y = 0.13
            char_metrics[char] = {"scale": target_scale, "y": base_y, "dir": char_faces_dir}

        for i, vc in enumerate(self.ir.voice_clips):
            char_idx = unique_chars.index(vc.character)
            v_track = char_tracks[char_idx]
            c_frame = current_frames[vc.character]
            x_pos = x_offsets[vc.character]

            char_faces_dir = char_metrics[vc.character]["dir"]

            emo = vc.emotion if vc.emotion else "neutral"
            z_body = str(char_faces_dir / f"{emo}_closed_{run_id}.png")
            z_mouth = str(char_faces_dir / f"{emo}_open_{run_id}.png")
            if not os.path.exists(z_body):
                z_body = str(char_faces_dir / f"neutral_closed_{run_id}.png")
                z_mouth = str(char_faces_dir / f"neutral_open_{run_id}.png")
                if not os.path.exists(z_body):
                    z_body = str(dst_dir.parent / f"neutral_closed_{run_id}.png")
                    z_mouth = str(dst_dir.parent / f"neutral_open_{run_id}.png")

            target_scale = char_metrics[vc.character]["scale"]
            base_y = char_metrics[vc.character]["y"]

            if vc.start_frame > c_frame:
                gap_dur = vc.start_frame - c_frame
                self._create_clipitem(v_track, str(char_faces_dir / f"neutral_closed_{run_id}.png"), c_frame, gap_dur, f"{char_idx}_gap_{i}", f"{vc.character} Neutral", scale=target_scale, x_offset=x_pos, y_offset=base_y)

            # Lip-sync intervals (phonetic with companion .query.json fallback to audio-reactive)
            intervals = resolve_lipsync_intervals(
                audio_path=vc.audio_path,
                duration_sec=vc.length / fps,
                prefer_phonetic=True,
                fps=fps,
                audio_query=vc.audio_query,
            )

            f_curr = vc.start_frame
            for k, (is_open, dur) in enumerate(intervals):
                sprite = z_mouth if is_open else z_body

                # Physics motion
                t_rel = f_curr - vc.start_frame
                y_pos = base_y
                actual_x = x_pos
                if vc.motion == 'jump':
                    y_pos += -0.05 * abs(math.sin(t_rel / 15.0 * math.pi))

                state_label = f"{vc.character} {emo} {'Open' if is_open else 'Closed'}"
                self._create_clipitem(v_track, sprite, f_curr, dur, f"{char_idx}_{i}_{k}", state_label, scale=target_scale, x_offset=round(actual_x, 4), y_offset=round(y_pos, 4))
                f_curr += dur

            current_frames[vc.character] = vc.start_frame + vc.length

        for char_idx, char in enumerate(unique_chars):
            c_frame = current_frames[char]
            char_faces_dir = char_metrics[char]["dir"]

            tail_body = str(char_faces_dir / f"neutral_closed_{run_id}.png")
            if not os.path.exists(tail_body):
                tail_body = str(char_faces_dir.parent / f"neutral_closed_{run_id}.png")

            if c_frame < total_frames:
                self._create_clipitem(char_tracks[char_idx], tail_body, c_frame, total_frames - c_frame, f"{char_idx}_gap_end", f"{char} Neutral", scale=char_metrics[char]["scale"], x_offset=x_offsets[char], y_offset=char_metrics[char]["y"])

    def _populate_speech_bubbles(self, v4_track: Element, bubble_dir: Path) -> None:
        """Populate V4 track with pre-rendered PNG speech bubbles."""
        bubble_dir.mkdir(parents=True, exist_ok=True)

        char_colors = {
            "ずんだもん": (46, 139, 87),    # Green
            "四国めたん": (255, 105, 180),  # Pink
            "春日部つむぎ": (255, 165, 0), # Orange
        }

        import time
        run_id = int(time.time())
        for i, vc in enumerate(self.ir.voice_clips):
            bubble_path = bubble_dir / f"bubble_{i}_{run_id}_pro.png"
            border_color = char_colors.get(vc.character, (128, 128, 128))
            create_speech_bubble_png(vc.text, bubble_path, border_color)
            self._create_clipitem(v4_track, bubble_path, vc.start_frame, vc.length, f"bubble_{i}", "Subtitle Bar", scale=100.0, x_offset=0.0, y_offset=0.0)

    def _populate_audio(self, audio_tracks: list, unique_chars: list, total_frames: int) -> None:
        import os
        from pathlib import Path
        fps = self.fps
        a1_track = audio_tracks[0]

        # Global clips audio (BGM)
        for i, gc in enumerate(self.ir.global_clips):
            file_path = gc.file_path or (gc.template_item.get("FilePath") if gc.template_item else None)
            if file_path and (gc.item_type == "AudioItem" or "Volume" in gc.template_item):
                clip = SubElement(a1_track, 'clipitem', id=f"global_bgm_{i}")
                SubElement(clip, 'name').text = "BGM"
                SubElement(clip, 'duration').text = str(total_frames)
                SubElement(clip, 'start').text = "0"
                SubElement(clip, 'end').text = str(total_frames)
                SubElement(clip, 'in').text = "0"
                SubElement(clip, 'out').text = str(total_frames)

                file = SubElement(clip, 'file', id=f"file_global_bgm_{i}")
                SubElement(file, 'name').text = Path(file_path).name
                SubElement(file, 'pathurl').text = f"file://localhost/{str(Path(file_path).absolute()).replace(os.sep, '/')}"
                f_rate = SubElement(file, 'rate')
                SubElement(f_rate, 'timebase').text = str(fps)
                SubElement(f_rate, 'ntsc').text = 'FALSE'
                media_elem = SubElement(file, 'media')
                audio_elem = SubElement(media_elem, 'audio')
                a_sc = SubElement(audio_elem, 'samplecharacteristics')
                SubElement(a_sc, 'depth').text = '16'
                SubElement(a_sc, 'samplerate').text = '48000'
                SubElement(audio_elem, 'channelcount').text = '2'

                filter_elem = SubElement(clip, 'filter')
                effect = SubElement(filter_elem, 'effect')
                SubElement(effect, 'name').text = "Audio Levels"
                SubElement(effect, 'effectid').text = "audiolevels"
                SubElement(effect, 'effecttype').text = "audiolevels"
                SubElement(effect, 'mediatype').text = "audio"
                param = SubElement(effect, 'parameter')
                SubElement(param, 'parameterid').text = "level"
                SubElement(param, 'name').text = "Level"
                SubElement(param, 'value').text = "0.17"

        # Dynamic BGM
        for i, ac in enumerate(self.ir.dynamic_audio_clips):
            if ac.audio_path:
                clip = SubElement(a1_track, 'clipitem', id=f"bgm_{i}")
                SubElement(clip, 'name').text = "BGM"
                SubElement(clip, 'duration').text = str(total_frames)
                SubElement(clip, 'start').text = "0"
                SubElement(clip, 'end').text = str(total_frames)
                SubElement(clip, 'in').text = "0"
                SubElement(clip, 'out').text = str(total_frames)

                file = SubElement(clip, 'file', id=f"file_bgm_{i}")
                SubElement(file, 'name').text = Path(ac.audio_path).name
                SubElement(file, 'pathurl').text = f"file://localhost/{str(Path(ac.audio_path).absolute()).replace(os.sep, '/')}"
                f_rate = SubElement(file, 'rate')
                SubElement(f_rate, 'timebase').text = str(fps)
                SubElement(f_rate, 'ntsc').text = 'FALSE'
                media_elem = SubElement(file, 'media')
                audio_elem = SubElement(media_elem, 'audio')
                a_sc = SubElement(audio_elem, 'samplecharacteristics')
                SubElement(a_sc, 'depth').text = '16'
                SubElement(a_sc, 'samplerate').text = '48000'
                SubElement(audio_elem, 'channelcount').text = '2'

                filter_elem = SubElement(clip, 'filter')
                effect = SubElement(filter_elem, 'effect')
                SubElement(effect, 'name').text = "Audio Levels"
                SubElement(effect, 'effectid').text = "audiolevels"
                SubElement(effect, 'effecttype').text = "audiolevels"
                SubElement(effect, 'mediatype').text = "audio"
                param = SubElement(effect, 'parameter')
                SubElement(param, 'parameterid').text = "level"
                SubElement(param, 'name').text = "Level"
                SubElement(param, 'value').text = "0.17"

        # Voices
        for i, vc in enumerate(self.ir.voice_clips):
            if vc.audio_path:
                char_idx = unique_chars.index(vc.character)
                a_track = audio_tracks[1 + char_idx]

                clip = SubElement(a_track, 'clipitem', id=f"voice_{i}")
                SubElement(clip, 'name').text = f"Voice ({vc.character})"
                SubElement(clip, 'duration').text = str(vc.length)
                SubElement(clip, 'start').text = str(vc.start_frame)
                SubElement(clip, 'end').text = str(vc.start_frame + vc.length)
                SubElement(clip, 'in').text = "0"
                SubElement(clip, 'out').text = str(vc.length)

                file = SubElement(clip, 'file', id=f"file_voice_{i}")
                SubElement(file, 'name').text = Path(vc.audio_path).name
                SubElement(file, 'pathurl').text = f"file://localhost/{str(Path(vc.audio_path).absolute()).replace(os.sep, '/')}"
                f_rate = SubElement(file, 'rate')
                SubElement(f_rate, 'timebase').text = str(fps)
                SubElement(f_rate, 'ntsc').text = 'FALSE'
                media_elem = SubElement(file, 'media')
                audio_elem = SubElement(media_elem, 'audio')
                a_sc = SubElement(audio_elem, 'samplecharacteristics')
                SubElement(a_sc, 'depth').text = '16'
                SubElement(a_sc, 'samplerate').text = '48000'
                SubElement(audio_elem, 'channelcount').text = '2'

    def _write_xml(self, root: Element, output_path: Path) -> None:
        """Write the xmeml tree to a file."""
        xml_str = prettify(root)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml_str)

    # ------------------------------------------------------------------
    # Public export methods
    # ------------------------------------------------------------------

    def export_xmeml(self, xml_output_dir: Path, proj_dir: Path, xml_filename: Optional[str] = None) -> Path:
        """Full xmeml export with pre-rendered PNG speech bubbles on V4.

        This is the original export path — self-contained, works with any
        NLE that supports xmeml import.

        Args:
            xml_output_dir: Directory to write the .xml file to.
            proj_dir: Project directory (for faces and bubble output).
            xml_filename: Optional custom XML filename (e.g. '02_market_analysis_2026.xml').

        Returns:
            Path to the generated XML file.
        """
        bubble_dir = proj_dir / "04_GRAPHICS" / "TITLES" / "speech_bubbles"
        root, video_tracks, audio_tracks, total_frames, unique_chars = self._build_xmeml_root()

        self._populate_backgrounds(video_tracks[0], video_tracks[1], total_frames)

        # Populate characters
        char_tracks = video_tracks[2:-1]
        self._populate_character_lipsync(char_tracks, unique_chars, proj_dir, total_frames)

        # Populate bubbles
        bubble_track = video_tracks[-1]
        self._populate_speech_bubbles(bubble_track, bubble_dir)

        # Populate audio
        self._populate_audio(audio_tracks, unique_chars, total_frames)

        fname = xml_filename if xml_filename else "Zundamon_Episode_1_PRO.xml"
        output_path = xml_output_dir / fname
        self._write_xml(root, output_path)

        # Also ensure Zundamon_Episode_1_PRO.xml exists for backward compatibility
        if fname != "Zundamon_Episode_1_PRO.xml":
            import shutil
            shutil.copy2(output_path, xml_output_dir / "Zundamon_Episode_1_PRO.xml")

        logger.info(f"Successfully generated xmeml at {output_path}")
        logger.info(f"Successfully generated FCPXML at {output_path}")
        return output_path

    def export_xmeml_without_bubbles(self, xml_output_dir: Path, proj_dir: Path) -> Path:
        """Export xmeml with V1-V3 and audio tracks, but NO speech bubbles on V4.

        Use this when speech bubbles will be placed natively via the MCP
        MOGRT pipeline. V4 track is still created (empty) so that MOGRT
        clips placed by ``export_native_bubbles`` land on the correct track.

        Args:
            xml_output_dir: Directory to write the .xml file to.
            proj_dir: Project directory (for faces).

        Returns:
            Path to the generated XML file.
        """
        root, video_tracks, audio_tracks, total_frames, unique_chars = self._build_xmeml_root()

        self._populate_backgrounds(video_tracks[0], video_tracks[1], total_frames)
        char_tracks = video_tracks[2:-1]
        self._populate_character_lipsync(char_tracks, unique_chars, proj_dir, total_frames)
        # Bubble track left empty — bubbles placed via MCP
        self._populate_audio(audio_tracks, unique_chars, total_frames)

        output_path = xml_output_dir / "Zundamon_Episode_1_PRO.xml"
        self._write_xml(root, output_path)
        logger.info(f"Successfully generated xmeml (no bubbles) at {output_path}")
        logger.info(f"Successfully generated FCPXML (no bubbles) at {output_path}")
        return output_path

    def export_native_bubbles(
        self,
        mogrt_path: Union[str, Path],
        mcp_call: Callable[..., Any],
    ) -> List[Dict[str, Any]]:
        """Place native MOGRT Essential Graphics speech bubbles via MCP bridge.

        For each VoiceClip, this method:
        1. Calls ``import_mogrt`` to place the template on V4 at the correct timecode
        2. Calls ``get_mogrt_component`` to discover the text parameter ID
        3. Calls ``set_effect_property`` to inject the Japanese text

        Args:
            mogrt_path: Path to the .mogrt speech bubble template file.
            mcp_call: A callable that invokes MCP tools.
                      Signature: ``mcp_call(tool_name: str, arguments: dict) -> dict``

        Returns:
            List of placement results (one per voice clip).

        Raises:
            FileNotFoundError: If mogrt_path doesn't exist.
            RuntimeError: If MCP bridge calls fail.
        """
        mogrt_path = Path(mogrt_path)
        if not mogrt_path.exists():
            raise FileNotFoundError(f"MOGRT template not found: {mogrt_path}")

        fps = self.fps
        results = []

        for i, vc in enumerate(self.ir.voice_clips):
            start_seconds = vc.start_frame / fps
            duration_seconds = vc.length / fps
            text = _wrap_japanese(vc.text, width=25)

            try:
                # Step 1: Place the MOGRT on V4
                place_result = mcp_call("import_mogrt", {
                    "mogrt_path": str(mogrt_path.absolute()),
                    "start_seconds": start_seconds,
                    "duration_seconds": duration_seconds,
                    "track_index": 3,  # V4 (0-indexed)
                })

                # Step 2: Get the node_id of the placed clip
                node_id = place_result.get("node_id") or place_result.get("nodeId")
                if not node_id:
                    logger.warning(f"Could not get node_id for bubble {i}, skipping text injection")
                    results.append({"index": i, "status": "placed_no_text", "result": place_result})
                    continue

                # Step 3: Discover MOGRT text parameters
                component_result = mcp_call("get_mogrt_component", {
                    "node_id": node_id,
                })

                # Step 4: Set the text content
                # The text parameter name varies by template — try common names
                text_param_name = None
                for candidate in ["Source Text", "Text", "Headline", "headline", "text"]:
                    params = component_result.get("parameters", component_result.get("params", []))
                    if isinstance(params, list):
                        for p in params:
                            if p.get("name", "").lower() == candidate.lower():
                                text_param_name = p.get("name", candidate)
                                break
                    elif isinstance(params, dict) and candidate.lower() in [k.lower() for k in params.keys()]:
                        text_param_name = candidate
                    if text_param_name:
                        break

                if not text_param_name:
                    text_param_name = "Source Text"  # Sensible default for Essential Graphics

                mcp_call("set_effect_property", {
                    "node_id": node_id,
                    "effect_name": "MOGRT",
                    "property_name": text_param_name,
                    "value": text,
                })

                results.append({"index": i, "status": "success", "node_id": node_id})
                logger.info(f"Placed native bubble {i}: '{vc.text[:20]}...' at {start_seconds:.2f}s")

            except Exception as e:
                logger.error(f"Failed to place native bubble {i}: {e}")
                results.append({"index": i, "status": "error", "error": str(e)})

        return results

    def get_bubble_timing_data(self) -> List[Dict[str, Any]]:
        """Extract bubble timing data for external tools or debugging.

        Returns:
            List of dicts with text, start_seconds, duration_seconds, and character.
        """
        fps = self.fps
        return [
            {
                "index": i,
                "text": vc.text,
                "character": vc.character,
                "start_seconds": vc.start_frame / fps,
                "duration_seconds": vc.length / fps,
                "subtitle_position": vc.subtitle_position,
                "subtitle_style": vc.subtitle_style,
            }
            for i, vc in enumerate(self.ir.voice_clips)
        ]


# ======================================================================
# Top-level convenience functions
# ======================================================================


def generate_fcp_xml(ir: TimelineIR, xml_output_dir: Path, proj_dir: Path) -> None:
    """Backward-compatible wrapper — generates full xmeml with PNG bubbles.

    This is the original function signature preserved for existing callers.
    """
    exporter = PremiereExporter(ir)
    exporter.export_xmeml(xml_output_dir, proj_dir)


def export_to_premiere(
    ir: TimelineIR,
    xml_output_dir: Path,
    proj_dir: Path,
    mogrt_path: Optional[Union[str, Path]] = None,
    mcp_call: Optional[Callable[..., Any]] = None,
    xml_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """Hybrid export: xmeml + optional native MOGRT bubbles via MCP.

    If ``mcp_call`` and ``mogrt_path`` are provided, exports xmeml without
    bubbles on V4 and places native MOGRT Essential Graphics clips instead.
    Otherwise, falls back to the full xmeml export with PNG bubbles.

    Args:
        ir: Compiled TimelineIR.
        xml_output_dir: Directory for the .xml output.
        proj_dir: Project directory for assets.
        mogrt_path: Optional path to a .mogrt speech bubble template.
        mcp_call: Optional callable for MCP bridge invocations.
        xml_filename: Optional custom XML filename (e.g. '02_market_analysis_2026.xml').

    Returns:
        Dict with 'xml_path' and optionally 'bubble_results'.
    """
    exporter = PremiereExporter(ir)

    if mcp_call is not None and mogrt_path is not None:
        xml_path = exporter.export_xmeml_without_bubbles(xml_output_dir, proj_dir)
        bubble_results = exporter.export_native_bubbles(mogrt_path, mcp_call)
        return {
            "mode": "hybrid_mogrt",
            "xml_path": str(xml_path),
            "bubble_results": bubble_results,
        }
    else:
        xml_path = exporter.export_xmeml(xml_output_dir, proj_dir, xml_filename=xml_filename)
        return {
            "mode": "xmeml_png",
            "xml_path": str(xml_path),
        }
