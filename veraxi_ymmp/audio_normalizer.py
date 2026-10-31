"""
Automated Audio Loudness Normalizer for Video Media and Upstream Speech Stems.

Applies EBU R128 / ITU-R BS.1770 loudnorm filtering via FFmpeg
to achieve standardized LUFS targets across social/broadcast platforms
and calibrate dialogue stems upstream.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional, Union

from .constants import (
    DEFAULT_AUDIO_SAMPLE_RATE,
    DEFAULT_SPEECH_TARGET_LUFS,
    DEFAULT_SPEECH_TARGET_TP,
)
from .logging import logger

PLATFORM_TARGETS: Dict[str, Dict[str, float]] = {
    "youtube": {"I": -14.0, "TP": -1.0, "LRA": 11.0},
    "spotify": {"I": -14.0, "TP": -1.0, "LRA": 11.0},
    "tiktok": {"I": -13.0, "TP": -1.0, "LRA": 11.0},
    "instagram": {"I": -13.0, "TP": -1.0, "LRA": 11.0},
    "broadcast": {"I": -23.0, "TP": -1.0, "LRA": 11.0},
    "cinema": {"I": -27.0, "TP": -1.0, "LRA": 11.0},
}


def gain_stage_audio_file(
    input_path: Union[Path, str],
    output_path: Optional[Union[Path, str]] = None,
    target_i: float = DEFAULT_SPEECH_TARGET_LUFS,
    target_tp: float = DEFAULT_SPEECH_TARGET_TP,
    sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE,
) -> Path:
    """Normalize an individual speech WAV file to dialogue LUFS / dBTP target.

    If output_path is omitted or identical to input_path, safe in-place replacement
    is performed via a temporary sibling file.
    """
    src = Path(input_path).resolve()
    if not src.exists():
        logger.error(f"Could not find input file {src}")
        raise FileNotFoundError(f"Input file not found: {src}")

    dst = Path(output_path).resolve() if output_path is not None else src
    dst.parent.mkdir(parents=True, exist_ok=True)

    temp_out = dst if dst != src else src.with_name(f".tmp_norm_{src.name}")

    loudnorm_filter = (
        f"loudnorm=I={target_i}:TP={target_tp}:LRA=11.0:print_format=summary"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(src),
        "-af", loudnorm_filter,
        "-ar", str(sample_rate),
        str(temp_out),
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL)
        if temp_out != dst:
            temp_out.replace(dst)
        logger.debug(f"Gain-staged dialogue stem: {dst.name} -> {target_i} LUFS")
        return dst
    except Exception as e:
        logger.warning(f"Upstream audio gain staging failed for {src.name}: {e}")
        if temp_out.exists() and temp_out != dst:
            try:
                temp_out.unlink()
            except OSError:
                pass
        return src


def gain_stage_audio_bytes(
    wav_bytes: bytes,
    target_i: float = DEFAULT_SPEECH_TARGET_LUFS,
    target_tp: float = DEFAULT_SPEECH_TARGET_TP,
    sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE,
) -> bytes:
    """Normalize raw WAV audio bytes to dialog LUFS/dBTP target using FFmpeg.

    Uses a temporary file to ensure the output WAV header is seekable and contains
    exact frame duration data. If FFmpeg fails, returns the original bytes unharmed.
    """
    if not wav_bytes:
        return wav_bytes

    tmp_in: Optional[Path] = None
    tmp_out: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as in_f:
            tmp_in = Path(in_f.name)
            in_f.write(wav_bytes)

        tmp_out = tmp_in.with_name(f"{tmp_in.stem}_staged.wav")
        res_path = gain_stage_audio_file(
            tmp_in,
            output_path=tmp_out,
            target_i=target_i,
            target_tp=target_tp,
            sample_rate=sample_rate,
        )
        if res_path.exists() and res_path != tmp_in:
            return res_path.read_bytes()
    except Exception as e:
        logger.warning(f"Upstream audio bytes gain staging skipped: {e}")
    finally:
        for p in (tmp_in, tmp_out):
            if p is not None and p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass

    return wav_bytes


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
        subprocess.run(cmd, capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL)
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
    "gain_stage_audio_bytes",
    "gain_stage_audio_file",
    "normalize_all_platforms",
    "normalize_video_audio",
]
