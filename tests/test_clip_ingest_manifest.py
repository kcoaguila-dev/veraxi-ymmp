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
import sys
import unicodedata
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


@pytest.mark.parametrize("entries,fragment", [
    # Non-string values must be rejected, not str()-coerced: JSON null
    # became the clip_id "None" (a valid-looking id producing None.mp4)
    # and 42 became the filename "42".
    ([{"clip_id": None, "filename": "a.mp4"}], "needs a non-empty"),
    ([{"clip_id": "a", "filename": None}], "needs a non-empty"),
    ([{"clip_id": 42, "filename": "a.mp4"}], "must be strings"),
    ([{"clip_id": "a", "filename": 42}], "must be strings"),
    ([{"clip_id": True, "filename": "a.mp4"}], "must be strings"),
    # Ids differing only by case collide on case-insensitive
    # filesystems: Opening.mp4 would overwrite opening.mp4 while the
    # manifest kept both entries.
    ([{"clip_id": "opening", "filename": "a.mp4"},
      {"clip_id": "Opening", "filename": "b.mp4"}], "duplicate clip_id"),
])
def test_load_clip_manifest_rejects_bad_types_and_case_dups(
    tmp_path, entries, fragment
):
    path = _write_manifest(tmp_path, entries)
    with pytest.raises(ValueError, match=fragment):
        ci.load_clip_manifest(path)


def test_output_dir_overlapping_a_source_aborts(tmp_path):
    # entry "scene-a" writes <out>/scene-a.mp4; with --output-dir set
    # to the inbox that IS entry "scene-b"'s declared source, which an
    # earlier write would silently replace before it is read.
    inbox = _inbox(tmp_path, "a.mp4", "scene-a.mp4")
    before = {p.name: p.read_bytes() for p in inbox.iterdir()}
    manifest_path = _write_manifest(tmp_path, [
        {"clip_id": "scene-a", "filename": "a.mp4"},
        {"clip_id": "scene-b", "filename": "scene-a.mp4"},
    ])
    result = ci.ingest_clips_from_manifest(
        inbox, manifest_path, output_dir=inbox
    )
    assert result["clips"] == []
    assert result["matching_aborted"] is True
    assert any("overwrite" in r["reason"] for r in result["rejected"])
    assert {p.name: p.read_bytes() for p in inbox.iterdir()} == before


def test_probe_failure_aborts_ingest_and_writes_nothing(
    tmp_path, monkeypatch
):
    # Stub the probe: this test exercises the flag/manifest logic and
    # must not require ffprobe on the machine (probe_video would raise
    # FileNotFoundError where ffprobe is absent).
    monkeypatch.setattr(ci, "probe_video", lambda _path: None)
    # Matching succeeded; the file is just unreadable. Manifest-mode
    # ingest is all-or-nothing in the processing phase too: the run
    # aborts (distinctly from a matching abort) and publishes nothing
    # — no manifest.json, no normalized outputs, no staging leftovers.
    inbox = _inbox(tmp_path, "bad.mp4")
    manifest_path = _write_manifest(tmp_path, [
        {"clip_id": "bad", "filename": "bad.mp4"},
    ])
    result = ci.ingest_clips_from_manifest(inbox, manifest_path)
    assert result["clips"] == []
    assert result["rejected"] != []
    assert result["matching_aborted"] is False
    assert result["ingest_aborted"] is True
    out_dir = tmp_path / "clips"
    assert not (out_dir / "manifest.json").exists()
    assert list(out_dir.iterdir()) == []


def test_publish_blocked_by_directory_keeps_previous_ingest(
    tmp_path, monkeypatch
):
    inbox = _inbox(tmp_path, "a.mp4", "b.mp4")
    _stub_probe_and_normalize(monkeypatch, {"a.mp4", "b.mp4"})
    out_dir = tmp_path / "clips"
    out_dir.mkdir()
    (out_dir / "a.mp4").write_bytes(b"old-a")
    (out_dir / "manifest.json").write_bytes(b"old-manifest")
    (out_dir / "b.mp4").mkdir()  # a directory blocks b's destination
    manifest_path = _write_manifest(tmp_path, [
        {"clip_id": "a", "filename": "a.mp4"},
        {"clip_id": "b", "filename": "b.mp4"},
    ])
    with pytest.raises(OSError):
        ci.ingest_clips_from_manifest(
            inbox, manifest_path, output_dir=out_dir
        )
    assert (out_dir / "a.mp4").read_bytes() == b"old-a"
    assert (out_dir / "manifest.json").read_bytes() == b"old-manifest"
    assert sorted(p.name for p in out_dir.iterdir()) == [
        "a.mp4", "b.mp4", "manifest.json",
    ]


def test_publish_failure_midway_rolls_back(tmp_path, monkeypatch):
    inbox = _inbox(tmp_path, "a.mp4", "b.mp4")
    _stub_probe_and_normalize(monkeypatch, {"a.mp4", "b.mp4"})
    out_dir = tmp_path / "clips"
    out_dir.mkdir()
    (out_dir / "a.mp4").write_bytes(b"old-a")
    (out_dir / "b.mp4").write_bytes(b"old-b")
    (out_dir / "manifest.json").write_bytes(b"old-manifest")
    real_replace = ci.os.replace

    def flaky_replace(src, dst):
        parent = Path(src).parent.name
        staged = parent.startswith(".clip-ingest-") and not parent.startswith(
            ".clip-ingest-backup-"
        )
        if Path(src).name == "b.mp4" and staged:
            raise PermissionError("simulated locked destination")
        return real_replace(src, dst)

    monkeypatch.setattr(ci.os, "replace", flaky_replace)
    manifest_path = _write_manifest(tmp_path, [
        {"clip_id": "a", "filename": "a.mp4"},
        {"clip_id": "b", "filename": "b.mp4"},
    ])
    with pytest.raises(PermissionError):
        ci.ingest_clips_from_manifest(
            inbox, manifest_path, output_dir=out_dir
        )
    assert (out_dir / "a.mp4").read_bytes() == b"old-a"
    assert (out_dir / "b.mp4").read_bytes() == b"old-b"
    assert (out_dir / "manifest.json").read_bytes() == b"old-manifest"
    assert sorted(p.name for p in out_dir.iterdir()) == [
        "a.mp4", "b.mp4", "manifest.json",
    ]


def test_crash_mid_publish_keeps_the_previous_manifest(
    tmp_path, monkeypatch
):
    # manifest.json is the commit point and publishes last, so a
    # hard crash mid-publish (simulated with a BaseException, which
    # the OSError rollback cannot catch) leaves the previous
    # complete manifest in place. With plain sorted order,
    # manifest.json would land before z.mp4 and this would fail.
    inbox = _inbox(tmp_path, "a.mp4", "z.mp4")
    _stub_probe_and_normalize(monkeypatch, {"a.mp4", "z.mp4"})
    out_dir = tmp_path / "clips"
    out_dir.mkdir()
    (out_dir / "a.mp4").write_bytes(b"old-a")
    (out_dir / "z.mp4").write_bytes(b"old-z")
    (out_dir / "manifest.json").write_bytes(b"old-manifest")
    real_replace = ci.os.replace

    def crashing_replace(src, dst):
        parent = Path(src).parent.name
        staged = parent.startswith(".clip-ingest-") and not parent.startswith(
            ".clip-ingest-backup-"
        )
        if Path(src).name == "z.mp4" and staged:
            raise KeyboardInterrupt("simulated hard crash")
        return real_replace(src, dst)

    monkeypatch.setattr(ci.os, "replace", crashing_replace)
    manifest_path = _write_manifest(tmp_path, [
        {"clip_id": "a", "filename": "a.mp4"},
        {"clip_id": "z", "filename": "z.mp4"},
    ])
    with pytest.raises(KeyboardInterrupt):
        ci.ingest_clips_from_manifest(
            inbox, manifest_path, output_dir=out_dir
        )
    assert (out_dir / "manifest.json").read_bytes() == b"old-manifest"


# --- Review follow-ups (post-merge review of PR #23) -----------------

@pytest.mark.parametrize("clip_id", [
    "con", "NUL", "aux", "prn", "com1", "lpt9", "con.txt",
])
def test_manifest_reserved_windows_ids_rejected(tmp_path, clip_id):
    path = _write_manifest(tmp_path, [
        {"clip_id": clip_id, "filename": "a.mp4"},
    ])
    with pytest.raises(ValueError, match="reserved Windows device name"):
        ci.load_clip_manifest(path)


def _stub_probe_and_normalize(monkeypatch, good_names):
    """Make probing succeed for the named files and normalization a
    byte write, so matching behavior can be tested without ffmpeg.
    Names compare by _name_key: a platform may hand back a file name
    in a different case/normalization than the one it was created
    with."""
    good_keys = {ci._name_key(n) for n in good_names}

    def fake_probe(path):
        if ci._name_key(Path(path).name) in good_keys:
            return {"duration_sec": 1.0, "has_audio": False}
        return None

    def fake_normalize(src, dst, probe, width, height, fps):
        Path(dst).write_bytes(b"normalized")

    monkeypatch.setattr(ci, "probe_video", fake_probe)
    monkeypatch.setattr(ci, "_normalize", fake_normalize)


def test_declared_name_matches_despite_case(tmp_path, monkeypatch):
    inbox = _inbox(tmp_path, "a.mp4")
    _stub_probe_and_normalize(monkeypatch, {"a.mp4"})
    manifest_path = _write_manifest(tmp_path, [
        {"clip_id": "x", "filename": "A.mp4"},
    ])
    result = ci.ingest_clips_from_manifest(inbox, manifest_path)
    assert result["matching_aborted"] is False
    assert [c["id"] for c in result["clips"]] == ["x"]
    # The manifest records the actual on-disk source name.
    assert result["clips"][0]["source"] == "a.mp4"


def test_declared_name_matches_despite_unicode_normalization(
    tmp_path, monkeypatch
):
    nfc = "がく.mp4"  # が decomposes under NFD (か + combining dakuten)
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    inbox = _inbox(tmp_path, nfd)
    on_disk_name = next(inbox.iterdir()).name
    _stub_probe_and_normalize(monkeypatch, {nfd})
    manifest_path = _write_manifest(tmp_path, [
        {"clip_id": "g", "filename": nfc},
    ])
    result = ci.ingest_clips_from_manifest(inbox, manifest_path)
    assert result["matching_aborted"] is False
    # The manifest records the name exactly as it exists on disk.
    assert result["clips"][0]["source"] == on_disk_name


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="files differing only by case cannot coexist on Windows",
)
def test_ambiguous_case_match_aborts(tmp_path):
    inbox = _inbox(tmp_path, "A.mp4", "a.mp4")
    manifest_path = _write_manifest(tmp_path, [
        {"clip_id": "x", "filename": "a.mp4"},
    ])
    result = ci.ingest_clips_from_manifest(inbox, manifest_path)
    assert result["matching_aborted"] is True
    assert any("several" in r["reason"] for r in result["rejected"])
    assert not (tmp_path / "clips").exists()


def test_same_file_claimed_by_two_entries_aborts(tmp_path):
    inbox = _inbox(tmp_path, "a.mp4")
    manifest_path = _write_manifest(tmp_path, [
        {"clip_id": "x", "filename": "A.mp4"},
        {"clip_id": "y", "filename": "a.mp4"},
    ])
    result = ci.ingest_clips_from_manifest(inbox, manifest_path)
    assert result["matching_aborted"] is True
    assert any("also declared" in r["reason"] for r in result["rejected"])


def test_cmd_matching_abort_exit_and_message(tmp_path, capsys):
    inbox = _inbox(tmp_path, "a.mp4")
    manifest_path = _write_manifest(tmp_path, [
        {"clip_id": "x", "filename": "missing.mp4"},
    ])
    with pytest.raises(SystemExit) as excinfo:
        ci.cmd_ingest_clips([str(inbox), "--from-manifest", str(manifest_path)])
    assert excinfo.value.code == 1
    assert "manifest matching failed; nothing was written" in (
        capsys.readouterr().out
    )


def test_cmd_processing_abort_exit_and_message(
    tmp_path, capsys, monkeypatch
):
    monkeypatch.setattr(ci, "probe_video", lambda _path: None)
    inbox = _inbox(tmp_path, "bad.mp4")
    manifest_path = _write_manifest(tmp_path, [
        {"clip_id": "bad", "filename": "bad.mp4"},
    ])
    with pytest.raises(SystemExit) as excinfo:
        ci.cmd_ingest_clips([str(inbox), "--from-manifest", str(manifest_path)])
    assert excinfo.value.code == 1
    assert "a clip failed to ingest; nothing was written" in (
        capsys.readouterr().out
    )


def test_cmd_manifest_load_error_exits_2(tmp_path, capsys):
    inbox = _inbox(tmp_path, "a.mp4")
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        ci.cmd_ingest_clips([str(inbox), "--from-manifest", str(bad)])
    assert excinfo.value.code == 2
