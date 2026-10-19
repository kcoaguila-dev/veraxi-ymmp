import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, cast

import numpy as np

if not os.environ.get("IMAGEIO_FFMPEG_EXE"):
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_bin

from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoClip,
)

from .ir import TimelineIR
from .logging import logger
from .phonetics import extract_phonetic_blocks
from .ports import ExportResult
from .typography import (
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


def create_speech_bubble(text: str, duration: float, border_color: Tuple[int, int, int, int] = (0, 128, 0, 255)) -> ImageClip:
    """Creates a beautiful white speech bubble with a dynamic border, drop shadow, and wrapped black text."""
    geom = calculate_speech_plate_geometry(
        text=text,
        font_size=52,
        canvas_w=1920,
        canvas_h=360,
        wrap_width=20,
        spacing=12,
        auto_scale_down=True,
    )
    effective_canvas_h = max(360, int(geom.box_h) + 80)
    if effective_canvas_h != 360:
        geom = calculate_speech_plate_geometry(
            text=text,
            font_size=52,
            canvas_w=1920,
            canvas_h=effective_canvas_h,
            wrap_width=20,
            spacing=12,
            auto_scale_down=True,
        )
    img = draw_rounded_speech_bubble(
        canvas_size=(1920, effective_canvas_h),
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

    layout_y = int(round(1030.0 - geom.box_y - geom.box_h))
    setattr(clip, "layout_y", layout_y)
    setattr(clip, "geom", geom)
    return clip.with_effects([Resize(pop_in)])


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

    def render(self, output_path: str) -> None:
        if self.ir is None:
            raise ValueError("TimelineIR must be provided to render")
        fps = self.ir.fps
        total_duration = self.ir.total_frames / fps

        video_clips = []
        audio_clips = []

        # 1. First, process voice clips to build a real-time mapping!
        frame_to_time = {0: 0.0}
        current_time = 0.0
        talk_times = []
        audio_readers = []
        bubbles_list = []
        char_open_intervals: Dict[str, List[Tuple[float, float]]] = {}

        for vc in self.ir.voice_clips:
            start_time = current_time
            frame_to_time[vc.start_frame] = start_time

            if vc.audio_path:
                ac = AudioFileClip(str(vc.audio_path))
                dur = ac.duration + 0.3
            else:
                dur = vc.length / fps

            talk_times.append((start_time, start_time + dur, vc.emotion, getattr(vc, "motion", "none"), vc.character))
            if vc.audio_path:
                audio_readers.append((start_time, start_time + dur, ac, vc.character))
                audio_clips.append(ac.with_start(start_time))

            # Sliced phonetic open intervals for speech lip-sync
            if vc.character not in char_open_intervals:
                char_open_intervals[vc.character] = []
            blocks = extract_phonetic_blocks(vc.audio_query, dur, fps=fps)
            for b_s, b_e, is_open in blocks:
                if is_open:
                    char_open_intervals[vc.character].append((start_time + b_s, start_time + b_e))

            border_color = get_char_color(vc.character)

            bubble = create_speech_bubble(vc.text, dur, border_color).with_start(start_time)
            bubble_y = getattr(bubble, "layout_y", 725)
            bubble = bubble.with_position(("center", bubble_y))
            bubbles_list.append(bubble)

            current_time += dur
            frame_to_time[vc.start_frame + vc.length] = current_time

        total_duration = current_time + 2.0

        # 2. Global clips (BG, BGM)
        for gc in self.ir.global_clips:
            t_item = gc.template_item or {}
            file_path = gc.file_path or t_item.get("FilePath")

            if not file_path:
                continue

            path = Path(file_path)
            if not path.exists():
                continue

            if gc.item_type == "AudioItem" or "Volume" in t_item:
                audio_clip = AudioFileClip(str(path))
                if audio_clip.duration > total_duration:
                    audio_clip = audio_clip.subclipped(0, total_duration)
                audio_clip = audio_clip.with_volume_scaled(0.03)
                audio_clips.append(audio_clip.with_start(0))
            else:
                img_clip = ImageClip(str(path)).with_duration(total_duration).with_position("center")
                video_clips.append(img_clip)

        # 2. Dynamic B-Roll (Shown directly, clean and normal)
        bgs = []
        brolls = []
        for d_clip in self.ir.dynamic_image_clips:
            is_bg = _is_background_clip(d_clip)

            # Use real time mapping instead of raw frames!
            start_t = frame_to_time.get(d_clip.start_frame, d_clip.start_frame / fps)
            end_frame = d_clip.start_frame + d_clip.length

            if d_clip.length == -1 or end_frame not in frame_to_time:
                dur = total_duration - start_t
            else:
                dur = frame_to_time[end_frame] - start_t

            if is_bg:
                img = ImageClip(str(d_clip.image_path)).with_start(start_t).with_duration(dur)
                img = img.resized((1920, 1080)).with_position("center")
                bgs.append(img)
            else:
                img = ImageClip(str(d_clip.image_path)).with_start(start_t).with_duration(dur)
                img = img.resized((1920, 1080)).with_position("center")
                brolls.append(img)


        video_clips.extend(bgs)
        video_clips.extend(brolls)

        # 3. Dynamic Characters
        unique_chars = []
        for vc in self.ir.voice_clips:
            if vc.character not in unique_chars:
                unique_chars.append(vc.character)

        # Calculate X offsets based on number of characters
        num_chars = len(unique_chars)
        x_offsets: Dict[str, Union[str, int, float]] = {}

        # YMM4 Convention: Zundamon is usually the reactor (Right), Metan is explainer (Left)
        def char_sort_key(c: str) -> int:
            convention = {
                "四国めたん": 0,
                "春日部つむぎ": 1,
                "ずんだもん": 10
            }
            return convention.get(c, 5)

        sorted_chars = sorted(unique_chars, key=char_sort_key)

        if num_chars == 1:
            x_offsets[sorted_chars[0]] = 'center'
        elif num_chars == 2:
            x_offsets[sorted_chars[0]] = 80   # Left (Metan)
            x_offsets[sorted_chars[1]] = 1180 # Right (Zundamon, moved inward from 1450)
        else:
            spacing = (1920 - 700) / (num_chars - 1)
            for i, c in enumerate(sorted_chars):
                x_offsets[c] = int(i * spacing)

        # Medium Character Scale (Viral YouTube Style)
        # Make characters very large to match Premiere XML output (YMM4 rival style)
        char_height = 1250
        y_pos = 1080 - char_height + 250 # Anchor to bottom, shift down slightly so they don't float

        broll_ranges = []
        for d_clip in self.ir.dynamic_image_clips:
            is_bg = _is_background_clip(d_clip)
            if not is_bg:
                s_t = frame_to_time.get(d_clip.start_frame, d_clip.start_frame / fps)
                e_fr = d_clip.start_frame + d_clip.length
                d_t = total_duration - s_t if d_clip.length == -1 or e_fr not in frame_to_time else (frame_to_time[e_fr] - s_t)
                broll_ranges.append((s_t, s_t + d_t))

        def is_in_broll(t: float) -> bool:
            for bs, be in broll_ranges:
                if bs <= t <= be:
                    return True
            return False

        def get_active_speaker(t: float) -> Optional[str]:
            for st, et, _, _, spk in talk_times:
                if st <= t <= et:
                    return spk
            return None

        for char in unique_chars:
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
                    c_open = ImageClip(str(path_open)).resized(height=char_height)
                    c_closed = ImageClip(str(path_closed)).resized(height=char_height)
                    emotion_clips[emotion] = {
                        "open_img": np.array(c_open.get_frame(0)),
                        "closed_img": np.array(c_closed.get_frame(0)),
                        "open_mask": np.array(c_open.mask.get_frame(0)),
                        "closed_mask": np.array(c_closed.mask.get_frame(0))
                    }

            def make_bounce_offset(c_name: str, base_x: Union[str, int, float]) -> Callable[[float], Tuple[Union[str, int, float], float]]:
                def get_bounce_offset(t: float) -> Tuple[Union[str, int, float], float]:
                    if is_in_broll(t):
                        spk = get_active_speaker(t)
                        if spk == c_name:
                            bx: Union[str, int, float] = 1350
                            by = 240.0
                        else:
                            return (-9999, -9999.0)
                    else:
                        bx, by = base_x, float(y_pos)

                    for st, et, emo, motion, char_speaker in talk_times:
                        if st <= t <= et and char_speaker == c_name:
                            if motion == "jump":
                                by += max(-20.0, -40.0 * abs(math.sin(math.pi * (t - st) / 0.5)))
                            elif motion == "shake":
                                if t - st < 1.0:
                                    if isinstance(bx, (int, float)):
                                        bx += 10.0 if int((t - st) * 30) % 2 == 0 else -2.0
                                    by += 10.0 if int((t - st) * 30 + 1) % 2 == 0 else -2.0
                            return (bx, by)
                    return (bx, by)
                return get_bounce_offset

            def get_mouth_state(t: float, c_name: str) -> bool:
                # Check exact mora-synchronized vowel intervals (the rival standard)
                intervals = char_open_intervals.get(c_name, [])
                for op_s, op_e in intervals:
                    if op_s <= t < op_e:
                        return True
                return False

            def get_current_emotion(t: float, c_name: str) -> str:
                for st, et, emo, motion, char_speaker in talk_times:
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
                    if is_in_broll(t):
                        spk = get_active_speaker(t)
                        if spk != c_name:
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

            c_clip = VideoClip(frame_function=make_mouth_image(char, emotion_clips)).with_duration(total_duration)
            c_mask = VideoClip(frame_function=make_mouth_mask(char, emotion_clips), is_mask=True).with_duration(total_duration)
            c_clip = c_clip.with_mask(c_mask).with_position(make_bounce_offset(char, x_offsets[char]))
            video_clips.append(c_clip)
        video_clips.extend(bubbles_list)

        logger.info("Compositing video...")
        final_video = CompositeVideoClip(video_clips, size=(1920, 1080)).with_duration(total_duration)
        # 6. Global Audio (BGM/SFX)
        from moviepy.audio.fx import AudioFadeOut

        for clip in self.ir.dynamic_audio_clips:
            if not clip.audio_path:
                continue

            try:
                ac = AudioFileClip(str(clip.audio_path))
                if clip.length == -1: # Looped BGM
                    dur = total_duration - (clip.start_frame/fps)
                    ac = ac.subclipped(0, min(dur, ac.duration)).with_volume_scaled(clip.volume)
                    ac = ac.with_effects([AudioFadeOut(2.0)])
                else:
                    dur = clip.length / fps
                    ac = ac.subclipped(0, min(dur, ac.duration)).with_volume_scaled(clip.volume)
                audio_clips.append(ac.with_start(clip.start_frame/fps))
            except Exception as e:
                logger.error(f"Failed to load audio {clip.audio_path}: {e}")

        if audio_clips:
            final_audio = CompositeAudioClip(audio_clips).with_duration(total_duration)
            final_video = final_video.with_audio(final_audio)

        from moviepy.video.fx import FadeOut
        final_video = final_video.with_effects([FadeOut(2.0)])

        self.final_video = final_video
        logger.info(f"Writing to {output_path}...")
        # Fast QA override if requested
        if self.fast_qa_duration is not None:
            final_video = final_video.subclipped(0, min(self.fast_qa_duration, total_duration))

        final_video.write_videofile(
            str(output_path),
            fps=30,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast"
        )

    def save_frame_at(self, t: float, output_path: str) -> None:
        if getattr(self, "final_video", None) is None:
            with tempfile.TemporaryDirectory() as tmp_dir:
                self.render(str(Path(tmp_dir) / "preview_dummy.mp4"))
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
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        self.render(str(out_p))
        total_duration = ir.total_frames / ir.fps
        return ExportResult(
            target_format="mp4",
            output_path=out_p,
            artifacts=[out_p],
            metadata={
                "fps": 30,
                "duration": total_duration,
                "fast_qa_duration": self.fast_qa_duration,
            },
        )
