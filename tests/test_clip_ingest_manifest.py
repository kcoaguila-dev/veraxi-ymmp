"""Tests for ingest-clips --from-manifest (WP8).

The matching/validation tests need no ffmpeg: matching problems abort
before any probing. The happy-path test generates a real tiny clip
and is skipped when ffmpeg/ffprobe are unavailable, mirroring
tests/test_video_ingest.py.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import veraxi_ymmp.app.clip_ingest as ci

ffmpeg_required = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not available",
)


def _write_manifest(tmp_path: Path, entries) -> Path:
    path = tmp_path / "clip-manifest.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def _inbox(tmp_path: Path, *names: str) -> Path:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for name in names:
        (inbox / name).write_bytes(b"placeholder")
    return inbox


def test_load_clip_manifest_ok(tmp_path):
    path = _write_manifest(tmp_path, [
        {"clip_id": "opening", "filename": "a.mp4"},
        {"clip_id": "lab-scene", "filename": "b.webm"},
    ])
    assert ci.load_clip_manifest(path) == [
        ("opening", "a.mp4"), ("lab-scene", "b.webm"),
    ]


@pytest.mark.parametrize("entries,fragment", [
    ([{"clip_id": "a", "filename": "a.mp4"},
      {"clip_id": "a", "filename": "b.mp4"}], "duplicate clip_id"),
    ([{"clip_id": "a", "filename": "a.mp4"},
      {"clip_id": "b", "filename": "a.mp4"}], "duplicate filename"),
    ([{"clip_id": "../evil", "filename": "a.mp4"}], "unsafe clip_id"),
    ([{"clip_id": "a", "filename": "../a.mp4"}], "bare file name"),
    ([{"clip_id": "a"}], "needs a non-empty"),
    ([{"filename": "a.mp4"}], "needs a non-empty"),
    (["just-a-string"], "not an object"),
    ([], "non-empty JSON list"),
])
def test_load_clip_manifest_rejects(tmp_path, entries, fragment):
    path = _write_manifest(tmp_path, entries)
    with pytest.raises(ValueError, match=fragment):
        ci.load_clip_manifest(path)


def test_manifest_missing_file_aborts_and_writes_nothing(tmp_path):
    inbox = _inbox(tmp_path, "a.mp4")
    manifest_path = _write_manifest(tmp_path, [
        {"clip_id": "opening", "filename": "a.mp4"},
        {"clip_id": "lab", "filename": "missing.mp4"},
    ])
    result = ci.ingest_clips_from_manifest(inbox, manifest_path)
    assert result["clips"] == []
    assert any(
        "missing.mp4" in r["source"] and "lab" in r["reason"]
        for r in result["rejected"]
    )
    assert not (tmp_path / "clips").exists()  # nothing written


def test_manifest_unmatched_file_aborts(tmp_path):
    inbox = _inbox(tmp_path, "a.mp4", "stray.mp4")
    manifest_path = _write_manifest(tmp_path, [
        {"clip_id": "opening", "filename": "a.mp4"},
    ])
    result = ci.ingest_clips_from_manifest(inbox, manifest_path)
    assert result["clips"] == []
    assert any(
        r["source"] == "stray.mp4" and "not listed" in r["reason"]
        for r in result["rejected"]
    )
    assert not (tmp_path / "clips").exists()


def _make_source_clip(path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=c=red:s=320x240:r=30:d=1",
         "-f", "lavfi", "-i", "sine=frequency=440:d=1",
         "-shortest", str(path)],
        check=True, capture_output=True,
    )


@ffmpeg_required
def test_manifest_ingest_uses_declared_ids_and_order(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _make_source_clip(inbox / "gen_zz.mp4")
    _make_source_clip(inbox / "gen_aa.mp4")
    manifest_path = _write_manifest(tmp_path, [
        {"clip_id": "second-scene", "filename": "gen_zz.mp4"},
        {"clip_id": "first-scene", "filename": "gen_aa.mp4"},
    ])
    result = ci.ingest_clips_from_manifest(inbox, manifest_path)
    assert result["rejected"] == []
    assert [c["id"] for c in result["clips"]] == [
        "second-scene", "first-scene",
    ]
    assert result["from_manifest"] == "clip-manifest.json"
    written = json.loads(
        (tmp_path / "clips" / "manifest.json").read_text(encoding="utf-8")
    )
    assert [c["id"] for c in written["clips"]] == [
        "second-scene", "first-scene",
    ]
    index = ci.load_clips_index(tmp_path / "clips" / "manifest.json")
    assert set(index) == {"second-scene", "first-scene"}
