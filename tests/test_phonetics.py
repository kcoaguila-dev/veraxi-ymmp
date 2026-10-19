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

    # '何でも' normalized to 'なんでも'
    assert normalize_tts_text("何でも買えば儲かる") == "なんでも買えば儲かる"

    # '要' normalized to 'かなめ' systematically for keystone/linchpin/noun
    assert normalize_tts_text("防御の要ですわ。") == "防御のかなめですわ。"
    assert normalize_tts_text("守りの要として活躍する。") == "守りのかなめとして活躍する。"
    assert normalize_tts_text("扇の要が壊れた。") == "扇のかなめが壊れた。"
    assert normalize_tts_text("チームの要になる。") == "チームのかなめになる。"
    assert normalize_tts_text("肝心要のポイントだ。") == "肝心かなめのポイントだ。"
    assert normalize_tts_text("守りの要は彼だ。") == "守りのかなめは彼だ。"
    assert normalize_tts_text("これが要。") == "これがかなめ。"

    # Non-kaname '要' preserved verbatim for OpenJTalk/VOICEVOX standard pronunciations
    assert normalize_tts_text("極めて重要ですわね。") == "極めて重要ですわね。"
    assert normalize_tts_text("必要不可欠な要素です。") == "必要不可欠な要素です。"
    assert normalize_tts_text("要約してください。") == "要約してください。"
    assert normalize_tts_text("多くの時間を要する。") == "多くの時間を要する。"
    assert normalize_tts_text("お金が要る。") == "お金が要る。"
    assert normalize_tts_text("そんなものは要らない。") == "そんなものは要らない。"
    assert normalize_tts_text("要は、こういうことです。") == "要は、こういうことです。"


def test_normalize_kaname_reading() -> None:
    from veraxi_ymmp.phonetics import normalize_kaname_reading

    assert normalize_kaname_reading("インフレ下でも値上げできる価格転嫁力を持つ企業や、割安で見直されている日本や世界市場へ広く分散することが防御の要ですわ。") == (
        "インフレ下でも値上げできる価格転嫁力を持つ企業や、割安で見直されている日本や世界市場へ広く分散することが防御のかなめですわ。"
    )
    assert normalize_kaname_reading("要の位置") == "かなめの位置"
    assert normalize_kaname_reading("要を握る") == "かなめを握る"
    assert normalize_kaname_reading("要だ") == "かなめだ"
    assert normalize_kaname_reading("要です") == "かなめです"
    assert normalize_kaname_reading("主要な要因") == "主要な要因"
    assert normalize_kaname_reading("要綱を確認") == "要綱を確認"
    assert normalize_kaname_reading("要点") == "要点"



def test_tune_audio_query_pitch() -> None:
    from veraxi_ymmp.phonetics import tune_audio_query_pitch

    query = {
        "accent_phrases": [
            {
                "moras": [
                    {"text": "エ", "pitch": 5.64, "vowel_length": 0.16},
                    {"text": "エ", "pitch": 5.56, "vowel_length": 0.16},
                ],
                "accent": 1,
            },
            {
                "moras": [
                    {"text": "ソ", "pitch": 5.8, "vowel_length": 0.12},
                    {"text": "ウ", "pitch": 5.7, "vowel_length": 0.12},
                ],
                "accent": 1,
            },
        ]
    }

    tuned = tune_audio_query_pitch(query)
    phrase0 = tuned["accent_phrases"][0]
    assert phrase0["accent"] == 2
    assert phrase0["moras"][0]["pitch"] == 5.38
    assert phrase0["moras"][1]["pitch"] == 5.48
    assert phrase0["moras"][0]["vowel_length"] == 0.13
    assert phrase0["moras"][1]["vowel_length"] == 0.15

    # Non-matching phrases (e.g. second phrase) should remain unchanged
    phrase1 = tuned["accent_phrases"][1]
    assert phrase1["accent"] == 1
    assert phrase1["moras"][0]["pitch"] == 5.8
