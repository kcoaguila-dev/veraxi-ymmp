"""
Constants used throughout the veraxi-ymmp project.
"""

from pathlib import Path
from typing import Dict, Iterable, Optional

# Timing constants
DEFAULT_FPS = 60
FRAMES_PER_CHAR = 5
MIN_LENGTH_FRAMES = 30

# VOICEVOX defaults
DEFAULT_VOICEVOX_URL = "http://localhost:50021"
DEFAULT_VOICEVOX_TIMEOUT = 30
DEFAULT_SPEAKER_ID = 3  # Zundamon
DEFAULT_SPEAKER_MAP: Dict[str, int] = {
    "ずんだもん": 3,
    "四国めたん": 2,
    "春日部つむぎ": 8,
}

# Default asset paths
DEFAULT_TEMPLATE_PATH = "examples/full_template.ymmp"
# Optional local assets (NOT tracked in git — see assets/ASSETS.md):
# ``assets/bg/classroom.jpg`` and ``assets/bgm/2_23_AM.*`` are licensed,
# user-supplied files. Every consumer must treat them as optional: when a
# candidate is absent, fall back to the in-repo ``default_dark.png``
# background, and omit BGM entirely instead of referencing a missing file.
FALLBACK_BG_IMAGE_PATH = "assets/bg/default_dark.png"
DEFAULT_BG_IMAGE_PATH = FALLBACK_BG_IMAGE_PATH
DEFAULT_BG_CANDIDATES = [
    "assets/bg/classroom.jpg",
    "assets/bg/default_dark.png",
]
DEFAULT_BGM_CANDIDATES = [
    "assets/bgm/2_23_AM.mp3",
    "assets/bgm/2_23_AM.m4a",
]


def resolve_optional_asset(
    candidates: Iterable[str], base: Optional[Path] = None
) -> Optional[Path]:
    """Return the first candidate that exists on disk, or ``None``.

    Candidates are tried in order, first as given (relative to the current
    working directory), then relative to *base* when one is supplied. A
    missing optional asset is a normal state on a fresh clone, never an
    error: callers fall back (backgrounds) or omit the asset (BGM).
    """
    for cand in candidates:
        path = Path(cand)
        if path.exists():
            return path
        if base is not None:
            based = base / cand
            if based.exists():
                return based
    return None


def resolve_background_image(base: Optional[Path] = None) -> Path:
    """Resolve the background image, falling back to ``default_dark.png``.

    Prefers the optional local ``classroom.jpg`` when present; otherwise
    returns the committed ``assets/bg/default_dark.png`` fallback path.
    """
    resolved = resolve_optional_asset(DEFAULT_BG_CANDIDATES, base=base)
    if resolved is not None:
        return resolved
    return (base / FALLBACK_BG_IMAGE_PATH) if base is not None else Path(FALLBACK_BG_IMAGE_PATH)

# Canvas and layout defaults
DEFAULT_CANVAS_WIDTH: int = 1920
DEFAULT_CANVAS_HEIGHT: int = 1080
DEFAULT_BGM_DUCKING_VOLUME: float = 18.0
DEFAULT_BG_FILL_ZOOM: float = 187.5
DEFAULT_SUBTITLE_SAFE_BOTTOM_MARGIN: float = 50.0
DEFAULT_SUBTITLE_BOTTOM_EDGE_Y: float = (DEFAULT_CANVAS_HEIGHT / 2.0) - DEFAULT_SUBTITLE_SAFE_BOTTOM_MARGIN
DEFAULT_SUBTITLE_CENTER_Y: float = 345.0
KNOWN_CHARACTERS: tuple[str, ...] = ("ずんだもん", "四国めたん", "春日部つむぎ", "Zundamon")

# Upstream audio gain staging targets (ITU-R BS.1770 / EBU R128)
DEFAULT_SPEECH_TARGET_LUFS: float = -16.0
DEFAULT_SPEECH_TARGET_TP: float = -1.5
DEFAULT_AUDIO_SAMPLE_RATE: int = 48000

# Audio tempo sculpting and zero-gap clamping defaults
DEFAULT_SPEAKER_SPEED_MAP: Dict[str, float] = {
    "ずんだもん": 1.18,
    "四国めたん": 1.12,
    "春日部つむぎ": 1.14,
}
DEFAULT_SPEECH_PADDING_SEC: float = 0.05
DEFAULT_PUNCHLINE_PAUSE_SEC: float = 0.25
