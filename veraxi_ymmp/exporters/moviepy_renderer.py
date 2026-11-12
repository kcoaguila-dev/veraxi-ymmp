import math
from dataclasses import dataclass, field
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, cast

import numpy as np

if "IMAGEIO_FFMPEG_EXE" in os.environ and not os.environ["IMAGEIO_FFMPEG_EXE"]:
    del os.environ["IMAGEIO_FFMPEG_EXE"]
if not os.environ.get("IMAGEIO_FFMPEG_EXE"):
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        try:
            import glob
            import imageio_ffmpeg._utils as _imgio_utils
            _bins = glob.glob(os.path.join(_imgio_utils._get_bin_dir(), "ffmpeg*"))
            if _bins:
                ffmpeg_bin = _bins[0]
        except Exception:
            pass
    if ffmpeg_bin:
        os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_bin

from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoClip,
    VideoFileClip,
)

from veraxi_ymmp.core.constants import DEFAULT_BGM_DUCKING_VOLUME
from veraxi_ymmp.core.ir import TimelineIR
from veraxi_ymmp.core.logging import logger
from veraxi_ymmp.audio.phonetics import extract_phonetic_blocks
from veraxi_ymmp.core.ports import ExportResult
from veraxi_ymmp.graphics.typography import (
    calculate_speech_plate_geometry,
    draw_rounded_speech_bubble,
    get_char_color,
)


def _ensure_ffmpeg_env() -> None:
    """Configure IMAGEIO_FFMPEG_EXE from system PATH if not already set."""
    if not os.environ.get("IMAGEIO_FFMPEG_EXE"):
        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_bin


def _is_background_clip(ic: Any) -> bool:
    """Return True if the dynamic image clip represents a background rather than B-roll."""
    return bool(
        getattr(ic, "is_bg", False)
        or any(k in str(ic.image_path).lower() for k in ("bg", "room", "classroom"))
    )


def create_speech_bubble(
    text: str,
    duration: float,
    border_color: Tuple[int, int, int, int] = (0, 128, 0, 255),
    is_vertical: bool = False,
) -> ImageClip:
    """Creates a beautiful white speech bubble with a dynamic border, drop shadow, and wrapped black text."""
    target_canvas_w = 980 if is_vertical else 1920
    target_canvas_h = 320 if is_vertical else 360
    target_wrap_w = 16 if is_vertical else 20
    target_font_size = 46 if is_vertical else 52

    geom = calculate_speech_plate_geometry(
        text=text,
        font_size=target_font_size,
        canvas_w=target_canvas_w,
        canvas_h=target_canvas_h,
        wrap_width=target_wrap_w,
        spacing=12,
        auto_scale_down=True,
    )
    effective_canvas_h = max(target_canvas_h, int(geom.box_h) + 80)
    if effective_canvas_h != target_canvas_h:
        geom = calculate_speech_plate_geometry(
            text=text,
            font_size=target_font_size,
            canvas_w=target_canvas_w,
            canvas_h=effective_canvas_h,
            wrap_width=target_wrap_w,
            spacing=12,
            auto_scale_down=True,
        )
    img = draw_rounded_speech_bubble(
        canvas_size=(target_canvas_w, effective_canvas_h),
        geometry=geom,
        border_color=border_color,
        fill_color=(255, 255, 255, 248),
        border_width=7,
        corner_radius=22,
        shadow_offset=(3, 4),
        shadow_color=(0, 0, 0, 85),
        shadow_blur=8,
        draw_text=True,
        text_color=(24, 24, 27, 255),
        text_spacing=12,
    )
    img_array = np.array(img)
    clip = ImageClip(img_array).with_duration(duration)

    from moviepy.video.fx import Resize
    def pop_in(t: float) -> float:
        if t < 0.15:
            return 0.8 + (t / 0.15) * 0.2
        return 1.0

    if is_vertical:
        layout_y = 1380
    else:
        layout_y = int(round(1030.0 - geom.box_y - geom.box_h))
    setattr(clip, "layout_y", layout_y)
    setattr(clip, "geom", geom)
    return clip.with_effects([Resize(pop_in)])


@dataclass
class _RenderContext:
    """Mutable state shared by the MoviePyRenderer.render stage functions.

    ``render`` is a thin sequencer; each stage reads and writes the fields
    it needs here instead of threading dozens of locals through the old
    463-line monolith.
    """

    ir: TimelineIR
    fps: int
    total_duration: float
    is_vertical: bool
    target_w: int
    target_h: int
    video_clips: List[Any] = field(default_factory=list)
    audio_clips: List[Any] = field(default_factory=list)
    frame_to_time: Dict[int, float] = field(default_factory=lambda: {0: 0.0})
    talk_times: List[Tuple[float, float, str, Any, str]] = field(default_factory=list)
    bubbles_list: List[Any] = field(default_factory=list)
    char_open_intervals: Dict[str, List[Tuple[float, float]]] = field(default_factory=dict)
    unique_chars: List[str] = field(default_factory=list)
    x_offsets: Dict[str, Union[str, int, float]] = field(default_factory=dict)
    char_height: int = 1250
    y_pos: float = 80.0
    right_side_chars: List[str] = field(default_factory=list)
    has_alternating_right: bool = False
    broll_ranges: List[Tuple[float, float]] = field(default_factory=list)
    bgs: List[Any] = field(default_factory=list)
    brolls: List[Any] = field(default_factory=list)
    get_active_right_char: Optional[Callable[[float], str]] = None
    is_in_broll: Optional[Callable[[float], bool]] = None
    get_active_speaker: Optional[Callable[[float], Optional[str]]] = None



class MoviePyRenderer:
    def __init__(
        self,
        timeline_ir: Optional[TimelineIR] = None,
        fast_qa_duration: Optional[float] = None,
    ) -> None:
        _ensure_ffmpeg_env()
        self.ir = timeline_ir
        self.fast_qa_duration: Optional[float] = fast_qa_duration
        self.final_video: Optional[Any] = None

    def _make_render_context(self) -> _RenderContext:
        """Setup stage: validate the IR and resolve canvas geometry."""
        if self.ir is None:
            raise ValueError("TimelineIR must be provided to render")
        ir = self.ir
        fps = ir.fps
        t_data = getattr(ir, "template_data", {})
        tl = t_data.get("Timelines", [{}])[0] if t_data.get("Timelines") else t_data.get("Timeline", {})
        v_info = tl.get("VideoInfo", {}) if isinstance(tl, dict) else {}
        is_vertical = bool(v_info.get("Height", 1080) > v_info.get("Width", 1920))
        return _RenderContext(
            ir=ir,
            fps=fps,
            total_duration=ir.total_frames / fps,
            is_vertical=is_vertical,
            target_w=1080 if is_vertical else 1920,
            target_h=1920 if is_vertical else 1080,
        )

    def render(
        self,
        output_path: Optional[str] = None,
        preset: str = "ultrafast",
        crf: Optional[int] = None,
    ) -> None:
        """Render the video: a thin sequencer over the stage functions."""
        ctx = self._make_render_context()
        self._build_voice_track(ctx)
        self._add_global_clips(ctx)
        self._add_dynamic_images(ctx)
        self._add_base_background(ctx)
        self._add_dynamic_videos(ctx)
        self._layout_characters(ctx)
        self._compose_characters(ctx)
        final_video = self._compose_scene(ctx)
        final_video = self._mix_audio(ctx, final_video)
        self._write_output(ctx, final_video, output_path, preset, crf)

    def _build_voice_track(self, ctx: _RenderContext) -> None:
        """Voice stage: real-time mapping, voice audio, bubbles, lip-sync intervals."""
        # 1. First, process voice clips to build a real-time mapping!
        ctx.frame_to_time = {0: 0.0}
        current_time = 0.0
        ctx.talk_times = []
        audio_readers = []
        ctx.bubbles_list = []
        ctx.char_open_intervals = {}

        for vc in ctx.ir.voice_clips:
            start_time = current_time
            ctx.frame_to_time[vc.start_frame] = start_time

            if vc.audio_path:
                ac = AudioFileClip(str(vc.audio_path))
                dur = ac.duration + 0.3
            else:
                dur = vc.length / ctx.fps

            ctx.talk_times.append((start_time, start_time + dur, vc.emotion, getattr(vc, "motion", "none"), vc.character))
            if vc.audio_path:
                audio_readers.append((start_time, start_time + dur, ac, vc.character))
                ctx.audio_clips.append(ac.with_start(start_time))

            # Sliced phonetic open intervals for speech lip-sync
            if vc.character not in ctx.char_open_intervals:
                ctx.char_open_intervals[vc.character] = []
            blocks = extract_phonetic_blocks(vc.audio_query, dur, fps=ctx.fps)
            for b_s, b_e, is_open in blocks:
                if is_open:
                    ctx.char_open_intervals[vc.character].append((start_time + b_s, start_time + b_e))

            border_color = get_char_color(vc.character)

            bubble = create_speech_bubble(vc.text, dur, border_color, is_vertical=ctx.is_vertical).with_start(start_time)
            bubble_y = getattr(bubble, "layout_y", 1380 if ctx.is_vertical else 725)
            bubble = bubble.with_position(("center", bubble_y))
            ctx.bubbles_list.append(bubble)

            current_time += dur
            ctx.frame_to_time[vc.start_frame + vc.length] = current_time

        ctx.total_duration = current_time + 2.0

    def _add_global_clips(self, ctx: _RenderContext) -> None:
        """Global clips stage: template background and BGM items."""
        # 2. Global clips (BG, BGM)
        for gc in ctx.ir.global_clips:
            t_item = gc.template_item or {}
            file_path = gc.file_path or t_item.get("FilePath")

            if not file_path:
                continue

            path = Path(file_path)
            if not path.exists():
                continue

            if gc.item_type == "AudioItem" or "Volume" in t_item:
                audio_clip = AudioFileClip(str(path))
                if audio_clip.duration > ctx.total_duration:
                    audio_clip = audio_clip.subclipped(0, ctx.total_duration)
                audio_clip = audio_clip.with_volume_scaled(DEFAULT_BGM_DUCKING_VOLUME / 100.0)
                ctx.audio_clips.append(audio_clip.with_start(0))
            else:
                img_clip = ImageClip(str(path)).with_duration(ctx.total_duration).with_position("center")
                ctx.video_clips.append(img_clip)

    def _add_dynamic_images(self, ctx: _RenderContext) -> None:
        """Per-clip compose (images): dynamic B-roll and background slides."""
        # 2. Dynamic B-Roll (Shown directly, clean and normal)
        ctx.bgs = []
        ctx.brolls = []
        for d_clip in ctx.ir.dynamic_image_clips:
            is_bg = _is_background_clip(d_clip)

            # Use real time mapping instead of raw frames!
            start_t = ctx.frame_to_time.get(d_clip.start_frame, d_clip.start_frame / ctx.fps)
            end_frame = d_clip.start_frame + d_clip.length

            if d_clip.length == -1 or end_frame not in ctx.frame_to_time:
                dur = ctx.total_duration - start_t
            else:
                dur = ctx.frame_to_time[end_frame] - start_t

            if is_bg:
                img = ImageClip(str(d_clip.image_path)).with_start(start_t).with_duration(dur)
                if ctx.is_vertical:
                    img = img.resized(height=1920).with_position("center")
                else:
                    img = img.resized((1920, 1080)).with_position("center")
                ctx.bgs.append(img)
            else:
                img = ImageClip(str(d_clip.image_path)).with_start(start_t).with_duration(dur)
                if ctx.is_vertical:
                    img = (img if getattr(img, "w", 0) == 1080 else img.resized(width=1080)).with_position(("center", 60))
                else:
                    img = img.resized((1920, 1080)).with_position("center")
                ctx.brolls.append(img)


    def _add_dynamic_videos(self, ctx: _RenderContext) -> None:
        """Per-clip compose (videos): ingested DynamicVideoClips above B-roll.

        Each clip is subclipped to [in_point, in_point + placed duration],
        resized to the canvas like B-roll images, and stripped of audio
        when muted (the default — voices/BGM are mixed separately).
        """
        for v_clip in ctx.ir.dynamic_video_clips:
            if v_clip.length <= 0:
                continue
            start_t = ctx.frame_to_time.get(
                v_clip.start_frame, v_clip.start_frame / ctx.fps
            )
            end_frame = v_clip.start_frame + v_clip.length
            if end_frame in ctx.frame_to_time:
                dur = ctx.frame_to_time[end_frame] - start_t
            else:
                dur = v_clip.length / ctx.fps
            try:
                src = VideoFileClip(str(v_clip.video_path))
            except Exception as e:
                logger.error(f"Failed to load video clip {v_clip.video_path}: {e}")
                continue
            end_t = min(v_clip.in_point + dur, src.duration)
            clip = src.subclipped(v_clip.in_point, end_t)
            if v_clip.muted:
                clip = clip.without_audio()
            if ctx.is_vertical:
                clip = clip.resized(width=1080).with_position(("center", 60))
            else:
                clip = clip.resized((1920, 1080)).with_position("center")
            ctx.video_clips.append(clip.with_start(start_t).with_duration(dur))

    def _add_base_background(self, ctx: _RenderContext) -> None:
        """Base background stage: classroom.jpg or the default_dark.png fallback."""
        # Base Background (Layer 0) - ensure default background is always present under slides
        # Optional local classroom.jpg is preferred; default_dark.png is the
        # committed fallback when it is absent (see assets/ASSETS.md).
        from veraxi_ymmp.core.constants import resolve_background_image
        default_bg_path = resolve_background_image()
        if default_bg_path.exists():
            bg_img = ImageClip(str(default_bg_path)).with_duration(ctx.total_duration)
            if ctx.is_vertical:
                bg_img = bg_img.resized(height=1920).with_position("center")
            else:
                bg_img = bg_img.resized((1920, 1080)).with_position("center")
            ctx.video_clips.insert(0, bg_img)
        else:
            # Fallback to in-memory Pro Dark Slate (#0F172A) canvas
            bg_size = (1080, 1920) if ctx.is_vertical else (1920, 1080)
            fallback_bg = ColorClip(size=bg_size, color=(15, 23, 42), duration=ctx.total_duration).with_position("center")
            ctx.video_clips.insert(0, fallback_bg)

        ctx.video_clips.extend(ctx.bgs)
        ctx.video_clips.extend(ctx.brolls)

    def _layout_characters(self, ctx: _RenderContext) -> None:
        """Character layout stage: positions, offsets and b-roll ranges."""
        # 3. Dynamic Characters
        ctx.unique_chars = []
        for vc in ctx.ir.voice_clips:
            if vc.character not in ctx.unique_chars:
                ctx.unique_chars.append(vc.character)

        # Calculate X offsets based on number of characters
        num_chars = len(ctx.unique_chars)
        ctx.x_offsets = {}

        # YMM4 Convention: Zundamon is usually the reactor (Right), Metan is explainer (Left)
        def char_sort_key(c: str) -> int:
            convention = {
                "四国めたん": 0,
                "春日部つむぎ": 1,
                "ずんだもん": 10
            }
            return convention.get(c, 5)

        sorted_chars = sorted(ctx.unique_chars, key=char_sort_key)

        char_positions: Dict[str, str] = {}
        for cclip in getattr(ctx.ir, "character_clips", []):
            if cclip.character not in char_positions:
                char_positions[cclip.character] = cclip.position

        ctx.right_side_chars = [
            c for c in ctx.unique_chars
            if char_positions.get(c) == "right" or c in ["ずんだもん", "春日部つむぎ"]
        ]
        ctx.has_alternating_right = len(ctx.right_side_chars) > 1

        def get_active_right_char(t: float) -> str:
            active = ctx.right_side_chars[0] if ctx.right_side_chars else ""
            for st, et, _, _, spk in ctx.talk_times:
                if spk in ctx.right_side_chars:
                    if st <= t:
                        active = spk
                    if st <= t <= et:
                        return spk
            return active

        if ctx.is_vertical:
            ctx.char_height = 800
            ctx.y_pos = 1920 - ctx.char_height - 300
            if ctx.has_alternating_right:
                for c in ctx.unique_chars:
                    ctx.x_offsets[c] = 470 if c in ctx.right_side_chars else 30
            elif num_chars == 1:
                ctx.x_offsets[sorted_chars[0]] = 'center'
            elif num_chars == 2:
                ctx.x_offsets[sorted_chars[0]] = 30   # Left (Metan)
                ctx.x_offsets[sorted_chars[1]] = 470  # Right (Zundamon)
            else:
                spacing = (1080 - 400) / max(num_chars - 1, 1)
                for i, c in enumerate(sorted_chars):
                    ctx.x_offsets[c] = int(i * spacing)
        else:
            ctx.char_height = 1250
            ctx.y_pos = 1080 - ctx.char_height + 250
            if ctx.has_alternating_right:
                for c in ctx.unique_chars:
                    ctx.x_offsets[c] = 1180 if c in ctx.right_side_chars else 80
            elif num_chars == 1:
                ctx.x_offsets[sorted_chars[0]] = 'center'
            elif num_chars == 2:
                ctx.x_offsets[sorted_chars[0]] = 80   # Left (Metan)
                ctx.x_offsets[sorted_chars[1]] = 1180 # Right (Zundamon)
            else:
                spacing = (1920 - 700) / (num_chars - 1)
                for i, c in enumerate(sorted_chars):
                    ctx.x_offsets[c] = int(i * spacing)

        ctx.broll_ranges = []
        for d_clip in ctx.ir.dynamic_image_clips:
            is_bg = _is_background_clip(d_clip)
            if not is_bg:
                s_t = ctx.frame_to_time.get(d_clip.start_frame, d_clip.start_frame / ctx.fps)
                e_fr = d_clip.start_frame + d_clip.length
                d_t = ctx.total_duration - s_t if d_clip.length == -1 or e_fr not in ctx.frame_to_time else (ctx.frame_to_time[e_fr] - s_t)
                ctx.broll_ranges.append((s_t, s_t + d_t))

        def is_in_broll(t: float) -> bool:
            for bs, be in ctx.broll_ranges:
                if bs <= t <= be:
                    return True
            return False

        def get_active_speaker(t: float) -> Optional[str]:
            for st, et, _, _, spk in ctx.talk_times:
                if st <= t <= et:
                    return spk
            return None

        ctx.get_active_right_char = get_active_right_char
        ctx.is_in_broll = is_in_broll
        ctx.get_active_speaker = get_active_speaker
    def _compose_character(self, ctx: _RenderContext, char: str) -> None:
        """Per-clip compose: one character's lip-sync video clip."""
        is_in_broll = cast(Callable[[float], bool], ctx.is_in_broll)
        get_active_speaker = cast(Callable[[float], Optional[str]], ctx.get_active_speaker)
        get_active_right_char = cast(Callable[[float], str], ctx.get_active_right_char)
        char_faces_dir = Path("assets/faces") / char
        if not char_faces_dir.exists():
            char_faces_dir = Path("assets/faces")

        emotion_clips = {}
        for emotion in ["neutral", "happy", "angry", "sad", "surprised"]:
            path_open = char_faces_dir / f"{emotion}_open.png"
            path_closed = char_faces_dir / f"{emotion}_closed.png"
            if not path_open.exists():
                path_open = char_faces_dir / "neutral_open.png"
                path_closed = char_faces_dir / "neutral_closed.png"
                if not path_open.exists():
                    path_open = Path("assets/faces/neutral_open.png")
                    path_closed = Path("assets/faces/neutral_closed.png")

            if path_open.exists() and path_closed.exists():
                c_open = ImageClip(str(path_open)).resized(height=ctx.char_height)
                c_closed = ImageClip(str(path_closed)).resized(height=ctx.char_height)
                emotion_clips[emotion] = {
                    "open_img": np.array(c_open.get_frame(0)),
                    "closed_img": np.array(c_closed.get_frame(0)),
                    "open_mask": np.array(c_open.mask.get_frame(0)),
                    "closed_mask": np.array(c_closed.mask.get_frame(0))
                }

        def make_bounce_offset(c_name: str, base_x: Union[str, int, float]) -> Callable[[float], Tuple[Union[str, int, float], float]]:
            def get_bounce_offset(t: float) -> Tuple[Union[str, int, float], float]:
                bx: Union[str, int, float] = base_x
                by: float = float(ctx.y_pos)
                if is_in_broll(t):
                    spk = get_active_speaker(t)
                    if not ctx.is_vertical:
                        if spk == c_name:
                            bx = 1350
                            by = 240.0
                        else:
                            return (-9999, -9999.0)
                elif ctx.has_alternating_right and c_name in ctx.right_side_chars:
                    if get_active_right_char(t) != c_name:
                        return (-9999, -9999.0)

                for st, et, emo, motion, char_speaker in ctx.talk_times:
                    if st <= t <= et and char_speaker == c_name:
                        if motion == "jump":
                            by += max(-20.0, -40.0 * abs(math.sin(math.pi * (t - st) / 0.5)))
                        return (bx, by)
                return (bx, by)
            return get_bounce_offset

        def get_mouth_state(t: float, c_name: str) -> bool:
            # Check exact mora-synchronized vowel intervals (the rival standard)
            intervals = ctx.char_open_intervals.get(c_name, [])
            for op_s, op_e in intervals:
                if op_s <= t < op_e:
                    return True
            return False

        def get_current_emotion(t: float, c_name: str) -> str:
            for st, et, emo, motion, char_speaker in ctx.talk_times:
                if st <= t <= et and char_speaker == c_name:
                    return str(emo)
            return "neutral"

        def make_mouth_image(c_name: str, e_clips: Dict[str, Dict[str, Any]]) -> Callable[[float], np.ndarray]:
            def get_mouth_image(t: float) -> np.ndarray:
                emo = get_current_emotion(t, c_name)
                if emo not in e_clips:
                    emo = "neutral"
                if emo not in e_clips:
                    return np.zeros((700, 700, 3), dtype=np.uint8)
                is_open = get_mouth_state(t, c_name)
                val = e_clips[emo]["open_img"] if is_open else e_clips[emo]["closed_img"]
                return cast(np.ndarray, val)
            return get_mouth_image

        def make_mouth_mask(c_name: str, e_clips: Dict[str, Dict[str, Any]]) -> Callable[[float], np.ndarray]:
            def get_mouth_mask(t: float) -> np.ndarray:
                if is_in_broll(t) and not ctx.is_vertical:
                    spk = get_active_speaker(t)
                    if spk != c_name:
                        h, w = e_clips["neutral"]["open_mask"].shape[:2] if "neutral" in e_clips else (700, 700)
                        return np.zeros((h, w), dtype=np.uint8)
                elif ctx.has_alternating_right and c_name in ctx.right_side_chars:
                    if get_active_right_char(t) != c_name:
                        h, w = e_clips["neutral"]["open_mask"].shape[:2] if "neutral" in e_clips else (700, 700)
                        return np.zeros((h, w), dtype=np.uint8)
                emo = get_current_emotion(t, c_name)
                if emo not in e_clips:
                    emo = "neutral"
                if emo not in e_clips:
                    return np.zeros((700, 700), dtype=np.uint8)
                is_open = get_mouth_state(t, c_name)
                val = e_clips[emo]["open_mask"] if is_open else e_clips[emo]["closed_mask"]
                return cast(np.ndarray, val)
            return get_mouth_mask

        c_clip = VideoClip(frame_function=make_mouth_image(char, emotion_clips)).with_duration(ctx.total_duration)
        c_mask = VideoClip(frame_function=make_mouth_mask(char, emotion_clips), is_mask=True).with_duration(ctx.total_duration)
        c_clip = c_clip.with_mask(c_mask).with_position(make_bounce_offset(char, ctx.x_offsets[char]))
        ctx.video_clips.append(c_clip)

    def _compose_characters(self, ctx: _RenderContext) -> None:
        """Compose every character clip onto the scene."""
        for char in ctx.unique_chars:
            self._compose_character(ctx, char)

    def _apply_camera(self, ctx: _RenderContext, scene_video: Any) -> Any:
        """Virtual camera stage: pan, zoom, punch-in and shake."""
        # Apply Dynamic Virtual Camera Shot IR (Pan, Zoom, Punch-in, Shake)
        camera_shots = getattr(ctx.ir, "camera_shots", [])
        has_dynamic_shots = any(
            (shot.zoom > 1.01 or shot.pan_x != 0.0 or shot.pan_y != 0.0 or getattr(shot, "shake_frames", 0) > 0)
            for shot in camera_shots
        )
        if camera_shots and has_dynamic_shots:
            from PIL import Image

            def get_active_camera_shot(t: float) -> Optional[Any]:
                fr = int(t * ctx.fps)
                for shot in camera_shots:
                    if shot.start_frame <= fr < shot.start_frame + shot.length:
                        return shot
                return None

            base_frame_fn = scene_video.frame_function

            def camera_frame_fn(t: float) -> np.ndarray:
                frame = cast(np.ndarray, base_frame_fn(t))
                shot = get_active_camera_shot(t)
                if shot is None or (shot.zoom <= 1.01 and shot.pan_x == 0.0 and shot.pan_y == 0.0):
                    return frame

                zoom = max(1.0, float(shot.zoom))
                pan_x = float(shot.pan_x)
                pan_y = float(shot.pan_y)

                if getattr(shot, "shake_frames", 0) > 0:
                    fr = int(t * ctx.fps)
                    elapsed_fr = fr - shot.start_frame
                    if elapsed_fr < shot.shake_frames:
                        shake_sign = 1 if (elapsed_fr % 2 == 0) else -1
                        pan_x += shake_sign * 8.0
                        pan_y -= shake_sign * 4.0

                h, w = frame.shape[:2]
                crop_w = int(w / zoom)
                crop_h = int(h / zoom)

                cx = int(w / 2.0 + pan_x)
                cy = int(h / 2.0 + pan_y)

                x1 = max(0, min(w - crop_w, cx - crop_w // 2))
                y1 = max(0, min(h - crop_h, cy - crop_h // 2))
                x2 = x1 + crop_w
                y2 = y1 + crop_h

                cropped = frame[y1:y2, x1:x2]
                img = Image.fromarray(cropped)
                resized = img.resize((w, h), Image.Resampling.BILINEAR)
                return cast(np.ndarray, np.array(resized))

            scene_video = VideoClip(frame_function=camera_frame_fn).with_duration(ctx.total_duration)

        return scene_video

    def _compose_scene(self, ctx: _RenderContext) -> Any:
        """Composite the scene, apply the virtual camera, overlay bubbles."""
        logger.info("Compositing scene elements...")
        scene_video = CompositeVideoClip(ctx.video_clips, size=(ctx.target_w, ctx.target_h)).with_duration(ctx.total_duration)
        scene_video = self._apply_camera(ctx, scene_video)

        # Overlay HUD speech bubbles above virtual camera rig
        if ctx.bubbles_list:
            logger.info("Overlaying speech bubbles above virtual camera rig...")
            return CompositeVideoClip([scene_video, *ctx.bubbles_list], size=(ctx.target_w, ctx.target_h)).with_duration(ctx.total_duration)
        return scene_video

    def _mix_audio(self, ctx: _RenderContext, final_video: Any) -> Any:
        """Audio mix stage: dynamic BGM/SFX, composite audio, fade-out."""
        # 6. Global Audio (BGM/SFX)
        from moviepy.audio.fx import AudioFadeOut

        for clip in ctx.ir.dynamic_audio_clips:
            if not clip.audio_path:
                continue

            try:
                ac = AudioFileClip(str(clip.audio_path))
                if clip.length == -1: # Looped BGM
                    dur = ctx.total_duration - (clip.start_frame/ctx.fps)
                    duck_factor = (DEFAULT_BGM_DUCKING_VOLUME / 100.0) if ctx.talk_times else 1.0
                    vol = clip.volume * duck_factor if clip.volume > 0.5 else clip.volume
                    ac = ac.subclipped(0, min(dur, ac.duration)).with_volume_scaled(vol)
                    ac = ac.with_effects([AudioFadeOut(2.0)])
                else:
                    dur = clip.length / ctx.fps
                    ac = ac.subclipped(0, min(dur, ac.duration)).with_volume_scaled(clip.volume)
                ctx.audio_clips.append(ac.with_start(clip.start_frame/ctx.fps))
            except Exception as e:
                logger.error(f"Failed to load audio {clip.audio_path}: {e}")

        if ctx.audio_clips:
            final_audio = CompositeAudioClip(ctx.audio_clips).with_duration(ctx.total_duration)
            final_video = final_video.with_audio(final_audio)

        from moviepy.video.fx import FadeOut
        final_video = final_video.with_effects([FadeOut(2.0)])
        return final_video

    def _write_output(self, ctx: _RenderContext, final_video: Any, output_path: Optional[str], preset: str, crf: Optional[int]) -> None:
        """Write stage: fast-QA trim and write_videofile."""
        self.final_video = final_video
        if output_path is None:
            return
        logger.info(f"Writing to {output_path}...")
        # Fast QA override if requested
        if self.fast_qa_duration is not None:
            final_video = final_video.subclipped(0, min(self.fast_qa_duration, ctx.total_duration))

        ffmpeg_params = []
        if crf is not None:
            ffmpeg_params.extend(["-crf", str(crf)])

        has_audio = final_video.audio is not None
        write_kwargs: Dict[str, Any] = {
            "fps": 30,
            "codec": "libx264",
            "preset": preset,
            "threads": 6,
            "logger": None,
        }
        if has_audio:
            write_kwargs["audio_codec"] = "aac"
        else:
            write_kwargs["audio"] = False

        if ffmpeg_params:
            write_kwargs["ffmpeg_params"] = ffmpeg_params

        final_video.write_videofile(
            str(output_path),
            **write_kwargs,
        )


    def save_frame_at(self, t: float, output_path: str) -> None:
        if getattr(self, "final_video", None) is None:
            self.render(None)
        assert self.final_video is not None
        self.final_video.save_frame(str(output_path), t=t)

    def export(
        self,
        ir: TimelineIR,
        output_path: Path,
        options: Optional[Dict[str, Any]] = None,
    ) -> ExportResult:
        """Export TimelineIR to MoviePy rendered video format (e.g. MP4)."""
        opts = options or {}
        self.ir = ir
        if "fast_qa_duration" in opts:
            self.fast_qa_duration = opts["fast_qa_duration"]
        preset = opts.get("preset", "ultrafast")
        crf = opts.get("crf")
        normalize_loudness = bool(opts.get("normalize_loudness", False))

        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        self.render(str(out_p), preset=preset, crf=crf)

        if normalize_loudness:
            try:
                from veraxi_ymmp.audio.audio_normalizer import normalize_video_audio
                norm_out = out_p.parent / f"{out_p.stem}_normalized{out_p.suffix}"
                normalize_video_audio(out_p, norm_out, target_i=-14.0)
                if norm_out.exists():
                    norm_out.replace(out_p)
            except Exception as e:
                logger.warning(f"Audio loudness normalization failed for {out_p}: {e}")

        total_duration = ir.total_frames / ir.fps
        return ExportResult(
            target_format="mp4",
            output_path=out_p,
            artifacts=[out_p],
            metadata={
                "fps": 30,
                "duration": total_duration,
                "fast_qa_duration": self.fast_qa_duration,
                "preset": preset,
                "crf": crf,
                "normalize_loudness": normalize_loudness,
            },
        )
