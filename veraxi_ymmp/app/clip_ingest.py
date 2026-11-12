"""ingest-clips: normalize dropped-in video clips into a project.

``veraxi-ymmp ingest-clips inbox/`` probes every video file in the
inbox with ffprobe, rejects unreadable files, normalizes the rest to
the project profile (1920x1080, project FPS, H.264 + AAC 48kHz stereo —
a silent track is synthesized when the source has no audio), and
writes ``clips/manifest.json`` with SHA-256 hashes of both the source
and the normalized file, matching the repo's provenance conventions.

A script entry references a clip by manifest ID (``clip_id``); the IR
builder resolves it to a ``DynamicVideoClip`` at build time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from veraxi_ymmp.core.constants import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    DEFAULT_FPS,
)
from veraxi_ymmp.core.ir import DynamicVideoClip

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
MANIFEST_NAME = "manifest.json"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return slug or "clip"


def probe_video(path: Path) -> Optional[Dict[str, Any]]:
    """Probe a video file with ffprobe; None when unreadable/not video."""
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format",
         "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        return None
    duration = video.get("duration") or data.get("format", {}).get("duration")
    if duration is None:
        return None
    fps = 0.0
    for key in ("avg_frame_rate", "r_frame_rate"):
        raw = str(video.get(key, "0/1"))
        try:
            num, _, den = raw.partition("/")
            fps = float(num) / float(den or 1)
        except (ValueError, ZeroDivisionError):
            fps = 0.0
        if fps > 0:
            break
    return {
        "width": int(video.get("width", 0)),
        "height": int(video.get("height", 0)),
        "fps": fps,
        "duration_sec": float(duration),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def _normalize(
    src: Path, dst: Path, probe: Dict[str, Any], width: int, height: int, fps: int
) -> None:
    """Re-encode src to the project profile at dst (ffmpeg)."""
    vf = (
        f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)]
    if not probe["has_audio"]:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    cmd += ["-map", "0:v:0", "-map", "0:a:0" if probe["has_audio"] else "1:a:0",
            "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-shortest", str(dst)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0 or not dst.is_file():
        raise RuntimeError(f"ffmpeg failed for {src.name}: {proc.stderr.strip()[-500:]}")


def ingest_clips(
    inbox: Path,
    output_dir: Optional[Path] = None,
    width: int = DEFAULT_CANVAS_WIDTH,
    height: int = DEFAULT_CANVAS_HEIGHT,
    fps: int = DEFAULT_FPS,
) -> Dict[str, Any]:
    """Ingest every video in inbox; returns (and writes) the manifest dict."""
    inbox = Path(inbox)
    out_dir = Path(output_dir) if output_dir else inbox.parent / "clips"
    out_dir.mkdir(parents=True, exist_ok=True)

    clips: List[Dict[str, Any]] = []
    rejected: List[Dict[str, str]] = []
    used_ids: Dict[str, int] = {}
    sources = sorted(
        p for p in inbox.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    )
    for src in sources:
        probe = probe_video(src)
        if probe is None:
            rejected.append({"source": src.name, "reason": "ffprobe could not read a video stream"})
            continue
        base_id = _slugify(src.stem)
        used_ids[base_id] = used_ids.get(base_id, 0) + 1
        clip_id = base_id if used_ids[base_id] == 1 else f"{base_id}-{used_ids[base_id]}"
        dst = out_dir / f"{clip_id}.mp4"
        try:
            _normalize(src, dst, probe, width, height, fps)
        except RuntimeError as exc:
            rejected.append({"source": src.name, "reason": str(exc)})
            continue
        normalized = probe_video(dst) or probe
        clips.append({
            "id": clip_id,
            "source": src.name,
            "source_sha256": _sha256_file(src),
            "file": dst.name,
            "sha256": _sha256_file(dst),
            "duration_sec": round(float(normalized["duration_sec"]), 3),
            "width": width,
            "height": height,
            "fps": fps,
            "has_audio": bool(normalized["has_audio"]),
            "muted": True,
        })

    manifest: Dict[str, Any] = {
        "version": 1,
        "profile": {"width": width, "height": height, "fps": fps},
        "clips": clips,
        "rejected": rejected,
    }
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def find_clips_manifest(search_from: List[Path]) -> Optional[Path]:
    """Locate clips/manifest.json near a project (audio_dir-relative search)."""
    candidates: List[Path] = []
    for base in search_from:
        candidates += [
            base / "clips" / MANIFEST_NAME,
            base.parent / "clips" / MANIFEST_NAME,
            base.parent.parent / "clips" / MANIFEST_NAME,
        ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def load_clips_index(manifest_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load a clips manifest as {clip_id: entry} with absolute file paths."""
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    index: Dict[str, Dict[str, Any]] = {}
    for entry in data.get("clips", []):
        resolved = dict(entry)
        resolved["path"] = str((manifest_path.parent / entry["file"]).resolve())
        index[str(entry["id"])] = resolved
    return index


def place_video_clip(
    entry: Dict[str, Any], start_frame: int, cut_frames: int, fps: int
) -> DynamicVideoClip:
    """Place a manifest clip into a cut.

    The placed length is the cut length when the clip is longer than
    the cut (the source span is simply not exhausted), or the clip's
    own frame count when the clip is shorter than the cut.
    """
    duration = float(entry["duration_sec"])
    in_point = float(entry.get("in_point", 0.0))
    span = max(0.0, duration - in_point)
    length = min(cut_frames, int(math.ceil(span * fps)))
    return DynamicVideoClip(
        start_frame=start_frame,
        length=length,
        video_path=Path(entry["path"]),
        clip_id=str(entry["id"]),
        in_point=in_point,
        out_point=duration,
        muted=bool(entry.get("muted", True)),
    )


def cmd_ingest_clips(argv: Sequence[str]) -> None:
    """Handle 'veraxi-ymmp ingest-clips'."""
    parser = argparse.ArgumentParser(
        prog="veraxi-ymmp ingest-clips",
        description="Probe, normalize and manifest video clips dropped into an inbox directory.",
    )
    parser.add_argument("inbox", help="Directory containing dropped-in video clips")
    parser.add_argument("-o", "--output-dir", default=None,
                        help="Where normalized clips + manifest.json go (default: <inbox>/../clips)")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS,
                        help=f"Target frames per second (default {DEFAULT_FPS})")
    parser.add_argument("--width", type=int, default=DEFAULT_CANVAS_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_CANVAS_HEIGHT)
    args = parser.parse_args(list(argv))

    inbox = Path(args.inbox)
    if not inbox.is_dir():
        sys.stderr.write(f"Error: inbox directory not found: {inbox}\n")
        sys.exit(2)
    manifest = ingest_clips(
        inbox,
        Path(args.output_dir) if args.output_dir else None,
        width=args.width, height=args.height, fps=args.fps,
    )
    out_dir = Path(args.output_dir) if args.output_dir else inbox.parent / "clips"
    for clip in manifest["clips"]:
        print(f"  - {clip['id']}: {clip['file']} ({clip['duration_sec']}s, sha256 {clip['sha256'][:12]}…)")
    for rej in manifest["rejected"]:
        sys.stderr.write(f"Rejected {rej['source']}: {rej['reason']}\n")
    print(f"Ingested {len(manifest['clips'])} clip(s); manifest: {out_dir / MANIFEST_NAME}")
    if manifest["rejected"]:
        sys.exit(1)
