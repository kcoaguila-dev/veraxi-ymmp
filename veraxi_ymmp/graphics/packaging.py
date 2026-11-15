"""
Title + Thumbnail Packaging for Veraxi YMMP — Test & Compare ready pairs.

Rivals research summary (2026-11-15, sources in PR description):
- YouTube Test & Compare tests up to 3 title/thumbnail pairs concurrently and
  picks the winner by watch-time share, so the deliverable of a packaging
  system is 3 deliberately different pairs, not 1 thumbnail + 1 title.
- Japanese Yukkuri-explainer genre rules (YukkuriGen guide): thumbnail main
  text 12-15 chars, contrast >= 7:1, strong tachie emotion, and the thumbnail
  text must NOT duplicate the title (title = topic, thumbnail = hook fragment).
- Japanese title rules (mirrors exporters/youtube_metadata.evaluate_title):
  genre tag first, hook inside the first 20 chars, <= 32 chars ideal so the
  title is not truncated on mobile, a concrete number OR a curiosity hook.

This module is deterministic and offline: it never invents a number. The
"result" axis only uses a metric that already exists in project artifacts
(broll hero_metric / thumbnail stat_callout / metric_highlight), which the
epistemic gate has already audited. Scores are a transparent heuristic
rubric for ranking variants before a real Test & Compare run — they are
NOT a CTR prediction.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import Image, ImageStat

from veraxi_ymmp.core.logging import logger
from veraxi_ymmp.graphics.packaging_patterns import is_generic_slop, load_patterns
from veraxi_ymmp.graphics.thumbnail import (
    ThumbnailConfig,
    auto_extract_thumbnail_config,
    generate_thumbnail,
)
from veraxi_ymmp.graphics.thumbnail_composer import validate_thumbnail_visual_qa

TITLE_TAG = "【ずんだもん解説】"
TITLE_IDEAL_MAX_CHARS = 32
TITLE_HARD_MAX_CHARS = 60
TITLE_HOOK_WINDOW = 20
THUMB_TEXT_IDEAL_CHARS = 15
THUMB_TEXT_MAX_CHARS = 20
STRONG_EMOTIONS = ("surprised", "angry", "happy")
CURIOSITY_MARKERS = ("？", "?", "なぜ", "正体", "末路", "誰", "分かれ目", "真実")
PACKAGING_AXES = ("curiosity", "result", "loss")

_AXIS_BADGES = {"curiosity": "【徹底解説】", "result": "【完全解説】", "loss": "【緊急警告】"}
_AXIS_THEMES = {"curiosity": "gold", "result": "cyan", "loss": "red"}
_AXIS_EMOTIONS = {"curiosity": "surprised", "result": "happy", "loss": "angry"}


@dataclass
class PackagingPair:
    """One Test & Compare candidate: a title + thumbnail on a single axis."""

    axis: str
    title: str
    config: Dict[str, Any]
    thumbnail_file: str = ""
    scores: Dict[str, int] = field(default_factory=dict)
    total: int = 0
    issues: List[str] = field(default_factory=list)
    image_qa: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _normalize_text(text: str) -> str:
    """Strip tags/punctuation/space so overlap checks compare real content."""
    text = re.sub(r"【[^】]*】", "", text or "")
    return re.sub(r"[\s？！?!。、・「」『』▶\-—_~…]", "", text)


def thumbnail_text_chars(config: ThumbnailConfig) -> int:
    """Total main-text characters (line1 + line2), spaces excluded."""
    raw = (config.title_line1 or "") + (config.title_line2 or "")
    return len(re.sub(r"\s", "", raw))


def title_thumbnail_overlap(title: str, config: ThumbnailConfig) -> float:
    """
    0.0 = fully complementary, 1.0 = thumbnail text copied into the title.
    A whole thumbnail line (>=4 normalized chars) inside the title is a copy;
    otherwise the char-bigram overlap ratio of thumbnail text vs title.
    """
    norm_title = _normalize_text(title)
    # Only the main hook text (line2) is checked: line1 is the subject name,
    # which legitimately appears in both (the title needs the keyword), and
    # the sub_hook is a supporting stat line that may restate a figure from
    # the title. Duplication means copying the hook, not naming the subject.
    lines = [_normalize_text(x) for x in (config.title_line2,)]
    lines = [x for x in lines if x]
    if not norm_title or not lines:
        return 0.0
    for line in lines:
        if len(line) >= 4 and line in norm_title:
            return 1.0
    thumb_all = "".join(lines)
    if len(thumb_all) < 2:
        return 0.0
    bigrams = {thumb_all[i : i + 2] for i in range(len(thumb_all) - 1)}
    if not bigrams:
        return 0.0
    shared = sum(1 for b in bigrams if b in norm_title)
    return round(shared / len(bigrams), 3)


def score_title(title: str, topic: str = "") -> Tuple[int, List[str]]:
    """Title rubric, 0-40. Mirrors the repo's evaluate_title rules."""
    issues: List[str] = []
    score = 0
    n = len(title)
    if n > TITLE_HARD_MAX_CHARS:
        issues.append(f"タイトルが長すぎます({n}字 > {TITLE_HARD_MAX_CHARS}字)")
    elif n > TITLE_IDEAL_MAX_CHARS:
        score += 8
        issues.append(f"タイトルが理想より長めです({n}字 > {TITLE_IDEAL_MAX_CHARS}字): スマホで省略される可能性があります")
    elif n >= 18:
        score += 14
    elif n >= 12:
        score += 10
    else:
        score += 5
        issues.append(f"タイトルが短すぎます({n}字)")
    if title.startswith("【"):
        score += 8
    else:
        issues.append("先頭にジャンルタグ【ずんだもん解説】がありません")
    body = title.split("】", 1)[-1] if title.startswith("【") else title
    has_digit = any(ch.isdigit() for ch in title)
    has_curiosity = any(m in body for m in CURIOSITY_MARKERS)
    if has_digit and has_curiosity:
        score += 10
    elif has_digit or has_curiosity:
        score += 9
    else:
        issues.append("数字または疑問・好奇心フックがありません")
    if topic:
        head = _normalize_text(topic)[:4]
        window = _normalize_text(title)[: TITLE_HOOK_WINDOW + 4]
        if head and head in window:
            score += 8
        else:
            issues.append("主題キーワードがタイトル先頭20字以内にありません")
    elif body:
        score += 8
    return score, issues


def score_thumbnail_text(config: ThumbnailConfig) -> Tuple[int, List[str]]:
    """Thumbnail-text rubric, 0-25: genre budget is 12-15 chars, 20 max."""
    issues: List[str] = []
    chars = thumbnail_text_chars(config)
    if chars == 0:
        issues.append("サムネイルのメインテキストが空です")
        return 0, issues
    if chars <= THUMB_TEXT_IDEAL_CHARS:
        score = 15
    elif chars <= THUMB_TEXT_MAX_CHARS:
        score = 11
        issues.append(f"サムネ文言がやや多めです({chars}字 > {THUMB_TEXT_IDEAL_CHARS}字)")
    elif chars <= 26:
        score = 6
        issues.append(f"サムネ文言が多すぎます({chars}字 > {THUMB_TEXT_MAX_CHARS}字): スマホで読めません")
    else:
        score = 2
        issues.append(f"サムネ文言が多すぎます({chars}字): 1メッセージに絞ってください")
    hl = (config.highlight_word or "").strip()
    if hl and hl in (config.title_line2 or ""):
        score += 5
    elif hl:
        issues.append("ハイライト語が2行目に含まれていません")
    else:
        issues.append("ハイライト語が未設定です")
    badge = (config.badge or "").strip()
    if badge:
        score += 5 if len(badge) <= 10 else 3
    else:
        # Clean mobile-first 2-element thumbnails (no pill badge) are valid and
        # reduce visual clutter in feed squint-tests.
        score += 3
    return score, issues


def score_complementarity(title: str, config: ThumbnailConfig) -> Tuple[int, List[str]]:
    """Complementarity rubric, 0-20: title and thumbnail must not repeat."""
    overlap = title_thumbnail_overlap(title, config)
    if overlap >= 0.99:
        return 0, ["サムネ文言がタイトルにそのまま含まれています(重複)"]
    if overlap >= 0.7:
        return 5, [f"タイトルとサムネ文言の重なりが大きいです(overlap={overlap})"]
    if overlap >= 0.4:
        return 10, [f"タイトルとサムネ文言が一部重なっています(overlap={overlap})"]
    if overlap >= 0.2:
        return 16, []
    return 20, []


def score_emotion(config: ThumbnailConfig) -> Tuple[int, List[str]]:
    """Emotion rubric, 0-5: strong tachie expressions carry the click."""
    emo = (config.emotion or "").strip().lower()
    if emo in STRONG_EMOTIONS:
        return 5, []
    if emo in ("sad", "surprise"):
        return 3, [f"表情 '{emo}' は弱めです(驚き・怒り・喜びが推奨)"]
    return 2, [f"表情 '{emo or '未設定'}' は弱めです(驚き・怒り・喜びが推奨)"]


def analyze_thumbnail_image(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Image rubric input: wraps validate_thumbnail_visual_qa and adds a
    brightness check (very dark thumbnails underperform in browse feeds).
    Returns the visual-QA dict plus mean_luminance and brightness_ok.
    """
    p = Path(path)
    qa = validate_thumbnail_visual_qa(p)
    try:
        with Image.open(p) as img:
            gray = img.convert("L")
            gray.thumbnail((320, 180))
            mean_lum = float(ImageStat.Stat(gray).mean[0])
    except Exception as e:
        logger.warning("Failed brightness analysis for %s: %s", p, e)
        mean_lum = -1.0
    qa["mean_luminance"] = round(mean_lum, 1)
    qa["brightness_ok"] = mean_lum >= 35.0
    return qa


def score_pair(
    title: str,
    config: ThumbnailConfig,
    topic: str = "",
    image_qa: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, int], int, List[str]]:
    """Full pair scorecard /100. Heuristic ranking only — not a CTR prediction."""
    s_title, i_title = score_title(title, topic)
    s_text, i_text = score_thumbnail_text(config)
    s_comp, i_comp = score_complementarity(title, config)
    s_emo, i_emo = score_emotion(config)
    scores = {"title": s_title, "thumbnail_text": s_text, "complementarity": s_comp, "emotion": s_emo}
    issues = i_title + i_text + i_comp + i_emo
    if image_qa is not None:
        s_image = int(round(float(image_qa.get("score", 0)) / 10.0))
        scores["image"] = s_image
        if not image_qa.get("passed", False):
            issues.append("画像QAが不合格です(寸法/サイズ/デッドゾーン/コントラストを確認)")
        if image_qa.get("brightness_ok") is False:
            issues.append(f"サムネイルが暗すぎます(平均輝度={image_qa.get('mean_luminance')})")
    total = sum(scores.values())
    if image_qa is None:
        # Rescale the 90-point text-only rubric to /100 for comparability.
        total = int(round(total / 90.0 * 100))
    scores["total"] = total
    return scores, total, issues


def _fit_title(topic: str, suffix: str) -> str:
    """Build TAG + topic + suffix, truncating the topic to the ideal length."""
    topic = re.sub(r"\s+", "", (topic or "").strip()).rstrip("。")
    budget = TITLE_IDEAL_MAX_CHARS - len(TITLE_TAG) - len(suffix)
    if budget < 4:
        budget = 4
    if len(topic) > budget:
        topic = topic[:budget]
    return f"{TITLE_TAG}{topic}{suffix}"


def build_axis_titles(
    topic: str,
    metric: str = "",
    patterns: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Three titles on different strategic axes. The result axis uses the
    caller-supplied metric verbatim; no number is ever invented here.

    When ``patterns`` is supplied (from `patterns.json` / outlier mining),
    titles adapt to live trend preferences (e.g., hook-first without the
    9-char 【ずんだもん解説】 prefix when rivals win without bracket tags).
    """
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("topic must not be empty")
    metric = re.sub(r"\s+", "", (metric or "").strip())

    if patterns and patterns.get("prefer_hook_first"):
        clean_topic = re.sub(r"\s+", "", topic).rstrip("。")
        max_len = TITLE_IDEAL_MAX_CHARS
        c_title = f"なぜ{clean_topic}は突然崩れたのか？"
        if len(c_title) > max_len:
            c_title = f"なぜ{clean_topic[: max(4, max_len - 10)]}は崩れたのか？"
        l_title = f"知らないと危ない{clean_topic}の落とし穴"
        if len(l_title) > max_len:
            l_title = f"危ない{clean_topic[: max(4, max_len - 8)]}の落とし穴"
        if metric:
            r_title = f"{metric}の異常値…{clean_topic}に何が？"
            if len(r_title) > max_len:
                keep = max(4, max_len - len(metric) - 9)
                r_title = f"{metric}の衝撃…{clean_topic[:keep]}の今"
        else:
            r_title = f"{clean_topic[: max(4, max_len - 11)]}の明暗を分けた一手"
        return {
            "curiosity": c_title[:max_len],
            "result": r_title[:max_len],
            "loss": l_title[:max_len],
        }

    titles = {
        "curiosity": _fit_title(topic, "の正体とは？"),
        "loss": _fit_title(topic, "で知らないと損する真実"),
    }
    if metric:
        body = f"{metric}の衝撃"
        budget = TITLE_IDEAL_MAX_CHARS - len(TITLE_TAG) - len(body) - 1
        keep = max(4, budget)
        t = topic[:keep] if len(topic) > keep else topic
        titles["result"] = f"{TITLE_TAG}{t}、{body}"
    else:
        titles["result"] = _fit_title(topic, "の分かれ目")
    return titles


_AXIS_HOOK_COPY = {
    "curiosity": ("なぜ崩れた？", "崩れた"),
    "result": ("異常値の正体", "異常値"),
    "loss": ("最大の落とし穴", "落とし穴"),
}


def build_axis_configs(
    base: ThumbnailConfig,
    metric: str = "",
    patterns: Optional[Dict[str, Any]] = None,
) -> Dict[str, ThumbnailConfig]:
    """Three thumbnail configs on different axes, derived from the base config."""
    base_dict = base.to_dict()
    clean_badge_free = bool(patterns and patterns.get("prefer_clean_badge_free"))
    has_subject = bool(base.subject_image_path or base.brand_logo_path)
    configs: Dict[str, ThumbnailConfig] = {}
    for axis in PACKAGING_AXES:
        data = dict(base_dict)
        data["theme"] = _AXIS_THEMES[axis]
        data["emotion"] = _AXIS_EMOTIONS[axis]
        data["badge"] = "" if clean_badge_free else _AXIS_BADGES[axis]
        if patterns is not None:
            # Differentiate hook copy per axis so Test & Compare tests real angles,
            # not just color/badge swaps.
            hook_line2, hl_word = _AXIS_HOOK_COPY[axis]
            if axis == "result" and metric:
                data["title_line2"] = f"{metric.strip()}の衝撃"
                data["highlight_word"] = metric.strip()
            else:
                data["title_line2"] = hook_line2
                data["highlight_word"] = hl_word
            if has_subject and axis in ("curiosity", "result"):
                data["layout"] = "editorial_spotlight"
        if axis == "result" and metric:
            data["sub_hook"] = f"▶ {metric.strip()}"
            data["stat_callout"] = metric.strip()
        configs[axis] = ThumbnailConfig.from_dict(data)
    return configs


def extract_packaging_inputs(project_dir: Union[str, Path]) -> Tuple[ThumbnailConfig, str, str]:
    """
    (base_config, topic, metric) from project artifacts only.
    Topic = first broll slide title, else the thumbnail line1, else dir name.
    Metric = first slide hero_metric, else config stat/metric fields, else "".
    """
    proj = Path(project_dir).resolve()
    base = auto_extract_thumbnail_config(proj)
    topic = ""
    metric = (base.stat_callout or base.metric_highlight or "").strip()
    manifest_path = proj / "broll_manifest.json"
    if manifest_path.is_file():
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            slides = raw if isinstance(raw, list) else raw.get("slides", [])
            for slide in slides:
                if not isinstance(slide, dict):
                    continue
                slide_topic = str(slide.get("title") or slide.get("hero_title") or "").strip()
                if not slide_topic:
                    continue
                topic = slide_topic
                slide_metric = str(slide.get("hero_metric") or "").strip()
                if slide_metric:
                    metric = slide_metric
                break
        except Exception as e:
            logger.warning("Failed to read broll_manifest.json in %s: %s", proj, e)
    if not topic:
        topic = (base.title_line1 or "").strip() or proj.name
    return base, topic, metric


def _resolve_patterns_path(proj: Path, patterns_path: Optional[Union[str, Path]] = None) -> Optional[Path]:
    if patterns_path is not None:
        return Path(patterns_path)
    for candidate in (
        proj / "patterns.json",
        proj.parent.parent / "artifacts" / "corpus" / "patterns.json",
    ):
        if candidate.is_file():
            return candidate
    return None


def generate_packaging(
    project_dir: Union[str, Path],
    patterns_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Render 3 Test & Compare pairs into <project>/packaging/ and write
    <project>/packaging.json with scorecards and the recommended axis.
    Does not touch thumbnail.png; selection is an explicit separate step.
    """
    proj = Path(project_dir).resolve()
    if not proj.is_dir():
        raise FileNotFoundError(f"Project directory '{project_dir}' not found.")
    resolved_patterns = _resolve_patterns_path(proj, patterns_path)
    patterns = load_patterns(resolved_patterns)
    base, topic, metric = extract_packaging_inputs(proj)
    titles = build_axis_titles(topic, metric, patterns=patterns)
    configs = build_axis_configs(base, metric, patterns=patterns)
    out_dir = proj / "packaging"
    out_dir.mkdir(parents=True, exist_ok=True)

    pairs: List[PackagingPair] = []
    for axis in PACKAGING_AXES:
        cfg = configs[axis]
        img_path = out_dir / f"thumbnail_{axis}.png"
        generate_thumbnail(cfg, img_path)
        image_qa = analyze_thumbnail_image(img_path)
        scores, total, issues = score_pair(titles[axis], cfg, topic, image_qa)
        if is_generic_slop(cfg.title_line2, patterns.get("anti_slop_phrases")):
            issues.append("サムネ2行目が汎用テンプレート表現です")
        pairs.append(
            PackagingPair(
                axis=axis,
                title=titles[axis],
                config=cfg.to_dict(),
                thumbnail_file=f"packaging/thumbnail_{axis}.png",
                scores=scores,
                total=total,
                issues=issues,
                image_qa=image_qa,
            )
        )
    recommended = max(pairs, key=lambda p: p.total).axis
    payload: Dict[str, Any] = {
        "topic": topic,
        "metric": metric,
        "recommended_axis": recommended,
        "selected_axis": None,
        "patterns_source": str(resolved_patterns) if resolved_patterns else "default",
        "score_note": "ヒューリスティックスコア(CTR予測ではありません)。YouTube Test & Compare の実測が最終判定です。",
        "pairs": [p.to_dict() for p in pairs],
    }
    (proj / "packaging.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Packaging generated for %s (recommended: %s)", proj.name, recommended)
    return payload


def load_packaging(project_dir: Union[str, Path]) -> Dict[str, Any]:
    """Read packaging.json; raises FileNotFoundError / ValueError if unusable."""
    proj = Path(project_dir).resolve()
    pkg_path = proj / "packaging.json"
    if not pkg_path.is_file():
        raise FileNotFoundError(f"packaging.json not found in '{project_dir}'")
    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        raise ValueError(f"packaging.json is corrupt: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("pairs"), list) or not data["pairs"]:
        raise ValueError("packaging.json has no pairs")
    return data


def select_packaging_pair(project_dir: Union[str, Path], axis: str) -> Dict[str, Any]:
    """
    Promote one pair: copy its thumbnail to thumbnail.png and record the
    selection in packaging.json. Fails closed on an unknown axis or a
    missing candidate image — thumbnail.png is never half-updated.
    """
    proj = Path(project_dir).resolve()
    if axis not in PACKAGING_AXES:
        raise ValueError(f"Unknown packaging axis '{axis}' (expected one of {PACKAGING_AXES})")
    data = load_packaging(proj)
    pair = next((p for p in data["pairs"] if isinstance(p, dict) and p.get("axis") == axis), None)
    if pair is None:
        raise ValueError(f"Axis '{axis}' not present in packaging.json")
    src = proj / str(pair.get("thumbnail_file") or "")
    if not src.is_file():
        raise FileNotFoundError(f"Candidate thumbnail missing: {src}")

    thumb_dest = proj / "thumbnail.png"
    pkg_dest = proj / "packaging.json"
    data["selected_axis"] = axis

    tmp_thumb: Optional[Path] = None
    tmp_pkg: Optional[Path] = None
    backup_thumb: Optional[Path] = None
    thumb_replaced = False
    try:
        with tempfile.NamedTemporaryFile(
            dir=proj, prefix=".thumbnail.", suffix=".png.tmp", delete=False
        ) as tf:
            tmp_thumb = Path(tf.name)
        shutil.copyfile(src, tmp_thumb)

        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=proj,
            prefix=".packaging.",
            suffix=".json.tmp",
            encoding="utf-8",
            delete=False,
        ) as pf:
            tmp_pkg = Path(pf.name)
            pf.write(json.dumps(data, ensure_ascii=False, indent=2))
            pf.flush()

        if thumb_dest.exists():
            with tempfile.NamedTemporaryFile(
                dir=proj, prefix=".thumbnail.bak.", suffix=".png", delete=False
            ) as bf:
                backup_thumb = Path(bf.name)
            shutil.copyfile(thumb_dest, backup_thumb)

        os.replace(tmp_thumb, thumb_dest)
        tmp_thumb = None
        thumb_replaced = True

        os.replace(tmp_pkg, pkg_dest)
        tmp_pkg = None
    except BaseException:
        if thumb_replaced and backup_thumb is not None and backup_thumb.exists():
            os.replace(backup_thumb, thumb_dest)
            backup_thumb = None
        raise
    finally:
        for leftover in (tmp_thumb, tmp_pkg, backup_thumb):
            if leftover is not None and leftover.exists():
                leftover.unlink(missing_ok=True)

    logger.info("Packaging pair '%s' selected for %s", axis, proj.name)
    return pair


def update_packaging_pair(
    project_dir: Union[str, Path],
    axis: str,
    title: Optional[str] = None,
    config_patch: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Live-edit a single packaging candidate (title and/or ThumbnailConfig fields),
    re-render its candidate thumbnail, recompute QA/scores, and persist packaging.json.
    """
    proj = Path(project_dir).resolve()
    if axis not in PACKAGING_AXES:
        raise ValueError(f"Unknown packaging axis '{axis}' (expected one of {PACKAGING_AXES})")
    data = load_packaging(proj)
    idx = next(
        (i for i, p in enumerate(data["pairs"]) if isinstance(p, dict) and p.get("axis") == axis),
        None,
    )
    if idx is None:
        raise ValueError(f"Axis '{axis}' not present in packaging.json")

    pair = dict(data["pairs"][idx])
    new_title = str(title).strip() if title is not None else str(pair.get("title") or "")
    cfg_dict = dict(pair.get("config") or {})
    if isinstance(config_patch, dict):
        allowed = {f.name for f in ThumbnailConfig.__dataclass_fields__.values()}
        for k, v in config_patch.items():
            if k in allowed:
                cfg_dict[k] = v

    cfg = ThumbnailConfig.from_dict(cfg_dict)
    out_dir = proj / "packaging"
    out_dir.mkdir(parents=True, exist_ok=True)
    img_path = out_dir / f"thumbnail_{axis}.png"
    generate_thumbnail(cfg, img_path)
    image_qa = analyze_thumbnail_image(img_path)
    topic = str(data.get("topic") or "")
    scores, total, issues = score_pair(new_title, cfg, topic, image_qa)

    updated_pair = PackagingPair(
        axis=axis,
        title=new_title,
        config=cfg.to_dict(),
        thumbnail_file=f"packaging/thumbnail_{axis}.png",
        scores=scores,
        total=total,
        issues=issues,
        image_qa=image_qa,
    ).to_dict()
    data["pairs"][idx] = updated_pair
    data["recommended_axis"] = max(data["pairs"], key=lambda p: p.get("total", 0)).get("axis")

    pkg_dest = proj / "packaging.json"
    tmp_pkg: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=proj,
            prefix=".packaging.",
            suffix=".json.tmp",
            encoding="utf-8",
            delete=False,
        ) as pf:
            tmp_pkg = Path(pf.name)
            pf.write(json.dumps(data, ensure_ascii=False, indent=2))
            pf.flush()
        os.replace(tmp_pkg, pkg_dest)
        tmp_pkg = None
    finally:
        if tmp_pkg is not None and tmp_pkg.exists():
            tmp_pkg.unlink(missing_ok=True)

    return data
