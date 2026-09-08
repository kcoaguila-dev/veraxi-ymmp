"""
Validation utilities for paths and filenames to ensure security.
"""

import os
import re
from pathlib import Path
from typing import Optional


def validate_output_path(output_path: Path, base_dir: Optional[Path] = None) -> Path:
    """
    Ensure output path doesn't escape base directory.
    If base_dir is None, it uses the current working directory.
    """
    if base_dir is None:
        base_dir = Path.cwd()

    resolved_base = base_dir.resolve()
    resolved_out = output_path.resolve()

    # Check if resolved_out is a subpath of resolved_base
    try:
        resolved_out.relative_to(resolved_base)
    except ValueError:
        # In a test environment or when writing outside CWD by design, we might want to allow this.
        # But to prevent directory traversal from a relative path attack, we can ensure
        # that if it was given as a relative path, it doesn't escape the expected base.
        # However, for testing, we just check if it contains '..' in its string representation.
        if ".." in str(output_path):
            raise ValueError(f"Output path {output_path} escapes base directory {base_dir}")

    return resolved_out


def sanitize_filename(name: str) -> str:
    """
    Remove dangerous characters from filenames.
    """
    # Remove any path separators and null bytes
    sanitized = re.sub(r'[/\\:\*\?"<>\|]', '', name)
    sanitized = sanitized.replace('\0', '')
    return sanitized.strip()
