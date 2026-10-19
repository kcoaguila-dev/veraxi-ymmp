"""Tests for phonetic synchronization and lip-sync utilities."""

from __future__ import annotations

import json
import wave
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pytest

from veraxi_ymmp.phonetics import (
    build_ymm4_lipsync_frames,
    format_ymm4_timespan,
    get_audio_reactive_intervals,
    resolve_lipsync_intervals,
)
from veraxi_ymmp.premiere_exporter import (
    get_audio_reactive_intervals as reexported_get_audio_reactive_intervals,
)


@pytest.fixture
def sample_wav(tmp_path: Path) -> Path:
    """Creates a temporary 1-second 48kHz mono WAV file."""
    wav_path = tmp_path / "test_audio.wav"
    sample_rate = 48000
    duration = 1.0  # seconds
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    # Generate 440Hz sine wave with an amplitude burst in the middle
    amplitude = np.zeros_like(t)
    amplitude[int(0.2 * sample_rate) : int(0.7 * sample_rate)] = 0.8
    signal = (amplitude * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(signal.tobytes())

    return wav_path


@pytest.fixture
def sample_query() -> Dict[str, Any]:
    """Sample VOICEVOX AudioQuery structure."""
    return {
        "accent_phrases": [
            {
                "moras": [
                    {
                        "text": "コ",
                        "consonant": "k",
                        "consonant_length": 0.05,
                        "vowel": "o",
                        "vowel_length": 0.12,
                        "pitch": 5.8,
                    },
                    {
                        "text": "ン",
                        "consonant": None,
                        "consonant_length": None,
                        "vowel": "N",
                        "vowel_length": 0.10,
                        "pitch": 5.9,
                    },
                    {
                        "text": "ニ",
                        "consonant": "n",
                        "consonant_length": 0.06,
                        "vowel": "i",
                        "vowel_length": 0.14,
                        "pitch": 5.7,
                    },
                ],
                "accent": 1,
                "pause_mora": None,
            }
        ],
        "speedScale": 1.0,
        "pitchScale": 0.0,
        "intonationScale": 1.0,
        "volumeScale": 1.0,
        "prePhonemeLength": 0.1,
        "postPhonemeLength": 0.1,
        "outputSamplingRate": 48000,
        "outputStereo": False,
    }


def test_format_ymm4_timespan() -> None:
    assert format_ymm4_timespan(0.0) == "00:00:00.0000000"
    assert format_ymm4_timespan(1.5) == "00:00:01.5000000"


def test_build_ymm4_lipsync_frames(sample_query: Dict[str, Any]) -> None:
    frames = build_ymm4_lipsync_frames(sample_query, total_dur=1.0)
    assert isinstance(frames, list)
    assert len(frames) >= 2
    assert frames[0]["Shape"] == "Silent"
    assert frames[-1]["Shape"] == "Silent"


def test_get_audio_reactive_intervals_fallback() -> None:
    # Missing audio path falls back to default alternation
    intervals = get_audio_reactive_intervals(wav_path=None, total_expected_frames=60, fps=60)
    assert sum(dur for _, dur in intervals) == 60
    assert len(intervals) > 0


def test_get_audio_reactive_intervals_with_wav(sample_wav: Path) -> None:
    intervals = get_audio_reactive_intervals(wav_path=sample_wav, total_expected_frames=60, fps=60)
    assert sum(dur for _, dur in intervals) == 60
    # Should contain both True (open) and False (closed) intervals given the burst
    states = set(state for state, _ in intervals)
    assert True in states
    assert False in states


def test_resolve_lipsync_intervals_with_companion_query(
    sample_wav: Path, sample_query: Dict[str, Any]
) -> None:
    # Save companion query file
    query_path = sample_wav.with_suffix(".query.json")
    with open(query_path, "w", encoding="utf-8") as f:
        json.dump(sample_query, f)

    # When companion query exists and prefer_phonetic=True
    intervals = resolve_lipsync_intervals(
        audio_path=sample_wav,
        duration_sec=1.0,
        prefer_phonetic=True,
        fps=60,
    )
    assert sum(dur for _, dur in intervals) == 60
    assert len(intervals) > 0


def test_resolve_lipsync_intervals_fallback_without_query(sample_wav: Path) -> None:
    # No companion query file
    intervals = resolve_lipsync_intervals(
        audio_path=sample_wav,
        duration_sec=1.0,
        prefer_phonetic=True,
        fps=60,
    )
    assert sum(dur for _, dur in intervals) == 60


def test_reexported_get_audio_reactive_intervals_in_premiere_exporter() -> None:
    # Ensure re-export matches identical function
    assert reexported_get_audio_reactive_intervals is get_audio_reactive_intervals


def test_normalize_tts_text() -> None:
    from veraxi_ymmp.phonetics import normalize_tts_text

    # Affirmative ええ at start of sentence/clause
    assert normalize_tts_text("ええ、極めて重要ですわね。") == "えー、極めて重要ですわね。"
    assert normalize_tts_text("ええ。そうですわね。") == "えー。そうですわね。"
    assert normalize_tts_text("はい。ええ、そうです。") == "はい。えー、そうです。"
    assert normalize_tts_text("エエ、その通り！") == "えー、その通り！"
    assert normalize_tts_text("ええ") == "えー"

    # Non-affirmative words containing ええ are preserved
    assert normalize_tts_text("ええと、これは") == "ええと、これは"
    assert normalize_tts_text("永遠の愛") == "永遠の愛"
    assert normalize_tts_text("") == ""
