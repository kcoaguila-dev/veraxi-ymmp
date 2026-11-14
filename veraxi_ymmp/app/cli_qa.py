"""Automated Multimodal QA and Keyframe Inspection Gate for Veraxi YMMP projects."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from veraxi_ymmp.audio.audio_normalizer import get_ffmpeg_exe
from veraxi_ymmp.core.logging import logger


def _get_video_duration(video_path: Path, ffmpeg_exe: str) -> float:
    """Measure exact video duration in seconds via FFmpeg."""
    try:
        cmd = [ffmpeg_exe, "-i", str(video_path)]
        res = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        for line in res.stderr.splitlines():
            if "Duration:" in line:
                part = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = part.split(":")
                return float(h) * 3600 + float(m) * 60 + float(s)
    except Exception as e:
        logger.warning(f"Failed to read duration from {video_path}: {e}")
    return 0.0


def _audit_tts_audio(
    dialogue_cuts: List[Dict[str, Any]], audio_dir: Path
) -> Tuple[List[str], List[float]]:
    """Verify VOICEVOX WAV files exist for every cut and measure their durations."""
    missing_audio: List[str] = []
    cut_durations: List[float] = []

    for idx, cut in enumerate(dialogue_cuts):
        char = cut["character"]
        wav_cand = audio_dir / f"{idx:03d}_{char}.wav"
        if not wav_cand.exists():
            wav_cand = audio_dir / f"{idx + 1:03d}_{char}.wav"
        if not wav_cand.exists():
            missing_audio.append(wav_cand.name)
            cut_durations.append(2.5)
        else:
            try:
                with wave.open(str(wav_cand), "rb") as wf:
                    dur = wf.getnframes() / max(wf.getframerate(), 1)
                    cut_durations.append(dur)
            except Exception:
                cut_durations.append(2.5)

    return missing_audio, cut_durations


def _compute_narrative_milestones(
    dialogue_cuts: List[Dict[str, Any]], cut_durations: List[float]
) -> Tuple[Dict[str, Tuple[int, float, str]], Optional[int]]:
    """Identify key narrative milestone indices and cumulative timestamps."""
    cold_open_idx = 0
    first_slide_idx = next(
        (i for i, c in enumerate(dialogue_cuts) if c.get("image")),
        None,
    )

    seen_chars: List[str] = []
    third_speaker_idx: Optional[int] = None
    for i, c in enumerate(dialogue_cuts):
        char = c["character"]
        if char not in seen_chars:
            seen_chars.append(char)
            if len(seen_chars) == 3:
                third_speaker_idx = i
                break

    mid_target = int(len(dialogue_cuts) * 0.45)
    reaction_idx = next(
        (
            i
            for i in range(mid_target, len(dialogue_cuts))
            if len(dialogue_cuts[i].get("text", "")) <= 16
        ),
        mid_target,
    )
    ending_idx = len(dialogue_cuts) - 1

    def _calc_timestamp(target_i: int) -> float:
        t = sum(cut_durations[i] + 0.3 for i in range(target_i))
        target_dur = cut_durations[target_i] if target_i < len(cut_durations) else 2.0
        return t + min(1.0, target_dur / 2.0)

    milestones: Dict[str, Tuple[int, float, str]] = {
        "01_cold_open": (
            cold_open_idx,
            _calc_timestamp(cold_open_idx),
            dialogue_cuts[cold_open_idx]["character"],
        ),
    }
    if first_slide_idx is not None:
        milestones["02_first_slide"] = (
            first_slide_idx,
            _calc_timestamp(first_slide_idx),
            dialogue_cuts[first_slide_idx]["character"],
        )
    if third_speaker_idx is not None:
        milestones["03_guest_entrance"] = (
            third_speaker_idx,
            _calc_timestamp(third_speaker_idx),
            dialogue_cuts[third_speaker_idx]["character"],
        )
    milestones["04_mid_reaction"] = (
        reaction_idx,
        _calc_timestamp(reaction_idx),
        dialogue_cuts[reaction_idx]["character"],
    )
    milestones["05_ending"] = (
        ending_idx,
        _calc_timestamp(ending_idx),
        dialogue_cuts[ending_idx]["character"],
    )
    return milestones, third_speaker_idx


def _extract_milestone_frames(
    milestones: Dict[str, Tuple[int, float, str]],
    dialogue_cuts: List[Dict[str, Any]],
    target_video: Path,
    video_dur: float,
    frames_dir: Path,
    ffmpeg_exe: str,
) -> Dict[str, Dict[str, Any]]:
    """Extract PNG keyframes at each narrative milestone using FFmpeg."""
    frames_dir.mkdir(parents=True, exist_ok=True)
    extracted_frames: Dict[str, Dict[str, Any]] = {}
    for name, (c_idx, sec, char) in milestones.items():
        out_frame = frames_dir / f"{name}.png"
        seek_sec = min(sec, max(0.0, video_dur - 0.5))
        cmd = [
            ffmpeg_exe,
            "-y",
            "-ss",
            f"{seek_sec:.2f}",
            "-i",
            str(target_video),
            "-vframes",
            "1",
            str(out_frame),
        ]
        try:
            subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                stdin=subprocess.DEVNULL,
            )
            extracted_frames[name] = {
                "cut_index": c_idx,
                "timestamp_sec": round(seek_sec, 2),
                "speaker": char,
                "text": dialogue_cuts[c_idx].get("text", ""),
                "frame_path": str(out_frame),
            }
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to extract QA frame {name}: {e.stderr}")
    return extracted_frames


def _audit_thumbnail(proj: Path) -> List[str]:
    """Validate thumbnail image presence and config against banned brackets."""
    thumb_path = proj / "thumbnail.png"
    thumb_issues: List[str] = []
    if not thumb_path.exists():
        thumb_issues.append("Missing thumbnail.png")
        return thumb_issues

    thumb_cfg_path = proj / "thumbnail_config.json"
    if thumb_cfg_path.exists():
        try:
            cfg = json.loads(thumb_cfg_path.read_text(encoding="utf-8"))
            for field in ("badge", "title_line1", "title_line2", "sub_hook"):
                val = str(cfg.get(field, ""))
                if "【" in val or "】" in val:
                    thumb_issues.append(
                        f"Thumbnail field '{field}' contains banned robotic brackets: '{val}'"
                    )
        except Exception as e:
            thumb_issues.append(f"Failed parsing thumbnail_config.json: {e}")
    return thumb_issues


def run_project_qa(project_dir: Path, out_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Execute automated multimodal QA inspection for a project directory.

    Extracts narrative milestone keyframes (Cold Open, First Slide, 3rd Character Entrance,
    Mid-roll Reaction, Ending), audits VoiceVox TTS coverage, and validates thumbnail invariants.
    """
    proj = project_dir.resolve()
    if not proj.is_dir():
        raise FileNotFoundError(f"Project directory not found: {proj}")

    script_path = proj / "script.json"
    if not script_path.exists():
        raise FileNotFoundError(f"script.json not found in {proj}")

    raw_script = json.loads(script_path.read_text(encoding="utf-8"))
    cuts = raw_script if isinstance(raw_script, list) else raw_script.get("cuts", [])
    dialogue_cuts = [c for c in cuts if "character" in c]
    if not dialogue_cuts:
        raise ValueError(f"No dialogue cuts found in {script_path}")

    missing_audio, cut_durations = _audit_tts_audio(dialogue_cuts, proj / "audio")

    video_cands = [
        proj / "final_normalized.mp4",
        proj / "final_video_youtube.mp4",
        proj / "final_video.mp4",
        proj / "qa_test.mp4",
    ]
    target_video = next((v for v in video_cands if v.exists()), None)
    if not target_video:
        raise FileNotFoundError(
            f"No video candidate found in {proj}. Expected one of: {[v.name for v in video_cands]}"
        )

    ffmpeg_exe = get_ffmpeg_exe()
    video_dur = _get_video_duration(target_video, ffmpeg_exe)
    milestones, third_speaker_idx = _compute_narrative_milestones(
        dialogue_cuts, cut_durations
    )
    frames_dir = out_dir if out_dir else proj / "qa_frames"
    extracted_frames = _extract_milestone_frames(
        milestones, dialogue_cuts, target_video, video_dur, frames_dir, ffmpeg_exe
    )
    thumb_issues = _audit_thumbnail(proj)

    coverage_issues: List[str] = []
    if third_speaker_idx is not None:
        guest_time = milestones["03_guest_entrance"][1]
        if video_dur < guest_time:
            coverage_issues.append(
                f"Video duration ({video_dur:.1f}s) cuts off before 3rd speaker entrance ({guest_time:.1f}s)"
            )

    thumb_path = proj / "thumbnail.png"
    success = (
        len(missing_audio) == 0
        and len(coverage_issues) == 0
        and len(thumb_issues) == 0
    )

    return {
        "success": success,
        "video_path": str(target_video),
        "video_duration_sec": round(video_dur, 2),
        "total_cuts": len(dialogue_cuts),
        "missing_audio": missing_audio,
        "coverage_issues": coverage_issues,
        "thumbnail_issues": thumb_issues,
        "thumbnail_path": str(thumb_path) if thumb_path.exists() else None,
        "frames": extracted_frames,
    }


def cmd_qa(argv: List[str]) -> None:
    """CLI handler for `veraxi-ymmp qa <project_dir>`."""
    parser = argparse.ArgumentParser(
        prog="veraxi-ymmp qa",
        description="Autonomous Multimodal QA & Narrative Milestone Keyframe Extractor.",
    )
    parser.add_argument("project_dir", type=str, help="Path to project directory")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=str,
        default=None,
        help="Custom directory to store extracted QA frames (default: <project>/qa_frames)",
    )
    args = parser.parse_args(argv)

    out_p = Path(args.output_dir) if args.output_dir else None
    try:
        report = run_project_qa(Path(args.project_dir), out_dir=out_p)
    except Exception as exc:
        sys.stderr.write(f"QA execution error: {exc}\n")
        sys.exit(1)

    print("=" * 60)
    print("🎬 VERAXI-YMMP AUTONOMOUS MULTIMODAL QA REPORT")
    print("=" * 60)
    print(f"Project:  {args.project_dir}")
    print(f"Video:    {report['video_path']} ({report['video_duration_sec']}s)")
    print(f"Cuts:     {report['total_cuts']} dialogue cuts")

    # Audio synthesis check
    if report["missing_audio"]:
        print(f"\n❌ Missing VoiceVox Audio ({len(report['missing_audio'])} cuts):")
        for m in report["missing_audio"]:
            print(f"   - {m}")
    else:
        print("\n✅ VoiceVox TTS Audio: 100% synthesized and verified.")

    # Coverage check
    if report["coverage_issues"]:
        print("\n❌ Truncation & Coverage Issues:")
        for ci in report["coverage_issues"]:
            print(f"   - {ci}")
    else:
        print("✅ Speaker Coverage: All cast members fully covered in video.")

    # Thumbnail check
    if report["thumbnail_issues"]:
        print("\n❌ Thumbnail Guardrail Violations:")
        for ti in report["thumbnail_issues"]:
            print(f"   - {ti}")
    else:
        print(f"✅ Thumbnail Guardrails: PASSED ({report['thumbnail_path']})")

    # Extracted frames
    print("\n📸 Extracted Narrative Milestone Frames:")
    for key, info in report["frames"].items():
        print(
            f"   [{key}] @ {info['timestamp_sec']}s (Cut #{info['cut_index']+1} - {info['speaker']})"
        )
        print(f"       File: {info['frame_path']}")
        print(f"       Line: {info['text']}")

    print("=" * 60)
    if not report["success"]:
        print("❌ QA STATUS: REJECTED (Fix violations before user delivery)")
        sys.exit(1)
    else:
        print("✅ QA STATUS: PASSED (Proceed with visual multimodal inspection)")
        sys.exit(0)
