"""ingest-clips: normalize dropped-in video clips into a project.

``veraxi-ymmp ingest-clips inbox/`` probes every video file in the
inbox with ffprobe, rejects unreadable files, normalizes the rest to
the project profile (1920x1080, project FPS, H.264 + AAC 48kHz stereo —
a silent track is synthesized when the source has no audio), and
writes ``clips/manifest.json`` with SHA-256 hashes of both the source
and the normalized file, matching the repo's provenance conventions.

A script entry references a clip by manifest ID (``clip_id``); the IR
builder resolves it to a ``DynamicVideoClip`` at build time.

``ingest-clips <inbox> --from-manifest clips.json`` (WP8) is the
web-chat variant: the chat declares which downloaded file is which
``clip_id`` (a JSON list of ``{"clip_id": ..., "filename": ...}`` in
script order) and matching is strict — a declared file that is
missing, or a video in the inbox that is not declared, aborts the
ingest with every problem named, instead of probing and guessing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
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


def _ingest_one(
    src: Path, clip_id: str, out_dir: Path,
    width: int, height: int, fps: int,
) -> tuple:
    """Probe + normalize one source; returns (entry, rejection)."""
    probe = probe_video(src)
    if probe is None:
        return None, {
            "source": src.name,
            "reason": "ffprobe could not read a video stream",
        }
    dst = out_dir / f"{clip_id}.mp4"
    try:
        _normalize(src, dst, probe, width, height, fps)
    except RuntimeError as exc:
        return None, {"source": src.name, "reason": str(exc)}
    normalized = probe_video(dst) or probe
    entry = {
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
    }
    return entry, None


def _write_manifest(out_dir: Path, manifest: Dict[str, Any]) -> None:
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


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
        base_id = _slugify(src.stem)
        used_ids[base_id] = used_ids.get(base_id, 0) + 1
        clip_id = base_id if used_ids[base_id] == 1 else f"{base_id}-{used_ids[base_id]}"
        entry, rejection = _ingest_one(src, clip_id, out_dir, width, height, fps)
        if entry is not None:
            clips.append(entry)
        if rejection is not None:
            rejected.append(rejection)

    manifest: Dict[str, Any] = {
        "version": 1,
        "profile": {"width": width, "height": height, "fps": fps},
        "clips": clips,
        "rejected": rejected,
    }
    _write_manifest(out_dir, manifest)
    return manifest


_CLIP_ID_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def load_clip_manifest(path: Path) -> List[tuple]:
    """Load a web-chat clip manifest as [(clip_id, filename), ...].

    The format is a JSON list of {"clip_id": ..., "filename": ...}
    objects in script order. Anything else raises ValueError with a
    message naming the exact problem — matching must never guess.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read clip manifest {path}: {exc}") from exc
    if not isinstance(data, list) or not data:
        raise ValueError("clip manifest must be a non-empty JSON list")
    entries: List[tuple] = []
    seen_ids: set = set()
    seen_files: set = set()
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"clip manifest entry {i} is not an object")
        raw_id = item.get("clip_id")
        raw_name = item.get("filename")
        if (raw_id is not None and not isinstance(raw_id, str)) or (
            raw_name is not None and not isinstance(raw_name, str)
        ):
            raise ValueError(
                f"clip manifest entry {i}: clip_id and filename must be strings"
            )
        clip_id = (raw_id or "").strip()
        filename = (raw_name or "").strip()
        if not clip_id or not filename:
            raise ValueError(
                f"clip manifest entry {i} needs a non-empty clip_id and filename"
            )
        if not _CLIP_ID_SAFE.match(clip_id):
            raise ValueError(
                f"clip manifest entry {i}: unsafe clip_id {clip_id!r} "
                "(letters, digits, '.', '_', '-' only)"
            )
        parts = Path(filename).parts
        if Path(filename).is_absolute() or ".." in parts or len(parts) != 1:
            raise ValueError(
                f"clip manifest entry {i}: filename {filename!r} must be a "
                "bare file name inside the inbox"
            )
        if clip_id.casefold() in seen_ids:
            raise ValueError(
                f"duplicate clip_id in clip manifest: {clip_id} (ids must "
                "differ by more than letter case; their output files "
                "would collide on a case-insensitive filesystem)"
            )
        if filename in seen_files:
            raise ValueError(f"duplicate filename in clip manifest: {filename}")
        seen_ids.add(clip_id.casefold())
        seen_files.add(filename)
        entries.append((clip_id, filename))
    return entries


def ingest_clips_from_manifest(
    inbox: Path,
    clip_manifest_path: Path,
    output_dir: Optional[Path] = None,
    width: int = DEFAULT_CANVAS_WIDTH,
    height: int = DEFAULT_CANVAS_HEIGHT,
    fps: int = DEFAULT_FPS,
) -> Dict[str, Any]:
    """Ingest exactly the clips a web-chat manifest declares (WP8).

    Matching is all-or-nothing: a declared file missing from the
    inbox, or a video file in the inbox that the manifest does not
    declare, aborts the ingest (nothing written) with every problem
    listed in the returned dict's ``rejected``. Matched files are
    probed and normalized exactly like :func:`ingest_clips`, keeping
    the declared clip_ids and order.
    """
    inbox = Path(inbox)
    out_dir = Path(output_dir) if output_dir else inbox.parent / "clips"
    entries = load_clip_manifest(clip_manifest_path)
    manifest: Dict[str, Any] = {
        "version": 1,
        "profile": {"width": width, "height": height, "fps": fps},
        "clips": [],
        "rejected": [],
        "from_manifest": Path(clip_manifest_path).name,
        "matching_aborted": False,
    }
    declared = {filename for _cid, filename in entries}
    declared_paths = {
        os.path.normcase(str((inbox / fn).resolve())) for _c, fn in entries
    }
    problems: List[Dict[str, str]] = []
    for clip_id, filename in entries:
        if not (inbox / filename).is_file():
            problems.append({
                "source": filename,
                "reason": f"declared for clip_id '{clip_id}' but not found in inbox",
            })
        dest = os.path.normcase(str((out_dir / f"{clip_id}.mp4").resolve()))
        if dest in declared_paths:
            problems.append({
                "source": filename,
                "reason": (
                    f"output for clip_id '{clip_id}' would overwrite a "
                    "declared source file; choose another --output-dir"
                ),
            })
    for src in sorted(
        p for p in inbox.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    ):
        if src.name not in declared:
            problems.append({
                "source": src.name,
                "reason": "video file not listed in the clip manifest",
            })
    if problems:
        manifest["rejected"] = problems
        manifest["matching_aborted"] = True
        return manifest
    out_dir.mkdir(parents=True, exist_ok=True)
    clips: List[Dict[str, Any]] = []
    rejected: List[Dict[str, str]] = []
    for clip_id, filename in entries:
        entry, rejection = _ingest_one(
            inbox / filename, clip_id, out_dir, width, height, fps
        )
        if entry is not None:
            clips.append(entry)
        if rejection is not None:
            rejected.append(rejection)
    manifest["clips"] = clips
    manifest["rejected"] = rejected
    _write_manifest(out_dir, manifest)
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
    parser.add_argument("--from-manifest", default=None, metavar="PATH",
                        help="Web-chat clip manifest (JSON list of "
                             "{clip_id, filename}); ingest exactly those "
                             "files under their declared ids (WP8)")
    args = parser.parse_args(list(argv))

    inbox = Path(args.inbox)
    if not inbox.is_dir():
        sys.stderr.write(f"Error: inbox directory not found: {inbox}\n")
        sys.exit(2)
    if args.from_manifest:
        try:
            manifest = ingest_clips_from_manifest(
                inbox, Path(args.from_manifest),
                Path(args.output_dir) if args.output_dir else None,
                width=args.width, height=args.height, fps=args.fps,
            )
        except ValueError as exc:
            sys.stderr.write(f"Error: {exc}\n")
            sys.exit(2)
    else:
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
    if args.from_manifest and manifest.get("matching_aborted"):
        print("Ingest aborted: manifest matching failed; nothing was written.")
    else:
        print(f"Ingested {len(manifest['clips'])} clip(s); manifest: {out_dir / MANIFEST_NAME}")
    if manifest["rejected"]:
        sys.exit(1)
