"""Phase 0: optional (not-in-git) assets must degrade gracefully.

``assets/bgm/2_23_AM.*`` and ``assets/bg/classroom.jpg`` are licensed,
user-supplied files that are intentionally absent from a fresh clone
(see assets/ASSETS.md). Backgrounds fall back to the committed
``assets/bg/default_dark.png`` and BGM is omitted when missing.
"""

from __future__ import annotations

from pathlib import Path

from veraxi_ymmp.core.constants import (
    DEFAULT_BGM_CANDIDATES,
    DEFAULT_BG_IMAGE_PATH,
    FALLBACK_BG_IMAGE_PATH,
    resolve_background_image,
    resolve_optional_asset,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_default_background_is_the_committed_fallback() -> None:
    assert DEFAULT_BG_IMAGE_PATH == FALLBACK_BG_IMAGE_PATH
    assert (REPO_ROOT / FALLBACK_BG_IMAGE_PATH).is_file()


def test_resolve_background_prefers_local_classroom(monkeypatch, tmp_path: Path) -> None:
    bg_dir = tmp_path / "assets" / "bg"
    bg_dir.mkdir(parents=True)
    fallback = bg_dir / "default_dark.png"
    fallback.write_bytes(b"png")
    monkeypatch.chdir(tmp_path)
    # No classroom.jpg: the committed fallback is used.
    assert resolve_background_image() == Path(FALLBACK_BG_IMAGE_PATH)
    # A user-supplied classroom.jpg wins when present.
    (bg_dir / "classroom.jpg").write_bytes(b"jpg")
    assert resolve_background_image().name == "classroom.jpg"


def test_bgm_candidates_are_optional(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    # Nothing on disk: BGM resolves to None (omitted), never an error.
    assert resolve_optional_asset(DEFAULT_BGM_CANDIDATES) is None
    bgm_dir = tmp_path / "assets" / "bgm"
    bgm_dir.mkdir(parents=True)
    track = bgm_dir / "2_23_AM.mp3"
    track.write_bytes(b"mp3")
    assert resolve_optional_asset(DEFAULT_BGM_CANDIDATES) == Path("assets/bgm/2_23_AM.mp3")
