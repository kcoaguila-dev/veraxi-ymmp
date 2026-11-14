#!/usr/bin/env python3
"""Build the PyInstaller sidecar executable for Tauri v2."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "packaging" / "veraxi-sidecar.spec"
BINARIES_DIR = REPO_ROOT / "frontend" / "src-tauri" / "binaries"


def detect_target_triple() -> str:
    """Return the Rust/Tauri target triple for the current host."""
    sys_name = sys.platform
    machine = platform.machine().lower()
    if sys_name == "win32":
        return "x86_64-pc-windows-msvc"
    if sys_name == "darwin":
        arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
        return f"{arch}-apple-darwin"
    arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
    return f"{arch}-unknown-linux-gnu"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build veraxi-sidecar via PyInstaller.")
    parser.add_argument("--onedir", action="store_true", help="Build --onedir bundle instead of --onefile")
    parser.add_argument("--clean", action="store_true", help="Clean PyInstaller cache before building")
    parser.add_argument("--target", type=str, default=None, help="Override Rust target triple")
    args = parser.parse_args()

    if not SPEC_PATH.is_file():
        print(f"ERROR: Spec file not found: {SPEC_PATH}", file=sys.stderr)
        return 1

    env = os.environ.copy()
    env["VERAXI_SIDECAR_ONEDIR"] = "1" if args.onedir else "0"

    dist_dir = REPO_ROOT / "dist" / "sidecar"
    work_dir = REPO_ROOT / "build" / "sidecar"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
    ]
    if args.clean:
        cmd.append("--clean")
    cmd.append(str(SPEC_PATH))

    print(f"Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    if proc.returncode != 0:
        return proc.returncode

    triple = args.target or detect_target_triple()
    ext = ".exe" if sys.platform == "win32" else ""
    BINARIES_DIR.mkdir(parents=True, exist_ok=True)

    if args.onedir:
        src_dir = dist_dir / "veraxi-sidecar"
        dst_dir = BINARIES_DIR / "veraxi-sidecar-onedir"
        if dst_dir.exists():
            shutil.rmtree(dst_dir)
        shutil.copytree(src_dir, dst_dir)
        print(f"Sidecar onedir bundle copied to: {dst_dir}")
    else:
        src_exe = dist_dir / f"veraxi-sidecar{ext}"
        dst_exe = BINARIES_DIR / f"veraxi-sidecar-{triple}{ext}"
        if not src_exe.is_file():
            print(f"ERROR: Expected built binary not found: {src_exe}", file=sys.stderr)
            return 1
        shutil.copy2(src_exe, dst_exe)
        print(f"Sidecar binary ready: {dst_exe} ({dst_exe.stat().st_size / (1024 * 1024):.1f} MB)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
