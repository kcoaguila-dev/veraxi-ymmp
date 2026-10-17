"""
Typography and plate rendering utilities for Veraxi YMMP.

Provides a single source of truth for:
- Japanese semantic line wrapping (BudouX + Kinsoku Shori + 2-line balancing)
- Character theme colors
- System font loading for subtitles/speech plates
- Speech plate geometry calculations and PIL rendering
"""

import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFont, ImageFilter

_budoux_parser = None


def _get_budoux_parser():
    """Lazily load and cache the BudouX Japanese parser."""
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


# Centralized Character Colors (RGBA)
DEFAULT_CHAR_COLOR: Tuple[int, int, int, int] = (100, 116, 139, 255) # Slate 500 default

CHAR_COLORS: Dict[str, Tuple[int, int, int, int]] = {
    "ずんだもん": (34, 197, 94, 255),    # Vibrant Zunda Green (#22C55E)
    "四国めたん": (236, 72, 153, 255),   # Vibrant Pink (#EC4899)
    "春日部つむぎ": (249, 115, 22, 255), # Vibrant Orange (#F97316)
    "default": DEFAULT_CHAR_COLOR,
}


def get_char_color(
    character: str,
    default: Optional[Union[Tuple[int, int, int], Tuple[int, int, int, int]]] = None
) -> Tuple[int, int, int, int]:
    """Return the RGBA border/accent color for a character."""
    if character in CHAR_COLORS:
        return CHAR_COLORS[character]
    if default is not None:
        if len(default) == 3:
            return (default[0], default[1], default[2], 255)
        return (default[0], default[1], default[2], default[3])
    return DEFAULT_CHAR_COLOR


def get_speech_font(font_size: int = 52) -> ImageFont.ImageFont:
    """Load system Japanese font (Meiryo Bold, Meiryo, or default)."""
    try:
        try:
            return ImageFont.truetype("meiryob.ttc", font_size)
        except Exception:
            return ImageFont.truetype("meiryo.ttc", font_size)
    except Exception:
        return ImageFont.load_default()


@dataclass
class SpeechPlateGeometry:
    """Geometric dimensions and text layout for a speech bubble plate."""
    box_x: float
    box_y: float
    box_w: float
    box_h: float
    text_w: float
    text_h: float
    bbox: Tuple[int, int, int, int]
    font: ImageFont.ImageFont
    wrapped_text: str


def calculate_speech_plate_geometry(
    text: str,
    font_size: int = 52,
    canvas_w: int = 1920,
    canvas_h: int = 360,
    wrap_width: int = 20,
    spacing: int = 12,
    auto_scale_down: bool = True,
    bottom_margin: Optional[int] = None,
    pad_x: int = 72,
    pad_y: int = 38,
    min_box_w: int = 480,
    min_box_h: int = 136,
    max_box_w: int = 1600,
) -> SpeechPlateGeometry:
    """Calculate speech bubble plate bounding box and text positioning."""
    wrapped_text = wrap_japanese(text, width=wrap_width)
    font = get_speech_font(font_size)

    dummy_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bbox = dummy_draw.multiline_textbbox((0, 0), wrapped_text, font=font, spacing=spacing)
    text_w = float(bbox[2] - bbox[0])
    text_h = float(bbox[3] - bbox[1])

    if auto_scale_down and text_w > 1550:
        scaled_size = max(font_size - 6, 40)
        font = get_speech_font(scaled_size)
        scaled_spacing = max(spacing - 2, 8)
        bbox = dummy_draw.multiline_textbbox((0, 0), wrapped_text, font=font, spacing=scaled_spacing)
        text_w = float(bbox[2] - bbox[0])
        text_h = float(bbox[3] - bbox[1])

    box_w = min(max(text_w + pad_x * 2, min_box_w), max_box_w)
    box_h = max(text_h + pad_y * 2, min_box_h)

    box_x = (canvas_w - box_w) / 2
    if bottom_margin is not None:
        box_y = canvas_h - box_h - bottom_margin
    else:
        box_y = (canvas_h - box_h) / 2

    return SpeechPlateGeometry(
        box_x=box_x,
        box_y=box_y,
        box_w=box_w,
        box_h=box_h,
        text_w=text_w,
        text_h=text_h,
        bbox=bbox,
        font=font,
        wrapped_text=wrapped_text,
    )


def draw_rounded_speech_bubble(
    canvas_size: Tuple[int, int],
    geometry: SpeechPlateGeometry,
    border_color: Union[Tuple[int, int, int], Tuple[int, int, int, int]] = (46, 139, 87, 255),
    fill_color: Tuple[int, int, int, int] = (255, 255, 255, 248),
    border_width: int = 7,
    corner_radius: int = 24,
    shadow_offset: Tuple[int, int] = (3, 4),
    shadow_color: Tuple[int, int, int, int] = (0, 0, 0, 85),
    shadow_blur: int = 8,
    draw_text: bool = True,
    text_color: Tuple[int, int, int, int] = (24, 24, 27, 255),
    text_spacing: int = 12,
) -> Image.Image:
    """Render a rounded speech bubble with drop shadow, border, and optional centered text."""
    canvas_w, canvas_h = canvas_size
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    if len(border_color) == 3:
        b_color = (border_color[0], border_color[1], border_color[2], 255)
    else:
        b_color = border_color  # type: ignore

    # 1. Soft drop shadow
    if len(shadow_color) == 4 and shadow_color[3] > 0 and shadow_blur >= 0:
        shadow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow)
        sx, sy = shadow_offset
        s_draw.rounded_rectangle(
            [
                geometry.box_x + sx,
                geometry.box_y + sy,
                geometry.box_x + geometry.box_w + sx,
                geometry.box_y + geometry.box_h + sy,
            ],
            radius=corner_radius,
            fill=shadow_color,
        )
        if shadow_blur > 0:
            shadow = shadow.filter(ImageFilter.GaussianBlur(shadow_blur))
        img.alpha_composite(shadow)

    # 2. Main rounded speech bubble
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [
            geometry.box_x,
            geometry.box_y,
            geometry.box_x + geometry.box_w,
            geometry.box_y + geometry.box_h,
        ],
        radius=corner_radius,
        fill=fill_color,
        outline=b_color,
        width=border_width,
    )

    # 3. Optional Centered Text
    if draw_text and geometry.wrapped_text:
        text_x = geometry.box_x + (geometry.box_w - geometry.text_w) / 2 - geometry.bbox[0]
        text_y = geometry.box_y + (geometry.box_h - geometry.text_h) / 2 - geometry.bbox[1]
        draw.multiline_text(
            (text_x, text_y),
            geometry.wrapped_text,
            font=geometry.font,
            fill=text_color,
            spacing=text_spacing,
            align="center",
        )

    return img
