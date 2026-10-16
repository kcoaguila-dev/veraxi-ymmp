"""
Phonetic synchronization utilities for YMMP and MoviePy rendering.

Extracts mora timing and phoneme intervals from VOICEVOX AudioQuery data
following Japanese animation lip-sync standards (e.g. KuchiPaku/PSDTool).
"""

from typing import Any, Dict, List, Optional, Tuple


def extract_phonetic_blocks(
    query: Optional[Dict[str, Any]],
    total_dur: float,
    fps: int = 30,
    lead_time: float = 0.035
) -> List[Tuple[float, float, bool]]:
    """
    Extracts speech-synchronized lip sync intervals (open vs closed mouth)
    from VOICEVOX AudioQuery mora timing data (the rival/KuchiPaku standard).
    
    Returns a list of (start_time, end_time, is_open) intervals in seconds.
    """
    if not query or "accent_phrases" not in query:
        # Fallback if no audio query: alternating cadence during active speech
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

            # Consonants are closed mouth
            if c_len > 0:
                raw_segments.append((t, t + c_len, False))
                t += c_len

            # Vowels: open mouth for 'a', 'i', 'u', 'e', 'o'.
            # 'N' (ん) and pauses are closed!
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

    # Merge adjacent segments with identical open state
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

    # Lead time: start opening 1-2 frames (approx 35ms) before vowel onset
    if lead_time > 0:
        for i in range(1, len(merged)):
            if not merged[i-1][2] and merged[i][2]: # transition from closed to open
                prev_dur = merged[i-1][1] - merged[i-1][0]
                shift = min(lead_time, prev_dur * 0.5)
                merged[i-1][1] -= shift
                merged[i][0] -= shift

    return [(float(s), float(e), bool(is_open)) for s, e, is_open in merged]
