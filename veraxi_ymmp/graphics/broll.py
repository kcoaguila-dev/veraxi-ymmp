"""
High-Definition B-Roll Presentation Board Generator (Pro Dark Mode Architecture)
Reusable engine for generating video presentation boards in veraxi_ymmp.

Supports both:
  - 16:9 Landscape Studio Boards (1920x1080, presenter safe zone X: 1350..1920, subtitle safe zone Y >= 780)
  - 9:16 Mobile Vertical Shorts Boards (1080x720 top-zone card with symmetric margins, auto-fitted mobile typography, and rounded floating slate frame)

Design Standards:
  - Deep Navy Slate Theme (#0F172A) reducing eye strain & halation
  - Zero redundant category tags & zero English buzzword clutter
  - 1-Slide-1-Impact Information Architecture (VS comparisons, punchy keyword pills)
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFont

from veraxi_ymmp.core.logging import logger

# Pro Dark Palette
COLOR_CANVAS = (15, 23, 42, 255)          # Slate 900
COLOR_CANVAS_FLOAT = (15, 23, 42, 246)    # Floating Mobile Board Slate 900
COLOR_SURFACE = (30, 41, 59, 255)         # Slate 800
COLOR_SURFACE_ALT = (24, 33, 47, 255)     # Darker Slate
COLOR_BORDER = (51, 65, 85, 255)          # Slate 700
COLOR_TEXT_PRIMARY = (248, 250, 252, 255)  # Slate 50
COLOR_TEXT_SECONDARY = (148, 163, 184, 255)  # Slate 400
COLOR_TEXT_MUTED = (100, 116, 139, 255)   # Slate 500

# High-Visibility Accents for Dark Mode
ACCENT_BLUE = (56, 189, 248)    # Sky 400
ACCENT_GREEN = (52, 211, 153)   # Emerald 400
ACCENT_AMBER = (251, 191, 36)   # Amber 400
ACCENT_RED = (248, 113, 113)    # Red 400
ACCENT_VIOLET = (167, 139, 250)  # Violet 400

# 9:16 Mobile Vertical B-Roll Card Dimensions
VERTICAL_BROLL_WIDTH = 1080
VERTICAL_BROLL_HEIGHT = 720

def _load_broll_font(size: int, bold: bool = True) -> Any:
    """Load BIZ UDP Gothic font at a specific pixel size with fallback."""
    font_file = "BIZ-UDGothicB.ttc" if bold else "BIZ-UDGothicR.ttc"
    for idx in (1, None):
        try:
            return ImageFont.truetype(font_file, size, index=idx) if idx is not None else ImageFont.truetype(font_file, size)
        except Exception:
            pass
    return ImageFont.load_default()

def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    default_font: Any,
    max_width: float,
    base_size: int,
    min_size: int = 22,
    bold: bool = True,
) -> Any:
    """Automatically steps down font size if text width exceeds max_width."""
    if not text or max_width <= 0 or draw.textlength(text, font=default_font) <= max_width:
        return default_font
    sz = base_size - 2
    while sz >= min_size:
        cand = _load_broll_font(sz, bold=bold)
        if draw.textlength(text, font=cand) <= max_width:
            return cand
        sz -= 2
    return _load_broll_font(min_size, bold=bold)

def get_fonts() -> dict:
    """Returns BIZ UDP Gothic Bold fonts with proper proportional kerning."""
    return {
        "hero": _load_broll_font(64), "hero_sub": _load_broll_font(30), "title": _load_broll_font(36),
        "card_title_lg": _load_broll_font(40), "card_title": _load_broll_font(32), "body": _load_broll_font(26),
        "footer": _load_broll_font(30), "badge": _load_broll_font(30), "num": _load_broll_font(34),
        "small": _load_broll_font(26, bold=True),
    }

def get_pill_text_color(pill_bg: Tuple[int, int, int]) -> Tuple[int, int, int, int]:
    """Calculates optimal contrast text color (crisp white or deep navy)."""
    r, g, b = pill_bg[:3]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return (15, 23, 42, 255) if lum > 175 else (255, 255, 255, 255)

def create_slide_base(
    title: str,
    step_tag: str = "",
    category_tag: str = "",
    theme_color: Tuple[int, int, int] = ACCENT_BLUE,
    width: int = 1920,
    height: int = 1080,
    is_vertical: bool = False,
) -> Tuple[Image.Image, ImageDraw.ImageDraw, dict]:
    """
    Creates a Studio Presentation Slide in Pro Dark Slate.
    When is_vertical=True, renders a 1080x720 mobile-optimized floating card
    with symmetric horizontal padding and zero side-cropping.
    """
    fonts = get_fonts()
    if is_vertical:
        width, height = 1080, 720
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Floating mobile presentation board with rounded frame
        draw.rounded_rectangle(
            [28, 12, 1052, 708],
            radius=28,
            fill=COLOR_CANVAS_FLOAT,
            outline=COLOR_BORDER,
            width=3,
        )
        header_bbox = [56, 36, 1024, 124]
        accent_bbox = [56, 36, 72, 124]
        cur_x = 92.0
        header_cy = 80.0
        max_title_x = 1004.0
    else:
        img = Image.new("RGBA", (width, height), COLOR_CANVAS)
        draw = ImageDraw.Draw(img)
        # Subtle horizontal ledger lines for financial / broadcast depth (Y: 60..780)
        for gy in range(60, 780, 56):
            draw.line([(50, gy), (1340, gy)], fill=(22, 32, 50, 255), width=1)
        header_bbox = [60, 24, 1340, 116]
        accent_bbox = [60, 24, 76, 116]
        cur_x = 96.0
        header_cy = 70.0
        max_title_x = 1320.0

    # Studio Top Header Bar
    draw.rounded_rectangle(header_bbox, radius=18, fill=COLOR_SURFACE, outline=COLOR_BORDER, width=2)
    draw.rounded_rectangle(accent_bbox, radius=6, fill=theme_color)

    if category_tag:
        cat_w = draw.textlength(category_tag, font=fonts["badge"]) + 36
        draw.rounded_rectangle(
            [cur_x, header_cy - 28, cur_x + cat_w, header_cy + 28],
            radius=12,
            fill=COLOR_CANVAS,
            outline=COLOR_BORDER,
            width=1,
        )
        draw.text((cur_x + cat_w / 2, header_cy), category_tag, font=fonts["badge"], fill=COLOR_TEXT_PRIMARY, anchor="mm")
        cur_x += cat_w + 14

    if step_tag:
        step_w = draw.textlength(step_tag, font=fonts["badge"]) + 36
        pill_txt_col = get_pill_text_color(theme_color)
        draw.rounded_rectangle([cur_x, header_cy - 32, cur_x + step_w, header_cy + 32], radius=12, fill=theme_color)
        draw.text((cur_x + step_w / 2, header_cy), step_tag, font=fonts["badge"], fill=pill_txt_col, anchor="mm")
        cur_x += step_w + 20
    elif not category_tag:
        cur_x += 10

    title_font = _fit_font(draw, title, fonts["title"], max_width=max_title_x - cur_x, base_size=36, min_size=22)
    draw.text((cur_x, header_cy), title, font=title_font, fill=COLOR_TEXT_PRIMARY, anchor="lm")

    return img, draw, fonts

def get_status_colors(accent_color: Tuple[int, int, int]) -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int], Tuple[int, int, int, int]]:
    """Returns dark container background, outline, and text color for status pills."""
    mapping = {
        ACCENT_RED: ((69, 10, 10, 255), (239, 68, 68, 255), (255, 255, 255, 255)),
        ACCENT_AMBER: ((69, 26, 3, 255), (245, 158, 11, 255), (255, 255, 255, 255)),
        ACCENT_GREEN: ((6, 78, 59, 255), (16, 185, 129, 255), (255, 255, 255, 255)),
        ACCENT_VIOLET: ((59, 7, 100, 255), (139, 92, 246, 255), (255, 255, 255, 255)),
    }
    return mapping.get(accent_color, ((12, 74, 110, 255), (14, 165, 233, 255), (255, 255, 255, 255)))

# Cognitive Load Safety Ceiling for 4-6 second YouTube Cuts
MAX_SLIDE_CHARS = 100
MAX_SLIDE_ELEMENTS = 6

def check_cognitive_load(
    slide_title: str,
    text_elements: List[str],
    max_chars: int = MAX_SLIDE_CHARS,
    max_elements: int = MAX_SLIDE_ELEMENTS,
) -> None:
    """
    Systematic Cognitive Load & Text Density Check.
    Enforces the '1-Slide-1-Impact' rule for video presentation boards.
    """
    clean_texts = [str(t).strip() for t in text_elements if t and str(t).strip()]
    total_chars = sum(len(t) for t in clean_texts)

    if len(clean_texts) > max_elements:
        raise ValueError(
            f"Cognitive Overload Violation on slide '{slide_title}': "
            f"Contains {len(clean_texts)} discrete text blocks (max {max_elements} allowed).\nElements: {clean_texts}"
        )
    if total_chars > max_chars:
        raise ValueError(
            f"Cognitive Overload Violation on slide '{slide_title}': "
            f"Total text length ({total_chars} chars) exceeds the safe limit of {max_chars} chars.\nElements: {clean_texts}"
        )
    for t in clean_texts:
        if re.search(r"(\d+[億万千兆]?|\d+)\$", t):
            raise ValueError(f"Currency Syntax Violation on slide '{slide_title}': Invalid trailing dollar sign in '{t}'. Use '2200億ドル' or '$220B'.")
        if any(slop in t for slop in ["3つのポイント", "３つのポイント", "3大視点", "３大視点", "3大潮流", "３大潮流", "3大原則", "本日のポイント"]):
            raise ValueError(f"AI Slop Violation on slide '{slide_title}': Generic presentation boilerplate detected in '{t}'.")

def render_clash_slide(
    out_path: Union[str, Path],
    title: str,
    step_tag: str,
    hero_metric: str,
    left_entity: Union[Tuple[str, str, Any], Dict[str, Any], str],
    right_entity: Union[Tuple[str, str, Any], Dict[str, Any], str],
    impact_tag: str = "リスク",
    impact_text: str = "",
    theme_color: Tuple[int, int, int] = ACCENT_AMBER,
    is_vertical: bool = False,
) -> None:
    """
    Renders a High-Contrast Dual Combatant Clash Board (Broadcast Studio Tier).
    Replaces generic nested card boxes with dynamic battle podiums & VS contrast.
    """
    def _parse_entity(e: Any, def_col: Tuple[int, int, int]) -> Tuple[str, str, str, Tuple[int, int, int]]:
        if isinstance(e, dict):
            return (
                str(e.get("name") or e.get("title") or ""),
                str(e.get("metric") or e.get("value") or ""),
                str(e.get("sub") or e.get("note") or ""),
                resolve_color(e.get("color") or def_col),
            )
        if isinstance(e, (list, tuple)):
            n = str(e[0]) if len(e) > 0 else ""
            m = str(e[1]) if len(e) > 1 else ""
            s = str(e[2]) if len(e) > 2 and isinstance(e[2], str) else ""
            c = resolve_color(e[-1]) if len(e) >= 3 and not isinstance(e[-1], str) else def_col
            return (n, m, s, c)
        s_val = str(e).strip()
        m_match = re.search(r"^(.+?)([\d,\.]+[億万千兆]?ドル?.*)$", s_val)
        if m_match:
            return (m_match.group(1).strip(), m_match.group(2).strip(), "", def_col)
        return (s_val, "", "", def_col)

    l_name, l_metric, l_sub, l_col = _parse_entity(left_entity, ACCENT_AMBER)
    r_name, r_metric, r_sub, r_col = _parse_entity(right_entity, ACCENT_BLUE)

    check_cognitive_load(
        title,
        [title, step_tag, hero_metric, l_name, l_metric, l_sub, r_name, r_metric, r_sub, impact_tag, impact_text],
        max_chars=MAX_SLIDE_CHARS + 25,
        max_elements=12,
    )

    img, draw, fonts = create_slide_base(title, step_tag=step_tag, theme_color=theme_color, is_vertical=is_vertical)
    x1, x2 = (56, 1024) if is_vertical else (70, 1340)

    # 1. Hero Total Line (Gracefully centered between top bar and clash podiums)
    if hero_metric:
        h_y = 182 if not is_vertical else 166
        f_hero = _fit_font(draw, hero_metric, fonts["hero"], max_width=float(x2 - x1), base_size=52 if not is_vertical else 40, min_size=32)
        draw.text((x1, h_y), hero_metric, font=f_hero, fill=theme_color, anchor="lm")

    # 2. Split Clash Podiums
    mid_y1 = 250 if not is_vertical else 210
    mid_y2 = 520 if not is_vertical else 500
    split_gap = 90 if not is_vertical else 40
    box_w = (x2 - x1 - split_gap) // 2
    left_x1, left_x2 = x1, x1 + box_w
    right_x1, right_x2 = left_x2 + split_gap, x2

    for bx1, bx2, bname, bmetric, bsub, bcol in [
        (left_x1, left_x2, l_name, l_metric, l_sub, l_col),
        (right_x1, right_x2, r_name, r_metric, r_sub, r_col),
    ]:
        draw.rounded_rectangle([bx1, mid_y1, bx2, mid_y2], radius=16, fill=(20, 29, 47, 255), outline=bcol, width=2)
        draw.rounded_rectangle([bx1, mid_y1, bx2, mid_y1 + 8], radius=4, fill=bcol)
        inner_w = float(bx2 - bx1 - 48)

        fn_name = _fit_font(draw, bname, fonts["card_title"], max_width=inner_w, base_size=30, min_size=24)
        draw.text((bx1 + 24, mid_y1 + 42), bname, font=fn_name, fill=bcol, anchor="lm")

        metric_txt = bmetric or bname
        fn_metric = _fit_font(draw, metric_txt, fonts["hero"], max_width=inner_w, base_size=56, min_size=34)
        draw.text((bx1 + 24, mid_y1 + 120), metric_txt, font=fn_metric, fill=COLOR_TEXT_PRIMARY, anchor="lm")

        if bsub:
            fn_sub = _fit_font(draw, bsub, fonts["small"], max_width=inner_w, base_size=26 if not is_vertical else 22, min_size=22 if not is_vertical else 19)
            if draw.textlength(bsub, font=fn_sub) > inner_w and len(bsub) > 16:
                mid = len(bsub) // 2
                split_idx = next((mid + o for o in range(min(5, mid)) if bsub[mid + o] in " ・、/へをの"), mid)
                f_w = _load_broll_font(22 if not is_vertical else 18, bold=True)
                draw.text((bx1 + 26, mid_y1 + 188), bsub[:split_idx].strip(), font=f_w, fill=(226, 232, 240, 255), anchor="lm")
                draw.text((bx1 + 26, mid_y1 + 218), bsub[split_idx:].strip(), font=f_w, fill=(226, 232, 240, 255), anchor="lm")
            else:
                draw.text((bx1 + 26, mid_y1 + 200), bsub, font=fn_sub, fill=(226, 232, 240, 255), anchor="lm")

    # Center VS Badge
    vs_cx = (left_x2 + right_x1) // 2
    vs_cy = (mid_y1 + mid_y2) // 2
    draw.ellipse([vs_cx - 38, vs_cy - 38, vs_cx + 38, vs_cy + 38], fill=(239, 68, 68, 255), outline=(255, 255, 255, 255), width=2)
    draw.text((vs_cx, vs_cy), "VS", font=fonts["card_title"], fill=(255, 255, 255, 255), anchor="mm")

    # 3. Bottom Impact Banner
    if impact_text:
        bot_y1, bot_y2 = (560, 670) if not is_vertical else (525, 680)
        cy = (bot_y1 + bot_y2) // 2
        draw.rounded_rectangle([x1, bot_y1, x2, bot_y2], radius=14, fill=(30, 41, 59, 255), outline=(239, 68, 68, 255), width=2)
        draw.rounded_rectangle([x1, bot_y1, x1 + 10, bot_y2], radius=4, fill=(239, 68, 68, 255))
        if impact_tag:
            tag_w = max(draw.textlength(impact_tag, font=fonts["badge"]) + 32, 90)
            draw.rounded_rectangle([x1 + 24, bot_y1 + 20, x1 + 24 + tag_w, bot_y2 - 20], radius=8, fill=(239, 68, 68, 255))
            draw.text((x1 + 24 + tag_w // 2, cy), impact_tag, font=fonts["badge"], fill=(255, 255, 255, 255), anchor="mm")
            txt_x = x1 + 44 + tag_w
        else:
            txt_x = x1 + 32
        fn_imp = _fit_font(draw, impact_text, fonts["title"], max_width=float(x2 - txt_x - 24), base_size=30, min_size=20)
        draw.text((txt_x, cy), impact_text, font=fn_imp, fill=COLOR_TEXT_PRIMARY, anchor="lm")

    if not is_vertical:
        img.putalpha(255)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    logger.info("Saved: %s", out_path)

def render_metric_slide(
    out_path: Path,
    title: str,
    step_tag: str,
    hero_metric: str,
    status_pill: str,
    takeaways: Optional[List[Tuple[str, str, Tuple[int, int, int]]]] = None,
    impact_tag: str = "影響",
    impact_text: str = "",
    badge_text: str = "",
    theme_color: Tuple[int, int, int] = ACCENT_BLUE,
    category_tag: str = "",
    is_vertical: bool = False,
) -> None:
    """
    Renders a high-retention, low-cognitive-load Metric Slide (2-3 second read):
    - Auto-promotes comparison status pills (with 'vs') to high-contrast Clash Battle Boards.
    - Single metrics render with sleek broadcast glass styling without nested box clutter.
    """
    if re.search(r"\s+[vV][sS]\s+", status_pill):
        parts = re.split(r"\s+[vV][sS]\s+", status_pill, maxsplit=1)
        render_clash_slide(
            out_path=out_path,
            title=title,
            step_tag=step_tag,
            hero_metric=hero_metric,
            left_entity=parts[0],
            right_entity=parts[1],
            impact_tag=impact_tag or "リスク",
            impact_text=impact_text,
            theme_color=theme_color,
            is_vertical=is_vertical,
        )
        return

    check_cognitive_load(
        title,
        [title, step_tag, category_tag, hero_metric, status_pill, impact_tag, impact_text, badge_text],
        max_chars=MAX_SLIDE_CHARS,
        max_elements=MAX_SLIDE_ELEMENTS,
    )
    img, draw, fonts = create_slide_base(
        title,
        step_tag=step_tag,
        category_tag=category_tag,
        theme_color=theme_color,
        is_vertical=is_vertical,
    )
    x1, x2 = (56, 1024) if is_vertical else (70, 1340)
    card_inner_w = float(x2 - x1 - 72)

    # 1. Hero Focus Card (Broadcast Glass Plate)
    y1, y2 = (144, 484) if is_vertical else (150, 475)
    draw.rounded_rectangle([x1, y1, x2, y2], radius=18, fill=(20, 29, 47, 240), outline=COLOR_BORDER, width=2)
    draw.rounded_rectangle([x1, y1, x1 + 10, y2], radius=4, fill=theme_color)

    if badge_text:
        badge_w = draw.textlength(badge_text, font=fonts["badge"]) + 32
        draw.rounded_rectangle(
            [x1 + 36, y1 + 24, x1 + 36 + badge_w, y1 + 68],
            radius=10,
            fill=COLOR_CANVAS,
            outline=COLOR_BORDER,
            width=1,
        )
        draw.text((x1 + 36 + badge_w / 2, y1 + 46), badge_text, font=fonts["badge"], fill=COLOR_TEXT_SECONDARY, anchor="mm")

    metric_y = (y1 + 148 if badge_text else y1 + 118) if is_vertical else (y1 + 145 if badge_text else y1 + 115)
    hero_font = _fit_font(draw, hero_metric, fonts["hero"], max_width=card_inner_w, base_size=64, min_size=36)
    draw.text((x1 + 36, metric_y), hero_metric, font=hero_font, fill=theme_color, anchor="lm")

    pill_base_font = _load_broll_font(34, bold=True) if is_vertical else fonts["hero_sub"]
    pill_font = _fit_font(
        draw,
        status_pill,
        pill_base_font,
        max_width=card_inner_w - 40,
        base_size=34 if is_vertical else 30,
        min_size=22,
    )
    status_w = draw.textlength(status_pill, font=pill_font) + 44
    bg_col, out_col, txt_col = get_status_colors(theme_color)
    pill_y = metric_y + (96 if is_vertical else 88)
    pill_half_h = 34 if is_vertical else 32
    draw.rounded_rectangle(
        [x1 + 36, pill_y - pill_half_h, x1 + 36 + status_w, pill_y + pill_half_h],
        radius=12,
        fill=bg_col,
        outline=out_col,
        width=2,
    )
    draw.text((x1 + 36 + status_w / 2, pill_y), status_pill, font=pill_font, fill=txt_col, anchor="mm")

    # 2. Single Clean Impact Banner
    tag = impact_tag
    text = impact_text
    color = theme_color
    if not text and takeaways and len(takeaways) > 0:
        tag, text, color = takeaways[0]

    if text:
        y_top, y_bot = (508, 676) if is_vertical else (510, 645)
        cy = (y_top + y_bot) / 2
        draw.rounded_rectangle([x1, y_top, x2, y_bot], radius=16, fill=(30, 41, 59, 230), outline=COLOR_BORDER, width=2)
        draw.rounded_rectangle([x1, y_top, x1 + 10, y_bot], radius=4, fill=color)

        base_impact_sz = 36 if is_vertical else 32
        base_impact_font = _load_broll_font(base_impact_sz, bold=True)
        if tag:
            pill_txt_col = get_pill_text_color(color)
            tag_w = max(draw.textlength(tag, font=fonts["badge"]) + 36, 92)
            pill_pad = 42 if is_vertical else 28
            draw.rounded_rectangle([x1 + 28, y_top + pill_pad, x1 + 28 + tag_w, y_bot - pill_pad], radius=10, fill=color)
            draw.text((x1 + 28 + tag_w / 2, cy), tag, font=fonts["badge"], fill=pill_txt_col, anchor="mm")
            text_x = x1 + 48 + tag_w
            impact_font = _fit_font(draw, text, base_impact_font, max_width=x2 - text_x - 28, base_size=base_impact_sz, min_size=22)
            draw.text((text_x, cy), text, font=impact_font, fill=COLOR_TEXT_PRIMARY, anchor="lm")
        else:
            impact_font = _fit_font(draw, text, base_impact_font, max_width=card_inner_w, base_size=base_impact_sz, min_size=22)
            draw.text((x1 + 36, cy), text, font=impact_font, fill=COLOR_TEXT_PRIMARY, anchor="lm")

    if not is_vertical:
        img.putalpha(255)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    logger.info("Saved: %s", out_path)

def render_vs_slide(
    out_path: Path,
    title: str,
    step_tag: str,
    hero_title: str,
    hero_status: str,
    left_box: Tuple[str, str, List[str]],   # (tag, title, bullets)
    right_box: Tuple[str, str, List[str]],  # (tag, title, bullets)
    bottom_tag: str,
    bottom_text: str,
    top_badge: str = "",
    theme_color: Tuple[int, int, int] = ACCENT_BLUE,
    is_vertical: bool = False,
) -> None:
    """
    Renders a Pro Split Comparison "VS" Slide for instant comprehension.
    Supports both 16:9 landscape and 9:16 mobile vertical layouts.
    """
    left_texts = [left_box[0], left_box[1]] + list(left_box[2]) if left_box else []
    right_texts = [right_box[0], right_box[1]] + list(right_box[2]) if right_box else []

    left_has_content = bool(left_box and (left_box[0].strip() or left_box[1].strip() or any(b.strip() for b in left_box[2])))
    right_has_content = bool(right_box and (right_box[0].strip() or right_box[1].strip() or any(b.strip() for b in right_box[2])))
    if not hero_title.strip() and not left_has_content and not right_has_content:
        raise ValueError(
            f"VS slide '{title}' has no comparison information: 'hero_title', 'left_box', and 'right_box' are all empty. "
            "Ensure the slide specification provides 'hero_title' and non-empty left/right comparison boxes."
        )

    check_cognitive_load(
        title,
        [title, step_tag, top_badge, hero_title, hero_status, bottom_tag, bottom_text] + left_texts + right_texts,
        max_chars=MAX_SLIDE_CHARS,
        max_elements=MAX_SLIDE_ELEMENTS + 6,
    )
    img, draw, fonts = create_slide_base(title, step_tag=step_tag, theme_color=theme_color, is_vertical=is_vertical)
    x1, x2 = (56, 1024) if is_vertical else (70, 1340)
    card_inner_w = float(x2 - x1 - 72)

    # 1. Top Card
    top_y1, top_y2 = (140, 316) if is_vertical else (140, 380)
    draw.rounded_rectangle([x1, top_y1, x2, top_y2], radius=20, fill=COLOR_SURFACE, outline=COLOR_BORDER, width=2)
    draw.rounded_rectangle([x1, top_y1, x1 + 12, top_y2], radius=6, fill=theme_color)

    if top_badge:
        badge_w = draw.textlength(top_badge, font=fonts["badge"]) + 32
        draw.rounded_rectangle([x1 + 36, top_y1 + 18, x1 + 36 + badge_w, top_y1 + 58], radius=10, fill=COLOR_CANVAS, outline=COLOR_BORDER, width=1)
        draw.text((x1 + 36 + badge_w / 2, top_y1 + 38), top_badge, font=fonts["badge"], fill=COLOR_TEXT_SECONDARY, anchor="mm")
        title_y = top_y1 + (92 if is_vertical else 120)
        status_y = top_y1 + (144 if is_vertical else 190)
    elif not hero_status:
        title_y = (top_y1 + top_y2) // 2
        status_y = top_y1
    else:
        title_y = top_y1 + (64 if is_vertical else 90)
        status_y = top_y1 + (130 if is_vertical else 170)

    hero_base_sz = 48 if is_vertical else 64
    hero_font = _fit_font(draw, hero_title, _load_broll_font(hero_base_sz, bold=True), max_width=card_inner_w, base_size=hero_base_sz, min_size=28)
    draw.text((x1 + 36, title_y), hero_title, font=hero_font, fill=theme_color, anchor="lm")

    if hero_status:
        status_font = _fit_font(draw, hero_status, fonts["hero_sub"], max_width=card_inner_w - 40, base_size=30, min_size=20)
        status_w = draw.textlength(hero_status, font=status_font) + 36
        bg_col, out_col, txt_col = get_status_colors(theme_color)
        draw.rounded_rectangle([x1 + 36, status_y - 24, x1 + 36 + status_w, status_y + 24], radius=10, fill=bg_col, outline=out_col, width=1)
        draw.text((x1 + 36 + status_w / 2, status_y), hero_status, font=status_font, fill=txt_col, anchor="mm")

    # 2. Split Comparison
    split_gap = 28 if is_vertical else 40
    box_w = (x2 - x1 - split_gap) // 2
    mid_y1, mid_y2 = (334, 566) if is_vertical else (405, 645)
    box_inner_w = float(box_w - 48)

    for bx1, (btag, btitle, bbullets), bcol in [
        (x1, left_box, ACCENT_RED),
        (x1 + box_w + split_gap, right_box, ACCENT_GREEN),
    ]:
        bx2 = bx1 + box_w
        draw.rounded_rectangle([bx1, mid_y1, bx2, mid_y2], radius=16, fill=(20, 29, 47, 255), outline=bcol, width=2)
        draw.rounded_rectangle([bx1, mid_y1, bx1 + 10, mid_y2], radius=4, fill=bcol)
        if btag.strip():
            tag_w = draw.textlength(btag, font=fonts["badge"]) + 24
            bg_c, out_c, _ = get_status_colors(bcol)
            draw.rounded_rectangle([bx1 + 24, mid_y1 + 18, bx1 + 24 + tag_w, mid_y1 + 58], radius=8, fill=bg_c, outline=out_c, width=1)
            draw.text((bx1 + 24 + tag_w / 2, mid_y1 + 38), btag, font=fonts["badge"], fill=bcol, anchor="mm")
            t_y = mid_y1 + 98
            y_b = mid_y1 + 150
        else:
            t_y = mid_y1 + 52
            y_b = mid_y1 + 112
        t_font = _fit_font(draw, btitle, fonts["card_title"], max_width=box_inner_w, base_size=32, min_size=20)
        draw.text((bx1 + 24, t_y), btitle, font=t_font, fill=COLOR_TEXT_PRIMARY, anchor="lm")
        for i, b in enumerate(bbullets[:2]):
            b_str = f"• {b}"
            bf = _fit_font(draw, b_str, fonts["body"], max_width=box_inner_w, base_size=26, min_size=18)
            draw.text((bx1 + 24, y_b), b_str, font=bf, fill=COLOR_TEXT_PRIMARY if i == 0 else COLOR_TEXT_SECONDARY, anchor="lm")
            y_b += 38

    # 3. Bottom Takeaway Card
    bot_y1, bot_y2 = (584, 678) if is_vertical else (670, 755)
    bot_cy = (bot_y1 + bot_y2) / 2
    draw.rounded_rectangle([x1, bot_y1, x2, bot_y2], radius=14, fill=COLOR_SURFACE, outline=theme_color, width=2)
    draw.rounded_rectangle([x1, bot_y1, x1 + 8, bot_y2], radius=4, fill=theme_color)
    if bottom_tag.strip():
        b_tag_w = max(draw.textlength(bottom_tag, font=fonts["badge"]) + 28, 96)
        draw.rounded_rectangle([x1 + 24, bot_y1 + 20, x1 + 24 + b_tag_w, bot_y2 - 20], radius=8, fill=theme_color)
        draw.text((x1 + 24 + b_tag_w / 2, bot_cy), bottom_tag, font=fonts["badge"], fill=(15, 23, 42, 255), anchor="mm")
        bot_txt_x = x1 + 42 + b_tag_w
    else:
        bot_txt_x = x1 + 28
    bot_font = _fit_font(draw, bottom_text, fonts["footer"], max_width=x2 - bot_txt_x - 24, base_size=30, min_size=20)
    draw.text((bot_txt_x, bot_cy), bottom_text, font=bot_font, fill=COLOR_TEXT_PRIMARY, anchor="lm")

    if not is_vertical:
        img.putalpha(255)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    logger.info("Saved: %s", out_path)

def render_overview_slide(
    out_path: Path,
    title: str,
    cards: List[Any],  # Tuple of (num, title, accent) or (num, title, content, accent)
    conclusion_tag: str = "",
    conclusion_text: str = "",
    theme_color: Tuple[int, int, int] = ACCENT_BLUE,
    is_vertical: bool = False,
) -> None:
    """
    Renders an Executive Overview / Agenda Slide:
    - Supports clean single-line cards (zero sub-bullet clutter) for fast 1-2 second scan
    - Supports both 16:9 landscape and 9:16 mobile vertical layouts.
    """
    card_texts = []
    for c in cards:
        if isinstance(c, (list, tuple)):
            card_texts.extend([str(x) for x in c[:-1] if isinstance(x, str)])
    check_cognitive_load(
        title,
        [title, conclusion_tag, conclusion_text] + card_texts,
        max_chars=MAX_SLIDE_CHARS,
        max_elements=MAX_SLIDE_ELEMENTS + 4,
    )
    img, draw, fonts = create_slide_base(title, theme_color=theme_color, is_vertical=is_vertical)
    x1, x2 = (56, 1024) if is_vertical else (70, 1340)
    n = max(len(cards), 1)

    norm_cards = []
    for c in cards:
        if len(c) == 3:
            norm_cards.append((c[0], c[1], "", c[2]))
        else:
            norm_cards.append((c[0], c[1], c[2], c[3]))

    has_banner = bool(conclusion_text.strip()) if conclusion_text else False

    if is_vertical:
        if has_banner:
            total_space = 415
            gap = 20 if n == 2 else 16
            card_h = (total_space - (n - 1) * gap) // n
            y = 142
        else:
            total_space = 510 if n == 3 else 430
            gap = 24 if n == 2 else 20
            card_h = (total_space - (n - 1) * gap) // n
            y = 160 if n == 2 else 148
    else:
        if has_banner:
            total_space = 510
            gap = 24 if n == 2 else 18
            card_h = (total_space - (n - 1) * gap) // n
            y = 140
        else:
            total_space = 450 if n == 3 else 360
            gap = 28 if n == 2 else 24
            card_h = (total_space - (n - 1) * gap) // n
            y = 180 if n == 2 else 160

    for num, card_title, content, col in norm_cards:
        draw.rounded_rectangle([x1, y, x2, y + card_h], radius=18, fill=COLOR_SURFACE, outline=COLOR_BORDER, width=2)
        draw.rounded_rectangle([x1, y, x1 + 10, y + card_h], radius=4, fill=col)

        num_w = max(draw.textlength(num, font=fonts["badge"]) + 36, 76)
        pill_h = 48
        pill_txt_col = get_pill_text_color(col)
        title_x = x1 + 48 + num_w
        max_title_w = float(x2 - title_x - 28)

        if not content:
            center_y = y + card_h / 2
            pill_y1 = center_y - pill_h / 2
            pill_y2 = center_y + pill_h / 2
            draw.rounded_rectangle([x1 + 28, pill_y1, x1 + 28 + num_w, pill_y2], radius=12, fill=col)
            draw.text((x1 + 28 + num_w / 2, center_y), num, font=fonts["badge"], fill=pill_txt_col, anchor="mm")

            ct_font = _fit_font(draw, card_title, fonts["card_title_lg"], max_width=max_title_w, base_size=40, min_size=24)
            draw.text((title_x, center_y), card_title, font=ct_font, fill=COLOR_TEXT_PRIMARY, anchor="lm")
        else:
            pill_y1 = y + (18 if n == 3 else 24)
            pill_y2 = pill_y1 + pill_h
            draw.rounded_rectangle([x1 + 28, pill_y1, x1 + 28 + num_w, pill_y2], radius=10, fill=col)
            draw.text((x1 + 28 + num_w / 2, (pill_y1 + pill_y2) / 2), num, font=fonts["badge"], fill=pill_txt_col, anchor="mm")
            ct_font = _fit_font(draw, card_title, fonts["card_title"], max_width=max_title_w, base_size=32, min_size=22)
            draw.text((x1 + 44 + num_w, (pill_y1 + pill_y2) / 2), card_title, font=ct_font, fill=COLOR_TEXT_PRIMARY, anchor="lm")

            bullets = content if isinstance(content, list) else ([content] if content else [])
            line_y = pill_y2 + (30 if isinstance(content, list) else (22 if n == 3 else 32))
            for i, bullet in enumerate(bullets[:2]):
                b_str = bullet if bullet.startswith("•") else f"• {bullet}"
                bf = _fit_font(draw, b_str, fonts["body"], max_width=float(x2 - x1 - 64), base_size=26, min_size=18)
                draw.text((x1 + 36, line_y), b_str, font=bf, fill=COLOR_TEXT_PRIMARY if i == 0 else COLOR_TEXT_SECONDARY, anchor="lm")
                line_y += 40

        y += card_h + gap

    if has_banner:
        banner_accent = norm_cards[0][3] if norm_cards else theme_color
        bot_y1, bot_y2 = (580, 676) if is_vertical else (670, 755)
        bot_cy = (bot_y1 + bot_y2) / 2
        draw.rounded_rectangle([x1, bot_y1, x2, bot_y2], radius=14, fill=COLOR_SURFACE, outline=banner_accent, width=2)
        draw.rounded_rectangle([x1, bot_y1, x1 + 8, bot_y2], radius=4, fill=banner_accent)

        tag_w = max(draw.textlength(conclusion_tag, font=fonts["badge"]) + 32, 80)
        draw.rounded_rectangle([x1 + 24, bot_y1 + 20, x1 + 24 + tag_w, bot_y2 - 20], radius=8, fill=banner_accent)
        banner_txt_col = get_pill_text_color(banner_accent)
        draw.text((x1 + 24 + tag_w / 2, bot_cy), conclusion_tag, font=fonts["badge"], fill=banner_txt_col, anchor="mm")
        c_txt_x = x1 + 40 + tag_w
        c_font = _fit_font(draw, conclusion_text, fonts["footer"], max_width=x2 - c_txt_x - 24, base_size=30, min_size=20)
        draw.text((c_txt_x, bot_cy), conclusion_text, font=c_font, fill=COLOR_TEXT_PRIMARY, anchor="lm")

    if not is_vertical:
        img.putalpha(255)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    logger.info("Saved: %s", out_path)

COLOR_MAP: Dict[str, Tuple[int, int, int]] = {
    "blue": ACCENT_BLUE, "green": ACCENT_GREEN, "emerald": ACCENT_GREEN,
    "amber": ACCENT_AMBER, "red": ACCENT_RED, "rose": ACCENT_RED,
    "violet": ACCENT_VIOLET, "purple": ACCENT_VIOLET,
}

def resolve_color(col: Any) -> Tuple[int, int, int]:
    if isinstance(col, str):
        return COLOR_MAP.get(col.lower(), ACCENT_BLUE)
    if isinstance(col, (tuple, list)) and len(col) >= 3:
        return (int(col[0]), int(col[1]), int(col[2]))
    return ACCENT_BLUE

def detect_project_vertical(proj_dir: Path, specs: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Auto-detects whether a project directory or slide manifest targets a 9:16 vertical format."""
    if specs:
        for s in specs:
            if isinstance(s, dict):
                if s.get("is_vertical") is True or str(s.get("orientation", "")).lower() == "vertical" or s.get("aspect_ratio") == "9:16":
                    return True
                if s.get("is_vertical") is False or str(s.get("orientation", "")).lower() == "horizontal":
                    return False
    proj_json = proj_dir / "project.json"
    if proj_json.exists():
        try:
            pdata = json.loads(proj_json.read_text(encoding="utf-8-sig"))
            if isinstance(pdata, dict) and (pdata.get("is_vertical") or pdata.get("aspect_ratio") == "9:16" or pdata.get("format") == "shorts"):
                return True
        except Exception:
            pass
    ymmp_file = proj_dir / "ymmp" / "final_video.ymmp"
    if ymmp_file.exists():
        try:
            with open(ymmp_file, "r", encoding="utf-8-sig") as yf:
                ydata = json.load(yf)
            tl = ydata.get("Timelines", [{}])[0] if ydata.get("Timelines") else ydata.get("Timeline", {})
            vinfo = tl.get("VideoInfo", {}) if isinstance(tl, dict) else {}
            if vinfo.get("Height", 1080) > vinfo.get("Width", 1920):
                return True
        except Exception:
            pass
    return False

def render_from_manifest(
    manifest: Union[str, Path, List[Dict[str, Any]]],
    out_dir: Union[str, Path],
    is_vertical: Optional[bool] = None,
) -> List[Path]:
    """
    Renders slides declaratively from a JSON manifest or list of slide spec dicts.
    Guarantees the standardized Pro Dark Slate theme across any project and automatically
    adapts to 9:16 mobile vertical layout when `is_vertical=True` or detected from the project.
    """
    manifest_dir: Optional[Path] = None
    if isinstance(manifest, (str, Path)):
        manifest_path = Path(manifest)
        manifest_dir = manifest_path.parent
        with open(manifest_path, "r", encoding="utf-8-sig") as f:
            raw_loaded = json.load(f)
    else:
        raw_loaded = manifest

    if isinstance(raw_loaded, dict):
        if is_vertical is None and "is_vertical" in raw_loaded:
            is_vertical = bool(raw_loaded["is_vertical"])
        specs = raw_loaded.get("slides", raw_loaded.get("broll_manifest", []))
    else:
        specs = raw_loaded

    if not isinstance(specs, list):
        specs = []

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    proj_dir = manifest_dir if manifest_dir is not None else out_dir.parent

    resolved_vertical = (
        is_vertical
        if is_vertical is not None
        else detect_project_vertical(proj_dir, specs=specs if isinstance(specs, list) else None)
    )

    generated: List[Path] = []

    for spec in specs:
        stype = spec.get("type", "metric")
        fname = spec.get("filename", "slide.png")
        dest = out_dir / fname
        theme_color = resolve_color(spec.get("theme_color", spec.get("color", "blue")))
        spec_vertical = bool(spec.get("is_vertical", resolved_vertical))

        if stype == "overview":
            raw_cards = spec.get("cards", [])
            if not raw_cards:
                raise ValueError(
                    f"Overview slide '{spec.get('title', '')}' has no cards in specification."
                )
            cards = []
            for c in raw_cards:
                if isinstance(c, (list, tuple)):
                    col = resolve_color(c[-1])
                    cards.append((*c[:-1], col))
                elif isinstance(c, dict):
                    col = resolve_color(c.get("color", "blue"))
                    cards.append((c.get("num", ""), c.get("title", ""), col))
            render_overview_slide(
                out_path=dest, title=spec.get("title", ""), cards=cards,
                conclusion_tag=spec.get("conclusion_tag", ""), conclusion_text=spec.get("conclusion_text", ""),
                theme_color=theme_color, is_vertical=spec_vertical,
            )
        elif stype == "metric":
            hero_m = (
                spec.get("hero_metric")
                or spec.get("hero_title")
                or spec.get("text_content")
                or ""
            )
            if not str(hero_m).strip():
                raise ValueError(
                    f"Metric slide '{spec.get('title', '')}' has no hero metric text in specification."
                )
            render_metric_slide(
                out_path=dest, title=spec.get("title", ""), step_tag=spec.get("step_tag", ""), hero_metric=hero_m,
                status_pill=spec.get("status_pill", spec.get("hero_status", "")),
                impact_tag=spec.get("impact_tag", spec.get("bottom_tag", spec.get("takeaway_tag", ""))),
                impact_text=spec.get("impact_text", spec.get("bottom_text", spec.get("takeaway_text", ""))),
                badge_text=spec.get("badge_text", ""), category_tag=spec.get("category_tag", ""),
                theme_color=theme_color, is_vertical=spec_vertical,
            )
        elif stype in ("clash", "metric_clash"):
            render_clash_slide(
                out_path=dest, title=spec.get("title", ""), step_tag=spec.get("step_tag", ""),
                hero_metric=str(spec.get("hero_metric") or spec.get("total_metric") or spec.get("headline") or ""),
                left_entity=spec.get("left", spec.get("left_box", spec.get("left_entity", {}))),
                right_entity=spec.get("right", spec.get("right_box", spec.get("right_entity", {}))),
                impact_tag=str(spec.get("impact_tag") or spec.get("bottom_tag") or ""),
                impact_text=str(spec.get("impact_text") or spec.get("bottom_text") or ""),
                theme_color=theme_color, is_vertical=spec_vertical,
            )
        elif stype == "vs":
            def _norm_box(b: Any) -> Tuple[str, str, List[str]]:
                if isinstance(b, (list, tuple)):
                    return (str(b[0]), str(b[1]), [str(x) for x in b[2]] if len(b) >= 3 and isinstance(b[2], list) else [])
                if isinstance(b, dict):
                    raw = b.get("bullets") or ([b[k]] if (k := next((k for k in ("sub", "description", "text") if k in b), None)) else [])
                    return (str(b.get("tag") or b.get("label") or ""), str(b.get("title") or b.get("name") or ""), [str(x) for x in raw])
                return ("", "", [])

            render_vs_slide(
                out_path=dest, title=spec.get("title", ""), step_tag=spec.get("step_tag", ""),
                hero_title=str(spec.get("hero_title") or spec.get("hero_metric") or spec.get("headline") or ""),
                hero_status=str(spec.get("hero_status") or spec.get("status_pill") or spec.get("status") or ""),
                left_box=_norm_box(spec.get("left_box") or spec.get("left")),
                right_box=_norm_box(spec.get("right_box") or spec.get("right")),
                bottom_tag=str(spec.get("bottom_tag") or spec.get("impact_tag") or spec.get("takeaway_tag") or ""),
                bottom_text=str(spec.get("bottom_text") or spec.get("impact_text") or spec.get("takeaway_text") or ""),
                top_badge=spec.get("top_badge", ""), theme_color=theme_color, is_vertical=spec_vertical,
            )
        elif stype in ("official_image", "image"):
            from veraxi_ymmp.graphics.official_assets import render_official_image_slide
            render_official_image_slide(
                out_path=dest, title=spec.get("title", ""),
                image_path=spec.get("image_path", spec.get("image", spec.get("asset", ""))),
                source_citation=spec.get("source_citation", spec.get("source", spec.get("citation", "公式ドキュメント"))),
                step_tag=spec.get("step_tag", "公式発表"), caption=spec.get("caption", spec.get("takeaway_text", spec.get("impact_text", ""))),
                theme_color=theme_color, is_vertical=spec_vertical, verification_badge=spec.get("verification_badge", "公式発表"),
                category_tag=spec.get("category_tag", ""), base_dir=proj_dir, layout=spec.get("layout", "hero"),
                show_caption=spec.get("show_caption", False), show_header=spec.get("show_header", True), show_citation=spec.get("show_citation", True),
            )
        elif stype in ("official_data", "official_stat"):
            from veraxi_ymmp.graphics.official_assets import render_official_data_slide
            render_official_data_slide(
                out_path=dest, title=spec.get("title", ""),
                hero_metric=spec.get("hero_metric", spec.get("metric", spec.get("hero_title", ""))),
                metric_label=spec.get("metric_label", spec.get("status_pill", spec.get("hero_status", ""))),
                source_citation=spec.get("source_citation", spec.get("source", spec.get("citation", "公的データ"))),
                step_tag=spec.get("step_tag", "公式データ"), impact_tag=spec.get("impact_tag", spec.get("bottom_tag", "結論")),
                impact_text=spec.get("impact_text", spec.get("bottom_text", spec.get("takeaway_text", ""))),
                verification_badge=spec.get("verification_badge", "VERIFIED"), theme_color=theme_color,
                category_tag=spec.get("category_tag", ""), is_vertical=spec_vertical,
            )
        elif stype in ("matrix", "flow", "architecture", "value_chain", "domino", "causality", "chain"):
            from veraxi_ymmp.graphics.infographic import render_infographic_slide
            render_infographic_slide(stype, spec, dest, theme_color, spec_vertical)
        generated.append(dest)

    return generated

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        manifest_file = sys.argv[1]
        output_dir = sys.argv[2]
        render_from_manifest(manifest_file, output_dir)
    else:
        print("Usage: python -m veraxi_ymmp.graphics.broll <manifest.json> <output_dir>")
