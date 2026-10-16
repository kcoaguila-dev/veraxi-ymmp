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
    Uses 2-state open/close lip-sync ('A' for open, 'Silent' for closed)
    matching rival YMM4 channels (1 open mouth + 1 closed mouth).
    """
    frames: List[Dict[str, str]] = [{"Time": "00:00:00.0000000", "Shape": "Silent"}]
    for s, e, is_open in extract_phonetic_blocks(query, total_dur):
        shape = "A" if is_open else "Silent"
        if frames[-1]["Shape"] != shape:
            frames.append({"Time": format_ymm4_timespan(s), "Shape": shape})
    if frames[-1]["Shape"] != "Silent":
        frames.append({"Time": format_ymm4_timespan(total_dur), "Shape": "Silent"})
    return frames


def extract_vowel_blocks(
    query: Optional[Dict[str, Any]],
    total_dur: float,
    fps: int = 30,
    lead_time: float = 0.035,
) -> List[Tuple[float, float, str]]:
    """
    Extracts 2-state lip-sync intervals ('a' for open mouth, 'silent' for closed mouth)
    following the rival YMM4 standard where only 1 open mouth and 1 closed mouth are used.
    """
    return [
        (s, e, "a" if is_open else "silent")
        for s, e, is_open in extract_phonetic_blocks(query, total_dur, fps=fps, lead_time=lead_time)
    ]


def extract_phonetic_blocks(
    query: Optional[Dict[str, Any]],
    total_dur: float,
    fps: int = 30,
    lead_time: float = 0.035,
) -> List[Tuple[float, float, bool]]:
    """
    Extracts binary speech-synchronized lip sync intervals (open vs closed mouth)
    from VOICEVOX AudioQuery mora timing data (the rival YMM4 2-mouth standard).

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
            step = 0.14 if is_op else 0.07
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

    open_run = 0.0
    for p in query.get("accent_phrases", []):
        for m in p.get("moras", []):
            c_len = (m.get("consonant_length") or 0.0) / speed
            v_len = (m.get("vowel_length") or 0.0) / speed
            consonant = (m.get("consonant") or "").lower()
            vowel = (m.get("vowel") or "").lower()
            is_open = vowel in ("a", "i", "u", "e", "o")

            if c_len > 0:
                # Close mouth on bilabials, non-open vowels, distinct consonants (>= 45ms),
                # or when mouth has been continuously open for >= 180ms (~2 moras)
                should_close = (
                    consonant in BILABIAL_CONSONANTS
                    or not is_open
                    or c_len >= 0.045
                    or open_run >= 0.18
                )
                if should_close:
                    raw_segments.append((t, t + c_len, False))
                    open_run = 0.0
                else:
                    raw_segments.append((t, t + c_len, True))
                    open_run += c_len
                t += c_len

            if v_len > 0:
                raw_segments.append((t, t + v_len, is_open))
                t += v_len
                if is_open:
                    open_run += v_len
                else:
                    open_run = 0.0

        if p.get("pause_mora"):
            pv_len = (p["pause_mora"].get("vowel_length") or 0.0) / speed
            if pv_len > 0:
                raw_segments.append((t, t + pv_len, False))
                t += pv_len
                open_run = 0.0

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

    # Ensure every closure between two open segments is at least 0.05s (3 frames at 60fps)
    # so the mouth never flickers for 1 frame or fails to visibly close.
    min_hold = 0.05
    for i in range(1, len(merged) - 1):
        seg_dur = merged[i][1] - merged[i][0]
        if not merged[i][2] and seg_dur < min_hold:
            deficit = min_hold - seg_dur
            next_dur = merged[i + 1][1] - merged[i + 1][0]
            if next_dur > min_hold + deficit:
                merged[i][1] += deficit
                merged[i + 1][0] += deficit
            elif lead_time > 0:
                prev_dur = merged[i - 1][1] - merged[i - 1][0]
                if prev_dur > min_hold + deficit:
                    merged[i - 1][1] -= deficit
                    merged[i][0] -= deficit

    return [(float(s), float(e), bool(is_open)) for s, e, is_open in merged]

