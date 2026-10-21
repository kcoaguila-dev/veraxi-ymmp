"""Application Service: YouTube Thumbnail A/B Experiment Coordinator.

Orchestrates multi-variant thumbnail rotation, state persistence, statistical
evaluation (two-proportion pooled Z-test), audience retention guardrails,
and winner commitment with QA audit reporting.

Strict Clean Architecture compliant: zero dependencies on outer adapters or Google API SDK.
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from veraxi_ymmp.ir import (
    RotationEvent,
    ThumbnailExperiment,
    ThumbnailVariant,
    WinnerDecision,
)
from veraxi_ymmp.ports import (
    VideoAnalyticsProvider,
    VideoPublisher,
)
from veraxi_ymmp.thumbnail import (
    auto_extract_variant_configs,
    generate_thumbnail_variants,
)

logger = logging.getLogger(__name__)


def _get_variant_ctr(v: ThumbnailVariant) -> float:
    """Helper to safely retrieve CTR or compute from views / impressions."""
    if v.metrics.ctr > 0.0:
        return v.metrics.ctr
    if v.metrics.impressions > 0:
        return v.metrics.views / v.metrics.impressions
    return 0.0


def save_experiment(
    experiment: ThumbnailExperiment,
    path: Optional[Path] = None,
) -> Path:
    """Atomically serialize ThumbnailExperiment to JSON."""
    target_path = Path(path) if path is not None else (experiment.project_dir / "thumbnail_ab_experiment.json")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    # Unique temp file per writer so concurrent saves never clobber each other's temp data.
    temp_path = target_path.with_name(f".tmp_{os.getpid()}_{uuid.uuid4().hex}_{target_path.name}")
    data = experiment.to_dict()
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # On Windows, replace() raises PermissionError while another handle has the target open;
    # retry briefly with backoff before giving up.
    for attempt in range(50):
        try:
            temp_path.replace(target_path)
            break
        except PermissionError:
            if attempt == 49:
                temp_path.unlink(missing_ok=True)
                raise
            time.sleep(0.01 * (attempt + 1))
    return target_path


def load_experiment(path_or_project_dir: Path) -> ThumbnailExperiment:
    """Load and reconstruct ThumbnailExperiment from file or project directory."""
    path_obj = Path(path_or_project_dir)
    if path_obj.is_dir():
        file_path = path_obj / "thumbnail_ab_experiment.json"
    else:
        file_path = path_obj

    if not file_path.exists():
        raise FileNotFoundError(f"Experiment state file not found: {file_path}")

    # Windows briefly denies access while a concurrent writer swaps the file in; retry.
    for attempt in range(50):
        try:
            content = file_path.read_text(encoding="utf-8")
            break
        except PermissionError:
            if attempt == 49:
                raise
            time.sleep(0.01 * (attempt + 1))
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid experiment JSON: expected object, got {type(data)}")
    if "variants" not in data:
        raise KeyError("Missing required 'variants' field in experiment JSON")

    return ThumbnailExperiment.from_dict(data)


def initialize_experiment(
    project_dir: Path,
    video_id: str,
    variants: Optional[List[ThumbnailVariant]] = None,
    publisher: Optional[VideoPublisher] = None,
    min_impressions: int = 500,
    min_observation_hours: float = 24.0,
) -> ThumbnailExperiment:
    """Initialize thumbnail A/B experiment, render variants if needed, and activate initial variant."""
    proj_dir = Path(project_dir)
    if not proj_dir.exists():
        raise FileNotFoundError(f"Project directory not found: {proj_dir}")

    # Preserve rotation history if re-initializing same experiment
    state_file = proj_dir / "thumbnail_ab_experiment.json"
    existing_history: List[RotationEvent] = []
    if state_file.exists():
        try:
            existing_exp = load_experiment(state_file)
            if existing_exp.video_id == video_id:
                existing_history = existing_exp.rotation_history
        except Exception:
            existing_history = []

    variants_dict: Dict[str, ThumbnailVariant] = {}
    if variants is not None and len(variants) > 0:
        for v in variants:
            variants_dict[v.variant_id] = v
    else:
        out_dir = proj_dir / "thumbnails"
        out_dir.mkdir(parents=True, exist_ok=True)
        rendered_paths = generate_thumbnail_variants(proj_dir, out_dir)
        configs = auto_extract_variant_configs(proj_dir)
        for vid, v_path in rendered_paths.items():
            cfg = configs.get(vid)
            cfg_dict: Dict[str, Any] = {}
            if cfg is not None:
                if hasattr(cfg, "to_dict"):
                    cfg_dict = cfg.to_dict()
                elif hasattr(cfg, "__dict__"):
                    cfg_dict = dict(cfg.__dict__)
            v_name = f"Variant {vid}"
            if cfg is not None and getattr(cfg, "badge", None):
                v_name = f"Variant {vid} ({cfg.badge})"
            variants_dict[vid] = ThumbnailVariant(
                variant_id=vid,
                name=v_name,
                thumbnail_path=v_path,
                config=cfg_dict,
                is_active=False,
                rotation_count=0,
            )

    if not variants_dict:
        raise ValueError("Cannot initialize experiment without variants.")

    # Set default active variant (prefer 'A', else first variant)
    active_vid = "A" if "A" in variants_dict else next(iter(variants_dict.keys()))
    for vid, v in variants_dict.items():
        v.is_active = (vid == active_vid)

    active_variant = variants_dict[active_vid]

    # Upload initial active thumbnail if publisher provided
    if publisher is not None and active_variant.thumbnail_path.exists():
        publisher.upload_thumbnail(video_id, active_variant.thumbnail_path)

    now_iso = datetime.now(timezone.utc).isoformat()
    init_event = RotationEvent(
        timestamp=now_iso,
        video_id=video_id,
        from_variant_id=None,
        to_variant_id=active_vid,
        reason="initial_activation",
    )

    history = existing_history + [init_event]

    experiment = ThumbnailExperiment(
        experiment_id=f"exp_{video_id}",
        video_id=video_id,
        project_dir=proj_dir,
        status="RUNNING",
        active_variant_id=active_vid,
        variants=variants_dict,
        rotation_history=history,
        min_impressions=min_impressions,
        min_observation_hours=min_observation_hours,
        created_at=now_iso,
        updated_at=now_iso,
    )
    save_experiment(experiment)
    return experiment


def rotate_thumbnail(
    project_dir: Path,
    video_id: str,
    target_variant_id: Optional[str] = None,
    publisher: Optional[VideoPublisher] = None,
    reason: str = "scheduled_rotation",
) -> RotationEvent:
    """Rotate active thumbnail to target variant or next variant in round-robin sequence."""
    experiment = load_experiment(project_dir)

    if experiment.status == "CONCLUDED":
        raise RuntimeError("Cannot rotate thumbnail on a CONCLUDED experiment.")
    if not experiment.variants:
        raise ValueError("No variants available for rotation.")

    if target_variant_id is None:
        keys = sorted(list(experiment.variants.keys()))
        if experiment.active_variant_id in keys:
            curr_idx = keys.index(experiment.active_variant_id)
            target_variant_id = keys[(curr_idx + 1) % len(keys)]
        else:
            target_variant_id = keys[0]

    if target_variant_id not in experiment.variants:
        raise KeyError(f"Target variant '{target_variant_id}' does not exist in experiment.")

    old_active_id = experiment.active_variant_id
    target_variant = experiment.variants[target_variant_id]

    if publisher is not None and target_variant.thumbnail_path.exists():
        publisher.upload_thumbnail(video_id, target_variant.thumbnail_path)

    for vid, v in experiment.variants.items():
        v.is_active = (vid == target_variant_id)

    target_variant.rotation_count += 1
    experiment.active_variant_id = target_variant_id
    experiment.status = "RUNNING"

    now_iso = datetime.now(timezone.utc).isoformat()
    event = RotationEvent(
        timestamp=now_iso,
        video_id=video_id,
        from_variant_id=old_active_id,
        to_variant_id=target_variant_id,
        reason=reason,
    )
    experiment.rotation_history.append(event)
    experiment.updated_at = now_iso

    save_experiment(experiment)
    return event


def evaluate_performance(
    project_dir: Path,
    video_id: str,
    analytics_provider: Optional[VideoAnalyticsProvider] = None,
    confidence_level: float = 0.95,
    min_impressions: Optional[int] = None,
) -> WinnerDecision:
    """Evaluate variant CTR performance via two-proportion Z-test with retention guardrails."""
    experiment = load_experiment(project_dir)
    eff_min_imp = min_impressions if min_impressions is not None else experiment.min_impressions

    # Fetch fresh metrics from analytics provider if supplied
    if analytics_provider is not None:
        for vid, variant in experiment.variants.items():
            m = analytics_provider.fetch_variant_metrics(vid)
            if m.impressions > 0 and (m.ctr == 0.0 or m.ctr is None):
                m.ctr = m.views / m.impressions
            variant.metrics = m

    # Validate minimum variants for comparative evaluation
    if len(experiment.variants) < 2:
        decision = WinnerDecision(
            winner_variant_id=next(iter(experiment.variants.keys())) if experiment.variants else None,
            winning_score=0.0,
            margin=0.0,
            is_significant=False,
            p_value=None,
            rationale="INCONCLUSIVE: Experiment requires at least two variants for comparative evaluation.",
        )
        experiment.winner_decision = decision
        experiment.updated_at = datetime.now(timezone.utc).isoformat()
        save_experiment(experiment)
        return decision

    # Sample size guardrail
    total_impressions = sum(v.metrics.impressions for v in experiment.variants.values())
    if total_impressions < eff_min_imp or any(
        v.metrics.impressions < (eff_min_imp // len(experiment.variants))
        for v in experiment.variants.values()
    ):
        decision = WinnerDecision(
            winner_variant_id=None,
            winning_score=0.0,
            margin=0.0,
            is_significant=False,
            p_value=None,
            rationale=f"INCONCLUSIVE_INSUFFICIENT_DATA: Impressions below threshold ({eff_min_imp}).",
        )
        experiment.winner_decision = decision
        experiment.updated_at = datetime.now(timezone.utc).isoformat()
        save_experiment(experiment)
        return decision

    # Sort variants by CTR descending
    sorted_vars = sorted(
        experiment.variants.values(),
        key=lambda v: _get_variant_ctr(v),
        reverse=True,
    )
    var1 = sorted_vars[0]
    var2 = sorted_vars[1]

    ctr1 = _get_variant_ctr(var1)
    ctr2 = _get_variant_ctr(var2)
    imp1 = var1.metrics.impressions
    imp2 = var2.metrics.impressions
    views1 = var1.metrics.views
    views2 = var2.metrics.views

    if ctr1 == ctr2:
        decision = WinnerDecision(
            winner_variant_id=None,
            winning_score=ctr1,
            margin=0.0,
            is_significant=False,
            p_value=1.0,
            rationale="INCONCLUSIVE: Identical CTR across variants.",
        )
        experiment.winner_decision = decision
        experiment.updated_at = datetime.now(timezone.utc).isoformat()
        save_experiment(experiment)
        return decision

    # Two-proportion pooled Z-test
    total_views = views1 + views2
    total_imp = imp1 + imp2
    p_pooled = total_views / total_imp if total_imp > 0 else 0.0

    if 0.0 < p_pooled < 1.0 and imp1 > 0 and imp2 > 0:
        se = math.sqrt(p_pooled * (1.0 - p_pooled) * ((1.0 / imp1) + (1.0 / imp2)))
    else:
        se = 0.0

    if se > 0.0:
        z_score = abs(ctr1 - ctr2) / se
        p_value = math.erfc(z_score / math.sqrt(2.0))
    else:
        z_score = 0.0
        p_value = 1.0

    alpha = 1.0 - confidence_level
    is_sig = (p_value < alpha) or (abs(z_score) >= 1.96 if confidence_level == 0.95 else False)
    margin = abs(ctr1 - ctr2)

    # Retention Guardrail: Veto clickbait with high CTR but severe audience drop-off
    cand_ret = var1.metrics.average_view_percentage
    alt_ret = var2.metrics.average_view_percentage
    retention_penalty = False
    if cand_ret < 40.0 or (alt_ret - cand_ret > 15.0):
        retention_penalty = True

    if retention_penalty:
        decision = WinnerDecision(
            winner_variant_id=var2.variant_id,
            winning_score=ctr2,
            margin=margin,
            is_significant=False,
            p_value=p_value,
            rationale=(
                f"Retention guardrail veto: Variant {var1.variant_id} had higher CTR ({ctr1:.2%}) "
                f"but failed audience retention check (retention={cand_ret:.1f}% vs {alt_ret:.1f}%). "
                f"Overriding winner to retentive variant {var2.variant_id}."
            ),
        )
    else:
        rationale = (
            f"Statistically significant CTR advantage (Z={z_score:.2f}, p={p_value:.4f}, margin={margin:.2%})"
            if is_sig
            else f"Inconclusive: Difference not statistically significant (Z={z_score:.2f}, p={p_value:.4f}, margin={margin:.2%})"
        )
        decision = WinnerDecision(
            winner_variant_id=var1.variant_id,
            winning_score=ctr1,
            margin=margin,
            is_significant=is_sig,
            p_value=p_value,
            rationale=rationale,
        )

    experiment.winner_decision = decision
    experiment.updated_at = datetime.now(timezone.utc).isoformat()
    save_experiment(experiment)
    return decision


def commit_winner(
    project_dir: Path,
    video_id: str,
    winner_id: Optional[str] = None,
    publisher: Optional[VideoPublisher] = None,
    analytics_provider: Optional[VideoAnalyticsProvider] = None,
) -> ThumbnailExperiment:
    """Lock in winning thumbnail permanently on YouTube and local project assets."""
    experiment = load_experiment(project_dir)

    if not experiment.variants:
        raise ValueError("Cannot commit winner: Experiment has no variants.")

    if winner_id is None:
        if experiment.winner_decision and experiment.winner_decision.winner_variant_id:
            winner_id = experiment.winner_decision.winner_variant_id
        else:
            decision = evaluate_performance(
                project_dir=project_dir,
                video_id=video_id,
                analytics_provider=analytics_provider,
            )
            winner_id = decision.winner_variant_id or next(iter(experiment.variants.keys()))

    if winner_id not in experiment.variants:
        raise KeyError(f"Winning variant '{winner_id}' does not exist in experiment variants.")

    winning_variant = experiment.variants[winner_id]

    # Final lock on YouTube via publisher
    if publisher is not None and winning_variant.thumbnail_path.exists():
        publisher.upload_thumbnail(video_id, winning_variant.thumbnail_path)

    # Copy to canonical project thumbnail.png
    canonical_thumb = experiment.project_dir / "thumbnail.png"
    if winning_variant.thumbnail_path.exists():
        shutil.copy2(winning_variant.thumbnail_path, canonical_thumb)

    # Sync configuration to thumbnail_config.json
    cfg_file = experiment.project_dir / "thumbnail_config.json"
    if cfg_file.exists():
        try:
            cfg_data = json.loads(cfg_file.read_text(encoding="utf-8-sig"))
            if winning_variant.config:
                for k, v in winning_variant.config.items():
                    cfg_data[k] = v
                if "default" in cfg_data and isinstance(cfg_data["default"], dict):
                    for k, v in winning_variant.config.items():
                        cfg_data["default"][k] = v
                cfg_file.write_text(json.dumps(cfg_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    now_iso = datetime.now(timezone.utc).isoformat()
    experiment.status = "CONCLUDED"
    experiment.active_variant_id = winner_id

    for vid, v in experiment.variants.items():
        v.is_active = (vid == winner_id)

    if experiment.winner_decision is None:
        experiment.winner_decision = WinnerDecision(
            winner_variant_id=winner_id,
            winning_score=_get_variant_ctr(winning_variant),
            is_significant=True,
            rationale=f"Winner {winner_id} committed.",
        )

    experiment.winner_decision.winner_variant_id = winner_id
    experiment.winner_decision.committed = True
    experiment.winner_decision.committed_at = now_iso
    experiment.updated_at = now_iso

    # Generate QA audit reports
    md_report = render_ab_report(experiment)
    json_report = json.dumps(experiment.to_dict(), ensure_ascii=False, indent=2)

    qa_dir = experiment.project_dir / "qa_reports"
    qa_dir.mkdir(parents=True, exist_ok=True)

    report_targets = [
        experiment.project_dir / "ab_test_report.md",
        experiment.project_dir / "ab_test_report.json",
        qa_dir / "ab_test_report.md",
        qa_dir / "ab_test_report.json",
        qa_dir / "thumbnail_ab_winner_report.md",
        qa_dir / "thumbnail_ab_winner_report.json",
    ]
    for target in report_targets:
        if target.suffix == ".md":
            target.write_text(md_report, encoding="utf-8")
        elif target.suffix == ".json":
            target.write_text(json_report, encoding="utf-8")

    save_experiment(experiment)
    return experiment


def get_status(project_dir: Path) -> ThumbnailExperiment:
    """Retrieve current thumbnail A/B experiment state from disk."""
    return load_experiment(project_dir)


def render_ab_report(experiment: ThumbnailExperiment) -> str:
    """Render comprehensive Markdown QA scorecard and history report."""
    lines = [
        "# YouTube Thumbnail A/B Test Audit Report",
        "",
        f"- **Experiment ID**: `{experiment.experiment_id}`",
        f"- **Video ID**: `{experiment.video_id}`",
        f"- **Status**: `{experiment.status}`",
        f"- **Active Variant**: `{experiment.active_variant_id}`",
        f"- **Created At**: `{experiment.created_at}`",
        f"- **Updated At**: `{experiment.updated_at}`",
        "",
        "## Winner Decision Scorecard",
    ]

    dec = experiment.winner_decision
    if dec is not None:
        p_val_str = f"{dec.p_value:.4f}" if dec.p_value is not None else "N/A"
        lines.extend([
            f"- **Winner Variant**: **{dec.winner_variant_id}**",
            f"- **Winning Score (CTR)**: {dec.winning_score:.2%}",
            f"- **Margin**: {dec.margin:.2%}",
            f"- **Statistically Significant**: {dec.is_significant}",
            f"- **p-value**: {p_val_str}",
            f"- **Committed**: {dec.committed} ({dec.committed_at or 'pending'})",
            f"- **Rationale**: {dec.rationale}",
        ])
    else:
        lines.append("- *No winner decision evaluated yet.*")

    lines.extend([
        "",
        "## Variant Performance Table",
        "| Variant ID | Name | Impressions | Views | CTR | Avg Watch % | Retention Score | Active | Rotations |",
        "|---|---|---|---|---|---|---|---|---|",
    ])

    for vid in sorted(experiment.variants.keys()):
        v = experiment.variants[vid]
        m = v.metrics
        ctr_val = _get_variant_ctr(v)
        lines.append(
            f"| {vid} | {v.name} | {m.impressions} | {m.views} | {ctr_val:.2%} | "
            f"{m.average_view_percentage:.1f}% | {m.retention_score:.2f} | "
            f"{'✅' if v.is_active else '❌'} | {v.rotation_count} |"
        )

    lines.extend([
        "",
        "## Rotation History Log",
        "| Timestamp | From | To | Reason |",
        "|---|---|---|---|",
    ])

    if experiment.rotation_history:
        for ev in experiment.rotation_history:
            from_str = ev.from_variant_id or "(initial)"
            lines.append(f"| {ev.timestamp} | {from_str} | {ev.to_variant_id} | {ev.reason} |")
    else:
        lines.append("| - | - | - | No rotation events recorded |")

    lines.append("")
    return "\n".join(lines)


class _HybridMethod:
    """Descriptor supporting calling coordinator methods on either class or instance."""

    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func

    def __get__(self, instance: Any, owner: Any) -> Any:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if instance is not None:
                return self.func(instance, *args, **kwargs)
            return self.func(owner(), *args, **kwargs)

        return wrapper


class ThumbnailABCoordinator:
    """Application Service coordinating YouTube thumbnail A/B testing lifecycle."""

    def __init__(
        self,
        publisher: Optional[VideoPublisher] = None,
        analytics_provider: Optional[VideoAnalyticsProvider] = None,
    ) -> None:
        self.publisher = publisher
        self.analytics_provider = analytics_provider

    @_HybridMethod
    def save_experiment(
        self,
        experiment: ThumbnailExperiment,
        path: Optional[Path] = None,
    ) -> Path:
        return save_experiment(experiment, path)

    @_HybridMethod
    def load_experiment(self, path_or_project_dir: Path) -> ThumbnailExperiment:
        return load_experiment(path_or_project_dir)

    @_HybridMethod
    def initialize_experiment(
        self,
        project_dir: Path,
        video_id: str,
        variants: Optional[List[ThumbnailVariant]] = None,
        publisher: Optional[VideoPublisher] = None,
        min_impressions: int = 500,
        min_observation_hours: float = 24.0,
    ) -> ThumbnailExperiment:
        pub = publisher if publisher is not None else self.publisher
        return initialize_experiment(
            project_dir=project_dir,
            video_id=video_id,
            variants=variants,
            publisher=pub,
            min_impressions=min_impressions,
            min_observation_hours=min_observation_hours,
        )

    @_HybridMethod
    def rotate_thumbnail(
        self,
        project_dir: Path,
        video_id: str,
        target_variant_id: Optional[str] = None,
        publisher: Optional[VideoPublisher] = None,
        reason: str = "scheduled_rotation",
    ) -> RotationEvent:
        pub = publisher if publisher is not None else self.publisher
        return rotate_thumbnail(
            project_dir=project_dir,
            video_id=video_id,
            target_variant_id=target_variant_id,
            publisher=pub,
            reason=reason,
        )

    @_HybridMethod
    def evaluate_performance(
        self,
        project_dir: Path,
        video_id: str,
        analytics_provider: Optional[VideoAnalyticsProvider] = None,
        confidence_level: float = 0.95,
        min_impressions: Optional[int] = None,
    ) -> WinnerDecision:
        analytics = analytics_provider if analytics_provider is not None else self.analytics_provider
        return evaluate_performance(
            project_dir=project_dir,
            video_id=video_id,
            analytics_provider=analytics,
            confidence_level=confidence_level,
            min_impressions=min_impressions,
        )

    @_HybridMethod
    def commit_winner(
        self,
        project_dir: Path,
        video_id: str,
        winner_id: Optional[str] = None,
        publisher: Optional[VideoPublisher] = None,
        analytics_provider: Optional[VideoAnalyticsProvider] = None,
    ) -> ThumbnailExperiment:
        pub = publisher if publisher is not None else self.publisher
        analytics = analytics_provider if analytics_provider is not None else self.analytics_provider
        return commit_winner(
            project_dir=project_dir,
            video_id=video_id,
            winner_id=winner_id,
            publisher=pub,
            analytics_provider=analytics,
        )

    @_HybridMethod
    def get_status(self, project_dir: Path) -> ThumbnailExperiment:
        return get_status(project_dir)

    @_HybridMethod
    def render_ab_report(self, experiment: ThumbnailExperiment) -> str:
        return render_ab_report(experiment)


__all__ = [
    "ThumbnailABCoordinator",
    "save_experiment",
    "load_experiment",
    "initialize_experiment",
    "rotate_thumbnail",
    "evaluate_performance",
    "commit_winner",
    "get_status",
    "render_ab_report",
]
