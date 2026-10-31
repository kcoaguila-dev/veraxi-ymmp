"""
Official Data and Image Standardization Engine for veraxi_ymmp.

Provides a unified, Clean Architecture-compliant foundation for incorporating
authoritative official data, benchmarks, documentation excerpts, and official brand
assets/diagrams into video production pipelines.

Standards & Guardrails:
- Pro Dark Slate Theme (#0F172A / #1E293B)
- Presenter-safe zone compliance (X: 1350..1920 preserved in landscape)
- Subtitle-safe zone compliance (Y >= 780 preserved in landscape)
- 1-Slide-1-Impact low cognitive load (<= 100 characters total across slide)
- Zero duplicate code: reuses base typography and canvas rendering from broll.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from PIL import Image, ImageDraw

from .logging import logger
from .broll import (
    COLOR_BORDER,
    COLOR_CANVAS,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    ACCENT_BLUE,
    _fit_font,
    _load_broll_font,
    check_cognitive_load,
    create_slide_base,
    get_pill_text_color,
    resolve_color,
)

OFFICIAL_ASSETS_DIR = Path("assets/official")


@dataclass(frozen=True)
class OfficialSourceCitation:
    """Standardized schema for official source attribution."""

    source_name: str
    source_url: Optional[str] = None
    published_date: Optional[str] = None
    verification_badge: str = "公式発表"

    def format_citation(self) -> str:
        parts = [f"出典: {self.source_name}"]
        if self.published_date:
            parts.append(self.published_date)
        return " | ".join(parts)


def _coerce_citation(val: Union[str, OfficialSourceCitation, Dict[str, Any], None]) -> OfficialSourceCitation:
    """Coerce various inputs into an OfficialSourceCitation instance."""
    if isinstance(val, OfficialSourceCitation):
        return val
    if isinstance(val, dict):
        return OfficialSourceCitation(
            source_name=str(val.get("source_name", val.get("name", "公式ドキュメント"))),
            source_url=val.get("source_url") or val.get("url"),
            published_date=val.get("published_date") or val.get("date"),
            verification_badge=str(val.get("verification_badge", val.get("badge", "公式発表"))),
        )
    if isinstance(val, str) and val.strip():
        s = val.strip()
        if s.startswith("出典:"):
            s = s[3:].strip()
        return OfficialSourceCitation(source_name=s)
    return OfficialSourceCitation(source_name="公式ドキュメント")


class OfficialAssetRegistry:
    """
    Registry and resolver for official tech brand graphics, diagrams, and benchmark charts.
    Can resolve local files or procedurally synthesize high-res brand badges offline.
    """

    _custom_registry: Dict[str, Path] = {}

    @classmethod
    def register(cls, name: str, path: Union[str, Path]) -> None:
        cls._custom_registry[name.lower()] = Path(path).resolve()

    @classmethod
    def resolve_asset(
        cls,
        name_or_path: Union[str, Path],
        base_dir: Optional[Path] = None,
    ) -> Path:
        """
        Resolves an asset name or path:
        1. Checks base_dir (e.g. project root or broll/ folder)
        2. Checks direct path
        3. Checks registered custom assets
        4. Checks assets/official/ and assets/
        5. Procedurally synthesizes official presets ('php', 'cve', 'w3techs', 'laravel', 'mysql', 'architecture')
        """
        raw_str = str(name_or_path).strip()
        normalized_name = raw_str.removeprefix("official:").lower()

        # 1. Base dir candidates
        if base_dir:
            cand1 = base_dir / raw_str
            if cand1.is_file():
                return cand1
            cand2 = base_dir / "broll" / raw_str
            if cand2.is_file():
                return cand2

        # 2. Direct path
        p = Path(raw_str)
        if p.is_file():
            return p

        # 3. Custom registry
        if normalized_name in cls._custom_registry:
            cand = cls._custom_registry[normalized_name]
            if cand.is_file():
                return cand

        # 4. Standard assets directories
        official_cand = OFFICIAL_ASSETS_DIR / raw_str
        if official_cand.is_file():
            return official_cand
        official_png = OFFICIAL_ASSETS_DIR / f"{normalized_name}.png"
        if official_png.is_file():
            return official_png

        general_cand = Path("assets") / raw_str
        if general_cand.is_file():
            return general_cand

        # 5. Procedural generation of known official presets
        OFFICIAL_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        if normalized_name in ("php", "php_logo", "php8"):
            target = OFFICIAL_ASSETS_DIR / "php.png"
            cls.generate_php_brand_badge(target, width=1200, height=580)
            return target
        elif normalized_name in ("cve", "cve_alert", "security", "php2shell"):
            target = OFFICIAL_ASSETS_DIR / "cve_alert.png"
            cls.generate_cve_shield_badge(out_path=target, width=1200, height=580)
            return target
        elif normalized_name in ("w3techs", "market_share", "survey"):
            target = OFFICIAL_ASSETS_DIR / "w3techs_survey.png"
            cls.generate_w3techs_stat_graphic(out_path=target, width=1200, height=580)
            return target
        elif normalized_name in ("architecture", "php_fpm", "stack"):
            target = OFFICIAL_ASSETS_DIR / "modern_web_architecture.png"
            cls.generate_architecture_diagram(out_path=target, width=1200, height=580)
            return target

        # 6. Fallback placeholder
        fallback_path = OFFICIAL_ASSETS_DIR / "placeholder.png"
        if not fallback_path.is_file():
            cls._generate_placeholder(fallback_path, raw_str)
        return fallback_path

    @staticmethod
    def _generate_placeholder(out_path: Path, label: str) -> Path:
        img = Image.new("RGBA", (800, 450), COLOR_SURFACE)
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([10, 10, 790, 440], radius=16, outline=COLOR_BORDER, width=2)
        font = _load_broll_font(32, bold=True)
        draw.text((400, 225), f"OFFICIAL ASSET: {label}", font=font, fill=COLOR_TEXT_SECONDARY, anchor="mm")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)
        return out_path

    @staticmethod
    def generate_php_brand_badge(
        out_path: Optional[Path] = None,
        width: int = 800,
        height: int = 450,
    ) -> Image.Image:
        """
        Synthesizes an official, ultra-crisp PHP 8.4 brand insignia card.
        Uses official PHP brand palette (#4F5D95, #8892BF).
        """
        w, h = width, height
        img = Image.new("RGBA", (w, h), (18, 24, 40, 255))
        draw = ImageDraw.Draw(img)

        # Background subtle tech grid / border
        draw.rounded_rectangle([12, 12, w - 12, h - 12], radius=20, fill=(24, 32, 54, 255), outline=(79, 93, 149, 180), width=3)

        # Header official pill
        f_pill = _load_broll_font(int(18 * h / 450), bold=True)
        pill_h = int(40 * h / 450)
        txt1 = "OFFICIAL LANGUAGE"
        w1 = draw.textlength(txt1, font=f_pill) + 32
        draw.rounded_rectangle([36, 32, 36 + w1, 32 + pill_h], radius=10, fill=(79, 93, 149, 220))
        draw.text((36 + w1 / 2, 32 + pill_h / 2), txt1, font=f_pill, fill=(255, 255, 255, 255), anchor="mm")

        # Top Right Version Pill
        txt2 = "PHP 8.4 READY"
        w2 = draw.textlength(txt2, font=f_pill) + 32
        draw.rounded_rectangle([w - 36 - w2, 32, w - 36, 32 + pill_h], radius=10, fill=(30, 41, 59, 255), outline=(136, 146, 191, 200), width=2)
        draw.text((w - 36 - w2 / 2, 32 + pill_h / 2), txt2, font=f_pill, fill=(136, 146, 191, 255), anchor="mm")

        # Iconic Official PHP Oval Badge
        cx, cy = w // 2, int(h * 0.55)
        oval_rx, oval_ry = int(w * 0.35), int(h * 0.28)
        draw.ellipse([cx - oval_rx, cy - oval_ry, cx + oval_rx, cy + oval_ry], fill=(79, 93, 149, 255), outline=(136, 146, 191, 255), width=6)

        # Stylized Bold PHP Wordmark
        f_php = _load_broll_font(int(135 * h / 450), bold=True)
        draw.text((cx, cy - 8), "php", font=f_php, fill=(255, 255, 255, 255), anchor="mm")

        if out_path:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(out_path)
        return img

    @staticmethod
    def generate_cve_shield_badge(
        cve_id: str = "CVE-2024-4577",
        severity: str = "CRITICAL 9.8",
        out_path: Optional[Path] = None,
        width: int = 800,
        height: int = 450,
    ) -> Image.Image:
        """Synthesizes an authoritative CVE Security Advisory card."""
        w, h = width, height
        img = Image.new("RGBA", (w, h), (26, 15, 20, 255))
        draw = ImageDraw.Draw(img)

        # Outer Alert Frame
        draw.rounded_rectangle([12, 12, w - 12, h - 12], radius=20, fill=(35, 18, 24, 255), outline=(220, 38, 38, 200), width=3)

        # Header Security Pill
        f_head = _load_broll_font(int(20 * h / 450), bold=True)
        pill_h = int(40 * h / 450)
        cve_head_txt = "SECURITY ADVISORY"
        head_w = draw.textlength(cve_head_txt, font=f_head) + 32
        draw.rounded_rectangle([36, 32, 36 + head_w, 32 + pill_h], radius=10, fill=(220, 38, 38, 255))
        draw.text((36 + head_w / 2, 32 + pill_h / 2), cve_head_txt, font=f_head, fill=(255, 255, 255, 255), anchor="mm")

        # Severity Pill
        f_sev = _load_broll_font(int(20 * h / 450), bold=True)
        sev_w = draw.textlength(severity, font=f_sev) + 32
        draw.rounded_rectangle([w - 36 - sev_w, 32, w - 36, 32 + pill_h], radius=10, fill=(153, 27, 27, 255), outline=(248, 113, 113, 255), width=2)
        draw.text((w - 36 - sev_w / 2, 32 + pill_h / 2), severity, font=f_sev, fill=(254, 202, 202, 255), anchor="mm")

        # Shield Contour Icon & Headline
        f_cve = _load_broll_font(int(70 * h / 450), bold=True)
        draw.text((w // 2, int(h * 0.44)), cve_id, font=f_cve, fill=(248, 113, 113, 255), anchor="mm")

        f_desc = _load_broll_font(int(30 * h / 450), bold=True)
        draw.text((w // 2, int(h * 0.62)), "Remote Code Execution (RCE)", font=f_desc, fill=(248, 250, 252, 255), anchor="mm")

        # Subtext / Impact
        f_sub = _load_broll_font(int(22 * h / 450), bold=False)
        draw.text((w // 2, int(h * 0.74)), "NVD / NIST National Vulnerability Database Verified", font=f_sub, fill=(203, 213, 225, 255), anchor="mm")

        if out_path:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(out_path)
        return img

    @staticmethod
    def generate_w3techs_stat_graphic(
        metric: str = "77.4%",
        label: str = "Web Technology Market Share",
        out_path: Optional[Path] = None,
        width: int = 800,
        height: int = 450,
    ) -> Image.Image:
        """Synthesizes an official W3Techs market share telemetry graphic."""
        w, h = width, height
        img = Image.new("RGBA", (w, h), COLOR_CANVAS)
        draw = ImageDraw.Draw(img)

        # Border Card
        draw.rounded_rectangle([12, 12, w - 12, h - 12], radius=20, fill=COLOR_SURFACE, outline=COLOR_BORDER, width=2)

        # Top Header
        f_top = _load_broll_font(int(24 * h / 450), bold=True)
        pill_h = int(40 * h / 450)
        draw.rounded_rectangle([40, 36, 300, 36 + pill_h], radius=10, fill=(2, 132, 199, 220))
        draw.text((170, 36 + pill_h / 2), "W3Techs VERIFIED", font=f_top, fill=(255, 255, 255, 255), anchor="mm")

        # Main Hero Metric
        f_hero = _load_broll_font(int(84 * h / 450), bold=True)
        draw.text((180, int(h * 0.42)), metric, font=f_hero, fill=ACCENT_BLUE, anchor="lm")

        f_lbl = _load_broll_font(int(32 * h / 450), bold=True)
        draw.text((185, int(h * 0.58)), label, font=f_lbl, fill=COLOR_TEXT_PRIMARY, anchor="lm")

        # Progress comparison bar
        bar_x1, bar_x2 = 185, w - 60
        bar_y1, bar_y2 = int(h * 0.67), int(h * 0.72)
        draw.rounded_rectangle([bar_x1, bar_y1, bar_x2, bar_y2], radius=8, fill=(15, 23, 42, 255))
        # 77.4% fill
        fill_w = int((bar_x2 - bar_x1) * 0.774)
        draw.rounded_rectangle([bar_x1, bar_y1, bar_x1 + fill_w, bar_y2], radius=8, fill=ACCENT_BLUE)

        if out_path:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(out_path)
        return img

    @staticmethod
    def generate_architecture_diagram(
        out_path: Optional[Path] = None,
        width: int = 800,
        height: int = 450,
    ) -> Image.Image:
        """Synthesizes a modern high-performance Web Architecture flow diagram."""
        w, h = width, height
        img = Image.new("RGBA", (w, h), COLOR_CANVAS)
        draw = ImageDraw.Draw(img)

        draw.rounded_rectangle([12, 12, w - 12, h - 12], radius=20, fill=COLOR_SURFACE, outline=COLOR_BORDER, width=2)

        f_pill = _load_broll_font(int(18 * h / 450), bold=True)
        pill_h = int(40 * h / 450)
        arch_pill_txt = "SYSTEM ARCHITECTURE"
        arch_pill_w = draw.textlength(arch_pill_txt, font=f_pill) + 32
        draw.rounded_rectangle([36, 32, 36 + arch_pill_w, 32 + pill_h], radius=10, fill=(16, 185, 129, 220))
        draw.text((36 + arch_pill_w / 2, 32 + pill_h / 2), arch_pill_txt, font=f_pill, fill=(15, 23, 42, 255), anchor="mm")

        nodes = [
            ("Edge / CDN", "Cloudflare", (56, 189, 248)),
            ("Web Server", "Nginx", (52, 211, 153)),
            ("Application", "PHP-FPM 8.4 (JIT)", (167, 139, 250)),
            ("Database", "MySQL / Redis", (251, 191, 36)),
        ]

        node_w = int(w * 0.215)
        node_h = int(h * 0.54)
        gap = int(w * 0.025)
        total_w = len(nodes) * node_w + (len(nodes) - 1) * gap
        start_x = (w - total_w) // 2
        cy = int(h * 0.56)

        f_title = _load_broll_font(int(18 * h / 450), bold=False)
        f_val = _load_broll_font(int(22 * h / 450), bold=True)

        for i, (layer, name, col) in enumerate(nodes):
            nx = start_x + i * (node_w + gap)
            ny = cy - node_h // 2
            # Node card
            draw.rounded_rectangle([nx, ny, nx + node_w, ny + node_h], radius=14, fill=COLOR_SURFACE_ALT, outline=COLOR_BORDER, width=2)
            draw.rounded_rectangle([nx, ny, nx + node_w, ny + 8], radius=4, fill=col)
            draw.text((nx + node_w // 2, ny + int(node_h * 0.28)), layer, font=f_title, fill=COLOR_TEXT_SECONDARY, anchor="mm")
            # Word-wrapped or scaled name
            f_n = _fit_font(draw, name, f_val, max_width=node_w - 20, base_size=int(22 * h / 450), min_size=14)
            draw.text((nx + node_w // 2, ny + int(node_h * 0.62)), name, font=f_n, fill=COLOR_TEXT_PRIMARY, anchor="mm")

            # Connector arrow
            if i < len(nodes) - 1:
                ax = nx + node_w + gap // 2
                arrow_sz = int(10 * h / 450)
                draw.polygon([(ax - arrow_sz, cy - arrow_sz), (ax + arrow_sz, cy), (ax - arrow_sz, cy + arrow_sz)], fill=COLOR_TEXT_MUTED)

        if out_path:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(out_path)
        return img


def render_official_image_slide(
    out_path: Union[str, Path],
    title: str,
    image_path: Union[str, Path],
    source_citation: Union[str, OfficialSourceCitation, Dict[str, Any]],
    step_tag: str = "公式発表",
    caption: str = "",
    theme_color: Union[str, Tuple[int, int, int]] = "blue",
    is_vertical: bool = False,
    verification_badge: str = "公式発表",
    category_tag: str = "",
    base_dir: Optional[Path] = None,
    layout: str = "hero",
    show_caption: bool = False,
    show_header: bool = True,
    show_citation: bool = True,
) -> Path:
    """
    Renders a standardized B-Roll Presentation Slide featuring an official image,
    diagram, or benchmark chart.

    Supported Layouts:
    - "hero" (Default): Clean, maximum-visibility layout. Eliminates redundant bottom
      caption banners and bulky sub-header bars. Expands the image to fill the maximum
      presentation zone (~610px height, +80% larger than legacy cards) with a discreet
      micro-attribution watermark.
    - "card" (Legacy): 3-tier card layout with explicit citation bar and bottom takeaway banner.

    Safe Zones:
    - Landscape: X: 70..1340 safe zone (leaving X: 1350..1920 clear for character avatar,
      Y >= 780 clear for subtitles).
    - Vertical: Standardized 1080x720 floating mobile presentation card.
    """
    col = resolve_color(theme_color)
    citation = _coerce_citation(source_citation)
    citation_text = citation.format_citation()

    is_hero = (layout == "hero") and not show_caption
    has_caption = bool(caption.strip()) and (show_caption or not is_hero)

    # Elements to count for cognitive load
    displayed_elements = [title, step_tag, category_tag]
    if has_caption:
        displayed_elements.append(caption)
    if show_citation and not is_hero:
        displayed_elements.extend([citation_text, verification_badge])

    check_cognitive_load(
        title,
        displayed_elements,
        max_chars=100,
        max_elements=6,
    )

    img, draw, fonts = create_slide_base(
        title=title if show_header else "",
        step_tag=step_tag if show_header else "",
        category_tag=category_tag if show_header else "",
        theme_color=col,
        is_vertical=is_vertical,
    )

    x1, x2 = (56, 1024) if is_vertical else (70, 1340)

    if is_hero:
        # === HERO / CLEAN IMAGE FOCUS MODE ===
        # Maximizes the visual real estate of the image.
        # No bulky citation bar; no redundant bottom caption banner.
        card_y1 = 136 if (show_header and title) else (36 if not is_vertical else 40)
        card_y2 = 684 if is_vertical else 746
        avail_w = max(50, x2 - x1)
        avail_h = max(50, card_y2 - card_y1)

        pad_x, pad_y = 12, 12
        max_inner_w = avail_w - 2 * pad_x
        max_inner_h = avail_h - 2 * pad_y

        # Resolve and place image
        resolved_img_path = OfficialAssetRegistry.resolve_asset(image_path, base_dir=base_dir)
        try:
            raw_inner = Image.open(resolved_img_path).convert("RGBA")
            img_aspect = raw_inner.width / raw_inner.height
            box_aspect = max_inner_w / max_inner_h

            if img_aspect > box_aspect:
                dest_w = max_inner_w
                dest_h = int(dest_w / img_aspect)
            else:
                dest_h = max_inner_h
                dest_w = int(dest_h * img_aspect)

            resized_inner = raw_inner.resize((dest_w, dest_h), Image.Resampling.LANCZOS)
            paste_x = x1 + pad_x + (max_inner_w - dest_w) // 2
            paste_y = card_y1 + pad_y + (max_inner_h - dest_h) // 2

            # Smooth rounded corners on the hero image
            mask = Image.new("L", (dest_w, dest_h), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle([0, 0, dest_w, dest_h], radius=16, fill=255)

            # Draw outer clean framing around the hero image
            draw.rounded_rectangle(
                [paste_x - 3, paste_y - 3, paste_x + dest_w + 3, paste_y + dest_h + 3],
                radius=18,
                fill=(18, 24, 38, 240),
                outline=COLOR_BORDER,
                width=2,
            )

            img.paste(resized_inner, (paste_x, paste_y), mask)

            # Subtle, discreet micro-attribution watermark at bottom-left of the hero image
            if show_citation and citation_text:
                wm_text = f"出典: {citation.source_name}"
                if citation.published_date:
                    wm_text += f" ({citation.published_date})"
                f_wm = fonts.get("micro") or fonts["small"]
                wm_w = draw.textlength(wm_text, font=f_wm) + 24
                wm_h = 28
                wm_x1 = paste_x + 16
                wm_y1 = paste_y + dest_h - wm_h - 14
                wm_x2 = min(wm_x1 + wm_w, paste_x + dest_w - 16)
                wm_y2 = wm_y1 + wm_h

                draw.rounded_rectangle(
                    [wm_x1, wm_y1, wm_x2, wm_y2],
                    radius=6,
                    fill=(15, 23, 42, 220),
                    outline=(51, 65, 85, 180),
                    width=1,
                )
                draw.text(
                    (wm_x1 + 12, (wm_y1 + wm_y2) / 2),
                    wm_text,
                    font=f_wm,
                    fill=COLOR_TEXT_SECONDARY,
                    anchor="lm",
                )
        except Exception as e:
            logger.warning(f"Failed to place official image {resolved_img_path}: {e}")
            draw.rounded_rectangle(
                [x1, card_y1, x2, card_y2],
                radius=18,
                fill=(18, 24, 38, 220),
                outline=COLOR_BORDER,
                width=2,
            )
            draw.text(
                ((x1 + x2) / 2, (card_y1 + card_y2) / 2),
                f"[画像読み込みエラー: {Path(image_path).name}]",
                font=fonts["body"],
                fill=COLOR_TEXT_MUTED,
                anchor="mm",
            )

    else:
        # === LEGACY 3-TIER CARD LAYOUT ===
        # 1. Official Citation Sub-header Bar (placed right under header)
        cite_y1, cite_y2 = (136, 184) if is_vertical else (134, 182)
        draw.rounded_rectangle([x1, cite_y1, x2, cite_y2], radius=12, fill=COLOR_SURFACE, outline=COLOR_BORDER, width=1)
        draw.rounded_rectangle([x1, cite_y1, x1 + 8, cite_y2], radius=4, fill=col)

        # Verification Badge inside citation bar
        badge_str = f"[{citation.verification_badge or verification_badge}]"
        badge_w = draw.textlength(badge_str, font=fonts["small"]) + 16
        draw.text((x1 + 20, (cite_y1 + cite_y2) / 2), badge_str, font=fonts["small"], fill=col, anchor="lm")

        # Source Text
        cite_font = _fit_font(draw, citation_text, fonts["small"], max_width=x2 - (x1 + 28 + badge_w) - 20, base_size=22, min_size=16)
        draw.text((x1 + 28 + badge_w, (cite_y1 + cite_y2) / 2), citation_text, font=cite_font, fill=COLOR_TEXT_SECONDARY, anchor="lm")

        # 2. Main Framed Card for the Official Image
        card_y1 = cite_y2 + 14
        if has_caption:
            card_y2 = 580 if is_vertical else 550
            cap_y1 = card_y2 + 16
            cap_y2 = 684 if is_vertical else 640
        else:
            card_y2 = 680 if is_vertical else 640

        draw.rounded_rectangle([x1, card_y1, x2, card_y2], radius=18, fill=COLOR_SURFACE, outline=COLOR_BORDER, width=2)

        # Resolve and place image
        resolved_img_path = OfficialAssetRegistry.resolve_asset(image_path, base_dir=base_dir)
        try:
            raw_inner = Image.open(resolved_img_path).convert("RGBA")
            # Target inner bounding box
            pad_x, pad_y = 24, 20
            box_w = max(50, (x2 - x1) - 2 * pad_x)
            box_h = max(50, (card_y2 - card_y1) - 2 * pad_y)

            # Scale maintaining aspect ratio
            img_aspect = raw_inner.width / raw_inner.height
            box_aspect = box_w / box_h

            if img_aspect > box_aspect:
                dest_w = box_w
                dest_h = int(dest_w / img_aspect)
            else:
                dest_h = box_h
                dest_w = int(dest_h * img_aspect)

            resized_inner = raw_inner.resize((dest_w, dest_h), Image.Resampling.LANCZOS)
            paste_x = x1 + pad_x + (box_w - dest_w) // 2
            paste_y = card_y1 + pad_y + (box_h - dest_h) // 2

            img.alpha_composite(resized_inner, (paste_x, paste_y))
        except Exception as e:
            logger.warning(f"Failed to place official image {resolved_img_path}: {e}")
            draw.text(((x1 + x2) / 2, (card_y1 + card_y2) / 2), f"[画像読み込みエラー: {Path(image_path).name}]", font=fonts["body"], fill=COLOR_TEXT_MUTED, anchor="mm")

        # 3. Optional Impact Takeaway Banner
        if has_caption:
            draw.rounded_rectangle([x1, cap_y1, x2, cap_y2], radius=14, fill=COLOR_SURFACE, outline=COLOR_BORDER, width=2)
            draw.rounded_rectangle([x1, cap_y1, x1 + 10, cap_y2], radius=4, fill=col)

            tag = "公式見解"
            tag_w = max(draw.textlength(tag, font=fonts["badge"]) + 36, 120)
            pill_txt_col = get_pill_text_color(col)
            draw.rounded_rectangle([x1 + 20, cap_y1 + 12, x1 + 20 + tag_w, cap_y2 - 12], radius=10, fill=col)
            draw.text((x1 + 20 + tag_w / 2, (cap_y1 + cap_y2) / 2), tag, font=fonts["badge"], fill=pill_txt_col, anchor="mm")

            cap_font = _fit_font(draw, caption, fonts["card_title"], max_width=x2 - (x1 + 36 + tag_w) - 20, base_size=32, min_size=20)
            draw.text((x1 + 36 + tag_w, (cap_y1 + cap_y2) / 2), caption, font=cap_font, fill=COLOR_TEXT_PRIMARY, anchor="lm")

    out_file = Path(out_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_file)
    return out_file


def render_official_data_slide(
    out_path: Union[str, Path],
    title: str,
    hero_metric: str,
    metric_label: str,
    source_citation: Union[str, OfficialSourceCitation, Dict[str, Any]],
    step_tag: str = "公式データ",
    impact_tag: str = "重要性",
    impact_text: str = "",
    verification_badge: str = "VERIFIED",
    theme_color: Union[str, Tuple[int, int, int]] = "blue",
    category_tag: str = "",
    is_vertical: bool = False,
) -> Path:
    """
    Renders an authoritative official statistics/data slide with high-retention layout.
    Features:
    - Dominant hero stat
    - Official verification seal
    - Formal citation footer
    - Clear single takeaway banner
    """
    col = resolve_color(theme_color)
    citation = _coerce_citation(source_citation)
    citation_text = citation.format_citation()

    takeaway_block = f"{impact_tag}: {impact_text}" if impact_tag and impact_text else (impact_text or impact_tag)
    check_cognitive_load(
        title,
        [title, step_tag, category_tag, hero_metric, metric_label, citation_text, takeaway_block],
        max_chars=100,
        max_elements=6,
    )

    img, draw, fonts = create_slide_base(
        title=title,
        step_tag=step_tag,
        category_tag=category_tag,
        theme_color=col,
        is_vertical=is_vertical,
    )

    x1, x2 = (56, 1024) if is_vertical else (70, 1340)
    card_inner_w = float(x2 - x1 - 72)

    # Main Metric Card
    y1, y2 = (144, 490) if is_vertical else (145, 480)
    draw.rounded_rectangle([x1, y1, x2, y2], radius=20, fill=COLOR_SURFACE, outline=COLOR_BORDER, width=2)
    draw.rounded_rectangle([x1, y1, x1 + 12, y2], radius=6, fill=col)

    # Top Verification Badge Pill
    badge_label = f"◆ {citation.verification_badge or verification_badge}"
    badge_w = draw.textlength(badge_label, font=fonts["badge"]) + 36
    draw.rounded_rectangle([x1 + 36, y1 + 22, x1 + 36 + badge_w, y1 + 66], radius=10, fill=COLOR_CANVAS, outline=COLOR_BORDER, width=1)
    draw.text((x1 + 36 + badge_w / 2, y1 + 44), badge_label, font=fonts["badge"], fill=col, anchor="mm")

    # Hero Metric (Giant)
    hero_y = y1 + 145
    f_hero = _fit_font(draw, hero_metric, fonts["hero"], max_width=card_inner_w, base_size=68, min_size=40)
    draw.text((x1 + 36, hero_y), hero_metric, font=f_hero, fill=col, anchor="lm")

    # Metric Label / Context
    lbl_y = hero_y + 78
    f_lbl = _fit_font(draw, metric_label, fonts["card_title_lg"], max_width=card_inner_w, base_size=38, min_size=24)
    draw.text((x1 + 36, lbl_y), metric_label, font=f_lbl, fill=COLOR_TEXT_PRIMARY, anchor="lm")

    # Official Citation Line inside the card
    cite_y = y2 - 40
    f_cite = _fit_font(draw, citation_text, fonts["small"], max_width=card_inner_w, base_size=22, min_size=16)
    draw.text((x1 + 36, cite_y), citation_text, font=f_cite, fill=COLOR_TEXT_SECONDARY, anchor="lm")

    # Bottom Impact Banner
    if impact_text:
        y_top, y_bot = (512, 676) if is_vertical else (510, 645)
        cy = (y_top + y_bot) / 2
        draw.rounded_rectangle([x1, y_top, x2, y_bot], radius=16, fill=COLOR_SURFACE, outline=COLOR_BORDER, width=2)
        draw.rounded_rectangle([x1, y_top, x1 + 10, y_bot], radius=4, fill=col)

        pill_txt_col = get_pill_text_color(col)
        tag_w = max(draw.textlength(impact_tag, font=fonts["badge"]) + 36, 96)
        draw.rounded_rectangle([x1 + 24, y_top + 24, x1 + 24 + tag_w, y_bot - 24], radius=10, fill=col)
        draw.text((x1 + 24 + tag_w / 2, cy), impact_tag, font=fonts["badge"], fill=pill_txt_col, anchor="mm")

        text_x = x1 + 44 + tag_w
        f_imp = _fit_font(draw, impact_text, fonts["card_title"], max_width=x2 - text_x - 24, base_size=32, min_size=20)
        draw.text((text_x, cy), impact_text, font=f_imp, fill=COLOR_TEXT_PRIMARY, anchor="lm")

    out_file = Path(out_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_file)
    return out_file
