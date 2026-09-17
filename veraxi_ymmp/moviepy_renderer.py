from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from moviepy import *
from moviepy import AudioFileClip
import numpy as np
import math

from .ir import TimelineIR

def wrap_japanese(text: str, width: int = 28) -> str:
    res = []
    while len(text) > width:
        res.append(text[:width])
        text = text[width:]
    if text:
        res.append(text)
    return "\n".join(res)

def create_speech_bubble(text: str, duration: float) -> ImageClip:
    """Creates a beautiful white speech bubble with a green border, drop shadow, and wrapped text."""
    # Wrap text properly for Japanese (no spaces)
    wrapped_text = wrap_japanese(text, width=24)
    
    try:
        font = ImageFont.truetype("meiryo.ttc", 60)
    except:
        font = ImageFont.load_default()
        
    # Create a dummy image to measure text
    dummy_draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    bbox = dummy_draw.multiline_textbbox((0, 0), wrapped_text, font=font, spacing=10)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    # Calculate bubble size dynamically based on full text width
    width = max(200, text_w + 60)
    height = max(50, text_h + 50)
    
    # Add padding for shadow
    canvas_w, canvas_h = width + 40, height + 40
    img = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    
    # Draw drop shadow
    shadow = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle([25, 25, width+15, height+15], radius=20, fill=(0, 0, 0, 100))
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    img.alpha_composite(shadow)
    
    draw = ImageDraw.Draw(img)
    
    border_color = (0, 128, 0, 255) # Green
    fill_color = (255, 255, 255, 245) # White
    draw.rounded_rectangle([20, 20, width, height], radius=20, fill=fill_color, outline=border_color, width=6)
    
    x = (width - text_w) / 2 + 20
    y = (height - text_h) / 2 + 20 - bbox[1] 
    
    # Draw text shadow/outline
    outline_color = (200, 255, 200, 255)
    for adj in [-2, 2]:
        draw.multiline_text((x+adj, y), wrapped_text, font=font, fill=outline_color, spacing=10)
        draw.multiline_text((x, y+adj), wrapped_text, font=font, fill=outline_color, spacing=10)
        
    draw.multiline_text((x, y), wrapped_text, font=font, fill=(0, 0, 0, 255), spacing=10)
    
    # Scale down the final image for 640x360 layout, so it looks crisp but fits
    img = img.resize((canvas_w // 3, canvas_h // 3), Image.Resampling.LANCZOS)
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
        
        for vc in self.ir.voice_clips:
            start_time = current_time
            frame_to_time[vc.start_frame] = start_time
            
            if vc.audio_path:
                ac = AudioFileClip(str(vc.audio_path))
                dur = ac.duration + 0.3
            else:
                dur = vc.length / fps
                
            talk_times.append((start_time, start_time + dur, vc.emotion, getattr(vc, "motion", "none")))
            if vc.audio_path:
                audio_readers.append((start_time, start_time + dur, ac))
                audio_clips.append(ac.with_start(start_time))
            
            bubble = create_speech_bubble(vc.text, dur).with_start(start_time).with_position(("center", 850))
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
                
        # 2. Dynamic B-Roll
        def broll_pop(t):
            if t < 0.3: return 0.5 + (t / 0.3) * 0.5
            elif t > 0.3 and t < 0.4: return 1.0 + math.sin((t-0.3)*10)*0.05
            return 1.0
            
        from moviepy.video.fx import Resize
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
                
            img = ImageClip(str(d_clip.image_path)).with_start(start_t).with_duration(dur)
            
            if is_bg:
                img = img.resized((1920, 1080)).with_position("center")
                bgs.append(img)
            else:
                img = img.resized(height=400)
                img = img.with_effects([Resize(broll_pop)])
                img = img.with_position((1400, 100))
                brolls.append(img)
                
        video_clips.extend(bgs)
        video_clips.extend(brolls)

        # 3. Zundamon Base Character
        pos = ('left', 'bottom')
        for cc in self.ir.character_clips:
            if cc.position == 'right':
                pos = ('right', 'bottom')
        
        x_pos = 48 if pos[0] == 'left' else (1920 - 700)
        y_pos = 1080 - 700 - 48 
        
        emotion_clips = {}
        for emotion in ["neutral", "happy", "angry", "sad", "surprised"]:
            path_open = Path(f"assets/faces/{emotion}_open.png")
            path_closed = Path(f"assets/faces/{emotion}_closed.png")
            if path_open.exists() and path_closed.exists():
                c_open = ImageClip(str(path_open)).resized(height=700)
                c_closed = ImageClip(str(path_closed)).resized(height=700)
                emotion_clips[emotion] = {
                    "open_img": np.array(c_open.get_frame(0)),
                    "closed_img": np.array(c_closed.get_frame(0)),
                    "open_mask": np.array(c_open.mask.get_frame(0)),
                    "closed_mask": np.array(c_closed.mask.get_frame(0))
                }
                
        # If PSD faces aren't ready, fallback
        if not emotion_clips:
            # Fallback to old base paths if needed
            print("Warning: No emotion faces found in assets/faces/. Using static character.")
            pass
            
        # Voice clips already processed above.
            
        def get_bounce_offset(t):
            base_x, base_y = x_pos, y_pos
            for st, et, emo, motion in talk_times:
                if st <= t <= et:
                    is_speaking = get_mouth_state(t)
                    
                    if motion == "jump":
                        time_in = t - st
                        if time_in < 0.5:
                            base_y -= math.sin(time_in / 0.5 * math.pi) * 100
                    elif motion == "shake":
                        if t - st < 1.0:
                            base_x += 10.0 if int((t - st) * 30) % 2 == 0 else -2.0
                            base_y += 10.0 if int((t - st) * 30 + 1) % 2 == 0 else -2.0
                        
                    return (base_x, base_y)
            return (base_x, base_y)

        def get_mouth_state(t):
            for st, et, ac in audio_readers:
                if st <= t <= et:
                    try:
                        vol = np.abs(ac.get_frame(t - st)).mean()
                        if vol > 0.015:
                            return True
                    except:
                        pass
            return False
            
        def get_current_emotion(t):
            for st, et, emo, motion in talk_times:
                if st <= t <= et:
                    return emo
            return "neutral"
            
        def get_mouth_image(t):
            emo = get_current_emotion(t)
            if emo not in emotion_clips: emo = "neutral"
            if emo not in emotion_clips: 
                # Total fallback if nothing exists
                return np.zeros((700, 700, 3), dtype=np.uint8)
            is_open = get_mouth_state(t)
            return emotion_clips[emo]["open_img"] if is_open else emotion_clips[emo]["closed_img"]
            
        def get_mouth_mask(t):
            emo = get_current_emotion(t)
            if emo not in emotion_clips: emo = "neutral"
            if emo not in emotion_clips: return np.zeros((700, 700), dtype=np.uint8)
            is_open = get_mouth_state(t)
            return emotion_clips[emo]["open_mask"] if is_open else emotion_clips[emo]["closed_mask"]
            
        z_clip = VideoClip(frame_function=get_mouth_image).with_duration(total_duration)
        z_mask = VideoClip(frame_function=get_mouth_mask, is_mask=True).with_duration(total_duration)
        z_clip = z_clip.with_mask(z_mask).with_position(lambda t: get_bounce_offset(t))
        video_clips.append(z_clip)
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
            
        print(f"Writing to {output_path}...")
        # Fast QA override if requested
        if getattr(self, 'fast_qa_duration', None):
            final_video = final_video.subclipped(0, 2.0)
            
        final_video.write_videofile(
            str(output_path), 
            fps=30,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast"
        )
