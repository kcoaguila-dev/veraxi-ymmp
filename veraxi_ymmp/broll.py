"""
High-Definition B-Roll Presentation Board Generator (Pro Dark Mode Architecture)
Reusable engine for generating video presentation boards in veraxi_ymmp.

Design Standards:
  - Deep Navy Slate Theme (#0F172A) reducing eye strain & halation
  - Zero redundant category tags & zero English buzzword clutter
  - 1-Slide-1-Impact Information Architecture (VS comparisons, punchy keyword pills)
  - Seamless presenter framing (leaves X: 1350 to 1920 natural for presenter)
  - Subtitle Safe Zone: strictly leaves Y >= 780 clear for dialogue
"""
from pathlib import Path
from typing import List, Tuple, Optional, Union
from PIL import Image, ImageDraw, ImageFont

# Pro Dark Palette
COLOR_CANVAS = (15, 23, 42, 255)       # Slate 900
COLOR_SURFACE = (30, 41, 59, 255)      # Slate 800
COLOR_SURFACE_ALT = (24, 33, 47, 255)  # Darker Slate
COLOR_BORDER = (51, 65, 85, 255)       # Slate 700
COLOR_TEXT_PRIMARY = (248, 250, 252, 255) # Slate 50
COLOR_TEXT_SECONDARY = (148, 163, 184, 255) # Slate 400
COLOR_TEXT_MUTED = (100, 116, 139, 255) # Slate 500

# High-Visibility Accents for Dark Mode
ACCENT_BLUE = (56, 189, 248)    # Sky 400
ACCENT_GREEN = (52, 211, 153)   # Emerald 400
ACCENT_AMBER = (251, 191, 36)   # Amber 400
ACCENT_RED = (248, 113, 113)    # Red 400
ACCENT_VIOLET = (167, 139, 250) # Violet 400


def get_fonts() -> dict:
    """Returns BIZ UDP Gothic Bold fonts with proper proportional kerning."""
    fb = "BIZ-UDGothicB.ttc"
    fr = "BIZ-UDGothicR.ttc"
    
    try:
        return {
            "hero": ImageFont.truetype(fb, 64, index=1),
            "hero_sub": ImageFont.truetype(fb, 30, index=1),
            "title": ImageFont.truetype(fb, 36, index=1),
            "card_title_lg": ImageFont.truetype(fb, 40, index=1),
            "card_title": ImageFont.truetype(fb, 32, index=1),
            "body": ImageFont.truetype(fb, 26, index=1),
            "footer": ImageFont.truetype(fb, 30, index=1),
            "badge": ImageFont.truetype(fb, 30, index=1),
            "num": ImageFont.truetype(fb, 34, index=1),
            "small": ImageFont.truetype(fr, 22, index=1)
        }
    except Exception:
        try:
            return {
                "hero": ImageFont.truetype(fb, 64),
                "hero_sub": ImageFont.truetype(fb, 30),
                "title": ImageFont.truetype(fb, 36),
                "card_title_lg": ImageFont.truetype(fb, 40),
                "card_title": ImageFont.truetype(fb, 32),
                "body": ImageFont.truetype(fb, 26),
                "footer": ImageFont.truetype(fb, 30),
                "badge": ImageFont.truetype(fb, 30),
                "num": ImageFont.truetype(fb, 34),
                "small": ImageFont.truetype(fr, 22)
            }
        except Exception:
            default = ImageFont.load_default()
            return {k: default for k in ["hero", "hero_sub", "title", "card_title_lg", "card_title", "body", "footer", "badge", "num", "small"]}


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
    height: int = 1080
):
    """
    Creates a 1920x1080 Studio Presentation Slide in Pro Dark Slate.
    Clean single-anchor header without badge traffic.
    """
    img = Image.new("RGBA", (width, height), COLOR_CANVAS)
    draw = ImageDraw.Draw(img)
    fonts = get_fonts()

    # Studio Top Header Bar
    header_bbox = [60, 24, 1860, 116]
    draw.rounded_rectangle(header_bbox, radius=18, fill=COLOR_SURFACE, outline=COLOR_BORDER, width=2)
    # Left accent indicator
    draw.rounded_rectangle([60, 24, 76, 116], radius=6, fill=theme_color)

    cur_x = 96
    if category_tag:
        cat_w = draw.textlength(category_tag, font=fonts["badge"]) + 36
        draw.rounded_rectangle([cur_x, 42, cur_x + cat_w, 98], radius=12, fill=COLOR_CANVAS, outline=COLOR_BORDER, width=1)
        draw.text((cur_x + cat_w / 2, 70), category_tag, font=fonts["badge"], fill=COLOR_TEXT_PRIMARY, anchor="mm")
        cur_x += cat_w + 14

    # Step Tag Pill (e.g. 要点 01, 条件 01, 第１期)
    if step_tag:
        step_w = draw.textlength(step_tag, font=fonts["badge"]) + 36
        pill_txt_col = get_pill_text_color(theme_color)
        draw.rounded_rectangle([cur_x, 38, cur_x + step_w, 102], radius=12, fill=theme_color)
        draw.text((cur_x + step_w / 2, 70), step_tag, font=fonts["badge"], fill=pill_txt_col, anchor="mm")
        cur_x += step_w + 20
    else:
        if not category_tag:
            cur_x += 10

    # Title text
    draw.text((cur_x, 70), title, font=fonts["title"], fill=COLOR_TEXT_PRIMARY, anchor="lm")

    return img, draw, fonts


def get_status_colors(accent_color: Tuple[int, int, int]):
    """Returns dark container background, outline, and text color for status pills."""
    if accent_color == ACCENT_RED:
        return (69, 10, 10, 255), (239, 68, 68, 255), (255, 255, 255, 255)
    elif accent_color == ACCENT_AMBER:
        return (69, 26, 3, 255), (245, 158, 11, 255), (255, 255, 255, 255)
    elif accent_color == ACCENT_GREEN:
        return (6, 78, 59, 255), (16, 185, 129, 255), (255, 255, 255, 255)
    elif accent_color == ACCENT_VIOLET:
        return (59, 7, 100, 255), (139, 92, 246, 255), (255, 255, 255, 255)
    else:
        return (12, 74, 110, 255), (14, 165, 233, 255), (255, 255, 255, 255)


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
    category_tag: str = ""
):
    """
    Renders a high-retention, low-cognitive-load Metric Slide (2-3 second read):
    - 1 Dominant Hero Focus Card (Giant Number + Status Pill)
    - 1 Clean Single Impact Banner (eliminating the cluttered multi-card stack)
    """
    img, draw, fonts = create_slide_base(title, step_tag=step_tag, category_tag=category_tag, theme_color=theme_color)
    x1, x2 = 70, 1340

    # 1. Hero Focus Card (Y: 150 to 475)
    y1, y2 = 150, 475
    draw.rounded_rectangle([x1, y1, x2, y2], radius=20, fill=COLOR_SURFACE, outline=COLOR_BORDER, width=2)
    draw.rounded_rectangle([x1, y1, x1 + 12, y2], radius=6, fill=theme_color)

    # Top Context Badge (Subtle context)
    if badge_text:
        badge_w = draw.textlength(badge_text, font=fonts["badge"]) + 32
        draw.rounded_rectangle([x1 + 36, y1 + 24, x1 + 36 + badge_w, y1 + 68], radius=10, fill=COLOR_CANVAS, outline=COLOR_BORDER, width=1)
        draw.text((x1 + 36 + badge_w / 2, y1 + 46), badge_text, font=fonts["badge"], fill=COLOR_TEXT_SECONDARY, anchor="mm")

    # The Giant Hero Metric Number (Centerpiece of the cut)
    metric_y = y1 + 145 if badge_text else y1 + 115
    draw.text((x1 + 36, metric_y), hero_metric, font=fonts["hero"], fill=theme_color, anchor="lm")

    # Status Pill (Core takeaway with 2px bright border and crisp white text)
    status_w = draw.textlength(status_pill, font=fonts["hero_sub"]) + 40
    bg_col, out_col, txt_col = get_status_colors(theme_color)
    pill_y = metric_y + 88
    draw.rounded_rectangle([x1 + 36, pill_y - 32, x1 + 36 + status_w, pill_y + 32], radius=12, fill=bg_col, outline=out_col, width=2)
    draw.text((x1 + 36 + status_w / 2, pill_y), status_pill, font=fonts["hero_sub"], fill=txt_col, anchor="mm")

    # 2. Single Clean Impact Banner (Y: 510 to 645)
    tag = impact_tag
    text = impact_text
    color = theme_color
    if not text and takeaways and len(takeaways) > 0:
        tag, text, color = takeaways[0]

    if text:
        y_top, y_bot = 510, 645
        draw.rounded_rectangle([x1, y_top, x2, y_bot], radius=16, fill=COLOR_SURFACE, outline=COLOR_BORDER, width=2)
        draw.rounded_rectangle([x1, y_top, x1 + 10, y_bot], radius=4, fill=color)

        if tag:
            pill_txt_col = get_pill_text_color(color)
            tag_w = max(draw.textlength(tag, font=fonts["badge"]) + 36, 92)
            draw.rounded_rectangle([x1 + 28, y_top + 28, x1 + 28 + tag_w, y_bot - 28], radius=10, fill=color)
            draw.text((x1 + 28 + tag_w / 2, (y_top + y_bot) / 2), tag, font=fonts["badge"], fill=pill_txt_col, anchor="mm")
            draw.text((x1 + 48 + tag_w, (y_top + y_bot) / 2), text, font=fonts["card_title"], fill=COLOR_TEXT_PRIMARY, anchor="lm")
        else:
            # Full-width natural impact text without cramped square badge
            draw.text((x1 + 36, (y_top + y_bot) / 2), text, font=fonts["card_title"], fill=COLOR_TEXT_PRIMARY, anchor="lm")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    print(f"Saved: {out_path}")


def render_vs_slide(
    out_path: Path,
    title: str,
    step_tag: str,
    hero_title: str,
    hero_status: str,
    left_box: Tuple[str, str, List[str]],  # (tag, title, bullets)
    right_box: Tuple[str, str, List[str]], # (tag, title, bullets)
    bottom_tag: str,
    bottom_text: str,
    top_badge: str = "",
    theme_color: Tuple[int, int, int] = ACCENT_BLUE
):
    """
    Renders a Pro Split Comparison "VS" Slide for instant comprehension.
    """
    img, draw, fonts = create_slide_base(title, step_tag=step_tag, theme_color=theme_color)
    x1, x2 = 70, 1340

    # 1. Top Card
    draw.rounded_rectangle([x1, 140, x2, 380], radius=20, fill=COLOR_SURFACE, outline=COLOR_BORDER, width=2)
    draw.rounded_rectangle([x1, 140, x1 + 12, 380], radius=6, fill=theme_color)

    if top_badge:
        badge_w = draw.textlength(top_badge, font=fonts["badge"]) + 32
        draw.rounded_rectangle([x1 + 36, 166, x1 + 36 + badge_w, 208], radius=10, fill=COLOR_CANVAS, outline=COLOR_BORDER, width=1)
        draw.text((x1 + 36 + badge_w / 2, 187), top_badge, font=fonts["badge"], fill=COLOR_TEXT_SECONDARY, anchor="mm")
        title_y = 260
        status_y = 330
    else:
        title_y = 230
        status_y = 310

    draw.text((x1 + 36, title_y), hero_title, font=fonts["hero"], fill=theme_color, anchor="lm")

    status_w = draw.textlength(hero_status, font=fonts["hero_sub"]) + 36
    bg_col, out_col, txt_col = get_status_colors(theme_color)
    draw.rounded_rectangle([x1 + 36, status_y - 25, x1 + 36 + status_w, status_y + 25], radius=10, fill=bg_col, outline=out_col, width=1)
    draw.text((x1 + 36 + status_w / 2, status_y), hero_status, font=fonts["hero_sub"], fill=txt_col, anchor="mm")

    # 2. Split Comparison
    box_w = (x2 - x1 - 40) // 2
    
    # Left Box
    tag_l, title_l, bullets_l = left_box
    left_x1 = x1
    left_x2 = left_x1 + box_w
    draw.rounded_rectangle([left_x1, 405, left_x2, 645], radius=16, fill=COLOR_SURFACE, outline=COLOR_BORDER, width=2)
    draw.rounded_rectangle([left_x1, 405, left_x1 + 10, 645], radius=4, fill=ACCENT_RED)
    
    tag_w = draw.textlength(tag_l, font=fonts["badge"]) + 24
    draw.rounded_rectangle([left_x1 + 24, 425, left_x1 + 24 + tag_w, 465], radius=8, fill=(69, 10, 10, 255), outline=ACCENT_RED, width=1)
    draw.text((left_x1 + 24 + tag_w / 2, 445), tag_l, font=fonts["badge"], fill=ACCENT_RED, anchor="mm")
    
    draw.text((left_x1 + 28, 510), title_l, font=fonts["card_title"], fill=COLOR_TEXT_PRIMARY, anchor="lm")
    y_b = 565
    for b in bullets_l[:2]:
        draw.text((left_x1 + 28, y_b), f"• {b}", font=fonts["body"], fill=COLOR_TEXT_SECONDARY if y_b == 565 else COLOR_TEXT_MUTED, anchor="lm")
        y_b += 40

    # Right Box
    tag_r, title_r, bullets_r = right_box
    right_x1 = left_x2 + 40
    right_x2 = x2
    draw.rounded_rectangle([right_x1, 405, right_x2, 645], radius=16, fill=COLOR_SURFACE, outline=ACCENT_GREEN, width=2)
    draw.rounded_rectangle([right_x1, 405, right_x1 + 10, 645], radius=4, fill=ACCENT_GREEN)
    
    tag_w = draw.textlength(tag_r, font=fonts["badge"]) + 24
    draw.rounded_rectangle([right_x1 + 24, 425, right_x1 + 24 + tag_w, 465], radius=8, fill=(6, 78, 59, 255), outline=ACCENT_GREEN, width=1)
    draw.text((right_x1 + 24 + tag_w / 2, 445), tag_r, font=fonts["badge"], fill=ACCENT_GREEN, anchor="mm")
    
    draw.text((right_x1 + 28, 510), title_r, font=fonts["card_title"], fill=ACCENT_GREEN, anchor="lm")
    y_b = 565
    for b in bullets_r[:2]:
        draw.text((right_x1 + 28, y_b), f"• {b}", font=fonts["body"], fill=COLOR_TEXT_PRIMARY if y_b == 565 else COLOR_TEXT_SECONDARY, anchor="lm")
        y_b += 40

    # 3. Bottom Takeaway Card
    draw.rounded_rectangle([x1, 670, x2, 755], radius=14, fill=COLOR_SURFACE, outline=theme_color, width=2)
    draw.rounded_rectangle([x1, 670, x1 + 8, 755], radius=4, fill=theme_color)
    draw.rounded_rectangle([x1 + 24, 690, x1 + 120, 735], radius=8, fill=theme_color)
    draw.text((x1 + 72, 712), bottom_tag, font=fonts["badge"], fill=(15, 23, 42, 255), anchor="mm")
    draw.text((x1 + 140, 712), bottom_text, font=fonts["footer"], fill=COLOR_TEXT_PRIMARY, anchor="lm")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    print(f"Saved: {out_path}")


def render_overview_slide(
    out_path: Path,
    title: str,
    cards: List[Any],  # Tuple of (num, title, accent) or (num, title, content, accent)
    conclusion_tag: str = "",
    conclusion_text: str = "",
    theme_color: Tuple[int, int, int] = ACCENT_BLUE
):
    """
    Renders an Executive Overview / Agenda Slide:
    - Supports clean single-line cards (zero sub-bullet clutter) for fast 1-2 second scan
    - If cards have sub-bullets, renders them with dynamic vertical balance
    - If conclusion_text is empty, omits the bottom banner for a clean agenda look
    - Dynamic badge width prevents cutoff for 第１期 / 第２期 / 条件 01
    """
    img, draw, fonts = create_slide_base(title, theme_color=theme_color)
    x1, x2 = 70, 1340
    n = len(cards)
    
    # Normalize card tuples
    norm_cards = []
    for c in cards:
        if len(c) == 3:
            norm_cards.append((c[0], c[1], "", c[2]))
        else:
            norm_cards.append((c[0], c[1], c[2], c[3]))

    has_content = any(bool(c[2]) for c in norm_cards)
    has_banner = bool(conclusion_text.strip()) if conclusion_text else False

    if has_banner:
        total_space = 510
        gap = 24 if n == 2 else 18
        card_h = (total_space - (n - 1) * gap) // n
        y = 140
    else:
        # Spacious clean layout without bottom banner
        total_space = 450 if n == 3 else 360
        gap = 28 if n == 2 else 24
        card_h = (total_space - (n - 1) * gap) // n
        y = 180 if n == 2 else 160

    for num, card_title, content, col in norm_cards:
        # Card base
        draw.rounded_rectangle([x1, y, x2, y + card_h], radius=18, fill=COLOR_SURFACE, outline=COLOR_BORDER, width=2)
        draw.rounded_rectangle([x1, y, x1 + 10, y + card_h], radius=4, fill=col)
        
        # Badge Pill
        num_w = max(draw.textlength(num, font=fonts["badge"]) + 36, 76)
        pill_h = 48
        pill_txt_col = get_pill_text_color(col)
        
        if not content:
            # Clean single-line headline card (Vertically centered)
            center_y = y + card_h / 2
            pill_y1 = center_y - pill_h / 2
            pill_y2 = center_y + pill_h / 2
            draw.rounded_rectangle([x1 + 28, pill_y1, x1 + 28 + num_w, pill_y2], radius=12, fill=col)
            draw.text((x1 + 28 + num_w / 2, center_y), num, font=fonts["badge"], fill=pill_txt_col, anchor="mm")
            
            # Big, bold headline text
            draw.text((x1 + 48 + num_w, center_y), card_title, font=fonts["card_title_lg"], fill=COLOR_TEXT_PRIMARY, anchor="lm")
        else:
            # Card with sub-bullets
            pill_y1 = y + (20 if n == 3 else 26)
            pill_y2 = pill_y1 + pill_h
            draw.rounded_rectangle([x1 + 28, pill_y1, x1 + 28 + num_w, pill_y2], radius=10, fill=col)
            draw.text((x1 + 28 + num_w / 2, (pill_y1 + pill_y2) / 2), num, font=fonts["badge"], fill=pill_txt_col, anchor="mm")
            draw.text((x1 + 44 + num_w, (pill_y1 + pill_y2) / 2), card_title, font=fonts["card_title"], fill=COLOR_TEXT_PRIMARY, anchor="lm")
            
            if isinstance(content, list):
                line_y = pill_y2 + 32
                for i, bullet in enumerate(content[:2]):
                    bullet_str = bullet if bullet.startswith("•") else f"• {bullet}"
                    font_col = COLOR_TEXT_PRIMARY if i == 0 else COLOR_TEXT_SECONDARY
                    draw.text((x1 + 36, line_y), bullet_str, font=fonts["body"], fill=font_col, anchor="lm")
                    line_y += 44
            else:
                bullet_str = content if content.startswith("•") else f"• {content}"
                line_y = pill_y2 + (24 if n == 3 else 36)
                draw.text((x1 + 36, line_y), bullet_str, font=fonts["body"], fill=COLOR_TEXT_SECONDARY, anchor="lm")
                
        y += card_h + gap

    # Optional Conclusion Banner
    if has_banner:
        banner_accent = norm_cards[0][3] if norm_cards else theme_color
        draw.rounded_rectangle([x1, 670, x2, 755], radius=14, fill=COLOR_SURFACE, outline=banner_accent, width=2)
        draw.rounded_rectangle([x1, 670, x1 + 8, 755], radius=4, fill=banner_accent)
        
        tag_w = max(draw.textlength(conclusion_tag, font=fonts["badge"]) + 32, 80)
        draw.rounded_rectangle([x1 + 24, 690, x1 + 24 + tag_w, 735], radius=8, fill=banner_accent)
        banner_txt_col = get_pill_text_color(banner_accent)
        draw.text((x1 + 24 + tag_w / 2, 712), conclusion_tag, font=fonts["badge"], fill=banner_txt_col, anchor="mm")
        draw.text((x1 + 40 + tag_w, 712), conclusion_text, font=fonts["footer"], fill=COLOR_TEXT_PRIMARY, anchor="lm")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    print(f"Saved: {out_path}")


COLOR_MAP: Dict[str, Tuple[int, int, int]] = {
    "blue": ACCENT_BLUE,
    "green": ACCENT_GREEN,
    "amber": ACCENT_AMBER,
    "red": ACCENT_RED,
    "violet": ACCENT_VIOLET,
}

def resolve_color(col: Any) -> Tuple[int, int, int]:
    if isinstance(col, str):
        return COLOR_MAP.get(col.lower(), ACCENT_BLUE)
    if isinstance(col, (tuple, list)) and len(col) >= 3:
        return (col[0], col[1], col[2])
    return ACCENT_BLUE


def render_from_manifest(manifest: Union[str, Path, List[Dict[str, Any]]], out_dir: Union[str, Path]) -> List[Path]:
    """
    Renders slides declaratively from a JSON manifest or list of slide spec dicts.
    Guarantees the standardized Pro Dark Slate theme across any project.
    """
    import json
    if isinstance(manifest, (str, Path)):
        manifest_path = Path(manifest)
        with open(manifest_path, "r", encoding="utf-8") as f:
            specs = json.load(f)
    else:
        specs = manifest

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    for spec in specs:
        stype = spec.get("type", "metric")
        fname = spec.get("filename", "slide.png")
        dest = out_dir / fname
        theme_color = resolve_color(spec.get("theme_color", spec.get("color", "blue")))

        if stype == "overview":
            raw_cards = spec.get("cards", [])
            cards = []
            for c in raw_cards:
                if isinstance(c, (list, tuple)):
                    col = resolve_color(c[-1])
                    cards.append((*c[:-1], col))
                elif isinstance(c, dict):
                    col = resolve_color(c.get("color", "blue"))
                    cards.append((c.get("num", ""), c.get("title", ""), col))
            render_overview_slide(
                out_path=dest,
                title=spec.get("title", ""),
                cards=cards,
                conclusion_tag=spec.get("conclusion_tag", ""),
                conclusion_text=spec.get("conclusion_text", ""),
                theme_color=theme_color
            )
        elif stype == "metric":
            render_metric_slide(
                out_path=dest,
                title=spec.get("title", ""),
                step_tag=spec.get("step_tag", ""),
                hero_metric=spec.get("hero_metric", ""),
                status_pill=spec.get("status_pill", ""),
                impact_tag=spec.get("impact_tag", ""),
                impact_text=spec.get("impact_text", ""),
                theme_color=theme_color
            )
        elif stype == "vs":
            render_vs_slide(
                out_path=dest,
                title=spec.get("title", ""),
                step_tag=spec.get("step_tag", ""),
                hero_title=spec.get("hero_title", ""),
                hero_status=spec.get("hero_status", ""),
                left_box=spec.get("left_box"),
                right_box=spec.get("right_box"),
                bottom_tag=spec.get("bottom_tag", "視点"),
                bottom_text=spec.get("bottom_text", ""),
                theme_color=theme_color
            )
        generated.append(dest)

    return generated


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        manifest_file = sys.argv[1]
        output_dir = sys.argv[2]
        render_from_manifest(manifest_file, output_dir)
    else:
        print("Usage: python -m veraxi_ymmp.broll <manifest.json> <output_dir>")
