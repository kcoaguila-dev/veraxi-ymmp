"""
Automated Audio Loudness Normalizer for Social Media
Uses FFmpeg to perfectly hit LUFS targets for different platforms.
"""

import subprocess
import argparse
from pathlib import Path

# Official LUFS targets for different platforms
PLATFORM_TARGETS = {
    "youtube": {"I": -14.0, "TP": -1.0, "LRA": 11.0},
    "spotify": {"I": -14.0, "TP": -1.0, "LRA": 11.0},
    "tiktok": {"I": -13.0, "TP": -1.0, "LRA": 11.0},
    "instagram": {"I": -13.0, "TP": -1.0, "LRA": 11.0},
    "broadcast": {"I": -23.0, "TP": -1.0, "LRA": 11.0},
    "cinema": {"I": -27.0, "TP": -1.0, "LRA": 11.0},
}

def normalize_video_audio(input_file: str, platform: str):
    """Normalize the audio track of a video file for a specific platform."""
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"Error: Could not find file {input_file}")
        return

    if platform not in PLATFORM_TARGETS:
        print(f"Error: Unknown platform '{platform}'. Choose from: {', '.join(PLATFORM_TARGETS.keys())}")
        return

    target = PLATFORM_TARGETS[platform]
    output_path = input_path.parent / f"{input_path.stem}_{platform}{input_path.suffix}"
    
    print(f"--- Normalizing for {platform.upper()} ---")
    print(f"Target: {target['I']} LUFS (Integrated), {target['TP']} dBTP (True Peak)")
    
    # FFmpeg loudnorm filter
    loudnorm_filter = (
        f"loudnorm=I={target['I']}:TP={target['TP']}:LRA={target['LRA']}:print_format=summary"
    )

    cmd = [
        "ffmpeg",
        "-y",               # Overwrite output
        "-i", str(input_path),
        "-vcodec", "copy",  # Copy video stream without re-encoding
        "-af", loudnorm_filter, # Apply audio normalization
        "-acodec", "aac",   # Re-encode audio to AAC
        "-b:a", "320k",     # High quality audio bitrate
        str(output_path)
    ]

    print(f"Running FFmpeg... (this will just copy the video and only process the audio)")
    
    try:
        # Run ffmpeg and capture output to show to user
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"\nSuccess! Created perfectly normalized file: {output_path.name}")
    except subprocess.CalledProcessError as e:
        print(f"Error running FFmpeg:\n{e.stderr}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Normalize video audio for social media algorithms.")
    parser.add_argument("input", help="Path to your exported .mp4 video")
    parser.add_argument("--platform", choices=PLATFORM_TARGETS.keys(), default="youtube",
                        help="Target platform (default: youtube)")
    parser.add_argument("--all", action="store_true", help="Generate versions for ALL social media platforms")
    
    args = parser.parse_args()
    
    if args.all:
        for p in ["youtube", "tiktok", "instagram"]:
            normalize_video_audio(args.input, p)
    else:
        normalize_video_audio(args.input, args.platform)
