import os
import subprocess
from pathlib import Path

# Get YMM4 path from environment variable, or fallback to a generic placeholder
ymm4_exe_path = os.environ.get("YMM4_PATH")
if not ymm4_exe_path:
    print("Error: YMM4_PATH environment variable is not set.")
    print("Please set it to the path of your YukkuriMovieMaker.exe")
    print("Example: set YMM4_PATH=C:\\path\\to\\YukkuriMovieMaker.exe")
    exit(1)

ymm4_exe = Path(ymm4_exe_path)
if not ymm4_exe.exists():
    print(f"Error: YMM4 not found at {ymm4_exe}")
    exit(1)

ymmp_path = Path("artifacts/final_video.ymmp").resolve()
mp4_path = Path("artifacts/final_video.mp4").resolve()

if mp4_path.exists():
    mp4_path.unlink()

print(f"Exporting {ymmp_path} to {mp4_path} using YMM4 CLI...")
subprocess.run([
    str(ymm4_exe),
    "--project", str(ymmp_path),
    "--output", str(mp4_path),
    "--export"
], check=True)

print("Export finished!")
