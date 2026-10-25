from pathlib import Path
from typing import NamedTuple, Union

from .constants import DEFAULT_SUBTITLE_CENTER_Y
from .typography import (
    CHAR_COLORS,
    DEFAULT_CHAR_COLOR,
    calculate_speech_plate_geometry,
    calculate_ymm4_subtitle_y,
    calculate_ymm4_voice_y_offset,
    draw_rounded_speech_bubble,
    get_char_color,
    wrap_japanese,
)


class SpeechPlateResult(NamedTuple):
    out_path: Path
    text_h: float
    box_h: float
    font_size: float = 44.0
    center_y: float = DEFAULT_SUBTITLE_CENTER_Y
    voice_y: float = DEFAULT_SUBTITLE_CENTER_Y


__all__ = [
    "CHAR_COLORS",
    "DEFAULT_CHAR_COLOR",
    "wrap_japanese",
    "create_speech_plate",
    "SpeechPlateResult",
    "calculate_ymm4_subtitle_y",
    "calculate_ymm4_voice_y_offset",
]


def create_speech_plate(
    text: str,
    character: str,
    out_path: Union[str, Path],
    canvas_w: int = 1920,
    canvas_h: int = 360,
    overwrite: bool = True,
    bottom_safe_margin: float = 50.0,
    canvas_total_h: int = 1080,
) -> SpeechPlateResult:
    """
    Renders a clean white speech bubble plate (Zabuton)
    with rounded corners, speaker-themed border, and soft drop shadow.
    Returns SpeechPlateResult(out_path, text_h, box_h, font_size, center_y) to allow exact vertical alignment.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    geom = calculate_speech_plate_geometry(
        text=text,
        font_size=40,
        canvas_w=canvas_w,
        canvas_h=canvas_h,
        wrap_width=20,
        spacing=10,
        auto_scale_down=True,
    )

    effective_canvas_h = max(canvas_h, int(geom.box_h) + 80)
    if effective_canvas_h != canvas_h:
        geom = calculate_speech_plate_geometry(
            text=text,
            font_size=40,
            canvas_w=canvas_w,
            canvas_h=effective_canvas_h,
            wrap_width=20,
            spacing=10,
            auto_scale_down=True,
        )

    if overwrite or not out_path.exists():
        border_color = get_char_color(character)
        img = draw_rounded_speech_bubble(
            canvas_size=(canvas_w, effective_canvas_h),
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

    center_y = calculate_ymm4_subtitle_y(
        geom.box_h, canvas_h=canvas_total_h, bottom_safe_margin=bottom_safe_margin
    )
    voice_y = float(center_y + geom.voice_y_offset)
    return SpeechPlateResult(
        out_path, float(geom.text_h), float(geom.box_h), float(geom.font_size), center_y, voice_y
    )
