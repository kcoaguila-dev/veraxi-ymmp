import os
import shutil
from pathlib import Path
from typing import Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

if not os.environ.get("IMAGEIO_FFMPEG_EXE"):
    _ffmpeg_bin = shutil.which("ffmpeg")
    if _ffmpeg_bin:
        os.environ["IMAGEIO_FFMPEG_EXE"] = _ffmpeg_bin

from moviepy import *
from moviepy import AudioFileClip
import math

from .ir import TimelineIR
from .phonetics import extract_phonetic_blocks

_budoux_parser = None

def _get_budoux_parser():
    global _budoux_parser
    if _budoux_parser is None:
        try:
            import budoux
            _budoux_parser = budoux.load_default_japanese_parser()
        except Exception:
            _budoux_parser = False
    return _budoux_parser if _budoux_parser is not False else None


def wrap_japanese(text: str, width: int = 20) -> str:
    """
    Wraps Japanese text cleanly using BudouX semantic phrase segmentation,
    unbreakable token protection, Kinsoku Shori (forbidden line start/end rules),
    and 2-line length balancing.

    Guarantees:
    - Numbers and units (e.g. 100, 100ドル, 4.0%, 5000億) are NEVER split across lines.
    - English words and acronyms (e.g. ROI, AI, GPU) are kept unbroken.
    - If text fits in 2 lines, divides at the most balanced phrase boundary.
    - Strict Japanese Kinsoku Shori (never starts line with punct, never ends line with opening bracket).
    """
    if not text:
        return ""
    if len(text) <= width:
        return text

    parser = _get_budoux_parser()
    if parser is not None:
        raw_chunks = parser.parse(text)
    else:
        import re
        # Fallback regex that treats alphanumeric/numbers + units as atomic tokens
        pattern = r'[0-9０-９]+(?:[.,．][0-9０-９]+)*[%％ドル円バレル万億兆人個点]*|[a-zA-Z]+|[一-龥ぁ-んァ-ヶー]+|[、。！？!?…]+|\s+|.'
        raw_chunks = [m.group(0) for m in re.finditer(pattern, text)]

    if not raw_chunks:
        return text

    # Merge punctuation / brackets to obey Kinsoku Shori (禁則処理)
    forbidden_starts = set('！!？?。、…・ー)」』％%')
    forbidden_ends = set('「『（(')

    chunks = []
    for c in raw_chunks:
        if chunks and (c in forbidden_starts or chunks[-1] in forbidden_ends):
            chunks[-1] += c
        else:
            chunks.append(c)

    total_len = sum(len(c) for c in chunks)

    # 1. Optimal 2-Line Balancing: If the text fits in 2 lines (<= width * 2),
    # find the semantic chunk boundary that minimizes line length difference
    if total_len <= width * 2:
        best_diff = 9999
        best_split_idx = -1
        cum_len = 0
        for i in range(len(chunks) - 1):
            cum_len += len(chunks[i])
            rem_len = total_len - cum_len
            if cum_len <= width and rem_len <= width:
                diff = abs(cum_len - rem_len)
                if diff < best_diff:
                    best_diff = diff
                    best_split_idx = i
        if best_split_idx != -1:
            line1 = ''.join(chunks[:best_split_idx + 1]).strip()
            line2 = ''.join(chunks[best_split_idx + 1:]).strip()
            return f"{line1}\n{line2}"

    # 2. Multi-line Greedy Packing
    lines = []
    curr = ""
    for c in chunks:
        if len(curr) + len(c) > width and curr:
            lines.append(curr.strip())
            curr = c
        else:
            curr += c
    if curr:
        lines.append(curr.strip())

    return "\n".join(lines)


def create_speech_bubble(text: str, duration: float, border_color: Tuple[int, int, int, int] = (0, 128, 0, 255)) -> ImageClip:
    """Creates a beautiful white speech bubble with a dynamic border, drop shadow, and wrapped black text."""
    wrapped_text = wrap_japanese(text, width=20)
    
    font_size = 52
    try:
        try:
            font = ImageFont.truetype("meiryob.ttc", font_size)
        except Exception:
            font = ImageFont.truetype("meiryo.ttc", font_size)
    except Exception:
        font = ImageFont.load_default()
        
    canvas_w, canvas_h = 1920, 360
    
    # Calculate text size
    dummy_draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    bbox = dummy_draw.multiline_textbbox((0, 0), wrapped_text, font=font, spacing=12)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    # If text is still slightly wide, scale down font
    if text_w > 1550:
        font_size = 46
        try:
            font = ImageFont.truetype("meiryob.ttc", font_size)
        except Exception:
            pass
        bbox = dummy_draw.multiline_textbbox((0, 0), wrapped_text, font=font, spacing=10)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    
    # Dynamic box size (YMM4 style zabuton)
    box_w = min(max(text_w + 140, 750), 1680)
    box_h = text_h + 60
    
    # Center the dynamic box in the fixed canvas
    box_x = (canvas_w - box_w) / 2
    box_y = (canvas_h - box_h) / 2
    
    img = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    
    # Draw drop shadow
    shadow = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle([box_x+3, box_y+4, box_x+box_w+3, box_y+box_h+4], radius=22, fill=(0, 0, 0, 85))
    shadow = shadow.filter(ImageFilter.GaussianBlur(8))
    img.alpha_composite(shadow)
    
    draw = ImageDraw.Draw(img)
    fill_color = (255, 255, 255, 248)
    draw.rounded_rectangle([box_x, box_y, box_x+box_w, box_y+box_h], radius=22, fill=fill_color, outline=border_color, width=7)
    
    # Calculate text center
    x = box_x + (box_w - text_w) / 2 - bbox[0]
    y = box_y + (box_h - text_h) / 2 - bbox[1]
    
    draw.multiline_text((x, y), wrapped_text, font=font, fill=(24, 24, 27, 255), spacing=12, align="center")
    
    img_array = np.array(img)
    clip = ImageClip(img_array).with_duration(duration)
    
    from moviepy.video.fx import Resize
    def pop_in(t):
        if t < 0.15:
            return 0.8 + (t / 0.15) * 0.2
        return 1.0
        
    return clip.with_effects([Resize(pop_in)])

class MoviePyRenderer:
    def __init__(self, timeline_ir: TimelineIR):
        self.ir = timeline_ir
        
    def render(self, output_path: str):
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
        char_open_intervals = {}
        
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
            
            char_colors = {
                "ずんだもん": (34, 197, 94, 255),    # Vibrant Green
                "四国めたん": (236, 72, 153, 255),   # Vibrant Pink
                "春日部つむぎ": (249, 115, 22, 255), # Vibrant Orange
            }
            border_color = char_colors.get(vc.character, (120, 130, 150, 255))
            
            bubble = create_speech_bubble(vc.text, dur, border_color).with_start(start_time).with_position(("center", 725))
            bubbles_list.append(bubble)
            
            current_time += dur
            frame_to_time[vc.start_frame + vc.length] = current_time
            
        total_duration = current_time + 2.0
        
        # 2. Global clips (BG, BGM)
        for gc in self.ir.global_clips:
            t_item = gc.template_item
            file_path = t_item.get("FilePath")
            
            if not file_path: continue
                
            path = Path(file_path)
            if not path.exists(): continue
                
            if "Volume" in t_item:
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
            is_bg = "bg" in str(d_clip.image_path).lower() or "room" in str(d_clip.image_path).lower() or "classroom" in str(d_clip.image_path).lower()
            
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
        x_offsets = {}
        
        # YMM4 Convention: Zundamon is usually the reactor (Right), Metan is explainer (Left)
        def char_sort_key(c):
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
            is_bg = "bg" in str(d_clip.image_path).lower() or "room" in str(d_clip.image_path).lower() or "classroom" in str(d_clip.image_path).lower()
            if not is_bg:
                s_t = frame_to_time.get(d_clip.start_frame, d_clip.start_frame / fps)
                e_fr = d_clip.start_frame + d_clip.length
                d_t = total_duration - s_t if d_clip.length == -1 or e_fr not in frame_to_time else (frame_to_time[e_fr] - s_t)
                broll_ranges.append((s_t, s_t + d_t))

        def is_in_broll(t):
            for bs, be in broll_ranges:
                if bs <= t <= be:
                    return True
            return False

        def get_active_speaker(t):
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
                    
            def make_bounce_offset(c_name, base_x):
                def get_bounce_offset(t):
                    if is_in_broll(t):
                        spk = get_active_speaker(t)
                        if spk == c_name:
                            bx, by = 1350, 240
                        else:
                            return (-9999, -9999)
                    else:
                        bx, by = base_x, y_pos

                    for st, et, emo, motion, char_speaker in talk_times:
                        if st <= t <= et and char_speaker == c_name:
                            if motion == "jump":
                                by += max(-20.0, -40.0 * abs(math.sin(math.pi * (t - st) / 0.5)))
                            elif motion == "shake":
                                if t - st < 1.0:
                                    bx += 10.0 if int((t - st) * 30) % 2 == 0 else -2.0
                                    by += 10.0 if int((t - st) * 30 + 1) % 2 == 0 else -2.0
                            return (bx, by)
                    return (bx, by)
                return get_bounce_offset
                
            def get_mouth_state(t, c_name):
                # Check exact mora-synchronized vowel intervals (the rival standard)
                intervals = char_open_intervals.get(c_name, [])
                for op_s, op_e in intervals:
                    if op_s <= t < op_e:
                        return True
                return False
                
            def get_current_emotion(t, c_name):
                for st, et, emo, motion, char_speaker in talk_times:
                    if st <= t <= et and char_speaker == c_name:
                        return emo
                return "neutral"
                
            def make_mouth_image(c_name, e_clips):
                def get_mouth_image(t):
                    emo = get_current_emotion(t, c_name)
                    if emo not in e_clips: emo = "neutral"
                    if emo not in e_clips: return np.zeros((700, 700, 3), dtype=np.uint8)
                    is_open = get_mouth_state(t, c_name)
                    return e_clips[emo]["open_img"] if is_open else e_clips[emo]["closed_img"]
                return get_mouth_image
                
            def make_mouth_mask(c_name, e_clips):
                def get_mouth_mask(t):
                    if is_in_broll(t):
                        spk = get_active_speaker(t)
                        if spk != c_name:
                            h, w = e_clips["neutral"]["open_mask"].shape[:2] if "neutral" in e_clips else (700, 700)
                            return np.zeros((h, w), dtype=np.uint8)
                    emo = get_current_emotion(t, c_name)
                    if emo not in e_clips: emo = "neutral"
                    if emo not in e_clips: return np.zeros((700, 700), dtype=np.uint8)
                    is_open = get_mouth_state(t, c_name)
                    return e_clips[emo]["open_mask"] if is_open else e_clips[emo]["closed_mask"]
                return get_mouth_mask
                
            c_clip = VideoClip(frame_function=make_mouth_image(char, emotion_clips)).with_duration(total_duration)
            c_mask = VideoClip(frame_function=make_mouth_mask(char, emotion_clips), is_mask=True).with_duration(total_duration)
            c_clip = c_clip.with_mask(c_mask).with_position(make_bounce_offset(char, x_offsets[char]))
            video_clips.append(c_clip)
        video_clips.extend(bubbles_list)

        print("Compositing video...")
        final_video = CompositeVideoClip(video_clips, size=(1920, 1080)).with_duration(total_duration)
        # 6. Global Audio (BGM/SFX)
        from moviepy.audio.fx import AudioFadeOut
        
        for clip in self.ir.dynamic_audio_clips:
            if not clip.audio_path: continue
            
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
                print(f"Failed to load audio {clip.audio_path}: {e}")

        if audio_clips:
            final_audio = CompositeAudioClip(audio_clips).with_duration(total_duration)
            final_video = final_video.with_audio(final_audio)
            
        from moviepy.video.fx import FadeOut
        final_video = final_video.with_effects([FadeOut(2.0)])
            
        self.final_video = final_video
        print(f"Writing to {output_path}...")
        # Fast QA override if requested
        if getattr(self, 'fast_qa_duration', None):
            final_video = final_video.subclipped(0, min(self.fast_qa_duration, total_duration))
            
        final_video.write_videofile(
            str(output_path), 
            fps=30,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast"
        )

    def save_frame_at(self, t: float, output_path: str):
        if not hasattr(self, 'final_video'):
            self.render("temp_dummy.mp4")
        self.final_video.save_frame(str(output_path), t=t)

