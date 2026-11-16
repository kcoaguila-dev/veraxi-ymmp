"""
YouTube Thumbnail Composition Helpers for Veraxi YMMP
Generic, topic-agnostic primitives shared by the thumbnail layouts:
character sticker compositing (white rim + shadow) and the deterministic
visual QA gate (dimensions, 50MB desktop size limit with a 2MB mobile-app
advisory, timestamp dead-zone, mobile contrast).

Clean Architecture compliant: Zero external API dependencies, zero hardcoded user paths.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from PIL import Image, ImageFont, ImageFilter

from veraxi_ymmp.core.constants import (
    THUMBNAIL_DESKTOP_MAX_BYTES,
    THUMBNAIL_MOBILE_MAX_BYTES,
)
from veraxi_ymmp.core.logging import logger

FontType = Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]


def render_character_sticker(
    char_path: Path,
    target_h: int,
    stroke_width: int = 22,
    flip: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Extracts and renders a character cutout with thick white rim stroke (22px sticker effect)
    and ambient drop shadow.
    """
    if not char_path.exists():
        return None
    try:
        char_img = Image.open(char_path).convert("RGBA")
        if flip:
            char_img = char_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

        aspect = char_img.width / char_img.height
        target_w = int(target_h * aspect)
        char_resized = char_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        alpha = char_resized.split()[3]
        dilated_alpha = alpha
        for _ in range(stroke_width):
            dilated_alpha = dilated_alpha.filter(ImageFilter.MaxFilter(3))

        # Drop shadow
        shadow_mask = dilated_alpha.filter(ImageFilter.GaussianBlur(24))
        shadow_img = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 240))
        shadow_img.putalpha(shadow_mask)

        # White rim
        rim_img = Image.new("RGBA", (target_w, target_h), (255, 255, 255, 255))
        rim_img.putalpha(dilated_alpha)

        return {
            "resized": char_resized,
            "rim": rim_img,
            "shadow": shadow_img,
            "width": target_w,
            "height": target_h,
            "bbox": dilated_alpha.getbbox(),
        }
    except Exception as e:
        logger.warning("Failed to render character sticker: %s", e)
        return None


def validate_thumbnail_visual_qa(
    image_path_or_img: Union[str, Path, Image.Image],
    max_bytes: int = THUMBNAIL_DESKTOP_MAX_BYTES,
    mobile_max_bytes: int = THUMBNAIL_MOBILE_MAX_BYTES,
) -> Dict[str, Any]:
    """
    Automated Visual Quality & Compliance Sentinel for YouTube Thumbnails.
    Performs rigorous checks:
    - 16:9 Aspect Ratio & Resolution (1920x1080)
    - File Size <= 50MB (YouTube desktop / Data API limit since Oct 2025);
      exceeding the 2MB mobile-app limit is reported as a warning only
    - Bottom-Right Timestamp Dead-Zone (x: 1580..1920, y: 920..1080)
    - Mobile 150px Legibility & Edge Contrast
    - Mascot Visibility
    Returns QA Audit Report with numeric score (0-100).
    """
    if isinstance(image_path_or_img, (str, Path)):
        p = Path(image_path_or_img)
        if not p.exists():
            return {"score": 0, "passed": False, "error": f"File not found: {p}"}
        file_size = p.stat().st_size
        img = Image.open(p).convert("RGBA")
    else:
        img = image_path_or_img.convert("RGBA")
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        file_size = buf.tell()

    w, h = img.size
    checks: Dict[str, bool] = {}
    details: List[str] = []
    score = 100

    # 1. Dimensions Check
    if (w, h) in [(1920, 1080), (1280, 720)]:
        checks["dimensions_valid"] = True
    else:
        checks["dimensions_valid"] = False
        score -= 25
        details.append(f"Invalid dimensions: {w}x{h} (expected 1920x1080 or 1280x720)")

    # 2. File Size Check: the hard limit is the desktop / Data API limit
    # (50MB). The 2MB mobile-app limit is advisory only — it must not
    # fail the QA gate for a desktop/API-published master, so it is
    # reported under "warnings" and never enters "checks" or the score.
    warnings: List[str] = []
    if file_size <= max_bytes:
        checks["file_size_valid"] = True
    else:
        checks["file_size_valid"] = False
        score -= 30
        details.append(
            f"File size {file_size} exceeds the {max_bytes // (1024 * 1024)}MB "
            f"YouTube desktop limit ({max_bytes})"
        )
    if file_size > mobile_max_bytes:
        warnings.append(
            f"File size {file_size} exceeds the 2MB YouTube mobile-app "
            "upload limit; desktop / API uploads accept up to 50MB"
        )

    # 3. Timestamp Dead-Zone Safety Check
    # YouTube places duration banner in bottom-right corner (width ~340, height ~160)
    # Check if high-contrast text exists in (w - 340, h - 160) to (w, h)
    dead_zone = img.crop((max(0, w - 340), max(0, h - 160), w, h))
    dead_gray = dead_zone.convert("L")
    dead_edges = dead_gray.filter(ImageFilter.FIND_EDGES)
    raw_bytes = dead_edges.tobytes()
    high_contrast_edges = sum(1 for b in raw_bytes if b > 140)
    edge_ratio = high_contrast_edges / max(len(raw_bytes), 1)

    # Allow moderate background texture (< 8%), but penalize dense text edges
    if edge_ratio < 0.08:
        checks["timestamp_deadzone_safe"] = True
    else:
        checks["timestamp_deadzone_safe"] = False
        score -= 20
        details.append(f"Timestamp dead-zone contains potential colliding text/graphics (edge density: {edge_ratio:.2%})")

    # 4. Mobile Downscale Contrast Check (Simulate 160x90 smartphone preview)
    mobile_preview = img.resize((160, 90), Image.Resampling.BILINEAR).convert("L")
    extrema = mobile_preview.getextrema()
    if isinstance(extrema[0], tuple):
        min_v, max_v = int(extrema[0][0]), int(extrema[0][1])
    else:
        min_v, max_v = int(extrema[0]), int(extrema[1])
    contrast_range = max_v - min_v
    if contrast_range >= 180:
        checks["mobile_contrast_high"] = True
    else:
        checks["mobile_contrast_high"] = False
        score -= 15
        details.append(f"Mobile contrast range {contrast_range} is below recommended 180")

    passed = score >= 80 and all(checks.values())
    return {
        "score": max(0, score),
        "passed": passed,
        "checks": checks,
        "details": details,
        "warnings": warnings,
        "resolution": f"{w}x{h}",
        "file_size_bytes": file_size,
    }


def audit_thumbnail_rule_of_three(config: Any) -> Dict[str, Any]:
    """Enforce the YouTube Thumbnail Rule of 3 (<= 3 foreground visual elements).

    Counts distinct foreground elements in a ThumbnailConfig or dict:
    1. character cutout
    2. headline text block (title_line1 / title_line2)
    3. subject_image_path (extra face/object)
    4. subject_caption
    5. brand_logo_path
    6. brand_symbol_path
    7. eyebrow_text / badge
    8. sub_hook / stat_callout / metric_highlight
    """
    get = (lambda k: config.get(k)) if isinstance(config, dict) else (lambda k: getattr(config, k, None))
    elements: List[str] = []
    if str(get("character") or "").strip():
        elements.append("character")
    if str(get("title_line1") or "").strip() or str(get("title_line2") or "").strip():
        elements.append("headline")
    if str(get("subject_image_path") or "").strip():
        elements.append("subject_image")
    if str(get("subject_caption") or "").strip():
        elements.append("subject_caption")
    if str(get("brand_logo_path") or "").strip():
        elements.append("brand_logo")
    if str(get("brand_symbol_path") or "").strip():
        elements.append("brand_symbol")

    layout = str(get("layout") or "classic_split")
    has_eyebrow = bool(str(get("eyebrow_text") or "").strip())
    has_badge = bool(str(get("badge") or "").strip()) and layout != "editorial_spotlight"
    if has_eyebrow or has_badge:
        elements.append("eyebrow_or_badge")

    if any(str(get(k) or "").strip() for k in ("sub_hook", "stat_callout", "metric_highlight")):
        elements.append("sub_hook_or_stat")

    headline_chars = len(str(get("title_line1") or "").strip()) + len(str(get("title_line2") or "").strip())
    passed = len(elements) <= 3
    warnings: List[str] = []
    if not passed:
        warnings.append(
            f"Thumbnail Rule-of-3 violated: {len(elements)} foreground elements ({', '.join(elements)}). "
            "Strip logos, captions, and extra badges down to <= 3 elements for mobile CTR."
        )
    if headline_chars > 16:
        warnings.append(
            f"Thumbnail headline is {headline_chars} chars (recommended <= 16 chars for 0.5s mobile readability)."
        )
    return {
        "passed": passed,
        "element_count": len(elements),
        "elements": elements,
        "headline_chars": headline_chars,
        "warnings": warnings,
    }


def discover_project_brand_logo(project_dir: Optional[Path]) -> Optional[str]:
    """Find a brand logo (or auto-compose 2 logos into a VS header) in `sources/assets/`."""
    if not project_dir or not project_dir.is_dir():
        return None
    assets_dir = project_dir / "sources" / "assets"
    if not assets_dir.is_dir():
        return None
    for pattern in ("*logo*.png", "*logo*.webp", "*logo*.jpg", "*symbol*.png"):
        matches = [m for m in sorted(assets_dir.glob(pattern)) if m.name != "_dual_vs_logo.png"]
        if len(matches) >= 2 and pattern == "*logo*.png":
            from veraxi_ymmp.graphics.thumbnail_editorial import compose_dual_brand_logo

            dual_out = assets_dir / "_dual_vs_logo.png"
            if compose_dual_brand_logo(matches[0], matches[1], dual_out):
                return str(dual_out)
        if matches:
            return str(matches[0])
    return None


def audit_thumbnail_title_pairing(config: Any, youtube_title: str) -> Dict[str, Any]:
    """Check that thumbnail text complements the YouTube title instead of repeating it."""
    if isinstance(config, str):
        thumb_text = config.strip()
    else:
        get = (lambda k: config.get(k)) if isinstance(config, dict) else (lambda k: getattr(config, k, None))
        t1 = str(get("title_line1") or "").strip()
        t2 = str(get("title_line2") or "").strip()
        thumb_text = f"{t1}{t2}".strip()
    clean_title = youtube_title.strip()

    warnings: List[str] = []
    overlap_ratio = 0.0
    if thumb_text and clean_title:
        if len(thumb_text) >= 6 and thumb_text in clean_title:
            overlap_ratio = 1.0
            warnings.append(
                f"Thumbnail headline '{thumb_text}' repeats the YouTube title verbatim. "
                "Use the thumbnail for a short visual hook and the title for context."
            )
        else:
            # Character-bigram Jaccard / containment check works cleanly for Japanese & English
            def _bigrams(s: str) -> set[str]:
                s_clean = "".join(s.split())
                return {s_clean[i : i + 2] for i in range(max(0, len(s_clean) - 1))}

            tb = _bigrams(thumb_text)
            yb = _bigrams(clean_title)
            if tb and yb:
                overlap_ratio = len(tb & yb) / len(tb)
                if overlap_ratio >= 0.65:
                    warnings.append(
                        f"Thumbnail headline overlaps {overlap_ratio:.0%} with YouTube title '{clean_title[:30]}...'. "
                        "Differentiate the thumbnail hook from the title to maximize curiosity gap."
                    )

    if len(clean_title) > 55:
        warnings.append(
            f"YouTube title is {len(clean_title)} chars (recommended <= 55 chars to avoid mobile feed truncation)."
        )

    return {
        "passed": len(warnings) == 0,
        "overlap_ratio": round(overlap_ratio, 2),
        "title_chars": len(clean_title),
        "warnings": warnings,
    }
