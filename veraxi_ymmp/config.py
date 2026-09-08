"""
Configuration object for compiler settings.
"""

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .constants import (
    DEFAULT_FPS,
    FRAMES_PER_CHAR,
    MIN_LENGTH_FRAMES,
    DEFAULT_VOICEVOX_URL,
    DEFAULT_VOICEVOX_TIMEOUT,
    DEFAULT_SPEAKER_ID,
)


@dataclass
class CompilerConfig:
    """Configuration options for the YMMP compiler."""
    fps: int = DEFAULT_FPS
    frames_per_char: int = FRAMES_PER_CHAR
    min_length_frames: int = MIN_LENGTH_FRAMES
    use_tts: bool = False
    voicevox_url: str = DEFAULT_VOICEVOX_URL
    voicevox_timeout: int = DEFAULT_VOICEVOX_TIMEOUT
    default_speaker_id: int = DEFAULT_SPEAKER_ID
    speaker_map: Dict[str, int] = field(default_factory=dict)
    use_cache: bool = True
    cache_dir: Optional[Path] = None
    use_bom: bool = False

    @classmethod
    def from_cli_args(cls, args: argparse.Namespace) -> "CompilerConfig":
        """Create a CompilerConfig from parsed CLI arguments."""
        config = cls()

        if hasattr(args, 'tts'):
            config.use_tts = args.tts

        if hasattr(args, 'voicevox_url') and args.voicevox_url:
            config.voicevox_url = args.voicevox_url

        if hasattr(args, 'default_speaker') and args.default_speaker is not None:
            config.default_speaker_id = args.default_speaker

        if hasattr(args, 'bom'):
            config.use_bom = args.bom

        if hasattr(args, 'no_cache') and args.no_cache:
            config.use_cache = False

        # Optional args for cache dir (could be added to CLI later)
        if hasattr(args, 'cache_dir') and args.cache_dir:
            config.cache_dir = Path(args.cache_dir)

        return config
