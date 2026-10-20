"""
Post-publish Audience Retention QA Feedback Loop & Correlation Engine.

Correlates YouTube Analytics retention curves (elapsedVideoTimeRatio, audienceWatchRatio)
with TimelineIR dialogue cuts, speaker attributions, and B-roll visual slides.
Detects cliff drop-offs (>5%) and cumulative cut-level losses, computes retention scores,
and exports actionable JSON and Markdown editorial scorecards.
"""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .ir import (
    CutRetentionMetric,
    DynamicImageClip,
    RetentionDropoffPoint,
    TimelineIR,
    VideoRetentionReport,
    VoiceClip,
)
from .logging import logger


class RetentionCorrelationEngine:
    """
    Application service that correlates YouTube Analytics audience retention curves
    with TimelineIR dialogue cuts and presentation visuals.
    """

    @staticmethod
    def _interpolate_watch_ratio(curve: List[Tuple[float, float]], ratio: float) -> float:
        """
        Interpolates the audience watch ratio at a specific elapsed video time ratio.
        """
        if not curve:
            return 0.0
        if ratio <= curve[0][0]:
            return curve[0][1]
        if ratio >= curve[-1][0]:
            return curve[-1][1]

        for i in range(len(curve) - 1):
            r_a, v_a = curve[i]
            r_b, v_b = curve[i + 1]
            if r_a <= ratio <= r_b:
                if math.isclose(r_a, r_b, abs_tol=1e-9):
                    return v_a
                t = (ratio - r_a) / (r_b - r_a)
                return v_a + t * (v_b - v_a)

        return curve[-1][1]

    @staticmethod
    def _find_voice_clip_at_frame(
        voice_clips: List[VoiceClip], frame: int
    ) -> Tuple[int, Optional[VoiceClip]]:
        """
        Finds the VoiceClip active at the given timeline frame.
        Falls back to the nearest preceding clip if the frame falls in an audio pad or trailing gap.
        """
        if not voice_clips:
            return -1, None

        # Direct containment check
        for idx, clip in enumerate(voice_clips):
            if clip.start_frame <= frame < clip.start_frame + clip.length:
                return idx, clip

        # If frame is after all clips or in a gap, find closest preceding clip
        closest_idx = -1
        closest_clip: Optional[VoiceClip] = None
        for idx, clip in enumerate(voice_clips):
            if clip.start_frame <= frame:
                closest_idx = idx
                closest_clip = clip

        if closest_clip is not None:
            return closest_idx, closest_clip

        # If frame is before the first clip, attribute to the first clip
        return 0, voice_clips[0]

    @staticmethod
    def _find_active_broll_at_frame(
        image_clips: List[DynamicImageClip], frame: int
    ) -> Optional[str]:
        """
        Finds the active non-background B-roll slide at the given timeline frame.
        Returns the filename or path string, or None if no slide is active.
        """
        if not image_clips:
            return None

        for clip in reversed(image_clips):
            if getattr(clip, "is_background", False):
                continue
            if clip.start_frame <= frame < clip.start_frame + clip.length:
                image_path = getattr(clip, "image_path", None)
                if image_path is not None:
                    if hasattr(image_path, "name"):
                        return str(image_path.name)
                    return str(image_path)
        return None

    def _compute_cut_metrics(
        self,
        timeline_ir: TimelineIR,
        curve: List[Tuple[float, float]],
        fps: int,
        total_frames: int,
        total_duration_sec: float,
    ) -> List[CutRetentionMetric]:
        """
        Computes retention telemetry aggregated per dialogue cut.
        """
        metrics: List[CutRetentionMetric] = []
        for idx, vc in enumerate(timeline_ir.voice_clips):
            start_frame = vc.start_frame
            end_frame = vc.start_frame + vc.length
            start_sec = round(start_frame / fps, 2)
            end_sec = round(end_frame / fps, 2)

            r_start = start_frame / total_frames if total_frames > 0 else 0.0
            r_end = end_frame / total_frames if total_frames > 0 else 0.0

            start_ret = self._interpolate_watch_ratio(curve, r_start)
            end_ret = self._interpolate_watch_ratio(curve, r_end)
            ret_change = round(end_ret - start_ret, 4)

            mid_frame = start_frame + (vc.length // 2)
            broll = self._find_active_broll_at_frame(
                timeline_ir.dynamic_image_clips, mid_frame
            )

            metrics.append(
                CutRetentionMetric(
                    cut_index=idx,
                    speaker=vc.character,
                    text=vc.text,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    start_retention=round(start_ret, 4),
                    end_retention=round(end_ret, 4),
                    retention_change=ret_change,
                    broll_image=broll,
                )
            )
        return metrics

    def correlate(
        self,
        timeline_ir: TimelineIR,
        retention_curve: List[Tuple[float, float]],
        video_id: str = "",
        video_title: str = "",
        threshold: float = 0.05,
    ) -> VideoRetentionReport:
        """
        Correlates audience retention data with TimelineIR dialogue cuts and B-roll visuals.
        """
        logger.info(
            f"Starting retention correlation for video '{video_id or video_title}' "
            f"with {len(retention_curve)} curve points and {len(timeline_ir.voice_clips)} cuts."
        )

        fps = max(1, timeline_ir.fps)
        total_frames = max(0, timeline_ir.total_frames)
        total_duration_sec = round(total_frames / fps, 2) if fps > 0 else 0.0
        total_cuts = len(timeline_ir.voice_clips)

        # Handle empty curve edge case
        if not retention_curve:
            logger.warning("Retention curve is empty. Returning nominal zero report.")
            cut_metrics = self._compute_cut_metrics(
                timeline_ir, [], fps, total_frames, total_duration_sec
            )
            return VideoRetentionReport(
                video_id=video_id,
                video_title=video_title,
                total_duration_sec=total_duration_sec,
                total_cuts=total_cuts,
                retention_score=0.0,
                average_view_percentage=0.0,
                dropoff_threshold=threshold,
                dropoff_points=[],
                cut_metrics=cut_metrics,
                summary_verdict="NOMINAL",
                editorial_recommendations=["離脱データが存在しないか、集計期間外です。"],
            )

        # Sort curve by elapsed_ratio ascending
        sorted_curve = sorted(retention_curve, key=lambda p: p[0])

        # Compute average view percentage
        avg_watch_ratio = sum(pt[1] for pt in sorted_curve) / len(sorted_curve)
        average_view_percentage = round(avg_watch_ratio * 100.0, 2)

        # Cut-level metrics
        cut_metrics = self._compute_cut_metrics(
            timeline_ir, sorted_curve, fps, total_frames, total_duration_sec
        )

        # Point-to-point cliff drop detection
        candidate_drops: List[Dict[str, Any]] = []
        for i in range(1, len(sorted_curve)):
            r_prev, w_prev = sorted_curve[i - 1]
            r_curr, w_curr = sorted_curve[i]

            # Exclude terminal point at/after 1.0 (end of video outro clickaway)
            if r_curr >= 1.0 - 1e-9:
                continue

            drop_mag = round(w_prev - w_curr, 6)
            delta_r = max(1e-9, r_curr - r_prev)
            slope = drop_mag / delta_r

            if drop_mag > threshold:
                timestamp_sec = round(r_curr * total_duration_sec, 2)
                frame = round(r_curr * total_frames)
                cut_idx, voice_clip = self._find_voice_clip_at_frame(
                    timeline_ir.voice_clips, frame
                )
                broll = self._find_active_broll_at_frame(
                    timeline_ir.dynamic_image_clips, frame
                )

                candidate_drops.append({
                    "timestamp_sec": timestamp_sec,
                    "elapsed_ratio": round(r_curr, 4),
                    "retention_before": round(w_prev, 4),
                    "retention_after": round(w_curr, 4),
                    "drop_magnitude": round(drop_mag, 4),
                    "slope": slope,
                    "cut_index": cut_idx,
                    "speaker": voice_clip.character if voice_clip else "Unknown",
                    "subtitle_text": voice_clip.text if voice_clip else "",
                    "emotion": voice_clip.emotion if voice_clip else "normal",
                    "broll_image": broll,
                })

        # Deduplicate drops per cut_index (select steepest slope / most severe cliff)
        final_dropoff_points: List[RetentionDropoffPoint] = []
        if total_cuts > 0:
            drops_by_cut: Dict[int, List[Dict[str, Any]]] = {}
            for d in candidate_drops:
                drops_by_cut.setdefault(d["cut_index"], []).append(d)

            for cut_idx in sorted(drops_by_cut.keys()):
                group = drops_by_cut[cut_idx]
                best = max(group, key=lambda x: (x["slope"], x["drop_magnitude"]))
                final_dropoff_points.append(
                    RetentionDropoffPoint(
                        timestamp_sec=best["timestamp_sec"],
                        elapsed_ratio=best["elapsed_ratio"],
                        retention_before=best["retention_before"],
                        retention_after=best["retention_after"],
                        drop_magnitude=best["drop_magnitude"],
                        cut_index=best["cut_index"],
                        speaker=best["speaker"],
                        subtitle_text=best["subtitle_text"],
                        emotion=best["emotion"],
                        broll_image=best["broll_image"],
                        issue_type="PACING_OR_FATIGUE",
                        recommendation="",
                    )
                )
        else:
            for best in candidate_drops:
                final_dropoff_points.append(
                    RetentionDropoffPoint(
                        timestamp_sec=best["timestamp_sec"],
                        elapsed_ratio=best["elapsed_ratio"],
                        retention_before=best["retention_before"],
                        retention_after=best["retention_after"],
                        drop_magnitude=best["drop_magnitude"],
                        cut_index=best["cut_index"],
                        speaker=best["speaker"],
                        subtitle_text=best["subtitle_text"],
                        emotion=best["emotion"],
                        broll_image=best["broll_image"],
                        issue_type="PACING_OR_FATIGUE",
                        recommendation="",
                    )
                )

        final_dropoff_points.sort(key=lambda d: d.timestamp_sec)

        # Calculate overall retention score [0, 100]
        # Formula: clamp(100 * avg_ratio - 10 * num_dropoffs, 0, 100)
        raw_score = (avg_watch_ratio * 100.0) - (10.0 * len(final_dropoff_points))
        retention_score = max(0.0, min(100.0, round(raw_score, 2)))

        # Assign summary verdict
        num_drops = len(final_dropoff_points)
        has_severe_drop = any(d.drop_magnitude >= 0.10 for d in final_dropoff_points)
        if num_drops == 0:
            summary_verdict = "EXCELLENT" if average_view_percentage >= 70.0 else "NOMINAL"
        elif num_drops >= 3 or has_severe_drop:
            summary_verdict = "NEEDS_OPTIMIZATION"
        else:
            summary_verdict = "ATTENTION_REQUIRED"

        # Formulate editorial recommendations
        editorial_recommendations: List[str] = []
        for drop in final_dropoff_points:
            if len(drop.subtitle_text) > 40:
                drop.issue_type = "COGNITIVE_OVERLOAD_LONG_TEXT"
                rec = (
                    f"カット #{drop.cut_index} ({drop.speaker}): セリフ文字数({len(drop.subtitle_text)}文字)が"
                    "上限40文字を超過しています。2つ以上の短いカットに分割してください。"
                )
                drop.recommendation = rec
                editorial_recommendations.append(rec)
            elif drop.drop_magnitude >= 0.10:
                drop.issue_type = "PACING_OR_FATIGUE"
                rec = (
                    f"カット #{drop.cut_index} ({drop.speaker}): {drop.drop_magnitude * 100:.1f}%の急激な離脱が"
                    "発生しています。セリフのテンポ改善またはフックの再設計を推奨します。"
                )
                drop.recommendation = rec
                editorial_recommendations.append(rec)
            elif not drop.broll_image:
                drop.issue_type = "STATIC_VISUAL_FATIGUE"
                rec = (
                    f"カット #{drop.cut_index} ({drop.speaker}): 映像変化のない立ち絵静止状態です。"
                    "Bロール画像またはスライドの挿入を推奨します。"
                )
                drop.recommendation = rec
                editorial_recommendations.append(rec)
            else:
                drop.issue_type = "PACING_OR_FATIGUE"
                rec = (
                    f"カット #{drop.cut_index} ({drop.speaker}): {drop.drop_magnitude * 100:.1f}%の視聴者離脱が"
                    "発生しています。視聴維持を促す演出を追加してください。"
                )
                drop.recommendation = rec
                editorial_recommendations.append(rec)

        # Check for cuts with high cumulative loss
        for cm in cut_metrics:
            if cm.retention_change <= -0.05:
                rec = (
                    f"カット #{cm.cut_index} ({cm.speaker}): カット全体で{abs(cm.retention_change) * 100:.1f}%の"
                    "累積離脱が発生しています。"
                )
                if not any(f"カット #{cm.cut_index}" in r for r in editorial_recommendations):
                    editorial_recommendations.append(rec)

        if not editorial_recommendations:
            editorial_recommendations.append(
                "顕著な離脱ポイントは検出されませんでした。良好な視聴維持率を維持しています。"
            )

        editorial_recommendations = list(dict.fromkeys(editorial_recommendations))

        report = VideoRetentionReport(
            video_id=video_id,
            video_title=video_title,
            total_duration_sec=total_duration_sec,
            total_cuts=total_cuts,
            retention_score=retention_score,
            average_view_percentage=average_view_percentage,
            dropoff_threshold=threshold,
            dropoff_points=final_dropoff_points,
            cut_metrics=cut_metrics,
            summary_verdict=summary_verdict,
            editorial_recommendations=editorial_recommendations,
        )

        logger.info(
            f"Retention correlation complete. Verdict: {summary_verdict}, "
            f"Score: {retention_score}, Drops: {len(final_dropoff_points)}"
        )
        return report

    def render_json(self, report: VideoRetentionReport, indent: int = 2) -> str:
        """
        Renders the VideoRetentionReport into a structured, machine-parseable JSON string.
        Safe against Path objects via default=str.
        """
        data = dataclasses.asdict(report)
        return json.dumps(data, indent=indent, ensure_ascii=False, default=str)

    def render_markdown(self, report: VideoRetentionReport) -> str:
        """
        Renders an editorial scorecard in Markdown format.
        """
        title = report.video_title or report.video_id or "Untitled"
        lines: List[str] = [
            f"# Retention QA Report: {title}",
            "",
            "## Executive Summary",
            f"- **Video ID**: `{report.video_id or 'N/A'}`",
            f"- **Duration**: `{report.total_duration_sec:.1f}s`",
            f"- **Total Cuts**: `{report.total_cuts}`",
            f"- **Drop-off Threshold**: `{report.dropoff_threshold * 100:.1f}%`",
            f"- **Average View Percentage**: `{report.average_view_percentage:.1f}%`",
            f"- **Retention Score**: `{report.retention_score:.1f} / 100`",
            f"- **Verdict**: **{report.summary_verdict}**",
            "",
            "## Retention Drop-Off Analysis",
        ]

        if report.dropoff_points:
            lines.extend([
                "| Timestamp | Ratio | Drop | Speaker | Text | Slide | Recommendation |",
                "|---|---|---|---|---|---|---|",
            ])
            for d in report.dropoff_points:
                clean_slide = (d.broll_image or "None").replace("\n", " ").replace("|", "\\|")
                clean_speaker = d.speaker.replace("\n", " ").replace("|", "\\|")
                clean_text = d.subtitle_text.replace("\n", " ").replace("|", "\\|")
                if len(clean_text) > 35:
                    clean_text = clean_text[:32] + "..."
                rec = d.recommendation.replace("\n", " ").replace("|", "\\|")
                lines.append(
                    f"| {d.timestamp_sec:.1f}s | {d.elapsed_ratio * 100:.1f}% | "
                    f"-{d.drop_magnitude * 100:.1f}% | {clean_speaker} | {clean_text} | "
                    f"`{clean_slide}` | {rec} |"
                )
        else:
            lines.append("*(No retention cliff drop-offs detected exceeding threshold)*")

        lines.extend([
            "",
            "## Cut-Level Progression",
        ])

        if report.cut_metrics:
            lines.extend([
                "| Cut # | Speaker | Interval | Start % | End % | Change | Slide | Text |",
                "|---|---|---|---|---|---|---|---|",
            ])
            for cm in report.cut_metrics:
                clean_slide = (cm.broll_image or "None").replace("\n", " ").replace("|", "\\|")
                clean_speaker = cm.speaker.replace("\n", " ").replace("|", "\\|")
                clean_text = cm.text.replace("\n", " ").replace("|", "\\|")
                if len(clean_text) > 30:
                    clean_text = clean_text[:27] + "..."
                lines.append(
                    f"| {cm.cut_index} | {clean_speaker} | {cm.start_sec:.1f}s - {cm.end_sec:.1f}s | "
                    f"{cm.start_retention * 100:.1f}% | {cm.end_retention * 100:.1f}% | "
                    f"{cm.retention_change * 100:+.1f}% | `{clean_slide}` | {clean_text} |"
                )
        else:
            lines.append("*(No dialogue cuts in timeline)*")

        lines.extend([
            "",
            "## Editorial Recommendations",
        ])
        for rec in report.editorial_recommendations:
            lines.append(f"- {rec}")

        lines.append("")
        return "\n".join(lines)

    def save_reports(
        self, report: VideoRetentionReport, output_dir: Path
    ) -> Tuple[Path, Path]:
        """
        Saves both JSON and Markdown reports to the target directory.
        Creates parent directories automatically if they do not exist.
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        safe_name = "".join(
            c if c.isalnum() or c in ("-", "_") else "_"
            for c in (report.video_id or "retention_qa")
        )
        json_file = out_path / f"{safe_name}_report.json"
        md_file = out_path / f"{safe_name}_report.md"

        json_content = self.render_json(report)
        md_content = self.render_markdown(report)

        json_file.write_text(json_content, encoding="utf-8")
        md_file.write_text(md_content, encoding="utf-8")

        logger.info(f"Saved retention QA reports to {json_file} and {md_file}")
        return json_file, md_file


__all__ = ["RetentionCorrelationEngine"]
