"""
Utility functions for veraxi-ymmp.
"""

from pathlib import Path
from typing import Union


def ensure_path(path: Union[str, Path]) -> Path:
    """Convert string to Path if necessary."""
    return Path(path) if isinstance(path, str) else path


def resolve_path(path: Union[str, Path]) -> Path:
    """Convert to Path and resolve to absolute path."""
    return ensure_path(path).resolve()
