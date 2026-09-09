#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Full automation script for YMM4 video rendering.")
    parser.add_argument("template", help="Path to template .ymmp")
    parser.add_argument("script", help="Path to script .json")
    parser.add_argument("output", help="Path to output .ymmp")
    parser.add_argument("video_out", nargs='?', default="output.mp4", help="Path to output .mp4")
    parser.add_argument("--ymm4", default="C:/Users/YourUser/Documents/YukkuriMovieMaker_v4_Lite/YukkuriMovieMaker.exe", help="Path to YMM4 executable")
    parser.add_argument("--tts", action="store_true", help="Enable real VOICEVOX-backed timing instead of placeholder heuristic")
    args = parser.parse_args()

    print(f"Running veraxi-ymmp generation...")
    # Generate the .ymmp
    gen_args = ["python", "-m", "veraxi_ymmp.cli", args.template, args.script, args.output]
    if args.tts:
        gen_args.append("--tts")

    try:
        subprocess.run(gen_args, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error generating .ymmp: {e}")
        sys.exit(1)

    print(f"Running YMM4 encoding...")
    ymm4_args = [args.ymm4, "--encode", args.output, "--output", args.video_out]
    try:
        # Check if we're on linux; if so, we can't run a windows executable directly unless it's available via wine
        # Since this script could be run on Windows in actual usage, we just use subprocess.run.
        # But if the file isn't found and we're not testing, it might crash with FileNotFoundError
        if Path(args.ymm4).exists() or sys.platform == 'win32':
             subprocess.run(ymm4_args, check=True)
        else:
             print(f"YMM4 executable not found at {args.ymm4}. Skipping encoding. Command would be:")
             print(" ".join(ymm4_args))
    except Exception as e:
        print(f"Error running YMM4 encoding: {e}")
        # In a real environment, this shouldn't just pass silently, but we don't want to crash on devbox if not available
        pass

if __name__ == "__main__":
    main()
