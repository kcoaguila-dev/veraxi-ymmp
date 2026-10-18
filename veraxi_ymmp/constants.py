"""
Constants used throughout the veraxi-ymmp project.
"""

# Timing constants
DEFAULT_FPS = 60
FRAMES_PER_CHAR = 5
MIN_LENGTH_FRAMES = 30

# VOICEVOX defaults
DEFAULT_VOICEVOX_URL = "http://localhost:50021"
DEFAULT_VOICEVOX_TIMEOUT = 30
DEFAULT_SPEAKER_ID = 3  # Zundamon

# Default asset paths
DEFAULT_TEMPLATE_PATH = "examples/full_template.ymmp"
DEFAULT_BG_IMAGE_PATH = "assets/bg/clean_classroom.jpg"
DEFAULT_BGM_CANDIDATES = [
    "assets/bgm/2_23_AM.mp3",
    "assets/bgm/2_23_AM.m4a",
]

# Canvas and layout defaults
DEFAULT_CANVAS_WIDTH: int = 1920
DEFAULT_CANVAS_HEIGHT: int = 1080
DEFAULT_BGM_DUCKING_VOLUME: float = 3.0
DEFAULT_BG_FILL_ZOOM: float = 187.5
KNOWN_CHARACTERS: tuple[str, ...] = ("ずんだもん", "四国めたん", "春日部つむぎ", "Zundamon")
