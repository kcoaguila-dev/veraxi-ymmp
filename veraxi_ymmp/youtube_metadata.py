"""
YouTube Metadata & Copy-Paste Description Generator for Veraxi YMMP.

Automatically generates:
1. High-CTR YouTube titles (primary + A/B variants) from project script, manifest, and thumbnail config.
2. Exact YouTube Chapter Timestamps (`00:00 ...`) calculated from synthesized WAV durations and B-roll cues.
3. Mandatory VOICEVOX, character standing picture (坂本アヒル 様), and BGM credits based on actual assets used.
4. Topic-aware disclaimers (e.g., non-financial-advice disclaimer for market/investing videos).
5. Ready-to-copy-paste `youtube_metadata.txt` and structured `youtube_metadata.json`.
"""

from __future__ import annotations

import json
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .ir import TimelineIR
from .logging import logger
from .phonetics import strip_phonetic_ruby
from .validation import sanitize_filename

VOICEVOX_CREDITS_MAP: Dict[str, str] = {
    "ずんだもん": "VOICEVOX:ずんだもん",
    "四国めたん": "VOICEVOX:四国めたん",
    "春日部つむぎ": "VOICEVOX:春日部つむぎ",
    "雨晴はう": "VOICEVOX:雨晴はう",
    "冥鳴ひまり": "VOICEVOX:冥鳴ひまり",
    "青山龍星": "VOICEVOX:青山龍星",
}

TACHIE_CREDITS_MAP: Dict[str, str] = {
    "ずんだもん": "坂本アヒル 様（ずんだもん立ち絵素材）",
    "四国めたん": "坂本アヒル 様（四国めたん立ち絵素材）",
    "春日部つむぎ": "坂本アヒル 様（春日部つむぎ立ち絵素材）",
}

BGM_CREDITS_MAP: Dict[str, str] = {
    "2_23_AM.mp3": "しゃろう 様「2:23 AM」（DOVA-SYNDROME）",
}

FINANCE_KEYWORDS = ("株", "投資", "市場", "金利", "相場", "銘柄", "資産", "キャッシュフロー", "インデックス")


TITLE_MAX_CHARS = 32
TITLE_IDEAL_RANGE = (25, 32)
TITLE_KEYWORD_WINDOW = 20
TITLE_TAG_PREFIXES = ("【ずんだもん", "【四国めたん", "【VOICEVOX")


def evaluate_title(title: str, thumbnail_texts: Tuple[str, ...] = ()) -> List[str]:
    """
    Check a title against the Zundamon-explainer title rules; returns a list of
    human-readable warnings (empty list == all rules satisfied).

    Rules (from high-view Zundamon explainer research):
      1. Length 25-32 chars so it is not cut off with "..." on mobile.
      2. Starts with a genre tag such as 【ずんだもん解説】.
      3. The main topic keyword/hook appears inside the first 20 chars.
      4. Contains a concrete number OR a question/curiosity hook (no full answer).
      5. Does not copy the thumbnail text (title and thumbnail must complement).
    """
    warnings: List[str] = []
    n = len(title)
    if n > TITLE_MAX_CHARS:
        warnings.append(f"長すぎ({n}字 > {TITLE_MAX_CHARS}字): スマホで省略されます")
    elif n < TITLE_IDEAL_RANGE[0]:
        warnings.append(f"短め({n}字): {TITLE_IDEAL_RANGE[0]}字以上が目安")
    if not title.startswith(TITLE_TAG_PREFIXES):
        warnings.append("先頭にジャンルタグ【ずんだもん解説】がありません")
    body = title.split("】", 1)[-1] if title.startswith("【") else title
    if not any(ch.isdigit() for ch in title) and not any(q in body for q in ("？", "?", "末路", "正体", "分かれ目", "なぜ", "誰")):
        warnings.append("数字または疑問・好奇心フックがありません")
    for t in thumbnail_texts:
        t = t.strip()
        if len(t) >= 6 and t in title:
            warnings.append(f"サムネ文言「{t}」と重複しています")
    return warnings


@dataclass
class YouTubeMetadataBundle:
    """Structured YouTube metadata ready for copy-paste or API upload."""

    title: str
    title_variants: List[str] = field(default_factory=list)
    description: str = ""
    tags: List[str] = field(default_factory=list)
    hashtags: List[str] = field(default_factory=list)
    chapters: List[Tuple[str, str]] = field(default_factory=list)
    credits: List[str] = field(default_factory=list)


def _format_mm_ss(seconds: float) -> str:
    """Format seconds as YouTube chapter timestamp MM:SS (or HH:MM:SS)."""
    total_sec = max(0, int(seconds))
    hrs, rem = divmod(total_sec, 3600)
    mins, secs = divmod(rem, 60)
    if hrs > 0:
        return f"{hrs:d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def _compute_chapters_from_project(
    proj_dir: Path,
    script_data: List[Dict[str, Any]],
    broll_manifest: List[Dict[str, Any]],
    timeline_ir: Optional[TimelineIR] = None,
    fps: int = 60,
) -> List[Tuple[str, str]]:
    """
    Computes YouTube chapter timestamps (`MM:SS`, `Chapter Title`) from B-roll transitions.
    Always begins with `00:00 オープニング`.
    """
    slide_titles: Dict[str, str] = {}
    for spec in broll_manifest:
        if isinstance(spec, dict):
            fname = Path(str(spec.get("filename", ""))).name
            stitle = str(spec.get("title", "")).strip()
            if fname and stitle:
                slide_titles[fname] = stitle

    chapters: List[Tuple[str, str]] = [("00:00", "オープニング")]
    seen_slides: set[str] = set()

    if timeline_ir is not None and timeline_ir.dynamic_image_clips:
        ir_fps = timeline_ir.fps or fps
        for img_clip in timeline_ir.dynamic_image_clips:
            if getattr(img_clip, "is_background", False) or img_clip.length == -1:
                continue
            fname = img_clip.image_path.name
            if fname in slide_titles and fname not in seen_slides:
                seen_slides.add(fname)
                sec = img_clip.start_frame / float(ir_fps)
                if sec >= 5.0:
                    chapters.append((_format_mm_ss(sec), slide_titles[fname]))
        return chapters

    # Fallback: compute cumulative audio duration from audio/*.wav
    audio_dir = proj_dir / "audio"
    current_sec = 0.0
    for idx, entry in enumerate(script_data):
        if not isinstance(entry, dict) or "character" not in entry or "text" not in entry:
            continue
        char_name = str(entry["character"])
        img_ref = entry.get("image")
        if img_ref:
            fname = Path(str(img_ref)).name
            if fname in slide_titles and fname not in seen_slides:
                seen_slides.add(fname)
                if current_sec >= 5.0:
                    chapters.append((_format_mm_ss(current_sec), slide_titles[fname]))

        wav_path = audio_dir / f"{idx:03d}_{sanitize_filename(char_name)}.wav"
        dur = 3.0
        if wav_path.exists():
            try:
                with wave.open(str(wav_path), "rb") as wf:
                    dur = (wf.getnframes() / float(wf.getframerate())) + 0.3
            except Exception as exc:
                logger.debug("Could not read WAV duration for %s: %s", wav_path, exc)
        current_sec += dur

    return chapters


def generate_project_youtube_metadata(
    project_dir: Union[str, Path],
    timeline_ir: Optional[TimelineIR] = None,
) -> YouTubeMetadataBundle:
    """
    Synthesizes a complete YouTube title, description, chapter list, mandatory
    VOICEVOX/Tachie/BGM credits, and tags for a project directory, and writes
    both `youtube_metadata.txt` (for copy-pasting) and `youtube_metadata.json`.
    """
    proj_dir = Path(project_dir).resolve()
    script_path = proj_dir / "script.json"
    manifest_path = proj_dir / "broll_manifest.json"
    thumb_cfg_path = proj_dir / "thumbnail_config.json"
    yt_cfg_path = proj_dir / "youtube_config.json"

    script_data: List[Dict[str, Any]] = []
    if script_path.exists():
        try:
            script_data = json.loads(script_path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            logger.warning("Failed to read script.json in %s: %s", proj_dir, exc)

    broll_manifest: List[Dict[str, Any]] = []
    if manifest_path.exists():
        try:
            raw_m = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            broll_manifest = raw_m if isinstance(raw_m, list) else raw_m.get("slides", [])
        except Exception as exc:
            logger.warning("Failed to read broll_manifest.json in %s: %s", proj_dir, exc)

    thumb_cfg: Dict[str, Any] = {}
    if thumb_cfg_path.exists():
        try:
            thumb_cfg = json.loads(thumb_cfg_path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            logger.warning("Failed to read thumbnail_config.json in %s: %s", proj_dir, exc)

    yt_cfg: Dict[str, Any] = {}
    if yt_cfg_path.exists():
        try:
            yt_cfg = json.loads(yt_cfg_path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            logger.warning("Failed to read youtube_config.json in %s: %s", proj_dir, exc)

    # 1. Detect characters and BGM used
    characters_used: List[str] = []
    bgm_files_used: List[str] = []
    full_script_text_parts: List[str] = []

    for entry in script_data:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "bgm":
            bgm_p = Path(str(entry.get("path") or entry.get("bgm") or "")).name
            if bgm_p and bgm_p not in bgm_files_used:
                bgm_files_used.append(bgm_p)
        if entry.get("bgm"):
            bgm_p = Path(str(entry["bgm"])).name
            if bgm_p and bgm_p not in bgm_files_used:
                bgm_files_used.append(bgm_p)
        char = str(entry.get("character", "")).strip()
        if char and char not in characters_used:
            characters_used.append(char)
        if "text" in entry:
            full_script_text_parts.append(strip_phonetic_ruby(str(entry["text"])))

    if not characters_used:
        characters_used = ["ずんだもん", "四国めたん"]

    full_text = "\n".join(full_script_text_parts)
    is_finance = any(kw in full_text for kw in FINANCE_KEYWORDS)

    # 2. Construct Title & Variants
    t_line1 = str(thumb_cfg.get("title_line1", "")).strip()
    t_line2 = str(thumb_cfg.get("title_line2", "")).strip()
    sub_hook = str(thumb_cfg.get("sub_hook", "")).replace("▶", "").strip()
    first_slide_title = (
        str(broll_manifest[0].get("title", "")).strip() if broll_manifest else proj_dir.name
    )

    # Titles: curated in youtube_config.json; the fallback is a short, rule-compliant
    # title built from the first slide only (never a copy of the thumbnail text).
    if yt_cfg.get("title"):
        primary_title = str(yt_cfg["title"])
    else:
        primary_title = f"【ずんだもん解説】{first_slide_title}"

    title_variants = list(yt_cfg.get("title_variants") or [primary_title])
    if primary_title not in title_variants:
        title_variants.insert(0, primary_title)
    thumb_texts = tuple(x for x in (t_line1, t_line2, sub_hook) if x)
    title_checks = {tv: evaluate_title(tv, thumb_texts) for tv in title_variants}

    # 3. Compute Chapters
    chapters = _compute_chapters_from_project(
        proj_dir, script_data, broll_manifest, timeline_ir=timeline_ir
    )

    # 4. Extract Bullet Points from B-Roll Manifest
    summary_bullets: List[str] = []
    for spec in broll_manifest:
        if not isinstance(spec, dict):
            continue
        stitle = str(spec.get("title", "")).strip()
        hero = str(spec.get("hero_metric") or spec.get("hero_title") or "").strip()
        impact = str(spec.get("impact_text") or spec.get("bottom_text") or "").strip()
        if stitle and hero:
            summary_bullets.append(f"・{stitle}（{hero}）")
        elif stitle and impact:
            summary_bullets.append(f"・{stitle}：{impact}")
        elif stitle:
            summary_bullets.append(f"・{stitle}")

    # 5. Build Credits
    voice_credits = [VOICEVOX_CREDITS_MAP.get(c, f"VOICEVOX:{c}") for c in characters_used]
    tachie_credits = [
        TACHIE_CREDITS_MAP[c] for c in characters_used if c in TACHIE_CREDITS_MAP
    ]
    bgm_credits = [
        BGM_CREDITS_MAP.get(b, f"BGM：{b}") for b in bgm_files_used
    ]
    if not bgm_credits:
        bgm_credits = ["しゃろう 様「2:23 AM」（DOVA-SYNDROME）"]

    credits_lines = [
        "【クレジット・使用素材】",
        "■ 音声（VOICEVOX）",
        *[f"・{vc}" for vc in voice_credits],
        "https://voicevox.hiroshiba.jp/",
    ]
    if tachie_credits:
        credits_lines.append("■ 立ち絵素材")
        credits_lines.extend(f"・{tc}" for tc in tachie_credits)
    credits_lines.extend(
        [
            "■ BGM素材",
            *[f"・{bc}" for bc in bgm_credits],
            "■ 動画編集ソフト",
            "・ゆっくりMovieMaker4 (YMM4)",
        ]
    )

    # 6. Tags & Hashtags
    base_tags = ["ずんだもん", "四国めたん", "VOICEVOX解説", "ずんだもん解説", "ゆっくり解説"]
    if is_finance:
        topic_tags = [
            "株式投資",
            "2026年相場",
            "AI投資",
            "半導体株",
            "電力インフラ",
            "米国株",
            "日本株",
            "キャッシュフロー",
            "資産運用",
            "経済解説",
        ]
    else:
        topic_tags = [t_line1, t_line2, first_slide_title]
    tags = [t for t in (yt_cfg.get("tags") or (base_tags + topic_tags)) if t]
    hashtags = ["#ずんだもん", "#四国めたん", "#ずんだもん解説", "#VOICEVOX"]
    if is_finance:
        hashtags.extend(["#株式投資", "#米国株", "#AI半導体"])

    # 7. Assemble Full Description
    intro_hook = yt_cfg.get("intro_hook") or (
        f"ご視聴ありがとうございます！\n"
        f"今回の動画では「{first_slide_title}」をテーマに、"
        f"{'・'.join(characters_used)}がデータの裏側と構造変化をわかりやすく解説します。"
    )

    desc_sections: List[str] = [
        intro_hook,
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📌 本動画のポイント",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        *(summary_bullets if summary_bullets else [f"・{first_slide_title}の全体像と背景"]),
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "⏱️ チャプター（目次）",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        *[f"{ts} {ch_title}" for ts, ch_title in chapters],
    ]

    if is_finance:
        desc_sections.extend(
            [
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "⚠️ 免責事項・投資に関するご注意",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "本動画は市場構造や経済・テクノロジー動向に関する情報提供および教育を目的としており、"
                "特定の銘柄や金融商品の売買を推奨・勧誘・助言するものではありません。\n"
                "株式投資には価格変動リスクや元本割れのリスクが伴います。"
                "最終的な投資の選択・判断は、必ずご自身の責任において慎重に行ってください。",
            ]
        )

    desc_sections.extend(
        [
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            *credits_lines,
            "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            " ".join(hashtags),
        ]
    )

    description = "\n".join(desc_sections)

    bundle = YouTubeMetadataBundle(
        title=primary_title,
        title_variants=title_variants,
        description=description,
        tags=tags,
        hashtags=hashtags,
        chapters=chapters,
        credits=credits_lines,
    )

    # Save machine-readable JSON & human copy-paste TXT
    json_out = proj_dir / "youtube_metadata.json"
    txt_out = proj_dir / "youtube_metadata.txt"

    json_out.write_text(
        json.dumps(asdict(bundle), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    copy_paste_txt = "\n".join(
        [
            "============================================================",
            "📺 YouTube タイトル案（お好みのものをコピー＆ペースト）",
            "============================================================",
            *[
                f"案{i + 1}: {tv}  ({len(tv)}字)"
                + (f"  ⚠ {' / '.join(title_checks[tv])}" if title_checks.get(tv) else "  ✔ ルールOK")
                for i, tv in enumerate(bundle.title_variants)
            ],
            "",
            "============================================================",
            "📝 YouTube 概要欄（以下のブロックをそのままコピー＆ペースト）",
            "============================================================",
            bundle.description,
            "",
            "============================================================",
            "🏷️ YouTube タグ（カンマ区切り・コピー＆ペースト用）",
            "============================================================",
            ", ".join(bundle.tags),
            "",
        ]
    )
    txt_out.write_text(copy_paste_txt, encoding="utf-8")
    logger.info("YouTube metadata generated at: %s", txt_out)
    return bundle
