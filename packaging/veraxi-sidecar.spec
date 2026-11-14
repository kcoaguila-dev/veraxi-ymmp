# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Veraxi YMMP desktop sidecar binary."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

REPO_ROOT = Path(SPECPATH).resolve().parent
ENTRY_SCRIPT = REPO_ROOT / "veraxi_ymmp" / "app" / "cli.py"

datas: list[tuple[str, str]] = []
binaries: list[tuple[str, str]] = []
hiddenimports: list[str] = []

# Collect packages that ship data files / dictionaries / dynamic plugins
_COLLECT_ALL_PACKAGES = (
    "ipadic",
    "MeCab",
    "pykakasi",
    "alkana",
    "budoux",
    "pint",
    "kanjize",
    "word2number",
    "moviepy",
    "imageio",
    "imageio_ffmpeg",
    "PIL",
    "pypdf",
    "bs4",
    "tldextract",
    "mcp",
)

for pkg in _COLLECT_ALL_PACKAGES:
    try:
        pkg_datas, pkg_bins, pkg_hidden = collect_all(pkg)
        datas.extend(pkg_datas)
        binaries.extend(pkg_bins)
        hiddenimports.extend(pkg_hidden)
    except Exception:
        pass

# edgartools / edgar (collect data & submodules if installed)
for pkg in ("edgar", "edgartools"):
    try:
        datas.extend(collect_data_files(pkg))
        hiddenimports.extend(collect_submodules(pkg))
    except Exception:
        pass

hiddenimports.extend(collect_submodules("veraxi_ymmp"))

# Bundle read-only repository assets for frozen workspace seeding
for rel_dir in ("assets", "examples"):
    src = REPO_ROOT / rel_dir
    if src.is_dir():
        datas.append((str(src), rel_dir))

agents_skills = REPO_ROOT / ".agents" / "skills"
if agents_skills.is_dir():
    datas.append((str(agents_skills), ".agents/skills"))

agents_web = REPO_ROOT / "AGENTS_WEB.md"
if agents_web.is_file():
    datas.append((str(agents_web), "."))

# Bundle ffmpeg.exe (from system PATH or imageio_ffmpeg) into bin/ so shutil.which("ffmpeg") succeeds
_ffmpeg_src = shutil.which("ffmpeg")
if not _ffmpeg_src:
    try:
        import imageio_ffmpeg
        _ffmpeg_src = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        _ffmpeg_src = None

if _ffmpeg_src and os.path.isfile(_ffmpeg_src):
    # Stage as bin/ffmpeg.exe inside _MEIPASS
    _stage_dir = REPO_ROOT / "build" / "sidecar_bin"
    _stage_dir.mkdir(parents=True, exist_ok=True)
    _ffmpeg_dst = _stage_dir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if not _ffmpeg_dst.exists() or os.path.getmtime(_ffmpeg_src) > os.path.getmtime(_ffmpeg_dst):
        shutil.copy2(_ffmpeg_src, _ffmpeg_dst)
    binaries.append((str(_ffmpeg_dst), "bin"))

_ffprobe_src = shutil.which("ffprobe")
if _ffprobe_src and os.path.isfile(_ffprobe_src):
    binaries.append((_ffprobe_src, "bin"))

block_cipher = None

a = Analysis(
    [str(ENTRY_SCRIPT)],
    pathex=[str(REPO_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pytest"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if os.environ.get("VERAXI_SIDECAR_ONEDIR", "0") == "1":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="veraxi-sidecar",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True,
        disable_windowed_traceback=False,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="veraxi-sidecar",
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="veraxi-sidecar",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,
        disable_windowed_traceback=False,
    )
