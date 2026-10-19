"""
Automated Audio Loudness Normalizer for Video Media.

Applies EBU R128 / ITU-R BS.1770 two-pass/loudnorm filtering via FFmpeg
to achieve standardized LUFS targets across social and broadcast platforms.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Optional, Union

from .logging import logger

PLATFORM_TARGETS: Dict[str, Dict[str, float]] = {
    "youtube": {"I": -14.0, "TP": -1.0, "LRA": 11.0},
    "spotify": {"I": -14.0, "TP": -1.0, "LRA": 11.0},
    "tiktok": {"I": -13.0, "TP": -1.0, "LRA": 11.0},
    "instagram": {"I": -13.0, "TP": -1.0, "LRA": 11.0},
    "broadcast": {"I": -23.0, "TP": -1.0, "LRA": 11.0},
    "cinema": {"I": -27.0, "TP": -1.0, "LRA": 11.0},
}


def normalize_video_audio(
    input_video: Path,
    output_video: Path,
    target_i: float = -14.0,
    target_tp: float = -1.0,
    target_lra: float = 11.0,
) -> Path:
    """Normalize the audio track of a video file to specific LUFS targets using FFmpeg.

    Args:
        input_video: Path to the input video file.
        output_video: Path to save the normalized video file.
        target_i: Integrated loudness target in LUFS (default: -14.0).
        target_tp: Maximum true peak in dBTP (default: -1.0).
        target_lra: Loudness range target in LU (default: 11.0).

    Returns:
        The Path to the created output video.

    Raises:
        FileNotFoundError: If input_video does not exist.
        RuntimeError: If FFmpeg execution fails.
    """
    input_path = Path(input_video).resolve()
    if not input_path.exists():
        logger.error(f"Could not find input file {input_path}")
        raise FileNotFoundError(f"Input file not found: {input_path}")

    out_path = Path(output_video).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        f"Normalizing audio for {input_path.name} -> {out_path.name} "
        f"(I={target_i} LUFS, TP={target_tp} dBTP, LRA={target_lra} LU)"
    )

    loudnorm_filter = (
        f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=summary"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-vcodec", "copy",
        "-af", loudnorm_filter,
        "-acodec", "aac",
        "-b:a", "320k",
        str(out_path),
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Successfully normalized audio to {out_path}")
        return out_path
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg audio normalization failed: {e.stderr}")
        raise RuntimeError(f"FFmpeg normalization failed: {e.stderr}") from e


def normalize_all_platforms(
    input_path: Union[Path, str],
    output_dir: Optional[Union[Path, str]] = None,
) -> Dict[str, Path]:
    """Normalize a video's audio track across all configured social/broadcast platforms.

    Args:
        input_path: Path to the source video file.
        output_dir: Optional target directory for normalized files (defaults to input's parent).

    Returns:
        Dictionary mapping platform name to the normalized output Path.
    """
    src = Path(input_path).resolve()
    if not src.exists():
        logger.error(f"Could not find input file {src}")
        raise FileNotFoundError(f"Input file not found: {src}")

    target_dir = Path(output_dir).resolve() if output_dir is not None else src.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    outputs: Dict[str, Path] = {}
    for platform, target in PLATFORM_TARGETS.items():
        out_file = target_dir / f"{src.stem}_{platform}{src.suffix}"
        outputs[platform] = normalize_video_audio(
            input_video=src,
            output_video=out_file,
            target_i=target["I"],
            target_tp=target["TP"],
            target_lra=target["LRA"],
        )
    return outputs


__all__ = [
    "PLATFORM_TARGETS",
    "normalize_all_platforms",
    "normalize_video_audio",
]
