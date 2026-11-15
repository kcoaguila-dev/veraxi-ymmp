"""Adaptive Packaging Pattern Library & Outlier Miner (Tier 2).

Extracts reusable title and thumbnail composition patterns from an outlier
corpus (`corpus.json` produced by `app/outlier_corpus.py`), stores them in
`patterns.json`, and calibrates archetype weights from Test & Compare /
YouTube Analytics feedback.

This module is pure Tier 2 (`graphics/`): it never imports from `app/` and
never invents quantitative claims.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_ANTI_SLOP_PHRASES: Tuple[str, ...] = (
    "衝撃の真実",
    "徹底解明",
    "完全解説",
    "ヤバすぎる",
    "徹底比較",
)

DEFAULT_TITLE_ARCHETYPES: List[Dict[str, Any]] = [
    {
        "id": "reversal_why",
        "axis": "curiosity",
        "label": "逆転・違和感フック",
        "template": "なぜ{entity}は突然崩れたのか？",
        "weight": 1.25,
        "wins": 0,
        "losses": 0,
        "hook_first": True,
    },
    {
        "id": "quantified_shock",
        "axis": "result",
        "label": "数字＋異常値フック",
        "template": "{metric}の異常値…{entity}に何が起きた？",
        "weight": 1.2,
        "wins": 0,
        "losses": 0,
        "hook_first": True,
    },
    {
        "id": "loss_warning",
        "axis": "loss",
        "label": "損失回避・落とし穴フック",
        "template": "知らないと危ない{entity}の落とし穴",
        "weight": 1.15,
        "wins": 0,
        "losses": 0,
        "hook_first": True,
    },
]

DEFAULT_LAYOUT_ARCHETYPES: List[Dict[str, Any]] = [
    {
        "id": "clean_impact",
        "label": "2要素モバイル特化 (バッジ無し)",
        "use_badge": False,
        "max_elements": 3,
        "weight": 1.25,
        "wins": 0,
        "losses": 0,
    },
    {
        "id": "editorial_spotlight",
        "label": "実写・ロゴ主役スポットライト",
        "use_badge": False,
        "max_elements": 3,
        "weight": 1.3,
        "wins": 0,
        "losses": 0,
    },
    {
        "id": "classic_split",
        "label": "クラシック3分割",
        "use_badge": True,
        "max_elements": 4,
        "weight": 0.9,
        "wins": 0,
        "losses": 0,
    },
]


def default_pattern_library() -> Dict[str, Any]:
    """Return a fresh copy of the default adaptive pattern library."""
    return {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source_outliers_count": 0,
        "bracket_tag_rate": 0.25,
        "prefer_hook_first": True,
        "prefer_clean_badge_free": True,
        "avg_outlier_title_chars": 28.0,
        "anti_slop_phrases": list(DEFAULT_ANTI_SLOP_PHRASES),
        "title_archetypes": [dict(a) for a in DEFAULT_TITLE_ARCHETYPES],
        "layout_archetypes": [dict(a) for a in DEFAULT_LAYOUT_ARCHETYPES],
        "recent_outlier_hooks": [],
    }


def is_generic_slop(text: str, extra_phrases: Optional[List[str]] = None) -> bool:
    """Return True if text relies on generic AI-slop filler as its main hook."""
    cleaned = re.sub(r"[\s？！?!【】\[\]▶]+", "", text or "")
    if not cleaned:
        return False
    phrases = tuple(extra_phrases) if extra_phrases else DEFAULT_ANTI_SLOP_PHRASES
    for phrase in phrases:
        if cleaned == phrase or cleaned.endswith(phrase):
            return True
    return False


def _recency_weight(published_at: str, now_dt: datetime) -> float:
    """Weight recent outliers (<=60d = 1.0, <=120d = 0.7, older = 0.35)."""
    if not published_at:
        return 0.6
    try:
        pub = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now_dt - pub).total_seconds() / 86400.0)
        if age_days <= 60.0:
            return 1.0
        if age_days <= 120.0:
            return 0.7
        return 0.35
    except Exception:
        return 0.6


def _classify_title_trigger(title: str) -> str:
    """Classify an outlier title into one of the core curiosity axes."""
    if any(tok in title for tok in ("危険", "損", "落とし穴", "末路", "崩壊", "罠", "NG", "注意")):
        return "loss"
    if any(ch.isdigit() for ch in title) or any(tok in title for tok in ("倍", "%", "％", "億", "万", "兆")):
        return "result"
    return "curiosity"


def extract_patterns_from_corpus(
    corpus: Dict[str, Any],
    existing: Optional[Dict[str, Any]] = None,
    now_dt: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Mine title & packaging trend signals from an outlier corpus dict."""
    now = now_dt or datetime.now(timezone.utc)
    lib = json.loads(json.dumps(existing)) if isinstance(existing, dict) else default_pattern_library()
    outliers = [o for o in (corpus.get("outliers") or []) if isinstance(o, dict)]
    if not outliers:
        lib["updated_at"] = now.isoformat()
        return lib

    total_w = 0.0
    bracket_w = 0.0
    len_w = 0.0
    axis_weights: Dict[str, float] = {"curiosity": 0.0, "result": 0.0, "loss": 0.0}
    hooks: List[Dict[str, Any]] = []

    for row in outliers:
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        ratio = float(row.get("ratio_vs_mean") or 1.0)
        rec = _recency_weight(str(row.get("published_at") or ""), now)
        w = max(0.1, min(ratio, 20.0)) * rec
        total_w += w
        len_w += len(title) * w
        if title.startswith("【"):
            bracket_w += w
        axis = _classify_title_trigger(title)
        axis_weights[axis] = axis_weights.get(axis, 0.0) + w
        if len(hooks) < 12:
            hooks.append(
                {
                    "video_id": row.get("video_id", ""),
                    "title": title,
                    "axis": axis,
                    "ratio_vs_mean": round(ratio, 2),
                    "views": int(row.get("views") or 0),
                    "channel_title": row.get("channel_title", ""),
                }
            )

    if total_w > 0:
        bracket_rate = round(bracket_w / total_w, 3)
        lib["bracket_tag_rate"] = bracket_rate
        lib["prefer_hook_first"] = bracket_rate < 0.6
        lib["avg_outlier_title_chars"] = round(len_w / total_w, 1)

    max_aw = max(axis_weights.values()) if axis_weights else 1.0
    for arch in lib.get("title_archetypes", []):
        ax = arch.get("axis", "curiosity")
        norm = (axis_weights.get(ax, 0.0) / max_aw) if max_aw > 0 else 0.5
        base_w = float(arch.get("weight", 1.0))
        arch["weight"] = round(max(0.5, min(2.5, 0.7 * base_w + 0.6 * (0.8 + norm))), 3)

    lib["source_outliers_count"] = len(outliers)
    lib["recent_outlier_hooks"] = hooks
    lib["updated_at"] = now.isoformat()
    return lib


def load_patterns(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load patterns.json if present and valid; otherwise return defaults."""
    if path is not None and path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict) and "title_archetypes" in data:
                return data
        except Exception:
            pass
    return default_pattern_library()


def save_patterns(patterns: Dict[str, Any], path: Path) -> Path:
    """Atomically write patterns.json."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=path.parent,
            prefix=".patterns.",
            suffix=".json.tmp",
            encoding="utf-8",
            delete=False,
        ) as handle:
            tmp_path = Path(handle.name)
            handle.write(json.dumps(patterns, ensure_ascii=False, indent=2))
            handle.flush()
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    return path


def apply_feedback_to_patterns(
    path: Path,
    axis: str,
    layout: Optional[str] = None,
    won: bool = True,
    ctr: Optional[float] = None,
) -> Dict[str, Any]:
    """Update archetype weights from Test & Compare or YouTube Analytics results."""
    patterns = load_patterns(path)
    delta = 0.15 if won else -0.1
    if ctr is not None and ctr >= 6.0:
        delta += 0.05

    for arch in patterns.get("title_archetypes", []):
        if arch.get("axis") == axis:
            arch["wins"] = int(arch.get("wins", 0)) + (1 if won else 0)
            arch["losses"] = int(arch.get("losses", 0)) + (0 if won else 1)
            arch["weight"] = round(max(0.4, min(3.0, float(arch.get("weight", 1.0)) + delta)), 3)

    if layout:
        for l_arch in patterns.get("layout_archetypes", []):
            if l_arch.get("id") == layout:
                l_arch["wins"] = int(l_arch.get("wins", 0)) + (1 if won else 0)
                l_arch["losses"] = int(l_arch.get("losses", 0)) + (0 if won else 1)
                l_arch["weight"] = round(
                    max(0.4, min(3.0, float(l_arch.get("weight", 1.0)) + delta)), 3
                )

    patterns["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_patterns(patterns, path)
    return patterns
