"""
SRT subtitle generator for Premiere Pro caption track import.

Generates standard SRT subtitle files from TimelineIR voice clips,
enabling native Premiere caption functionality as an alternative to
pre-rendered PNG speech bubbles.
"""

from pathlib import Path
from typing import Union

from .ir import TimelineIR


def _format_srt_time(seconds: float) -> str:
    """Format a time value in seconds to SRT timestamp format (HH:MM:SS,mmm).

    Args:
        seconds: Time in seconds (non-negative).

    Returns:
        Formatted SRT timestamp string.
    """
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    # Clamp milliseconds to 999 to avoid rollover from rounding
    if millis >= 1000:
        millis = 999
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(ir: TimelineIR, output_path: Union[str, Path]) -> Path:
    """Generate an SRT subtitle file from TimelineIR voice clips.

    Each voice clip becomes one SRT entry with timing derived from
    the clip's start_frame and length relative to the IR's fps.

    Args:
        ir: The compiled TimelineIR containing voice clips.
        output_path: Path to write the .srt file to.

    Returns:
        The resolved output path as a Path object.

    Example:
        >>> from veraxi_ymmp.srt_generator import generate_srt
        >>> srt_path = generate_srt(timeline_ir, Path("output/subtitles.srt"))
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        for i, vc in enumerate(ir.voice_clips, 1):
            start_sec = vc.start_frame / ir.fps
            end_sec = (vc.start_frame + vc.length) / ir.fps

            f.write(f"{i}\n")
            f.write(f"{_format_srt_time(start_sec)} --> {_format_srt_time(end_sec)}\n")
            f.write(f"{vc.text}\n\n")

    return output_path
