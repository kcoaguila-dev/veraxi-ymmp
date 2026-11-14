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
import shutil
import subprocess
import sys
import tempfile
import unicodedata
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
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60,
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
    proc = subprocess.run(
        cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=1800
    )
    if proc.returncode != 0 or not dst.is_file():
        raise RuntimeError(f"ffmpeg failed for {src.name}: {proc.stderr.strip()[-500:]}")


def _ingest_probed(
    src: Path, clip_id: str, out_dir: Path,
    width: int, height: int, fps: int, probe: Dict[str, Any],
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
    """Normalize an already-probed source; returns (entry, rejection)."""
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


def _ingest_one(
    src: Path, clip_id: str, out_dir: Path,
    width: int, height: int, fps: int,
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
    """Probe + normalize one source; returns (entry, rejection)."""
    probe = probe_video(src)
    if probe is None:
        return None, {
            "source": src.name,
            "reason": "ffprobe could not read a video stream",
        }
    return _ingest_probed(src, clip_id, out_dir, width, height, fps, probe)


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
        # Probe before taking an id: a file ffprobe cannot read is
        # rejected without consuming a numbering slot, so the ids of
        # the surviving clips do not shift (pre-WP8 semantics; scripts
        # reference these ids). A file that probes but fails to
        # normalize HAS taken its id, as before.
        probe = probe_video(src)
        if probe is None:
            rejected.append({
                "source": src.name,
                "reason": "ffprobe could not read a video stream",
            })
            continue
        base_id = _slugify(src.stem)
        used_ids[base_id] = used_ids.get(base_id, 0) + 1
        clip_id = base_id if used_ids[base_id] == 1 else f"{base_id}-{used_ids[base_id]}"
        entry, rejection = _ingest_probed(
            src, clip_id, out_dir, width, height, fps, probe
        )
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

# Windows reserves these names for devices regardless of extension:
# an output file named con.mp4 or nul.mp4 is invalid there. The check
# is on the segment before the first dot (con.txt.mp4 is still CON).
_WINDOWS_RESERVED = (
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


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
        if clip_id.split(".")[0].casefold() in _WINDOWS_RESERVED:
            raise ValueError(
                f"clip manifest entry {i}: clip_id {clip_id!r} begins "
                "with a reserved Windows device name (con, prn, aux, "
                "nul, com1-9, lpt1-9); its output file would be invalid"
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


def _name_key(name: str) -> str:
    """Comparison key for inbox file names: NFC-normalized and
    case-folded, so a declared name matches the on-disk file across
    letter-case differences and Unicode normalization forms (both
    common with Japanese file names from web downloads)."""
    return unicodedata.normalize("NFC", name).casefold()


def _match_declared(
    inbox: Path, entries: List[tuple], out_dir: Path
) -> tuple[Dict[str, Path], List[Dict[str, str]]]:
    """Resolve declared filenames to actual inbox files.

    Returns (resolved, problems): resolved maps each declared
    filename to the real file to ingest — its on-disk name is what
    the manifest records as the source. A declared file that is
    missing, matches several inbox files up to case/normalization,
    or is claimed by two entries, and any video the manifest does
    not declare, become problems; the caller aborts before writing.
    """
    by_key: Dict[str, List[Path]] = {}
    for p in inbox.iterdir():
        if p.is_file():
            by_key.setdefault(_name_key(p.name), []).append(p)
    declared_keys = {_name_key(fn) for _cid, fn in entries}
    resolved: Dict[str, Path] = {}
    claimed: Dict[Path, str] = {}
    problems: List[Dict[str, str]] = []
    for clip_id, filename in entries:
        candidates = by_key.get(_name_key(filename), [])
        if not candidates:
            problems.append({
                "source": filename,
                "reason": f"declared for clip_id '{clip_id}' but not found in inbox",
            })
        elif len(candidates) > 1:
            names = ", ".join(sorted(p.name for p in candidates))
            problems.append({
                "source": filename,
                "reason": (
                    f"declared for clip_id '{clip_id}' but several "
                    f"inbox files match it up to case/normalization: {names}"
                ),
            })
        elif candidates[0] in claimed:
            problems.append({
                "source": filename,
                "reason": (
                    f"the same inbox file is also declared for "
                    f"clip_id '{claimed[candidates[0]]}'"
                ),
            })
        else:
            claimed[candidates[0]] = clip_id
            resolved[filename] = candidates[0]
    # Destinations are always <clip_id>.mp4, so an inbox file one
    # could overwrite is necessarily a video file: declared ones are
    # checked here, undeclared ones abort in the scan below.
    source_paths = {os.path.normcase(str(p.resolve())) for p in claimed}
    for clip_id, filename in entries:
        dest = os.path.normcase(str((out_dir / f"{clip_id}.mp4").resolve()))
        if dest in source_paths:
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
        if _name_key(src.name) not in declared_keys:
            problems.append({
                "source": src.name,
                "reason": "video file not listed in the clip manifest",
            })
    return resolved, problems


def _publish_stage(stage: Path, out_dir: Path, backup: Path) -> None:
    """Publish every staged file into out_dir as one unit.

    A destination that exists but is not a file aborts the publish
    before anything moves. Otherwise each existing destination is
    first moved into backup; if any move then fails, every file
    already published is removed and every backup restored, so the
    previous complete ingest survives untouched. Raises OSError on
    failure, after the rollback.

    ``manifest.json`` is published last: it is the commit point of
    the ingest. A hard crash mid-publish (which no rollback can
    catch) can still leave new clip files beside it, but the
    surviving manifest is the previous complete one, whose recorded
    checksums expose the mix instead of blessing it.
    """
    names = sorted(
        (p.name for p in stage.iterdir()),
        key=lambda n: (n == MANIFEST_NAME, n),
    )
    for name in names:
        dest = out_dir / name
        if dest.exists() and not dest.is_file():
            raise OSError(
                f"cannot publish {name}: {dest} exists and is not a file"
            )
    published: List[str] = []
    try:
        for name in names:
            dest = out_dir / name
            if dest.is_file():
                os.replace(dest, backup / name)
            os.replace(stage / name, dest)
            published.append(name)
    except OSError:
        # Rollback is best-effort: if an unlink or a restore here
        # itself raises, that error replaces the original one and
        # the caller's cleanup discards any unrestored backups, so
        # the output can be left partial. Accepted for this
        # single-user CLI — re-running the ingest is the recovery —
        # but not a guarantee to build on silently.
        for name in reversed(published):
            dest = out_dir / name
            if dest.is_file():
                dest.unlink()
            saved = backup / name
            if saved.exists():
                os.replace(saved, dest)
        # The name whose publish failed midway may hold the only
        # backup not yet restored.
        for saved in list(backup.iterdir()):
            os.replace(saved, out_dir / saved.name)
        raise


def ingest_clips_from_manifest(
    inbox: Path,
    clip_manifest_path: Path,
    output_dir: Optional[Path] = None,
    width: int = DEFAULT_CANVAS_WIDTH,
    height: int = DEFAULT_CANVAS_HEIGHT,
    fps: int = DEFAULT_FPS,
) -> Dict[str, Any]:
    """Ingest exactly the clips a web-chat manifest declares (WP8).

    All-or-nothing, in both phases. Matching: a declared file
    missing or ambiguous, a file claimed twice, or a video file in
    the inbox that the manifest does not declare, aborts the ingest
    with every problem listed in the returned dict's ``rejected``
    (``matching_aborted``). Processing: matched files are normalized
    into a staging directory inside the output dir, and only when
    every clip succeeds are the outputs and ``manifest.json``
    published; any failure discards the staging directory and writes
    nothing (``ingest_aborted``). Publication itself is one unit:
    if a publish move fails, the previous ingest is restored and
    the error raises. The returned manifest dict also carries
    ``from_manifest`` (the clip manifest's file name) — these three
    keys are part of the manifest-mode result schema.
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
        "ingest_aborted": False,
    }
    resolved, problems = _match_declared(inbox, entries, out_dir)
    if problems:
        manifest["rejected"] = problems
        manifest["matching_aborted"] = True
        return manifest
    out_dir.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".clip-ingest-", dir=out_dir))
    backup = Path(tempfile.mkdtemp(prefix=".clip-ingest-backup-", dir=out_dir))
    try:
        clips: List[Dict[str, Any]] = []
        rejected: List[Dict[str, str]] = []
        for clip_id, filename in entries:
            entry, rejection = _ingest_one(
                resolved[filename], clip_id, stage, width, height, fps
            )
            if entry is not None:
                clips.append(entry)
            if rejection is not None:
                rejected.append(rejection)
        if rejected:
            manifest["rejected"] = rejected
            manifest["ingest_aborted"] = True
            return manifest
        manifest["clips"] = clips
        _write_manifest(stage, manifest)
        _publish_stage(stage, out_dir, backup)
        return manifest
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)


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
    elif args.from_manifest and manifest.get("ingest_aborted"):
        print("Ingest aborted: a clip failed to ingest; nothing was written.")
    else:
        print(f"Ingested {len(manifest['clips'])} clip(s); manifest: {out_dir / MANIFEST_NAME}")
    if manifest["rejected"]:
        sys.exit(1)
