from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from moviepy import *
from moviepy import AudioFileClip
import numpy as np
import math

from .ir import TimelineIR

import textwrap

def create_speech_bubble(text: str, duration: float) -> ImageClip:
    """Creates a beautiful white speech bubble with a green border, drop shadow, and wrapped text."""
    # Wrap text to ~28 characters per line (approx 1100px at 40px font)
    wrapped_text = "\n".join(textwrap.wrap(text, width=28))
    
    try:
        font = ImageFont.truetype("meiryo.ttc", 60)
    except:
        font = ImageFont.load_default()
        
    # Create a dummy image to measure text
    dummy_draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    bbox = dummy_draw.multiline_textbbox((0, 0), wrapped_text, font=font, spacing=10)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    # Calculate bubble size dynamically
    width = max(200, (text_w//3) + 33)
    height = max(50, (text_h//3) + 26)
    
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
    
    clip = ImageClip(np.array(img)).with_duration(duration)
    
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
        
        # 1. Global clips (BG, BGM)
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
                audio_clip = audio_clip.with_volume_scaled(0.1)
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
            
            start_t = d_clip.start_frame / fps
            dur = d_clip.length / fps
            img = ImageClip(str(d_clip.image_path)).with_start(start_t).with_duration(dur)
            
            if is_bg:
                img = img.resized((640, 360)).with_position("center")
                bgs.append(img)
            else:
                img = img.resized(height=133)
                img = img.with_effects([Resize(broll_pop)])
                img = img.with_position((366, 66))
                brolls.append(img)
                
        video_clips.extend(bgs)
        video_clips.extend(brolls)

        # 3. Zundamon Base Character
        pos = ('left', 'bottom')
        for cc in self.ir.character_clips:
            if cc.position == 'right':
                pos = ('right', 'bottom')
        
        x_pos = 16 if pos[0] == 'left' else (640 - 233)
        y_pos = 360 - 233 - 16 
        
        # CHIBI ASSETS
        base_path_closed = Path("assets/mouth_closed.png")
        base_path_open = Path("assets/mouth_open.png")
        
        if base_path_closed.exists() and base_path_open.exists():
            clip_closed = ImageClip(str(base_path_closed)).resized(height=233)
            clip_open = ImageClip(str(base_path_open)).resized(height=233)
            
            base_img_closed = np.array(clip_closed.get_frame(0))
            base_img_open = np.array(clip_open.get_frame(0))
            
            mask_img_closed = np.array(clip_closed.mask.get_frame(0))
            mask_img_open = np.array(clip_open.mask.get_frame(0))
            
            talk_times = []
            audio_readers = []
            for vc in self.ir.voice_clips:
                st = vc.start_frame / fps
                dur = vc.length / fps
                talk_times.append((st, st + dur))
                audio_readers.append((st, st + dur, AudioFileClip(str(vc.audio_path))))
                
            def get_bounce_offset(t):
                # Static position, matching the natural YMM4 style used by rivals.
                return (x_pos, y_pos)

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
                
            def get_mouth_image(t):
                return base_img_open if get_mouth_state(t) else base_img_closed
                
            def get_mouth_mask(t):
                return mask_img_open if get_mouth_state(t) else mask_img_closed
                
            z_clip = VideoClip(frame_function=get_mouth_image).with_duration(total_duration)
            z_mask = VideoClip(frame_function=get_mouth_mask, is_mask=True).with_duration(total_duration)
            z_clip = z_clip.with_mask(z_mask).with_position(lambda t: get_bounce_offset(t))
            video_clips.append(z_clip)

        # 4. Voices and Bubbles
        for vc in self.ir.voice_clips:
            start_time = vc.start_frame / fps
            duration = vc.length / fps
            
            if vc.audio_path:
                audio_clip = AudioFileClip(str(vc.audio_path)).with_start(start_time)
                audio_clips.append(audio_clip)
            
            bubble = create_speech_bubble(vc.text, duration).with_start(start_time).with_position(("center", 266))
            video_clips.append(bubble)

        print("Compositing video...")
        final_video = CompositeVideoClip(video_clips, size=(640, 360))
        # 6. Global Audio (BGM/SFX)
        for clip in self.ir.dynamic_audio_clips:
            if not clip.audio_path: continue
            
            try:
                ac = AudioFileClip(str(clip.audio_path))
                if clip.length == -1: # Looped BGM
                    dur = total_duration - (clip.start_frame/fps)
                    ac = ac.subclipped(0, min(dur, ac.duration)).with_volume_scaled(0.1)
                else:
                    dur = clip.length / fps
                    ac = ac.subclipped(0, min(dur, ac.duration))
                audio_clips.append(ac.set_start(clip.start_frame / fps))
            except Exception as e:
                print(f"Failed to load audio {clip.audio_path}: {e}")

        if audio_clips:
            final_audio = CompositeAudioClip(audio_clips)
            final_video = final_video.with_audio(final_audio)
            
        print(f"Writing to {output_path}...")
        # Fast QA override if requested
        if getattr(self, 'fast_qa_duration', None):
            final_video = final_video.subclipped(0, 2.0)
            
        final_video.write_videofile(
            str(output_path), 
            fps=10,
            codec="libx264",
            audio_codec="aac"
        )
