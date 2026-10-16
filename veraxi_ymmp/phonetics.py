"""
Phonetic synchronization utilities for YMMP and MoviePy rendering.

Extracts mora timing, 5-vowel mouth shapes (a, i, u, e, o, silent), and
native YMM4 LipSyncFrames from VOICEVOX AudioQuery data following Japanese
animation lip-sync standards (YMM4 / PSDToolKit / KuchiPaku).
"""

from typing import Any, Dict, List, Optional, Tuple

VOWEL_MAP_YMM4 = {
    "a": "A",
    "i": "I",
    "u": "U",
    "e": "E",
    "o": "O",
    "silent": "Silent",
}

# Consonants where human lips physically close (bilabials) or glottal stop
BILABIAL_CONSONANTS = {"m", "p", "b", "my", "py", "by", "cl", "pau", "sil"}


def format_ymm4_timespan(seconds: float) -> str:
    """Format seconds as .NET TimeSpan string 'HH:MM:SS.fffffff'."""
    t = max(0.0, float(seconds))
    total_ticks = int(round(t * 10_000_000))
    hours, rem = divmod(total_ticks, 36_000_000_000)
    minutes, rem = divmod(rem, 600_000_000)
    secs, ticks = divmod(rem, 10_000_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ticks:07d}"


def build_ymm4_lipsync_frames(
    query: Optional[Dict[str, Any]],
    total_dur: float,
) -> List[Dict[str, str]]:
    """
    Build native YMM4 VoiceItem LipSyncFrames from VOICEVOX AudioQuery.
    Matches YukkuriMovieMaker.Plugin.Voice.VOICEVOX.VOICEVOXVoiceSpeaker.CreateLipSyncFrame.
    """
    frames: List[Dict[str, str]] = [{"Time": "00:00:00.0000000", "Shape": "Silent"}]
    for s, e, vowel in extract_vowel_blocks(query, total_dur):
        shape = VOWEL_MAP_YMM4.get(vowel, "Silent")
        if frames[-1]["Shape"] != shape:
            frames.append({"Time": format_ymm4_timespan(s), "Shape": shape})
    if frames[-1]["Shape"] != "Silent":
        frames.append({"Time": format_ymm4_timespan(total_dur), "Shape": "Silent"})
    return frames


def extract_vowel_blocks(
    query: Optional[Dict[str, Any]],
    total_dur: float,
    fps: int = 30,
    lead_time: float = 0.045,
) -> List[Tuple[float, float, str]]:
    """
    Extracts natural 5-vowel phonetic lip-sync intervals ('a', 'i', 'u', 'e', 'o', 'silent')
    from VOICEVOX AudioQuery mora timing data for multi-layer PSD characters.

    Rules matching YMM4 & Japanese anime lip-sync:
    - Pauses, 'N' (ん), 'cl' (っ), and bilabial consonants (m, p, b) close the mouth ('silent').
    - Non-bilabial consonants between DIFFERENT vowels transition smoothly without snapping shut.
    - Non-bilabial consonants between IDENTICAL vowels (e.g. 'ka-ga' -> a..a) dip to half-open
      'i' (or 'u' if repeating 'i') so consecutive identical vowels visibly articulate without
      robotic full-closure flapping.
    """
    if not query or "accent_phrases" not in query:
        blocks: List[Tuple[float, float, str]] = []
        delay = min(0.1, total_dur * 0.1)
        if delay > 0:
            blocks.append((0.0, delay, "silent"))
        t = delay
        cycle = ["a", "o", "i", "e", "u", "a", "silent"]
        idx = 0
        while t < total_dur:
            v = cycle[idx % len(cycle)]
            step = 0.07 if v == "silent" else 0.11
            next_t = min(total_dur, t + step)
            blocks.append((t, next_t, v))
            idx += 1
            t = next_t
        return blocks

    speed = query.get("speedScale", 1.0) or 1.0
    t = (query.get("prePhonemeLength", 0.1) or 0.1) / speed
    raw_segments: List[Tuple[float, float, str]] = []

    if t > 0:
        raw_segments.append((0.0, t, "silent"))

    prev_vowel = "silent"

    for p in query.get("accent_phrases", []):
        for m in p.get("moras", []):
            c_len = (m.get("consonant_length") or 0.0) / speed
            v_len = (m.get("vowel_length") or 0.0) / speed
            consonant = (m.get("consonant") or "").lower()
            vowel = (m.get("vowel") or "").lower()
            v_shape = vowel if vowel in ("a", "i", "u", "e", "o") else "silent"

            if c_len > 0:
                if consonant in BILABIAL_CONSONANTS or v_shape == "silent":
                    c_shape = "silent"
                elif v_shape == prev_vowel and c_len >= 0.03:
                    # Dip to half-open mouth between identical consecutive vowels
                    c_shape = "u" if v_shape == "i" else "i"
                else:
                    # Smooth transition across different vowels or initial open-mouth consonant
                    c_shape = v_shape
                raw_segments.append((t, t + c_len, c_shape))
                t += c_len

            if v_len > 0:
                raw_segments.append((t, t + v_len, v_shape))
                t += v_len
                prev_vowel = v_shape

        if p.get("pause_mora"):
            pv_len = (p["pause_mora"].get("vowel_length") or 0.0) / speed
            if pv_len > 0:
                raw_segments.append((t, t + pv_len, "silent"))
                t += pv_len
                prev_vowel = "silent"

    if t < total_dur:
        raw_segments.append((t, total_dur, "silent"))

    # Merge adjacent identical vowel states
    merged: List[List[Any]] = []
    for s, e, v_shape in raw_segments:
        if e <= s:
            continue
        if not merged:
            merged.append([s, e, v_shape])
        else:
            if merged[-1][2] == v_shape:
                merged[-1][1] = e
            else:
                merged.append([s, e, v_shape])

    # Lead time: start opening ~25ms before vowel onset after silence
    if lead_time > 0:
        for i in range(1, len(merged)):
            if merged[i - 1][2] == "silent" and merged[i][2] != "silent":
                prev_dur = merged[i - 1][1] - merged[i - 1][0]
                shift = min(lead_time, prev_dur * 0.45)
                merged[i - 1][1] -= shift
                merged[i][0] -= shift

    return [(float(s), float(e), str(v_shape)) for s, e, v_shape in merged]


def extract_phonetic_blocks(
    query: Optional[Dict[str, Any]],
    total_dur: float,
    fps: int = 30,
    lead_time: float = 0.035,
) -> List[Tuple[float, float, bool]]:
    """
    Extracts binary speech-synchronized lip sync intervals (open vs closed mouth)
    from VOICEVOX AudioQuery mora timing data (used by 2-state MoviePy PNG renderer).

    Returns a list of (start_time, end_time, is_open) intervals in seconds.
    """
    if not query or "accent_phrases" not in query:
        blocks = []
        delay = min(0.1, total_dur * 0.1)
        if delay > 0:
            blocks.append((0.0, delay, False))
        t = delay
        is_op = True
        while t < total_dur:
            step = 0.12 if is_op else 0.08
            next_t = min(total_dur, t + step)
            blocks.append((t, next_t, is_op))
            t = next_t
            is_op = not is_op
        return blocks

    speed = query.get("speedScale", 1.0) or 1.0
    t = (query.get("prePhonemeLength", 0.1) or 0.1) / speed
    raw_segments: List[Tuple[float, float, bool]] = []

    if t > 0:
        raw_segments.append((0.0, t, False))

    for p in query.get("accent_phrases", []):
        for m in p.get("moras", []):
            c_len = (m.get("consonant_length") or 0.0) / speed
            v_len = (m.get("vowel_length") or 0.0) / speed
            vowel = (m.get("vowel") or "").lower()

            if c_len > 0:
                raw_segments.append((t, t + c_len, False))
                t += c_len

            is_open = vowel in ("a", "i", "u", "e", "o")
            if v_len > 0:
                raw_segments.append((t, t + v_len, is_open))
                t += v_len

        if p.get("pause_mora"):
            pv_len = (p["pause_mora"].get("vowel_length") or 0.0) / speed
            if pv_len > 0:
                raw_segments.append((t, t + pv_len, False))
                t += pv_len

    if t < total_dur:
        raw_segments.append((t, total_dur, False))

    merged: List[List[Any]] = []
    for s, e, is_open in raw_segments:
        if e <= s:
            continue
        if not merged:
            merged.append([s, e, is_open])
        else:
            if merged[-1][2] == is_open:
                merged[-1][1] = e
            else:
                merged.append([s, e, is_open])

    if lead_time > 0:
        for i in range(1, len(merged)):
            if not merged[i - 1][2] and merged[i][2]:
                prev_dur = merged[i - 1][1] - merged[i - 1][0]
                shift = min(lead_time, prev_dur * 0.5)
                merged[i - 1][1] -= shift
                merged[i][0] -= shift

    return [(float(s), float(e), bool(is_open)) for s, e, is_open in merged]
