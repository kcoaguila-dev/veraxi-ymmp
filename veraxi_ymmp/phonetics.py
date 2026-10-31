"""
Phonetic synchronization utilities for YMMP and MoviePy rendering.

Extracts mora timing, 5-vowel mouth shapes (a, i, u, e, o, silent), and
native YMM4 LipSyncFrames from VOICEVOX AudioQuery data following Japanese
animation lip-sync standards (YMM4 / PSDToolKit / KuchiPaku).
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .logging import logger

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


def get_audio_reactive_intervals(
    wav_path: Optional[Union[str, Path]],
    total_expected_frames: int,
    fps: int = 60,
    threshold: float = 0.10,
) -> List[Tuple[bool, int]]:
    """Extract realistic audio-reactive lip-sync intervals directly from the WAV waveform."""
    if not wav_path or not Path(wav_path).exists():
        # Fallback to standard 0.1s alternation
        step = int(0.12 * fps)
        intervals: List[Tuple[bool, int]] = []
        f = 0
        state = True
        while f < total_expected_frames:
            dur = min(step, total_expected_frames - f)
            intervals.append((state, dur))
            f += dur
            state = not state
        return intervals

    try:
        import wave
        import numpy as np

        with wave.open(str(wav_path), "rb") as wf:
            sr = wf.getframerate()
            n_frames = wf.getnframes()
            data = np.frombuffer(wf.readframes(n_frames), dtype=np.int16)

        samples_per_video_frame = int(sr // fps)
        total_video_frames = min(total_expected_frames, n_frames // samples_per_video_frame)

        frame_states = []
        for f in range(total_video_frames):
            chunk = data[f * samples_per_video_frame : (f + 1) * samples_per_video_frame]
            rms = np.sqrt(np.mean(chunk.astype(float) ** 2)) if len(chunk) > 0 else 0
            frame_states.append(rms)

        max_v = max(frame_states) if frame_states else 1.0
        if max_v == 0:
            max_v = 1.0

        # Increase threshold to 20% so the mouth actually closes between syllables
        raw_is_open = [rms / max_v > 0.2 for rms in frame_states]

        # Enforce minimum durations (e.g. mouth must stay open for at least 3 frames, and closed for at least 2 frames)
        smoothed = []
        if raw_is_open:
            current_state = raw_is_open[0]
            current_len = 0
            for state in raw_is_open:
                if state == current_state:
                    current_len += 1
                else:
                    if (current_state and current_len >= 3) or (
                        not current_state and current_len >= 2
                    ):
                        smoothed.extend([current_state] * current_len)
                        current_state = state
                        current_len = 1
                    else:
                        current_len += 1
            smoothed.extend([current_state] * current_len)

        intervals = []
        if smoothed:
            curr_state = smoothed[0]
            curr_len = 0
            for state in smoothed:
                if state == curr_state:
                    curr_len += 1
                else:
                    intervals.append((curr_state, curr_len))
                    curr_state = state
                    curr_len = 1
            if curr_len > 0:
                intervals.append((curr_state, curr_len))

        covered = sum(dur for _, dur in intervals)
        if covered < total_expected_frames:
            intervals.append((False, total_expected_frames - covered))

        return intervals
    except Exception as e:
        logger.warning("Audio-reactive lipsync fallback: %s", e)
        return [(False, total_expected_frames)]


def resolve_lipsync_intervals(
    audio_path: Optional[Union[str, Path]],
    duration_sec: float,
    prefer_phonetic: bool = True,
    fps: int = 60,
    audio_query: Optional[Dict[str, Any]] = None,
) -> List[Tuple[bool, int]]:
    """
    Resolves lip-sync open/close intervals in video frames.

    Resolution strategy:
    1. If prefer_phonetic is True, look for an explicit audio_query or companion
       `.query.json` file beside audio_path.
    2. If found, convert phonetic blocks to frame intervals.
    3. Fall back to audio-reactive waveform analysis (or periodic alternation).
    """
    total_expected_frames = int(round(duration_sec * fps))
    if total_expected_frames <= 0:
        return []

    query = audio_query
    if query is None and prefer_phonetic and audio_path:
        p = Path(audio_path)
        candidates = [
            p.with_suffix(".query.json"),
            p.parent / f"{p.name}.query.json",
        ]
        for c in candidates:
            if c.exists():
                try:
                    with open(c, "r", encoding="utf-8") as f:
                        query = json.load(f)
                    break
                except Exception as e:
                    logger.warning("Failed to load companion query file %s: %s", c, e)

    if prefer_phonetic and query and "accent_phrases" in query:
        blocks = extract_phonetic_blocks(query, duration_sec, fps=fps)
        intervals: List[Tuple[bool, int]] = []
        curr_frame = 0
        for s_sec, e_sec, is_open in blocks:
            target_end = min(total_expected_frames, int(round(e_sec * fps)))
            dur = target_end - curr_frame
            if dur > 0:
                if intervals and intervals[-1][0] == is_open:
                    intervals[-1] = (is_open, intervals[-1][1] + dur)
                else:
                    intervals.append((is_open, dur))
                curr_frame = target_end

        if curr_frame < total_expected_frames:
            remaining = total_expected_frames - curr_frame
            if intervals and not intervals[-1][0]:
                intervals[-1] = (False, intervals[-1][1] + remaining)
            else:
                intervals.append((False, remaining))

        if intervals:
            return intervals

    return get_audio_reactive_intervals(
        wav_path=audio_path,
        total_expected_frames=total_expected_frames,
        fps=fps,
    )


def normalize_kaname_reading(text: str) -> str:
    """
    Normalizes occurrences of '要' that represent the Japanese noun 'かなめ'
    (keystone, linchpin, pivot, essential core, or fan pivot) to 'かなめ'.

    Distinguishes noun '要' (かなめ) from:
    - On-yomi compound words ('重要', '必要', '要素', '要求', '要約', '要点', '主要', etc.)
    - Inflections of the verb '要る' (要る, 要らない, 要ります, 要れば, 要った)
    - Inflections of '要する' (要する, 要します, 要して, 要した, 要せず)
    - Sentence/clause-initial adverb '要は' (ようは, meaning 'in short')
    """
    if not text or "要" not in text:
        return text

    # 1. 肝心要 -> 肝心かなめ
    t = text.replace("肝心要", "肝心かなめ")

    # 2. 〜の要 (e.g. 防御の要, 守りの要, 扇の要, チームの要, 組織の要, 安全の要)
    # where 要 is not followed by kanji or verb inflection of 要る (る,り,れ,ら,っ) or 要する (す,し,せ)
    t = re.sub(r"の要(?![一-龥るりれらっすしせ])", "のかなめ", t)

    # 3. Protect clause-initial adverb '要は' (ようは = in short / the point is)
    # e.g. "^要は" or after punctuation/space
    t = re.sub(r"(^|[、,\s。！？!?])要は", r"\1__YOU_WA__", t)

    # 4. Standalone '要': not preceded or followed by kanji, and not followed by okurigana (る,り,れ,ら,っ,す,し,せ)
    # Matches: 要となる, 要として, 要である, 要です, 要だ, 要の位置, 要を握る, 要に据える, 要が外れる, これが要。
    t = re.sub(r"(?<![一-龥])要(?![一-龥るりれらっすしせ])", "かなめ", t)

    # 5. Restore protected '要は'
    t = t.replace("__YOU_WA__", "要は")

    return t


DEFAULT_PHONETICS_DICT_PATH = Path(__file__).with_name("phonetics_dict.json")
_RUBY_PATTERN = re.compile(r"[｛\{]([^｜\|\}｝]+)[｜\|]([^\}｝]+)[｝\}]")


def strip_phonetic_ruby(text: str) -> str:
    """Strips inline phonetic ruby notation `{漢字|よみ}` -> `漢字` for display subtitles."""
    if not text:
        return ""
    return _RUBY_PATTERN.sub(r"\1", text)


def expand_phonetic_ruby(text: str) -> str:
    """Expands inline phonetic ruby notation `{漢字|よみ}` -> `よみ` for TTS synthesis."""
    if not text:
        return ""
    return _RUBY_PATTERN.sub(r"\2", text)


def load_phonetics_dict(
    project_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, str]:
    """Loads global `phonetics_dict.json` and merges optional project-level overrides."""
    merged: Dict[str, str] = {}
    candidates = [DEFAULT_PHONETICS_DICT_PATH]
    if project_dir is not None:
        candidates.append(Path(project_dir) / "phonetics_dict.json")

    for p in candidates:
        if p.exists() and p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8-sig"))
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(k, str) and isinstance(v, str) and k:
                            merged[k] = v
            except Exception as exc:
                logger.warning("Failed to load phonetics dictionary %s: %s", p, exc)
    return merged


def normalize_okonau_reading(text: str) -> str:
    """
    Normalizes occurrences of the verb '行う' (おこなう: to perform/conduct) so OpenJTalk
    and pykakasi do not misread inflections like '行って' as 'いって' (to go).
    Preserves directional '行く' when preceded by 'へ' or destination 'に'.
    """
    if not text or "行" not in text:
        return text

    t = re.sub(r"を行([っいうえおわ])", r"をおこな\1", text)
    t = re.sub(
        r"(ご自身で|自分で|慎重に|適切に|確実に|定期的に|厳格に|速やかに|直ちに|優先して|徹底して|継続して|共同で|手動で|自動で|無断で|独自に|判断で|責任で)行([っいうえおわ])",
        r"\1おこな\2",
        t,
    )
    t = re.sub(
        r"(判断|対策|対処|検証|処理|投資|分析|取引|確認|見直し|点検|分散|移行|更新|修正|設定|テスト|チェック|審査|選定|計算|評価|議論|説明|解説|発表|報告|連絡|相談|契約|決済|売買|リバランス)([はもをがこそなど、\s][^。！？!?へに]{0,16}?)(?<![へに])行([っいうえおわ])",
        r"\1\2おこな\3",
        t,
    )
    t = re.sub(r"(?<![へに])行って(ください|下さい)", r"おこなって\1", t)
    return t


def normalize_bun_reading(text: str) -> str:
    """
    Normalizes occurrences of '分' meaning portion/amount/degree ('ぶん')
    after past-tense verbs/adjectives or quantity nouns so OpenJTalk does not
    misread them as 'ふん' (minute).
    """
    if not text or "分" not in text:
        return text

    t = re.sub(
        r"([っいいしんでれけめげせてねべ]た|んだ|いだ)分(?![一-龥])",
        r"\1ぶん",
        text,
    )
    t = re.sub(
        r"(その|この|どの|自分の|あなたの|人数|世帯|不足|余剰|増加|減少|相当|必要|過剰)分(?![一-龥])",
        r"\1ぶん",
        t,
    )
    return t


def normalize_tts_text(
    text: str,
    custom_dict: Optional[Dict[str, str]] = None,
    project_dir: Optional[Union[str, Path]] = None,
) -> str:
    """
    Normalizes text for TTS speech synthesis (VOICEVOX / OpenJTalk).

    Fixes known pronunciation and pitch accent anomalies without modifying
    the original verbatim display subtitle:
    - Conversational affirmative 'ええ、' / 'ええ' (which OpenJTalk parses with
      an unnatural Atamadaka drop ['エ', 'エ'] accent=1, sounding like 'Eh? What?!')
      is normalized to 'えー、' (accent=2, smooth affirmative rising/flat mora).
    - '何でも' (which OpenJTalk parses as 'なにでも') is normalized to 'なんでも'.
    - '要' when used as a noun meaning cornerstone/linchpin/keystone (e.g. '防御の要',
      '守りの要', '扇の要', '要となる', '要として', '肝心要') is normalized to 'かなめ'.
    """
    if not text:
        return ""
    normalized = expand_phonetic_ruby(text)
    pdict = load_phonetics_dict(project_dir=project_dir)
    if custom_dict:
        pdict.update(custom_dict)
    for surface in sorted(pdict.keys(), key=len, reverse=True):
        if surface in normalized:
            normalized = normalized.replace(surface, pdict[surface])
    # Replace sentence-initial or clause-initial 'ええ' / 'エエ' with 'えー'
    # e.g. "ええ、" -> "えー、", "ええ。" -> "えー。", "ええ " -> "えー "
    normalized = re.sub(r"^(ええ|エエ)([、,\s。！？!?]|$)", r"えー\2", normalized)
    # Also after sentence-ending punctuation (e.g. "はい。ええ、そうです")
    normalized = re.sub(r"([。！？!?]\s*)(ええ|エエ)([、,\s。！？!?]|$)", r"\1えー\3", normalized)
    # '何でも' (which OpenJTalk parses as 'なにでも') must be pronounced 'なんでも'
    normalized = normalized.replace("何でも", "なんでも")
    # '要' must be pronounced 'かなめ' in keystone/linchpin/noun positions
    normalized = normalize_kaname_reading(normalized)
    normalized = normalize_okonau_reading(normalized)
    normalized = normalize_bun_reading(normalized)
    return normalized


def tune_audio_query_pitch(audio_query: Dict[str, Any]) -> Dict[str, Any]:
    """
    Directly tunes mora pitches and accent types in a VOICEVOX AudioQuery dictionary.
    Guarantees natural affirmative intonation:
    - If a phrase begins with ['エ', 'エ'] with accent == 1 (falling question/incredulous pitch),
      adjusts accent = 2 and elevates the second mora pitch relative to the first to create
      a polite, gentle affirmative agreement pitch contour.
    """
    accent_phrases = audio_query.get("accent_phrases", [])
    for p in accent_phrases:
        moras = p.get("moras", [])
        mora_texts = [m.get("text") for m in moras]
        # Check for clause-initial 'ええ'
        if mora_texts == ["エ", "エ"] and p.get("accent") == 1:
            p["accent"] = 2
            # Natural affirmative agreement: first mora starts slightly lower, second mora rises gently
            base_p = moras[0].get("pitch", 5.4)
            moras[0]["pitch"] = round(min(base_p, 5.38), 3)
            moras[1]["pitch"] = round(moras[0]["pitch"] + 0.10, 3)
            moras[0]["vowel_length"] = 0.13
            moras[1]["vowel_length"] = 0.15
    return audio_query
