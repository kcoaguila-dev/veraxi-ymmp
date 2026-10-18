"""
Automated Audio Loudness Normalizer for Social Media.
Thin CLI wrapper delegating to veraxi_ymmp.audio_normalizer.
"""

import argparse
import sys
from pathlib import Path

from veraxi_ymmp.audio_normalizer import (
    PLATFORM_TARGETS,
    normalize_video_audio as _normalize_core,
)


def normalize_video_audio(input_file: str, platform: str) -> None:
    """Normalize the audio track of a video file for a specific platform."""
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"Error: Could not find file {input_file}", file=sys.stderr)
        return

    if platform not in PLATFORM_TARGETS:
        print(
            f"Error: Unknown platform '{platform}'. Choose from: {', '.join(PLATFORM_TARGETS.keys())}",
            file=sys.stderr,
        )
        return

    target = PLATFORM_TARGETS[platform]
    output_path = input_path.parent / f"{input_path.stem}_{platform}{input_path.suffix}"

    print(f"--- Normalizing for {platform.upper()} ---")
    print(f"Target: {target['I']} LUFS (Integrated), {target['TP']} dBTP (True Peak)")
    print("Running FFmpeg... (this will just copy the video and only process the audio)")

    try:
        _normalize_core(
            input_video=input_path,
            output_video=output_path,
            target_i=target["I"],
            target_tp=target["TP"],
            target_lra=target["LRA"],
        )
        print(f"\nSuccess! Created perfectly normalized file: {output_path.name}")
    except Exception as e:
        print(f"Error running FFmpeg:\n{e}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Normalize video audio for social media algorithms.")
    parser.add_argument("input", help="Path to your exported .mp4 video")
    parser.add_argument(
        "--platform",
        choices=PLATFORM_TARGETS.keys(),
        default="youtube",
        help="Target platform (default: youtube)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate versions for ALL social media platforms",
    )

    args = parser.parse_args()

    if args.all:
        for p in ["youtube", "tiktok", "instagram"]:
            normalize_video_audio(args.input, p)
    else:
        normalize_video_audio(args.input, args.platform)
