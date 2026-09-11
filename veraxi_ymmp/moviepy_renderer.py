from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from moviepy import *
import math

from .ir import TimelineIR

def create_speech_bubble(text: str, duration: float) -> ImageClip:
    """Creates a beautiful white speech bubble with a green border, drop shadow, and text."""
    width, height = 1200, 200
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
    
    try:
        font = ImageFont.truetype("meiryo.ttc", 50)
    except:
        font = ImageFont.load_default()
        
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    x = (width - text_w) / 2 + 20
    y = (height - text_h) / 2 - 5 
    
    # Draw text shadow/outline
    outline_color = (200, 255, 200, 255)
    for adj in [-2, 2]:
        draw.text((x+adj, y), text, font=font, fill=outline_color)
        draw.text((x, y+adj), text, font=font, fill=outline_color)
        
    draw.text((x, y), text, font=font, fill=(0, 0, 0, 255))
    
    clip = ImageClip(np.array(img)).with_duration(duration)
    
    from moviepy.video.fx import Resize
    def pop_in(t):
        if t < 0.2:
            return 0.5 + (t / 0.2) * 0.5
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
        for d_clip in self.ir.dynamic_image_clips:
            is_bg = "bg/" in str(d_clip.image_path).replace("\\", "/") or "bg\\" in str(d_clip.image_path)
            
            start_t = d_clip.start_frame / fps
            dur = d_clip.length / fps
            img = ImageClip(str(d_clip.image_path)).with_start(start_t).with_duration(dur)
            
            if is_bg:
                img = img.resized(height=1080).with_position("center")
                # Append background so it covers the global background but is behind characters
                video_clips.append(img)
            else:
                img = img.resized(height=400).with_position(("center", 200))
                img = img.with_effects([Resize(broll_pop)])
                video_clips.append(img)

        # 3. Zundamon Base Character
        pos = ('left', 'bottom')
        for cc in self.ir.character_clips:
            if cc.position == 'right':
                pos = ('right', 'bottom')
        
        x_pos = 100 if pos[0] == 'left' else (1920 - 700)
        y_pos = 1080 - 700 - 50 
        
        # PRO ASSETS
        base_path = Path("assets/pro_base.png")
        if base_path.exists():
            # Build talk times for bounce
            talk_times = []
            for vc in self.ir.voice_clips:
                st = vc.start_frame / fps
                dur = vc.length / fps
                talk_times.append((st, st + dur))
                
            def get_bounce_offset(t):
                is_talking = False
                for st, et in talk_times:
                    if st <= t <= et:
                        is_talking = True
                        break
                if is_talking:
                    bounce = abs(math.sin(t * 15)) * 15
                    return (x_pos, y_pos - bounce)
                return (x_pos, y_pos)

            # Base Body
            base_z = ImageClip(str(base_path)).with_duration(total_duration).resized(height=700).with_position(get_bounce_offset)
            video_clips.append(base_z)
            
            # Eyes (Blinking)
            eye_open = Path("assets/pro_eye_open.png")
            eye_closed = Path("assets/pro_eye_closed.png")
            
            # Blinking logic: Open for 3.5s, closed for 0.15s
            if eye_open.exists() and eye_closed.exists():
                eye_o_clip = ImageClip(str(eye_open)).resized(height=700).with_position(get_bounce_offset)
                eye_c_clip = ImageClip(str(eye_closed)).resized(height=700).with_position(get_bounce_offset)
                
                t = 0
                while t < total_duration:
                    dur_open = 3.5
                    if t + dur_open > total_duration: dur_open = total_duration - t
                    video_clips.append(eye_o_clip.with_start(t).with_duration(dur_open))
                    t += dur_open
                    
                    if t >= total_duration: break
                    dur_closed = 0.15
                    if t + dur_closed > total_duration: dur_closed = total_duration - t
                    video_clips.append(eye_c_clip.with_start(t).with_duration(dur_closed))
                    t += dur_closed

            # Mouths (Lip Sync)
            mouth_map = {
                'a': Path("assets/pro_mouth_a.png"),
                'i': Path("assets/pro_mouth_i.png"),
                'u': Path("assets/pro_mouth_u.png"),
                'e': Path("assets/pro_mouth_e.png"),
                'o': Path("assets/pro_mouth_o.png"),
                'n': Path("assets/pro_mouth_n.png")
            }
            mouth_clips = {k: ImageClip(str(v)).resized(height=700).with_position(get_bounce_offset) for k, v in mouth_map.items() if v.exists()}
            
            # Default mouth (closed) for non-talking
            if 'n' in mouth_clips:
                t = 0
                for st, et in talk_times:
                    if st > t:
                        video_clips.append(mouth_clips['n'].with_start(t).with_duration(st - t))
                    t = et
                if t < total_duration:
                    video_clips.append(mouth_clips['n'].with_start(t).with_duration(total_duration - t))

            # 4. Voices, Lip Sync, and Bubbles
            for vc in self.ir.voice_clips:
                start_time = vc.start_frame / fps
                duration = vc.length / fps
                
                # Audio
                if vc.audio_path:
                    audio_clip = AudioFileClip(str(vc.audio_path)).with_start(start_time)
                    audio_clips.append(audio_clip)
                
                # Speech Bubble
                bubble = create_speech_bubble(vc.text, duration).with_start(start_time).with_position(("center", "bottom"))
                video_clips.append(bubble)
                
                # Vowel Lip Sync
                if vc.audio_query and 'accent_phrases' in vc.audio_query:
                    current_t = start_time
                    for phrase in vc.audio_query.get('accent_phrases', []):
                        # 1. Process standard moras
                        for mora in phrase.get('moras', []):
                            vowel = mora.get('vowel')
                            v_len = mora.get('vowel_length') or 0
                            c_len = mora.get('consonant_length') or 0
                            
                            if c_len > 0:
                                if 'n' in mouth_clips:
                                    video_clips.append(mouth_clips['n'].with_start(current_t).with_duration(c_len))
                                current_t += c_len
                                
                            if vowel and v_len > 0:
                                m_key = vowel.lower() # Maps 'N' to 'n'
                                if m_key not in mouth_clips: m_key = 'n' if vowel == 'pau' else 'a'
                                if m_key in mouth_clips:
                                    video_clips.append(mouth_clips[m_key].with_start(current_t).with_duration(v_len))
                                current_t += v_len
                        
                        # 2. Process pause_mora to prevent audio desync!
                        pause_mora = phrase.get('pause_mora')
                        if pause_mora:
                            p_v_len = pause_mora.get('vowel_length') or 0
                            if p_v_len > 0:
                                if 'n' in mouth_clips:
                                    video_clips.append(mouth_clips['n'].with_start(current_t).with_duration(p_v_len))
                                current_t += p_v_len

        print("Compositing video...")
        final_video = CompositeVideoClip(video_clips)
        if audio_clips:
            final_audio = CompositeAudioClip(audio_clips)
            final_video = final_video.with_audio(final_audio)
            
        print(f"Writing to {output_path}...")
        final_video.write_videofile(
            output_path, 
            fps=fps,
            codec="libx264",
            audio_codec="aac"
        )
