"""
Tactile Sound FX (Sonic Punctuation) Generator and Registry for veraxi-ymmp.

Provides procedural, broadcast-clean tactile sound design assets (WAV 48kHz 16-bit PCM)
without relying on external sound libraries or cartoon slapstick effects:
- whoosh_subtle: Soft airy transition whoosh on slide appearances
- impact_sub_bass: 55Hz cinematic sub-bass thud on alarming metrics / market shocks
- ui_snap: Tactile 2ms click / snap on micro-reaction punch-ins
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from typing import Dict


def generate_sub_bass_impact(out_path: Path, duration: float = 0.38, freq: float = 55.0, sample_rate: int = 48000) -> Path:
    """Generate a clean, low-end 55Hz cinematic sub-thud with exponential decay."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total_samples = int(duration * sample_rate)
    frames = bytearray()

    for i in range(total_samples):
        t = i / sample_rate
        # Exponential volume envelope
        env = math.exp(-t * 9.0)
        # Gentle pitch drop from freq to freq*0.75
        current_freq = freq * (1.0 - (t / duration) * 0.25)
        sample = math.sin(2.0 * math.pi * current_freq * t) * env * 0.70
        clamped = max(-1.0, min(1.0, sample))
        val = int(clamped * 32767.0)
        frames.extend(struct.pack("<h", val))

    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(frames))

    return out_path


def generate_subtle_whoosh(out_path: Path, duration: float = 0.28, sample_rate: int = 48000) -> Path:
    """Generate a soft, airy transition whoosh (smooth noise/sine sweep)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total_samples = int(duration * sample_rate)
    frames = bytearray()

    # Deterministic pseudo-random sequence for noise
    seed = 1234567

    for i in range(total_samples):
        t = i / sample_rate
        norm_t = t / duration
        # Smooth bell envelope (Hann curve)
        env = 0.5 * (1.0 - math.cos(2.0 * math.pi * norm_t))

        # Sweep center tone
        center_f = 120.0 + 380.0 * math.sin(math.pi * norm_t)
        sine_comp = math.sin(2.0 * math.pi * center_f * t)

        # Subtle noise texture
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        noise_comp = (seed / 0x3FFFFFFF) - 1.0

        sample = (0.6 * sine_comp + 0.4 * noise_comp) * env * 0.35
        clamped = max(-1.0, min(1.0, sample))
        val = int(clamped * 32767.0)
        frames.extend(struct.pack("<h", val))

    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(frames))

    return out_path


def generate_ui_snap(out_path: Path, duration: float = 0.04, sample_rate: int = 48000) -> Path:
    """Generate a tactile 2ms micro-click / snap for punch-in camera transitions."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total_samples = int(duration * sample_rate)
    frames = bytearray()

    for i in range(total_samples):
        t = i / sample_rate
        # Rapid 3ms decay
        env = math.exp(-t * 220.0)
        sample = math.sin(2.0 * math.pi * 1400.0 * t) * env * 0.45
        clamped = max(-1.0, min(1.0, sample))
        val = int(clamped * 32767.0)
        frames.extend(struct.pack("<h", val))

    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(frames))

    return out_path


def ensure_tactile_sfx_suite(target_dir: Path | None = None) -> Dict[str, Path]:
    """
    Ensure all three tactile sound design files exist on disk, generating them if missing.

    Returns:
        Dictionary mapping SFX name to its resolved Path.
    """
    base_dir = (target_dir or (Path(__file__).parent.parent / "assets" / "sfx")).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)

    whoosh_p = base_dir / "whoosh_subtle.wav"
    impact_p = base_dir / "impact_sub_bass.wav"
    snap_p = base_dir / "ui_snap.wav"

    if not whoosh_p.exists():
        generate_subtle_whoosh(whoosh_p)
    if not impact_p.exists():
        generate_sub_bass_impact(impact_p)
    if not snap_p.exists():
        generate_ui_snap(snap_p)

    return {
        "whoosh": whoosh_p,
        "impact": impact_p,
        "snap": snap_p,
    }
