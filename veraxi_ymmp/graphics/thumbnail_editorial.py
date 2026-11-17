"""
Editorial & Subject-Anchored Thumbnail Engine for Veraxi YMMP
Implements high-CTR, mobile-first YouTube thumbnail layouts combining:
- Real-world subject anchors (CEO portraits, company logos, brand symbols)
- Single high-emotion mascot reaction (Zundamon / Metan)
- Ultra-concise 2-tier Fukuro typography with strict auto-fit (zero clipping)
- Protected YouTube bottom-right timestamp dead-zone
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Tuple
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from veraxi_ymmp.core.logging import logger


def crop_portrait_focus(
    img: Image.Image,
    target_w: int,
    target_h: int,
    focus_y: float = 0.28,
) -> Image.Image:
    """
    Crops and resizes a portrait photo to fill (target_w, target_h) while
    anchoring on the upper-center subject (face/head) rather than dead center.
    """
    src = img.convert("RGBA")
    src_aspect = src.width / max(1, src.height)
    dst_aspect = target_w / max(1, target_h)

    if src_aspect > dst_aspect:
        # Source is wider than target: crop horizontally around center
        new_w = int(src.height * dst_aspect)
        left = max(0, (src.width - new_w) // 2)
        cropped = src.crop((left, 0, left + new_w, src.height))
    else:
        # Source is taller than target: crop vertically around focus_y
        new_h = int(src.width / dst_aspect)
        center_y = int(src.height * focus_y)
        top = max(0, min(src.height - new_h, center_y - new_h // 2))
        cropped = src.crop((0, top, src.width, top + new_h))

    return cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)


def prepare_brand_logo(
    logo_path: Path,
    max_w: int,
    max_h: int,
    invert_to_white: bool = False,
) -> Optional[Image.Image]:
    """
    Loads a transparent brand logo/symbol, scales it proportionally within
    (max_w, max_h), and optionally tints opaque pixels pure white for dark UIs.
    """
    if not logo_path.exists():
        return None
    try:
        logo = Image.open(logo_path).convert("RGBA")
        bbox = logo.getbbox()
        if bbox:
            logo = logo.crop(bbox)
        scale = min(max_w / max(1, logo.width), max_h / max(1, logo.height))
        new_w = max(1, int(logo.width * scale))
        new_h = max(1, int(logo.height * scale))
        logo = logo.resize((new_w, new_h), Image.Resampling.LANCZOS)

        if invert_to_white:
            alpha = logo.split()[3]
            white_layer = Image.new("RGBA", logo.size, (255, 255, 255, 255))
            white_layer.putalpha(alpha)
            logo = white_layer
        return logo
    except Exception as e:
        logger.warning(f"Failed to prepare brand logo {logo_path}: {e}")
        return None


def compose_dual_brand_logo(
    left_logo: Path,
    right_logo: Path,
    out_path: Path,
    target_h: int = 90,
) -> Optional[Path]:
    """Combine two official brand PNGs side-by-side ('left vs right') for dark-slate thumbnails."""
    if not left_logo.exists() or not right_logo.exists():
        return None

    def _dark_mode(im: Image.Image) -> Image.Image:
        im = im.convert("RGBA")
        px = im.load()
        if px is not None:
            for y in range(im.height):
                for x in range(im.width):
                    pixel = px[x, y]
                    if isinstance(pixel, tuple) and len(pixel) >= 4:
                        r, g, b, a = int(pixel[0]), int(pixel[1]), int(pixel[2]), int(pixel[3])
                        if a > 20 and max(r, g, b) < 150 and (max(r, g, b) - min(r, g, b)) < 25:
                            px[x, y] = (245, 248, 255, a)
        bbox = im.getbbox()
        return im.crop(bbox) if bbox else im

    with Image.open(left_logo) as l_raw, Image.open(right_logo) as r_raw:
        l_im = _dark_mode(l_raw)
        r_im = _dark_mode(r_raw)
    l_r = l_im.resize((max(1, int(l_im.width * target_h / max(1, l_im.height))), target_h), Image.Resampling.LANCZOS)
    r_r = r_im.resize((max(1, int(r_im.width * target_h / max(1, r_im.height))), target_h), Image.Resampling.LANCZOS)
    gap, vs_w = 36, 80
    canvas = Image.new("RGBA", (l_r.width + r_r.width + vs_w + gap * 2, target_h + 24), (0, 0, 0, 0))
    canvas.paste(l_r, (0, 6), l_r)
    draw = ImageDraw.Draw(canvas)
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 46)
    except Exception:
        font = ImageFont.load_default()
    vs_x = l_r.width + gap
    draw.text((vs_x + 8, 22), "vs", font=font, fill=(250, 204, 21, 255))
    canvas.paste(r_r, (vs_x + vs_w + gap, 14), r_r)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "PNG")
    return out_path


def create_editorial_backdrop(
    w: int = 1920,
    h: int = 1080,
    accent_rgb: Tuple[int, int, int] = (217, 119, 87),
    danger_rgb: Tuple[int, int, int] = (220, 38, 38),
) -> Image.Image:
    """
    Creates a deep editorial dark-slate backdrop (#0B0F19) with subtle
    warm-terracotta left glow and crimson warning aura on the right.
    """
    canvas = Image.new("RGBA", (w, h), (11, 15, 25, 255))
    aura = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    adraw = ImageDraw.Draw(aura)

    # Left subject warm spotlight
    for r in [760, 560, 380, 220]:
        alpha = int(42 * (1.0 - r / 820.0))
        adraw.ellipse([420 - r, 340 - r, 420 + r, 340 + r], fill=accent_rgb + (alpha,))

    # Right reaction crimson aura
    for r in [720, 520, 340]:
        alpha = int(38 * (1.0 - r / 780.0))
        adraw.ellipse([1560 - r, 500 - r, 1560 + r, 500 + r], fill=danger_rgb + (alpha,))

    aura = aura.filter(ImageFilter.GaussianBlur(70))
    canvas = Image.alpha_composite(canvas, aura)

    # Subtle editorial grid lines for financial/dossier feel
    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grid)
    for gx in range(0, w, 120):
        gdraw.line([(gx, 0), (gx, h)], fill=(255, 255, 255, 10), width=1)
    for gy in range(0, h, 120):
        gdraw.line([(0, gy), (w, gy)], fill=(255, 255, 255, 10), width=1)
    canvas = Image.alpha_composite(canvas, grid)
    return canvas


def _draw_rounded_card_photo(
    canvas: Image.Image,
    photo_path: Path,
    box: Tuple[int, int, int, int],
    radius: int = 32,
    border_color: Tuple[int, int, int, int] = (217, 119, 87, 255),
    caption: str = "",
    font_path: Optional[str] = None,
    font_index: int = 0,
) -> None:
    """Renders a high-contrast editorial portrait card with drop shadow and optional caption."""
    x, y, card_w, card_h = box
    try:
        raw = Image.open(photo_path)
    except Exception as e:
        logger.warning(f"Failed to open subject photo {photo_path}: {e}")
        return

    cropped = crop_portrait_focus(raw, card_w, card_h, focus_y=0.25)
    cropped = ImageEnhance.Contrast(cropped).enhance(1.15)
    cropped = ImageEnhance.Color(cropped).enhance(1.08)

    # Bottom gradient fade inside card for caption/text legibility
    grad = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grad)
    for row in range(card_h // 2, card_h):
        t = (row - card_h // 2) / max(1, card_h // 2)
        gdraw.line([(0, row), (card_w, row)], fill=(8, 11, 20, int(195 * t)))
    cropped = Image.alpha_composite(cropped, grad)

    # Rounded mask
    mask = Image.new("L", (card_w, card_h), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle([0, 0, card_w, card_h], radius=radius, fill=255)

    # Drop shadow
    shadow = Image.new("RGBA", (card_w + 40, card_h + 40), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle([20, 20, card_w + 20, card_h + 20], radius=radius, fill=(0, 0, 0, 190))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas.paste(shadow, (x - 14, y - 6), shadow)

    # Paste rounded card
    canvas.paste(cropped, (x, y), mask)

    # Crisp border
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle([x, y, x + card_w, y + card_h], radius=radius, outline=border_color, width=5)

    if caption:
        cap_font = ImageFont.truetype(font_path, 34, index=font_index) if font_path else ImageFont.load_default()
        draw.text((x + 24, y + card_h - 54), caption, font=cap_font, fill=(241, 245, 249, 245))


def render_editorial_spotlight_layout(
    config: Any,
    font_path: Optional[str],
    font_index: int,
) -> Image.Image:
    """
    Renders the 'editorial_spotlight' layout:
    1. Real-world Subject Card (top-left) + Brand Logo/Symbol
    2. Ultra-concise Eyebrow + 2-line Auto-Fitted Fukuro Headline (bottom-left)
    3. Single High-Emotion Mascot Sticker (right, timestamp safe-zone protected)
    """
    from veraxi_ymmp.graphics.thumbnail import (
        resolve_character_face,
    )
    from veraxi_ymmp.graphics.thumbnail_composer import render_character_sticker

    w, h = config.width, config.height
    accent = (217, 119, 87)  # Anthropic terracotta coral
    bg_str = getattr(config, "bg_path", None)
    if bg_str and Path(bg_str).exists():
        with Image.open(bg_str) as bg_raw:
            canvas = crop_portrait_focus(bg_raw, w, h, focus_y=0.45)
        canvas = ImageEnhance.Brightness(canvas).enhance(0.75)
        scrim = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(scrim)
        for gx in range(0, int(w * 0.72)):
            alpha = int(165 * (1.0 - gx / (w * 0.72)))
            sdraw.line([(gx, 0), (gx, h)], fill=(8, 12, 22, alpha))
        canvas = Image.alpha_composite(canvas, scrim)
    else:
        canvas = create_editorial_backdrop(w, h, accent_rgb=accent, danger_rgb=(220, 38, 38))

    # 1. Optional subtle brand symbol watermark behind center-left
    symbol_path_str = getattr(config, "brand_symbol_path", None)
    if symbol_path_str:
        sym = prepare_brand_logo(Path(symbol_path_str), max_w=380, max_h=380, invert_to_white=False)
        if sym:
            sym_faded = sym.copy()
            r, g, b, a = sym_faded.split()
            a = a.point(lambda p: int(p * 0.14))
            sym_faded = Image.merge("RGBA", (r, g, b, a))
            canvas.paste(sym_faded, (780, 170), sym_faded)

    subject_str = getattr(config, "subject_image_path", None)
    subject_path = Path(subject_str) if isinstance(subject_str, (str, Path)) and subject_str else None
    has_subject = bool(subject_path and subject_path.exists())

    # 2. Right-side Mascot Sticker (single high-emotion close-up reaction)
    char_name = getattr(config, "character", "ずんだもん") or "ずんだもん"
    char_emo = getattr(config, "emotion", "surprised") or "surprised"
    char_mouth = getattr(config, "mouth_open", True)
    char_path = resolve_character_face(char_name, char_emo, char_mouth)
    char_left_x = w - 620

    if char_path and char_path.exists():
        base_h = 1380 if has_subject else 1880
        sticker = render_character_sticker(
            char_path,
            target_h=int(base_h * getattr(config, "character_scale", 1.0)),
            stroke_width=22,
            flip=False,
        )
        if sticker:
            cx = w - sticker["width"] + (140 if has_subject else 220)
            cy = 70 if has_subject else 30
            canvas.paste(sticker["shadow"], (cx - 14, cy + 20), sticker["shadow"])
            canvas.paste(sticker["rim"], (cx, cy), sticker["rim"])
            canvas.paste(sticker["resized"], (cx, cy), sticker["resized"])
            char_left_x = max(1060, cx + 60)

    # 3. Left-top Subject Anchor Card (CEO Portrait / Real Subject Photo)
    card_x, card_y, card_w, card_h = 70, 65, 500, 470
    if has_subject and subject_path is not None:
        _draw_rounded_card_photo(
            canvas,
            subject_path,
            box=(card_x, card_y, card_w, card_h),
            radius=28,
            border_color=(217, 119, 87, 255),
            caption=getattr(config, "subject_caption", "") or "",
            font_path=font_path,
            font_index=font_index,
        )

    # 4. Brand Logo & Stat Callout Panel (top-center next to portrait, or top-left)
    panel_x = card_x + card_w + 42 if has_subject else 70
    panel_max_w = max(360, char_left_x - panel_x - 30)
    draw = ImageDraw.Draw(canvas)
    _draw_brand_and_badges(canvas, draw, config, panel_x, panel_max_w, font_path, font_index, compact=has_subject)

    # 5. Colossal 2-Line Power Hook (auto-fitted, fills left canvas when no subject card)
    headline_max_w = max(500, char_left_x - 70 - 30)
    _draw_editorial_headline(draw, config, headline_max_w, font_path, font_index, has_subject=has_subject)
    return canvas


def _draw_brand_and_badges(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    config: Any,
    panel_x: int,
    panel_max_w: int,
    font_path: Optional[str],
    font_index: int,
    compact: bool = True,
) -> None:
    """Renders the brand wordmark, eyebrow pill, and optional stat callout."""
    from veraxi_ymmp.graphics.thumbnail import fit_font_to_width

    cur_y = 75 if compact else 95
    brand_str = getattr(config, "brand_logo_path", None)
    if brand_str and Path(brand_str).exists():
        logo_img = prepare_brand_logo(
            Path(brand_str),
            max_w=min(560 if compact else 760, panel_max_w),
            max_h=88 if compact else 140,
            invert_to_white=bool(getattr(config, "invert_brand_logo", True)),
        )
        if logo_img:
            canvas.paste(logo_img, (panel_x, cur_y), logo_img)
            cur_y += logo_img.height + 28

    eyebrow = getattr(config, "eyebrow_text", "") or getattr(config, "badge", "")
    if eyebrow:
        f_eye, _ = fit_font_to_width(eyebrow, 54, panel_max_w - 52, font_path, font_index)
        eb = f_eye.getbbox(eyebrow)
        ew = int(eb[2] - eb[0] + 52)
        eh = int(eb[3] - eb[1] + 34)
        draw.rounded_rectangle(
            [panel_x, cur_y, panel_x + ew, cur_y + eh],
            radius=16,
            fill=(220, 38, 38, 255),
            outline=(255, 255, 255, 255),
            width=4,
        )
        draw.text((panel_x + 26 - eb[0], cur_y + 17 - eb[1]), eyebrow, font=f_eye, fill=(255, 255, 255, 255))
        cur_y += eh + 24

    stat_text = getattr(config, "stat_callout", "")
    if stat_text:
        f_stat, _ = fit_font_to_width(stat_text, 58, panel_max_w - 48, font_path, font_index)
        sb = f_stat.getbbox(stat_text)
        sw = int(sb[2] - sb[0] + 48)
        sh = int(sb[3] - sb[1] + 34)
        draw.rounded_rectangle(
            [panel_x, cur_y, panel_x + sw, cur_y + sh],
            radius=16,
            fill=(15, 23, 42, 240),
            outline=(250, 204, 21, 255),
            width=4,
        )
        draw.text((panel_x + 24 - sb[0], cur_y + 17 - sb[1]), stat_text, font=f_stat, fill=(250, 204, 21, 255))


def _draw_editorial_headline(
    draw: ImageDraw.ImageDraw,
    config: Any,
    headline_max_w: int,
    font_path: Optional[str],
    font_index: int,
    has_subject: bool = True,
) -> None:
    """Renders the 2-line auto-fitted Fukuro headline with keyword jump-rate."""
    from veraxi_ymmp.graphics.thumbnail import draw_fukuro_text, fit_font_to_width

    t1 = getattr(config, "title_line1", "") or ""
    t2 = getattr(config, "title_line2", "") or ""
    hl = (getattr(config, "highlight_word", "") or "").strip()

    y_line1 = 560 if has_subject else 340
    max_s1 = 170 if has_subject else 260
    if t1:
        f1, s1 = fit_font_to_width(t1, max_s1, headline_max_w, font_path, font_index)
        sw1 = max(14, int(s1 * 0.14))
        draw_fukuro_text(draw, (70, y_line1), t1, f1, fill_color=(255, 255, 255, 255), stroke_w=sw1)

    y_line2 = 760 if has_subject else 620
    max_s2 = 200 if has_subject else 290
    if t2:
        f2, s2 = fit_font_to_width(t2, max_s2, headline_max_w, font_path, font_index, hl_word=hl)
        sw2 = max(16, int(s2 * 0.14))
        if hl and hl in t2:
            prefix, suffix = t2.split(hl, 1)
            cx = 70
            if prefix:
                draw_fukuro_text(draw, (cx, y_line2), prefix, f2, fill_color=(255, 255, 255, 255), stroke_w=sw2)
                pb = f2.getbbox(prefix)
                cx += int(pb[2] - pb[0]) + 8
            draw_fukuro_text(draw, (cx, y_line2), hl, f2, fill_color=(250, 204, 21, 255), stroke_w=sw2)
            hb = f2.getbbox(hl)
            cx += int(hb[2] - hb[0]) + 10
            if suffix:
                draw_fukuro_text(draw, (cx, y_line2), suffix, f2, fill_color=(255, 75, 75, 255), stroke_w=sw2)
        else:
            draw_fukuro_text(draw, (70, y_line2), t2, f2, fill_color=(250, 204, 21, 255), stroke_w=sw2)


def render_rival_fullbleed_layout(
    config: Any,
    font_path: Optional[str],
    font_index: int,
) -> Image.Image:
    """
    Renders the 'rival_fullbleed' layout modeled after top Japanese Zundamon
    finance/tech channels:
    1. Bright, unblurred full-bleed scene background (subtle bottom scrim only)
    2. Single high-emotion mascot sticker on the right (timestamp safe-zone clear)
    3. Massive 1-2 line yellow/white Fukuro headline strictly auto-fitted so it
       never collides with the character, with zero pill badges or small text.
    """
    from veraxi_ymmp.graphics.thumbnail import (
        draw_fukuro_text,
        fit_font_to_width,
        resolve_character_face,
    )
    from veraxi_ymmp.graphics.thumbnail_composer import render_character_sticker

    w, h = config.width, config.height
    bg_str = getattr(config, "bg_path", None)
    if bg_str and Path(bg_str).exists():
        canvas = Image.open(bg_str).convert("RGBA").resize((w, h), Image.Resampling.LANCZOS)
    else:
        canvas = create_editorial_backdrop(w, h, accent_rgb=(220, 38, 38), danger_rgb=(234, 179, 8))

    # Subtle bottom-only gradient scrim so lower headline pops without darkening the scene
    scrim = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(scrim)
    scrim_top = int(h * 0.52)
    for row in range(scrim_top, h):
        alpha = int(145 * ((row - scrim_top) / max(1, h - scrim_top)))
        sdraw.line([(0, row), (w, row)], fill=(5, 8, 16, alpha))
    canvas = Image.alpha_composite(canvas, scrim)

    # Right-side expressive mascot (no thick sticker rim over full-bleed scenes)
    char_name = getattr(config, "character", "ずんだもん") or "ずんだもん"
    char_emo = getattr(config, "emotion", "surprised") or "surprised"
    char_mouth = getattr(config, "mouth_open", True)
    char_path = resolve_character_face(char_name, char_emo, char_mouth)

    if char_path and char_path.exists():
        sticker = render_character_sticker(
            char_path,
            target_h=int(1280 * getattr(config, "character_scale", 1.0)),
            stroke_width=0,
            flip=False,
        )
        if sticker:
            cx = w - sticker["width"] + 90
            cy = 45
            canvas.paste(sticker["shadow"], (cx - 10, cy + 14), sticker["shadow"])
            canvas.paste(sticker["resized"], (cx, cy), sticker["resized"])

    draw = ImageDraw.Draw(canvas)
    # Span nearly full-width across the lower frame (in front of character's lower body)
    # so the headline stays massive and legible at mobile postage-stamp size.
    headline_max_w = w - 130
    t1 = (getattr(config, "title_line1", "") or "").strip()
    t2 = (getattr(config, "title_line2", "") or "").strip()

    if t1 and t2:
        f1, s1 = fit_font_to_width(t1, 165, headline_max_w, font_path, font_index)
        f2, s2 = fit_font_to_width(t2, 200, headline_max_w, font_path, font_index)
        draw_fukuro_text(draw, (65, 565), t1, f1, fill_color=(255, 255, 255, 255), stroke_w=max(14, int(s1 * 0.14)))
        draw_fukuro_text(draw, (65, 765), t2, f2, fill_color=(250, 204, 21, 255), stroke_w=max(16, int(s2 * 0.14)))
    elif t1 or t2:
        single = t1 or t2
        f, s = fit_font_to_width(single, 240, headline_max_w, font_path, font_index)
        draw_fukuro_text(draw, (65, 745), single, f, fill_color=(250, 204, 21, 255), stroke_w=max(18, int(s * 0.14)))

    return canvas
