from pathlib import Path
from typing import Tuple, Dict
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from .moviepy_renderer import wrap_japanese

CHAR_COLORS: Dict[str, Tuple[int, int, int, int]] = {
    "ずんだもん": (34, 197, 94, 255),    # Vibrant Zunda Green (#22C55E)
    "四国めたん": (236, 72, 153, 255),   # Vibrant Pink (#EC4899)
    "春日部つむぎ": (249, 115, 22, 255), # Vibrant Orange (#F97316)
}

def create_speech_plate(
    text: str,
    character: str,
    out_path: Path,
    canvas_w: int = 1920,
    canvas_h: int = 360
) -> Tuple[Path, float, float]:
    """
    Renders a clean white speech bubble plate (Zabuton)
    with rounded corners, speaker-themed border, and soft drop shadow.
    Returns (out_path, text_h, box_h) to allow exact vertical alignment.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    wrapped_text = wrap_japanese(text, width=20)
    font_size = 48
    try:
        try:
            font = ImageFont.truetype("meiryob.ttc", font_size)
        except Exception:
            font = ImageFont.truetype("meiryo.ttc", font_size)
    except Exception:
        font = ImageFont.load_default()

    # Calculate text bounding box to size the plate dynamically
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bbox = dummy.multiline_textbbox((0, 0), wrapped_text, font=font, spacing=12)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Calculate card dimensions with generous padding so text never clips
    box_w = min(max(text_w + 140, 750), 1680)
    box_h = text_h + 60

    box_x = (canvas_w - box_w) / 2
    box_y = (canvas_h - box_h) / 2

    if not out_path.exists():
        img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

        # Soft drop shadow
        shadow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow)
        s_draw.rounded_rectangle(
            [box_x + 3, box_y + 4, box_x + box_w + 3, box_y + box_h + 4],
            radius=22,
            fill=(0, 0, 0, 85)
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(8))
        img.alpha_composite(shadow)

        # Clean white speech plate with speaker-colored border
        border_color = CHAR_COLORS.get(character, (100, 116, 139, 255))
        fill_color = (255, 255, 255, 248)
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [box_x, box_y, box_x + box_w, box_y + box_h],
            radius=22,
            fill=fill_color,
            outline=border_color,
            width=7
        )

        img.save(out_path, format="PNG")
    return out_path, float(text_h), float(box_h)
