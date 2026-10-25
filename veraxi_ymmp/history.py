"""Script Revision and History Manager for Veraxi YMMP.

Provides automated snapshotting, backup rotation, revision inspection,
and non-destructive rollback capabilities for project script.json and broll_manifest.json.
Also handles audio artifact synchronization upon script cut count changes.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from veraxi_ymmp.logging import logger

HISTORY_DIR_NAME = ".history"
DEFAULT_MAX_HISTORY = 25
SAFE_ID_PATTERN = re.compile(r"^\d{8}_\d{6}(?:_\d{3,6})?$")


def get_history_dir(project_path: Path) -> Path:
    """Returns and ensures the .history directory for a given project."""
    h_dir = project_path / HISTORY_DIR_NAME
    h_dir.mkdir(parents=True, exist_ok=True)
    return h_dir


def extract_script_summary(script_data: Any) -> Dict[str, Any]:
    """Extracts cut count, character count, and preview snippet from script data."""
    if not isinstance(script_data, list):
        return {"cut_count": 0, "total_chars": 0, "preview": ""}

    cuts = [e for e in script_data if isinstance(e, dict) and e.get("character")]
    total_chars = sum(len(e.get("text", "")) for e in cuts if isinstance(e.get("text"), str))

    preview = ""
    for e in cuts:
        text = e.get("text", "")
        if text:
            char = e.get("character", "")
            preview = f"{char}: {text[:40]}"
            break

    return {
        "cut_count": len(cuts),
        "total_chars": total_chars,
        "preview": preview,
    }


def backup_project_script(
    project_path: Path,
    reason: str = "gui_override",
    max_history: int = DEFAULT_MAX_HISTORY,
) -> Optional[str]:
    """Creates a timestamped snapshot of the current script and broll manifest.

    Returns the snapshot ID if a backup was made, or None if no valid script exists.
    """
    script_file = project_path / "script.json"
    if not script_file.is_file():
        return None

    try:
        raw_content = script_file.read_text(encoding="utf-8")
        if not raw_content.strip() or raw_content.strip() == "[]":
            return None
        script_data = json.loads(raw_content)
    except Exception as exc:
        logger.warning(f"Could not parse existing script for backup: {exc}")
        return None

    h_dir = get_history_dir(project_path)
    now = datetime.now()
    snapshot_id = now.strftime("%Y%m%d_%H%M%S")

    # If ID already exists (e.g. rapid saves), append microseconds
    if (h_dir / f"script_{snapshot_id}.json").exists():
        snapshot_id = now.strftime("%Y%m%d_%H%M%S_%f")

    # 1. Save script copy
    target_script = h_dir / f"script_{snapshot_id}.json"
    target_script.write_text(raw_content, encoding="utf-8")

    # 2. Save broll copy if it exists
    broll_file = project_path / "broll_manifest.json"
    has_broll = False
    if broll_file.is_file():
        try:
            broll_content = broll_file.read_text(encoding="utf-8")
            if broll_content.strip():
                (h_dir / f"broll_{snapshot_id}.json").write_text(broll_content, encoding="utf-8")
                has_broll = True
        except Exception as exc:
            logger.debug(f"Could not backup broll manifest: {exc}")

    # 3. Save metadata
    summary = extract_script_summary(script_data)
    meta = {
        "id": snapshot_id,
        "timestamp": now.isoformat(),
        "reason": reason,
        "cut_count": summary["cut_count"],
        "total_chars": summary["total_chars"],
        "preview": summary["preview"],
        "has_broll": has_broll,
        "size_bytes": len(raw_content.encode("utf-8")),
    }
    (h_dir / f"meta_{snapshot_id}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info(f"Created script snapshot '{snapshot_id}' for project '{project_path.name}' (reason: {reason})")

    # 4. Prune older history
    prune_history(project_path, max_history=max_history)

    return snapshot_id


def list_script_history(project_path: Path) -> List[Dict[str, Any]]:
    """Returns a list of all historical snapshots for the project, newest first."""
    h_dir = project_path / HISTORY_DIR_NAME
    if not h_dir.is_dir():
        return []

    snapshots: List[Dict[str, Any]] = []

    for meta_file in h_dir.glob("meta_*.json"):
        match = re.match(r"^meta_(.+)\.json$", meta_file.name)
        if not match:
            continue
        snap_id = match.group(1)

        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            snapshots.append(meta)
        except Exception:
            # Fallback if metadata is corrupted
            script_path = h_dir / f"script_{snap_id}.json"
            if script_path.exists():
                snapshots.append({
                    "id": snap_id,
                    "timestamp": datetime.fromtimestamp(script_path.stat().st_mtime).isoformat(),
                    "reason": "unknown",
                    "cut_count": 0,
                    "total_chars": 0,
                    "preview": "Legacy backup",
                    "has_broll": (h_dir / f"broll_{snap_id}.json").exists(),
                    "size_bytes": script_path.stat().st_size,
                })

    # Sort descending by timestamp / id
    snapshots.sort(key=lambda s: s.get("id", ""), reverse=True)
    return snapshots


def restore_script_history(project_path: Path, history_id: str) -> Dict[str, Any]:
    """Non-destructively restores a script snapshot.

    Before overwriting, the current state is automatically backed up so that
    the restore action itself can always be undone.
    """
    if not SAFE_ID_PATTERN.match(history_id):
        raise ValueError(f"Invalid history ID format: {history_id}")

    h_dir = project_path / HISTORY_DIR_NAME
    source_script = h_dir / f"script_{history_id}.json"
    if not source_script.is_file():
        raise FileNotFoundError(f"Historical snapshot '{history_id}' not found.")

    # 1. Back up current script before restoring (safe undo guard)
    pre_restore_id = backup_project_script(project_path, reason=f"pre_restore_{history_id}")

    # 2. Restore script.json
    script_target = project_path / "script.json"
    shutil.copyfile(source_script, script_target)

    # 3. Restore broll_manifest.json if snapshot had it
    source_broll = h_dir / f"broll_{history_id}.json"
    broll_target = project_path / "broll_manifest.json"
    restored_broll = False
    if source_broll.is_file():
        shutil.copyfile(source_broll, broll_target)
        restored_broll = True

    # 4. Parse restored script for summary and clean up stale audio
    restored_data = json.loads(source_script.read_text(encoding="utf-8"))
    summary = extract_script_summary(restored_data)
    cleaned_audio_count = cleanup_stale_audio(project_path, summary["cut_count"])

    logger.info(
        f"Restored project '{project_path.name}' to snapshot '{history_id}' "
        f"({summary['cut_count']} cuts, {cleaned_audio_count} stale audio files cleaned)"
    )

    return {
        "success": True,
        "restored_id": history_id,
        "pre_restore_backup_id": pre_restore_id,
        "cut_count": summary["cut_count"],
        "restored_broll": restored_broll,
        "cleaned_audio_count": cleaned_audio_count,
    }


def prune_history(project_path: Path, max_history: int = DEFAULT_MAX_HISTORY) -> int:
    """Removes historical snapshots exceeding max_history, keeping the newest ones."""
    snapshots = list_script_history(project_path)
    if len(snapshots) <= max_history:
        return 0

    to_remove = snapshots[max_history:]
    h_dir = project_path / HISTORY_DIR_NAME
    removed_count = 0

    for item in to_remove:
        snap_id = item.get("id")
        if not snap_id:
            continue
        for prefix in ("script_", "broll_", "meta_"):
            f = h_dir / f"{prefix}{snap_id}.json"
            if f.exists():
                try:
                    f.unlink()
                except OSError as exc:
                    logger.debug(f"Could not delete old snapshot file {f}: {exc}")
        removed_count += 1

    return removed_count


def cleanup_stale_audio(project_path: Path, active_cut_count: int) -> int:
    """Removes orphaned audio files whose cut index is >= active_cut_count.

    When overriding a long script (e.g. 50 cuts) with a shorter script (e.g. 10 cuts),
    stale audio files 010_*.wav, 011_*.wav, etc. are pruned to prevent ghost audio or
    timeline length corruption.
    """
    audio_dir = project_path / "audio"
    if not audio_dir.is_dir():
        return 0

    removed = 0
    pattern = re.compile(r"^(\d{3,})_")

    for file_path in audio_dir.iterdir():
        if not file_path.is_file():
            continue
        match = pattern.match(file_path.name)
        if match:
            idx = int(match.group(1))
            if idx >= active_cut_count:
                try:
                    file_path.unlink()
                    removed += 1
                except OSError as exc:
                    logger.debug(f"Could not remove stale audio file {file_path}: {exc}")

    if removed > 0:
        logger.info(f"Cleaned up {removed} stale audio files beyond cut {active_cut_count}")

    return removed
