from pathlib import Path
from typing import Dict, Tuple, Union

from .typography import (
    CHAR_COLORS,
    DEFAULT_CHAR_COLOR,
    calculate_speech_plate_geometry,
    draw_rounded_speech_bubble,
    get_char_color,
    wrap_japanese,
)

__all__ = ["CHAR_COLORS", "wrap_japanese", "create_speech_plate"]


def create_speech_plate(
    text: str,
    character: str,
    out_path: Union[str, Path],
    canvas_w: int = 1920,
    canvas_h: int = 360,
    overwrite: bool = True,
) -> Tuple[Path, float, float]:
    """
    Renders a clean white speech bubble plate (Zabuton)
    with rounded corners, speaker-themed border, and soft drop shadow.
    Returns (out_path, text_h, box_h) to allow exact vertical alignment.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    geom = calculate_speech_plate_geometry(
        text=text,
        font_size=44,
        canvas_w=canvas_w,
        canvas_h=canvas_h,
        wrap_width=20,
        spacing=14,
        auto_scale_down=False,
    )

    if overwrite or not out_path.exists():
        border_color = get_char_color(character)
        img = draw_rounded_speech_bubble(
            canvas_size=(canvas_w, canvas_h),
            geometry=geom,
            border_color=border_color,
            fill_color=(255, 255, 255, 248),
            border_width=7,
            corner_radius=24,
            shadow_offset=(3, 4),
            shadow_color=(0, 0, 0, 85),
            shadow_blur=8,
            draw_text=False,
        )
        img.save(out_path, format="PNG")

    return out_path, float(geom.text_h), float(geom.box_h)
