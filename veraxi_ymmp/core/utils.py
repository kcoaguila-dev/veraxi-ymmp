"""
Utility functions for veraxi-ymmp.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Optional, Union


class ValidationError(ValueError):
    """Exception raised when path traversal or project validation fails."""

    pass


def validate_output_path(output_path: Path, base_dir: Optional[Path] = None) -> Path:
    """
    Ensure output path doesn't escape base directory.
    If base_dir is None, it uses the current working directory.
    """
    explicit_base = base_dir is not None
    if base_dir is None:
        base_dir = Path.cwd()

    resolved_base = base_dir.resolve()
    resolved_out = output_path.resolve()

    # Check if resolved_out is a subpath of resolved_base
    try:
        resolved_out.relative_to(resolved_base)
    except ValueError:
        if explicit_base or ".." in str(output_path):
            raise ValidationError(f"Path traversal detected: {output_path} is outside {base_dir}")

    return resolved_out


def sanitize_filename(name: str) -> str:
    """
    Remove dangerous characters from filenames.
    """
    # Remove any path separators and null bytes
    sanitized = re.sub(r'[/\\:\*\?"<>\|]', "", name)
    sanitized = sanitized.replace("\0", "")
    return sanitized.strip()


def ensure_path(path: Union[str, Path]) -> Path:
    """Convert string to Path if necessary."""
    return Path(path) if isinstance(path, str) else path


def resolve_path(path: Union[str, Path]) -> Path:
    """Convert to Path and resolve to absolute path."""
    return ensure_path(path).resolve()


def normalize_japanese_typography(text: str) -> str:
    """
    Normalizes Japanese script typography according to standard digital editorial rules:
    - Normalizes awkward counter idioms (e.g. 3条件/３条件 -> 3つの条件)
    - Converts full-width alphanumeric characters (０-９, Ａ-Ｚ, ａ-ｚ) to standard half-width ASCII
    - Normalizes full-width percent sign (％ -> %)
    - Removes artificial whitespace between Japanese kana/kanji and ASCII words/numbers
    """
    if not text:
        return ""

    # Standardize phrasing to natural Japanese idiom
    t = text.replace("3条件", "3つの条件").replace("３条件", "3つの条件")

    # Full-width alphanumeric & symbols to standard half-width ASCII
    def _to_half(m: re.Match[str]) -> str:
        c = m.group(0)
        code = ord(c)
        if 0xFF10 <= code <= 0xFF19:  # 0-9
            return chr(code - 0xFF10 + 0x30)
        elif 0xFF21 <= code <= 0xFF3A:  # A-Z
            return chr(code - 0xFF21 + 0x41)
        elif 0xFF41 <= code <= 0xFF5A:  # a-z
            return chr(code - 0xFF41 + 0x61)
        elif code == 0xFF05:  # ％
            return "%"
        return c

    t = re.sub(r"[０-９Ａ-Ｚａ-ｚ％]", _to_half, t)

    # Clean up artificial whitespace between Japanese characters and numbers/Latin words
    t = re.sub(r"([ぁ-んァ-ヶ一-龥])\s+([A-Za-z0-9])", r"\1\2", t)
    t = re.sub(r"([A-Za-z0-9])\s+([ぁ-んァ-ヶ一-龥])", r"\1\2", t)
    return t


def get_workspace_root() -> Path:
    """Resolve the active writable workspace root.

    Precedence:
    1. ``VERAXI_WORKSPACE_DIR`` environment variable (if set and non-empty).
    2. Platform app-data directory when running as a frozen PyInstaller binary.
    3. Current working directory (``Path.cwd()``).
    """
    env_dir = os.environ.get("VERAXI_WORKSPACE_DIR", "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
            base = Path(local_app_data) if local_app_data else (Path.home() / "AppData" / "Local")
            return (base / "VeraxiStudio" / "workspace").resolve()
        return (Path.home() / ".local" / "share" / "VeraxiStudio" / "workspace").resolve()

    return Path.cwd().resolve()


def set_workspace_root(path: Union[str, Path]) -> Path:
    """Set ``VERAXI_WORKSPACE_DIR`` to a resolved directory and ensure it exists."""
    resolved = Path(path).expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    os.environ["VERAXI_WORKSPACE_DIR"] = str(resolved)
    return resolved


def get_bundle_root() -> Path:
    """Return the read-only bundle root (``sys._MEIPASS`` when frozen, else repo root)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parent.parent.parent


def seed_frozen_workspace(workspace_dir: Optional[Path] = None) -> Path:
    """Ensure workspace directories exist and seed read-only assets in frozen mode."""
    ws = workspace_dir or get_workspace_root()
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "projects").mkdir(parents=True, exist_ok=True)

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundle = Path(getattr(sys, "_MEIPASS")).resolve()
        for rel_dir in ("assets", "examples"):
            src_dir = bundle / rel_dir
            dst_dir = ws / rel_dir
            if src_dir.is_dir() and not dst_dir.exists():
                shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
        for rel_file in ("AGENTS_WEB.md",):
            src_file = bundle / rel_file
            dst_file = ws / rel_file
            if src_file.is_file() and not dst_file.exists():
                shutil.copy2(src_file, dst_file)

    return ws
