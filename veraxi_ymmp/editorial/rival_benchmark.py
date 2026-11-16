"""Numeric-density cognitive-load auditing and rival-transcript benchmarking.

Provides:
1. Numeric-density analysis for `script.json` dialogue cuts (detecting
   cognitive overload, multi-number bubbles, and long numeric streaks).
2. Free, open-source rival transcript benchmarking from local `.srt`/`.vtt`/`.txt`
   files or YouTube URLs/IDs via `youtube-transcript-api` or `yt-dlp` (when
   installed), measuring numbers-per-minute, numeric segment share, and
   first-number hook latency.
"""

from __future__ import annotations

import dataclasses
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_RUBY_RE = re.compile(r"\{([^|{}]+)\|[^|{}]+\}")
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_SRT_TIME_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)
_VTT_TIME_RE = re.compile(
    r"(?:(\d{2}):)?(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(?:(\d{2}):)?(\d{2}):(\d{2})\.(\d{3})"
)
_YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})")

# Cognitive-load thresholds calibrated against Veraxi projects (08-10 averaged 7-16%).
MAX_HEALTHY_NUMERIC_CUT_RATIO = 0.25
SEVERE_NUMERIC_CUT_RATIO = 0.35
MAX_HEALTHY_MULTI_NUMBER_RATIO = 0.10
MAX_HEALTHY_NUMERIC_STREAK = 4


@dataclasses.dataclass
class NumericDensityReport:
    """Cognitive-load telemetry for quantitative density in a script or transcript."""

    total_cuts: int
    cuts_with_numbers: int
    total_numbers: int
    multi_number_cuts: int
    max_numeric_streak: int
    numeric_cut_ratio: float
    multi_number_ratio: float
    numbers_per_minute: Optional[float] = None
    first_number_seconds: Optional[float] = None


@dataclasses.dataclass
class RivalBenchmarkReport:
    """Benchmark metrics extracted from a rival video's transcript/subtitles."""

    source_label: str
    title: str
    channel: Optional[str]
    duration_seconds: Optional[float]
    view_count: Optional[int]
    total_segments: int
    total_chars: int
    density: NumericDensityReport
    hook_preview: str


def _clean_text(text: str) -> str:
    """Normalize width and strip inline `{Kanji|ruby}` annotations."""
    stripped = _RUBY_RE.sub(r"\1", text)
    return unicodedata.normalize("NFKC", stripped).strip()


def extract_numbers(text: str) -> List[str]:
    """Extract normalized numeric tokens from dialogue or subtitle text."""
    return _NUM_RE.findall(_clean_text(text))


def analyze_numeric_density(
    segments: Sequence[Tuple[str, Optional[float], Optional[float]]],
) -> NumericDensityReport:
    """Compute numeric-density and streak metrics over `(text, start_sec, end_sec)` items."""
    total_cuts = len(segments)
    if total_cuts == 0:
        return NumericDensityReport(
            total_cuts=0,
            cuts_with_numbers=0,
            total_numbers=0,
            multi_number_cuts=0,
            max_numeric_streak=0,
            numeric_cut_ratio=0.0,
            multi_number_ratio=0.0,
        )

    cuts_with_numbers = 0
    total_numbers = 0
    multi_number_cuts = 0
    max_streak = 0
    cur_streak = 0
    first_number_sec: Optional[float] = None
    max_end_sec: Optional[float] = None

    for text, start_sec, end_sec in segments:
        if end_sec is not None:
            max_end_sec = end_sec if max_end_sec is None else max(max_end_sec, end_sec)
        elif start_sec is not None:
            max_end_sec = start_sec if max_end_sec is None else max(max_end_sec, start_sec)

        nums = extract_numbers(text)
        if nums:
            cuts_with_numbers += 1
            total_numbers += len(nums)
            if len(nums) >= 2:
                multi_number_cuts += 1
            cur_streak += 1
            max_streak = max(max_streak, cur_streak)
            if first_number_sec is None and start_sec is not None:
                first_number_sec = start_sec
        else:
            cur_streak = 0

    npm: Optional[float] = None
    if max_end_sec is not None and max_end_sec > 0:
        npm = round(total_numbers / (max_end_sec / 60.0), 2)

    return NumericDensityReport(
        total_cuts=total_cuts,
        cuts_with_numbers=cuts_with_numbers,
        total_numbers=total_numbers,
        multi_number_cuts=multi_number_cuts,
        max_numeric_streak=max_streak,
        numeric_cut_ratio=cuts_with_numbers / total_cuts,
        multi_number_ratio=multi_number_cuts / total_cuts,
        numbers_per_minute=npm,
        first_number_seconds=first_number_sec,
    )


def audit_script_numeric_density(
    dialogue_entries: Sequence[Dict[str, Any]],
) -> Tuple[NumericDensityReport, List[Dict[str, Optional[str]]]]:
    """Audit `script.json` entries and return `(report, violation_dicts)` for `pacing.py`."""
    segments = [
        (str(entry.get("text", "")), None, None) for entry in dialogue_entries
    ]
    report = analyze_numeric_density(segments)
    violations: List[Dict[str, Optional[str]]] = []

    if report.total_cuts == 0:
        return report, violations

    if report.numeric_cut_ratio > SEVERE_NUMERIC_CUT_RATIO:
        violations.append({
            "rule_name": "NUMERIC_OVERLOAD",
            "severity": "ERROR",
            "character": None,
            "message": (
                f"{report.numeric_cut_ratio * 100:.1f}% of cuts ({report.cuts_with_numbers}/{report.total_cuts}) "
                f"contain numbers ({report.total_numbers} total; target <= {MAX_HEALTHY_NUMERIC_CUT_RATIO * 100:.0f}%)."
            ),
            "remedy": (
                "Cut secondary line-item figures from spoken dialogue; keep 1 hero number per beat "
                "and translate supporting metrics into plain-language consequences or visual-only B-roll."
            ),
        })
    elif report.numeric_cut_ratio > MAX_HEALTHY_NUMERIC_CUT_RATIO:
        violations.append({
            "rule_name": "NUMERIC_OVERLOAD",
            "severity": "WARNING",
            "character": None,
            "message": (
                f"{report.numeric_cut_ratio * 100:.1f}% of cuts ({report.cuts_with_numbers}/{report.total_cuts}) "
                f"contain numbers (recommended <= {MAX_HEALTHY_NUMERIC_CUT_RATIO * 100:.0f}%)."
            ),
            "remedy": "Replace secondary figures with analogies or reaction beats to reduce viewer cognitive load.",
        })

    if report.max_numeric_streak > MAX_HEALTHY_NUMERIC_STREAK:
        violations.append({
            "rule_name": "NUMERIC_STREAK_FATIGUE",
            "severity": "WARNING",
            "character": None,
            "message": (
                f"Detected {report.max_numeric_streak} consecutive cuts with numbers "
                f"(recommended <= {MAX_HEALTHY_NUMERIC_STREAK})."
            ),
            "remedy": "Insert a non-numeric reaction, analogy, or story pivot cut every 3-4 data lines.",
        })

    if report.multi_number_ratio > MAX_HEALTHY_MULTI_NUMBER_RATIO:
        violations.append({
            "rule_name": "MULTI_NUMBER_BUBBLES",
            "severity": "INFO",
            "character": None,
            "message": (
                f"{report.multi_number_cuts} cuts ({report.multi_number_ratio * 100:.1f}%) pack 2+ numbers "
                "into a single subtitle bubble."
            ),
            "remedy": "Split dense multi-figure lines so each bubble anchors a single quantitative takeaway.",
        })

    return report, violations


def _hms_to_sec(h: str, m: str, s: str, ms: str) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_subtitle_file(path: Path) -> List[Tuple[str, Optional[float], Optional[float]]]:
    """Parse `.srt`, `.vtt`, or plain `.txt` transcript files into `(text, start, end)`."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return [(line.strip(), None, None) for line in raw.splitlines() if line.strip()]

    segments: List[Tuple[str, Optional[float], Optional[float]]] = []
    cur_start: Optional[float] = None
    cur_end: Optional[float] = None
    buf: List[str] = []

    def _flush() -> None:
        nonlocal cur_start, cur_end, buf
        if buf:
            text = re.sub(r"<[^>]+>", "", " ".join(buf)).strip()
            if text and not text.startswith("WEBVTT"):
                segments.append((text, cur_start, cur_end))
        cur_start = None
        cur_end = None
        buf = []

    for line in raw.splitlines():
        s = line.strip()
        if not s:
            _flush()
            continue
        m_srt = _SRT_TIME_RE.match(s)
        m_vtt = _VTT_TIME_RE.match(s) if not m_srt else None
        if m_srt:
            _flush()
            cur_start = _hms_to_sec(*m_srt.groups()[:4])
            cur_end = _hms_to_sec(*m_srt.groups()[4:])
        elif m_vtt:
            _flush()
            cur_start = _hms_to_sec(*m_vtt.groups()[:4])
            cur_end = _hms_to_sec(*m_vtt.groups()[4:])
        elif s.isdigit() and cur_start is None:
            continue
        else:
            if not segments or s != segments[-1][0]:
                buf.append(s)
    _flush()
    return segments


def _extract_video_id(target: str) -> Optional[str]:
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", target.strip()):
        return target.strip()
    m = _YT_ID_RE.search(target)
    return m.group(1) if m else None


def _fetch_via_transcript_api(video_id: str) -> Optional[List[Tuple[str, Optional[float], Optional[float]]]]:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
    except ImportError:
        return None
    transcript = YouTubeTranscriptApi().fetch(video_id, languages=["ja", "en"])
    return [
        (str(item.text), float(item.start), float(item.start) + float(item.duration))
        for item in transcript
    ]


def _fetch_via_yt_dlp(
    url: str,
) -> Tuple[List[Tuple[str, Optional[float], Optional[float]]], Dict[str, Any]]:
    yt_dlp_bin = shutil.which("yt-dlp")
    if not yt_dlp_bin:
        raise RuntimeError(
            "Neither `youtube-transcript-api` nor `yt-dlp` is installed. "
            "Install one (`pip install youtube-transcript-api` or `yt-dlp`) or pass a local .srt/.vtt/.txt file."
        )
    with tempfile.TemporaryDirectory() as tmp:
        out_tpl = str(Path(tmp) / "%(id)s.%(ext)s")
        cmd = [
            yt_dlp_bin,
            "--skip-download",
            "--write-sub",
            "--write-auto-sub",
            "--sub-langs",
            "ja,en",
            "--sub-format",
            "srt/vtt",
            "--write-info-json",
            "-o",
            out_tpl,
            url,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"yt-dlp failed: {res.stderr.strip()[:300]}")
        info: Dict[str, Any] = {}
        info_files = list(Path(tmp).glob("*.info.json"))
        if info_files:
            info = json.loads(info_files[0].read_text(encoding="utf-8", errors="replace"))
        sub_files = list(Path(tmp).glob("*.srt")) + list(Path(tmp).glob("*.vtt"))
        if not sub_files:
            raise RuntimeError("yt-dlp succeeded but no Japanese/English subtitles were available.")
        return parse_subtitle_file(sub_files[0]), info


def benchmark_rival_source(target: str) -> RivalBenchmarkReport:
    """Benchmark a local `.srt`/`.vtt`/`.txt` file or YouTube URL/ID."""
    path = Path(target)
    info: Dict[str, Any] = {}
    if path.exists():
        segments = parse_subtitle_file(path)
        title = path.stem
    else:
        vid = _extract_video_id(target)
        segments_opt = _fetch_via_transcript_api(vid) if vid else None
        if segments_opt is not None:
            segments = segments_opt
            title = vid or target
        else:
            segments, info = _fetch_via_yt_dlp(target)
            title = str(info.get("title") or vid or target)

    density = analyze_numeric_density(segments)
    total_chars = sum(len(_clean_text(t)) for t, _, _ in segments)
    duration = info.get("duration")
    if duration is None and segments:
        ends = [e for _, _, e in segments if e is not None]
        if ends:
            duration = max(ends)

    hook_parts = [
        _clean_text(t)
        for t, s, _ in segments
        if s is None or s <= 30.0
    ]
    hook_preview = " ".join(hook_parts[:6])[:180]

    return RivalBenchmarkReport(
        source_label=target,
        title=title,
        channel=info.get("channel") or info.get("uploader"),
        duration_seconds=float(duration) if duration is not None else None,
        view_count=int(info["view_count"]) if info.get("view_count") is not None else None,
        total_segments=len(segments),
        total_chars=total_chars,
        density=density,
        hook_preview=hook_preview,
    )


def format_benchmark_comparison_markdown(
    project_name: Optional[str],
    project_density: Optional[NumericDensityReport],
    rivals: Sequence[RivalBenchmarkReport],
) -> str:
    """Render a Markdown comparison table between a local project and rival videos."""
    lines = ["### Rival Numeric-Density & Hook Benchmark", ""]
    lines.append(
        "| Source | Segments | Cuts w/ Numbers | Total Numbers | Max Streak | Nums/Min | 1st Number (s) |"
    )
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")

    if project_name and project_density:
        d = project_density
        lines.append(
            f"| **{project_name} (Ours)** | {d.total_cuts} | "
            f"{d.numeric_cut_ratio * 100:.1f}% ({d.cuts_with_numbers}) | {d.total_numbers} | "
            f"{d.max_numeric_streak} | {d.numbers_per_minute if d.numbers_per_minute is not None else '-'} | - |"
        )

    for r in rivals:
        d = r.density
        npm = f"{d.numbers_per_minute:.1f}" if d.numbers_per_minute is not None else "-"
        first_s = f"{d.first_number_seconds:.1f}s" if d.first_number_seconds is not None else "-"
        label = r.title[:36] + ("..." if len(r.title) > 36 else "")
        lines.append(
            f"| {label} | {r.total_segments} | "
            f"{d.numeric_cut_ratio * 100:.1f}% ({d.cuts_with_numbers}) | {d.total_numbers} | "
            f"{d.max_numeric_streak} | {npm} | {first_s} |"
        )

    if rivals:
        lines.extend(["", "#### Rival Hook Previews (First 30s):"])
        for r in rivals:
            lines.append(f"- **{r.title}**: {r.hook_preview}")

    return "\n".join(lines)
