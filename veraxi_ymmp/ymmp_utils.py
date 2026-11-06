"""
Helper utilities and dictionary builders for YMM4 (.ymmp) rendering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Union


def anim_val(val: float, span: float = 0.0, anim_type: str = "なし") -> Dict[str, Any]:
    """Create a standard YMM4 animated property dictionary."""
    return {"Values": [{"Value": val}], "Span": span, "AnimationType": anim_type}


# Backwards compatibility alias
_anim_val = anim_val


def format_voice_duration(sec: float) -> str:
    """Format duration in seconds into YMM4 TimeSpan string (HH:MM:SS.fffffff)."""
    hours = int(sec // 3600)
    mins = int((sec % 3600) // 60)
    secs = sec % 60
    return f"{hours:02d}:{mins:02d}:{secs:09.6f}0"


_format_voice_duration = format_voice_duration


def is_background_clip(ic: Any) -> bool:
    """Return True if a dynamic image clip is a background rather than B-roll."""
    if getattr(ic, "is_background", False) or getattr(ic, "is_bg", False):
        return True
    p_str = str(getattr(ic, "image_path", "")).lower()
    return any(
        k in p_str
        for k in (
            "assets/bg",
            "assets\\bg",
            "classroom",
            "room",
            "living_room",
            "washitsu",
            "clean_classroom",
        )
    )


_is_background_clip = is_background_clip


def get_vertical_broll_zoom(img_path: Union[str, Path]) -> float:
    """Calculate optimal YMM4 zoom for a B-roll image on a 1080x1920 vertical canvas."""
    try:
        from PIL import Image

        with Image.open(img_path) as im:
            w = im.size[0]
            if w > 1080:
                return round((1080.0 / float(w)) * 100.0, 2)
    except Exception:
        pass
    return 100.0


_get_vertical_broll_zoom = get_vertical_broll_zoom


def build_image_item(
    file_path: Union[str, Path],
    frame: int,
    length: int,
    layer: int,
    x: float = 0.0,
    y: float = 0.0,
    zoom: Union[float, Dict[str, Any]] = 100.0,
    animated_opacity_rot: bool = False,
) -> Dict[str, Any]:
    """Construct a YMM4 ImageItem dictionary."""
    zoom_dict = zoom if isinstance(zoom, dict) else anim_val(zoom)
    opacity_dict = anim_val(100.0) if animated_opacity_rot else {"Values": [{"Value": 100.0}]}
    rot_dict = anim_val(0.0) if animated_opacity_rot else {"Values": [{"Value": 0.0}]}
    return {
        "$type": "YukkuriMovieMaker.Project.Items.ImageItem, YukkuriMovieMaker",
        "FilePath": str(file_path),
        "X": anim_val(x),
        "Y": anim_val(y),
        "Opacity": opacity_dict,
        "Zoom": zoom_dict,
        "Rotation": rot_dict,
        "Blend": "Normal",
        "Layer": layer,
        "Frame": frame,
        "Length": length,
        "VideoEffects": [],
    }


_build_image_item = build_image_item
