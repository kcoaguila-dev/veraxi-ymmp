"""
Advanced Infographic and Diagram Presentation Board Renderers for veraxi_ymmp.

Extends the B-Roll presentation engine with rival-grade visual modalities:
1. Matrix Comparison Table (render_matrix_slide):
   Multi-dimensional enterprise comparison heatmaps (Pricing, Models, Lock-in, Margins).
2. Architecture / Value Chain Flow (render_architecture_flow_slide):
   Supply-chain and stack comparison diagrams (Silicon -> Cloud -> Model -> Customer).
3. Causal Domino Chain (render_domino_slide):
   Mechanistic domino chain reactions (Capex -> Depreciation -> FCF Depletion -> Multiples).

Adheres strictly to Clean Architecture, Pro Dark Slate (#0F172A), and cognitive load limits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple, Union


from .broll import (
    ACCENT_AMBER,
    ACCENT_BLUE,
    ACCENT_GREEN,
    ACCENT_RED,
    COLOR_BORDER,
    COLOR_SURFACE,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    _fit_font,
    _load_broll_font,
    check_cognitive_load,
    create_slide_base,
    get_pill_text_color,
    resolve_color,
)
from .logging import logger


def render_matrix_slide(
    out_path: Union[str, Path],
    title: str,
    columns: List[str],  # [Dimension Header, Left Entity Name, Right Entity Name]
    rows: List[Dict[str, Any]],  # [{"label": "価格体系", "left": "...", "right": "...", "advantage": "right"}]
    bottom_tag: str = "結論",
    bottom_text: str = "",
    step_tag: str = "戦略比較",
    theme_color: Union[str, Tuple[int, int, int]] = ACCENT_BLUE,
    is_vertical: bool = False,
) -> Path:
    """
    Renders an authoritative Enterprise Comparison Matrix / Heatmap slide.
    Replaces repetitive 2-box VS slides with high-density, structured evaluation tables.
    """
    col = resolve_color(theme_color)
    flat_texts = [title, step_tag, bottom_tag, bottom_text] + list(columns)
    for r in rows:
        flat_texts.append(f"{r.get('label', '')}: {r.get('left', '')} / {r.get('right', '')}")

    check_cognitive_load(
        title,
        flat_texts,
        max_chars=200,
        max_elements=16,
    )

    img, draw, fonts = create_slide_base(title, step_tag=step_tag, theme_color=col, is_vertical=is_vertical)
    x1, x2 = (56, 1024) if is_vertical else (70, 1340)

    # Table Geometry
    table_y1 = 145 if not is_vertical else 135
    row_count = min(len(rows), 4)
    row_h = 80 if not is_vertical else 72
    table_y2 = table_y1 + 54 + (row_count * row_h)

    # Table Container Box
    draw.rounded_rectangle([x1, table_y1, x2, table_y2], radius=16, fill=(20, 29, 47, 255), outline=COLOR_BORDER, width=2)
    draw.rounded_rectangle([x1, table_y1, x1 + 10, table_y2], radius=4, fill=col)

    # Column Widths
    w_total = x2 - x1
    col0_w = int(w_total * 0.24)
    col1_w = int((w_total - col0_w) * 0.50)
    col2_w = w_total - col0_w - col1_w

    c0_x = x1 + 24
    c1_x = x1 + col0_w
    c2_x = c1_x + col1_w

    # 1. Header Row
    head_h = 54
    draw.rounded_rectangle([x1, table_y1, x2, table_y1 + head_h], radius=16, fill=COLOR_SURFACE)
    draw.line([(x1, table_y1 + head_h), (x2, table_y1 + head_h)], fill=COLOR_BORDER, width=2)

    f_th = fonts["badge"]
    f_th_ent = _load_broll_font(26, bold=True)
    th_y = table_y1 + head_h // 2

    # Dimension Title
    draw.text((c0_x, th_y), columns[0] if len(columns) > 0 else "比較項目", font=f_th, fill=COLOR_TEXT_SECONDARY, anchor="lm")

    # Entity A (e.g., MSFT / Copilot)
    ent_left = columns[1] if len(columns) > 1 else "マイクロソフト"
    draw.text((c1_x + 18, th_y), ent_left, font=f_th_ent, fill=ACCENT_BLUE, anchor="lm")

    # Entity B (e.g., AMZN / Bedrock)
    ent_right = columns[2] if len(columns) > 2 else "アマゾン"
    draw.text((c2_x + 18, th_y), ent_right, font=f_th_ent, fill=ACCENT_AMBER, anchor="lm")

    # 2. Data Rows
    f_lbl = _load_broll_font(24, bold=True)
    f_val = _load_broll_font(22, bold=False)
    f_val_bold = _load_broll_font(22, bold=True)

    for idx, rdata in enumerate(rows[:row_count]):
        ry1 = table_y1 + head_h + (idx * row_h)
        ry2 = ry1 + row_h
        rcy = (ry1 + ry2) // 2

        # Subtle row zebra / divider
        if idx % 2 == 1:
            draw.rectangle([x1 + 10, ry1, x2, ry2], fill=(24, 34, 54, 255))
        if idx < row_count - 1:
            draw.line([(x1 + 16, ry2), (x2 - 16, ry2)], fill=(51, 65, 85, 255), width=1)

        # Label Pill
        lbl_txt = str(rdata.get("label", ""))
        draw.text((c0_x, rcy), lbl_txt, font=f_lbl, fill=COLOR_TEXT_PRIMARY, anchor="lm")

        # Left Value & Right Value
        l_val = str(rdata.get("left", ""))
        r_val = str(rdata.get("right", ""))
        adv = str(rdata.get("advantage", "")).lower()

        # Advantage highlighting
        l_color = ACCENT_GREEN if adv in ("left", "msft", "copilot") else (ACCENT_RED if adv in ("right", "aws", "amzn") else COLOR_TEXT_PRIMARY)
        r_color = ACCENT_GREEN if adv in ("right", "aws", "amzn") else (ACCENT_RED if adv in ("left", "msft", "copilot") else COLOR_TEXT_PRIMARY)

        # Render Left Value
        l_font = _fit_font(draw, l_val, f_val_bold if adv in ("left", "msft") else f_val, max_width=col1_w - 36, base_size=22, min_size=17)
        draw.text((c1_x + 18, rcy), l_val, font=l_font, fill=l_color, anchor="lm")

        # Render Right Value
        r_font = _fit_font(draw, r_val, f_val_bold if adv in ("right", "aws", "amzn") else f_val, max_width=col2_w - 36, base_size=22, min_size=17)
        draw.text((c2_x + 18, rcy), r_val, font=r_font, fill=r_color, anchor="lm")

    # 3. Bottom Takeaway Card
    if bottom_text:
        bot_y1, bot_y2 = (table_y2 + 20, table_y2 + 105) if not is_vertical else (585, 685)
        bot_cy = (bot_y1 + bot_y2) // 2
        draw.rounded_rectangle([x1, bot_y1, x2, bot_y2], radius=14, fill=COLOR_SURFACE, outline=col, width=2)
        draw.rounded_rectangle([x1, bot_y1, x1 + 8, bot_y2], radius=4, fill=col)

        if bottom_tag:
            tag_w = max(draw.textlength(bottom_tag, font=fonts["badge"]) + 32, 90)
            draw.rounded_rectangle([x1 + 24, bot_y1 + 18, x1 + 24 + tag_w, bot_y2 - 18], radius=8, fill=col)
            draw.text((x1 + 24 + tag_w // 2, bot_cy), bottom_tag, font=fonts["badge"], fill=get_pill_text_color(col), anchor="mm")
            txt_x = x1 + 42 + tag_w
        else:
            txt_x = x1 + 32
        fn_bot = _fit_font(draw, bottom_text, fonts["footer"], max_width=float(x2 - txt_x - 24), base_size=28, min_size=19)
        draw.text((txt_x, bot_cy), bottom_text, font=fn_bot, fill=COLOR_TEXT_PRIMARY, anchor="lm")

    if not is_vertical:
        img.putalpha(255)
    out_file = Path(out_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_file)
    logger.info("Saved matrix slide: %s", out_file)
    return out_file


def render_architecture_flow_slide(
    out_path: Union[str, Path],
    title: str,
    routes: List[Dict[str, Any]],  # 2 routes: [{"name": "MSFT", "color": "blue", "steps": [{"node": "NVIDIA GPU", "sub": "高額上納金"}], "takeaway": "粗利圧迫"}]
    step_tag: str = "調達構造",
    bottom_tag: str = "勝敗の分岐点",
    bottom_text: str = "",
    theme_color: Union[str, Tuple[int, int, int]] = ACCENT_BLUE,
    is_vertical: bool = False,
) -> Path:
    """
    Renders a High-Contrast Dual Value-Chain Architecture Flow diagram.
    Contrasts multi-tier supply chains (External GPU dependance vs Vertical custom silicon).
    """
    col = resolve_color(theme_color)
    flat_texts = [title, step_tag, bottom_tag, bottom_text]
    for route in routes:
        flat_texts.append(str(route.get("name", "")))
        if route.get("takeaway"):
            flat_texts.append(str(route.get("takeaway", "")))
        for s in route.get("steps", []):
            if s.get("sub"):
                flat_texts.append(f"{s.get('node', '')} ({s.get('sub', '')})")
            else:
                flat_texts.append(str(s.get("node", "")))

    check_cognitive_load(
        title,
        flat_texts,
        max_chars=180,
        max_elements=16,
    )

    img, draw, fonts = create_slide_base(title, step_tag=step_tag, theme_color=col, is_vertical=is_vertical)
    x1, x2 = (56, 1024) if is_vertical else (70, 1340)

    # 2 Routes stacked vertically
    r_h = 195 if not is_vertical else 180
    r_gap = 24
    top_y = 145 if not is_vertical else 135

    f_route_title = _load_broll_font(26, bold=True)
    f_node_title = _load_broll_font(22, bold=True)
    f_node_sub = _load_broll_font(17, bold=False)

    for idx, rdata in enumerate(routes[:2]):
        ry1 = top_y + idx * (r_h + r_gap)
        ry2 = ry1 + r_h
        rcol = resolve_color(rdata.get("color", col))

        # Route container
        draw.rounded_rectangle([x1, ry1, x2, ry2], radius=16, fill=(20, 29, 47, 255), outline=rcol, width=2)
        draw.rounded_rectangle([x1, ry1, x1 + 10, ry2], radius=4, fill=rcol)

        # Route Header Tag (Left badge)
        r_name = str(rdata.get("name", f"ルート {idx+1}"))
        nw = draw.textlength(r_name, font=f_route_title) + 28
        draw.rounded_rectangle([x1 + 24, ry1 + 14, x1 + 24 + nw, ry1 + 52], radius=8, fill=rcol)
        draw.text((x1 + 24 + nw // 2, ry1 + 33), r_name, font=f_route_title, fill=get_pill_text_color(rcol), anchor="mm")

        # Route Sub-takeaway (Right aligned)
        r_sub = str(rdata.get("takeaway", ""))
        if r_sub:
            draw.text((x2 - 24, ry1 + 33), r_sub, font=f_node_title, fill=rcol, anchor="rm")

        # Pipeline Steps
        steps = rdata.get("steps", [])
        n_steps = max(len(steps), 1)
        avail_w = (x2 - x1) - 48
        arrow_w = 36
        total_arrow_w = (n_steps - 1) * arrow_w
        box_w = (avail_w - total_arrow_w) // n_steps

        step_y1 = ry1 + 68
        step_y2 = ry2 - 20
        step_cy = (step_y1 + step_y2) // 2

        cur_bx = x1 + 24
        for s_idx, st in enumerate(steps):
            bx2 = cur_bx + box_w
            # Step Node Card
            draw.rounded_rectangle([cur_bx, step_y1, bx2, step_y2], radius=10, fill=COLOR_SURFACE, outline=COLOR_BORDER, width=1)

            node_txt = str(st.get("node", ""))
            sub_txt = str(st.get("sub", ""))

            if sub_txt:
                fn_txt = _fit_font(draw, node_txt, f_node_title, max_width=box_w - 16, base_size=22, min_size=16)
                draw.text(((cur_bx + bx2) // 2, step_cy - 12), node_txt, font=fn_txt, fill=COLOR_TEXT_PRIMARY, anchor="mm")
                fn_sub = _fit_font(draw, sub_txt, f_node_sub, max_width=box_w - 16, base_size=17, min_size=13)
                draw.text(((cur_bx + bx2) // 2, step_cy + 16), sub_txt, font=fn_sub, fill=COLOR_TEXT_SECONDARY, anchor="mm")
            else:
                fn_txt = _fit_font(draw, node_txt, f_node_title, max_width=box_w - 16, base_size=24, min_size=16)
                draw.text(((cur_bx + bx2) // 2, step_cy), node_txt, font=fn_txt, fill=COLOR_TEXT_PRIMARY, anchor="mm")

            # Arrow to next step (crisp vector polygon, zero font tofu)
            if s_idx < n_steps - 1:
                arr_x = bx2 + arrow_w // 2
                draw.polygon(
                    [(arr_x - 7, step_cy - 9), (arr_x + 9, step_cy), (arr_x - 7, step_cy + 9)],
                    fill=COLOR_BORDER,
                )

            cur_bx = bx2 + arrow_w

    # Bottom Impact Card
    if bottom_text:
        bot_y1, bot_y2 = (top_y + 2 * (r_h + r_gap), top_y + 2 * (r_h + r_gap) + 80) if not is_vertical else (585, 685)
        bot_cy = (bot_y1 + bot_y2) // 2
        draw.rounded_rectangle([x1, bot_y1, x2, bot_y2], radius=14, fill=COLOR_SURFACE, outline=col, width=2)
        draw.rounded_rectangle([x1, bot_y1, x1 + 8, bot_y2], radius=4, fill=col)

        if bottom_tag:
            tag_w = max(draw.textlength(bottom_tag, font=fonts["badge"]) + 32, 90)
            draw.rounded_rectangle([x1 + 24, bot_y1 + 16, x1 + 24 + tag_w, bot_y2 - 16], radius=8, fill=col)
            draw.text((x1 + 24 + tag_w // 2, bot_cy), bottom_tag, font=fonts["badge"], fill=get_pill_text_color(col), anchor="mm")
            txt_x = x1 + 42 + tag_w
        else:
            txt_x = x1 + 32
        fn_bot = _fit_font(draw, bottom_text, fonts["footer"], max_width=float(x2 - txt_x - 24), base_size=28, min_size=19)
        draw.text((txt_x, bot_cy), bottom_text, font=fn_bot, fill=COLOR_TEXT_PRIMARY, anchor="lm")

    if not is_vertical:
        img.putalpha(255)
    out_file = Path(out_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_file)
    logger.info("Saved architecture flow slide: %s", out_file)
    return out_file


def render_domino_slide(
    out_path: Union[str, Path],
    title: str,
    stages: List[Dict[str, Any]],  # 4 stages: [{"num": "01", "title": "巨額設備投資", "sub": "年60兆円 Capex", "color": "amber"}]
    bottom_tag: str = "結末",
    bottom_text: str = "",
    step_tag: str = "因果連鎖",
    theme_color: Union[str, Tuple[int, int, int]] = ACCENT_RED,
    is_vertical: bool = False,
) -> Path:
    """
    Renders a Lehman-Style Mechanistic Domino Causality Chain slide.
    Visualizes the structural trap (Investment -> Fixed Cost -> FCF Depletion -> Multiples).
    """
    col = resolve_color(theme_color)
    flat_texts = [title, step_tag, bottom_tag, bottom_text]
    for st in stages:
        flat_texts.append(f"{st.get('num', '')}. {st.get('title', '')} ({st.get('sub', '')})")

    check_cognitive_load(
        title,
        flat_texts,
        max_chars=140,
        max_elements=16,
    )

    img, draw, fonts = create_slide_base(title, step_tag=step_tag, theme_color=col, is_vertical=is_vertical)
    x1, x2 = (56, 1024) if is_vertical else (70, 1340)

    # 4 Domino Stage Cards arranged horizontally
    n = max(len(stages), 1)
    arrow_w = 28 if not is_vertical else 16
    avail_w = (x2 - x1) - ((n - 1) * arrow_w)
    card_w = avail_w // n

    c_y1 = 160 if not is_vertical else 150
    c_y2 = 540 if not is_vertical else 510

    f_num = _load_broll_font(38, bold=True)
    f_stage_title = _load_broll_font(26, bold=True)
    f_stage_sub = _load_broll_font(20, bold=False)

    cur_x = x1
    for idx, sdata in enumerate(stages[:n]):
        bx2 = cur_x + card_w
        scol = resolve_color(sdata.get("color", col))

        # Card Container
        draw.rounded_rectangle([cur_x, c_y1, bx2, c_y2], radius=16, fill=(20, 29, 47, 255), outline=scol, width=2)
        draw.rounded_rectangle([cur_x, c_y1, bx2, c_y1 + 10], radius=4, fill=scol)

        # Stage Number Pill
        num_str = str(sdata.get("num", f"0{idx+1}"))
        num_w = draw.textlength(num_str, font=f_num) + 24
        draw.rounded_rectangle([cur_x + 20, c_y1 + 24, cur_x + 20 + num_w, c_y1 + 74], radius=10, fill=scol)
        draw.text((cur_x + 20 + num_w // 2, c_y1 + 49), num_str, font=f_num, fill=get_pill_text_color(scol), anchor="mm")

        # Stage Title
        st_title = str(sdata.get("title", ""))
        fn_title = _fit_font(draw, st_title, f_stage_title, max_width=card_w - 36, base_size=26, min_size=18)
        draw.text((cur_x + 20, c_y1 + 115), st_title, font=fn_title, fill=COLOR_TEXT_PRIMARY, anchor="lm")

        # Stage Subtext / Metric
        st_sub = str(sdata.get("sub", ""))
        if st_sub:
            fn_sub = _fit_font(draw, st_sub, f_stage_sub, max_width=card_w - 36, base_size=20, min_size=15)
            draw.text((cur_x + 20, c_y1 + 180), st_sub, font=fn_sub, fill=scol, anchor="lm")

        # Arrow to next stage (crisp vector polygon, zero font tofu)
        if idx < n - 1:
            arr_cx = bx2 + arrow_w // 2
            mid_stage_y = (c_y1 + c_y2) // 2
            draw.polygon(
                [(arr_cx - 8, mid_stage_y - 11), (arr_cx + 10, mid_stage_y), (arr_cx - 8, mid_stage_y + 11)],
                fill=COLOR_BORDER,
            )

        cur_x = bx2 + arrow_w

    # Bottom Impact Card
    if bottom_text:
        bot_y1, bot_y2 = (575, 685) if not is_vertical else (540, 680)
        bot_cy = (bot_y1 + bot_y2) // 2
        draw.rounded_rectangle([x1, bot_y1, x2, bot_y2], radius=14, fill=COLOR_SURFACE, outline=col, width=2)
        draw.rounded_rectangle([x1, bot_y1, x1 + 8, bot_y2], radius=4, fill=col)

        if bottom_tag:
            tag_w = max(draw.textlength(bottom_tag, font=fonts["badge"]) + 32, 90)
            draw.rounded_rectangle([x1 + 24, bot_y1 + 18, x1 + 24 + tag_w, bot_y2 - 18], radius=8, fill=col)
            draw.text((x1 + 24 + tag_w // 2, bot_cy), bottom_tag, font=fonts["badge"], fill=get_pill_text_color(col), anchor="mm")
            txt_x = x1 + 42 + tag_w
        else:
            txt_x = x1 + 32
        fn_bot = _fit_font(draw, bottom_text, fonts["footer"], max_width=float(x2 - txt_x - 24), base_size=28, min_size=19)
        draw.text((txt_x, bot_cy), bottom_text, font=fn_bot, fill=COLOR_TEXT_PRIMARY, anchor="lm")

    if not is_vertical:
        img.putalpha(255)
    out_file = Path(out_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_file)
    logger.info("Saved domino causality slide: %s", out_file)
    return out_file


def render_infographic_slide(
    stype: str,
    spec: Dict[str, Any],
    dest: Path,
    theme_color: Tuple[int, int, int],
    is_vertical: bool,
) -> bool:
    """Dispatches declarative spec to specialized infographic renderers."""
    if stype == "matrix":
        render_matrix_slide(
            out_path=dest,
            title=spec.get("title", ""),
            columns=spec.get("columns", ["比較項目", "Microsoft", "Amazon"]),
            rows=spec.get("rows", []),
            bottom_tag=spec.get("bottom_tag", "結論"),
            bottom_text=spec.get("bottom_text", ""),
            step_tag=spec.get("step_tag", "戦略比較"),
            theme_color=theme_color,
            is_vertical=is_vertical,
        )
        return True
    elif stype in ("flow", "architecture", "value_chain"):
        render_architecture_flow_slide(
            out_path=dest,
            title=spec.get("title", ""),
            routes=spec.get("routes", []),
            step_tag=spec.get("step_tag", "調達構造"),
            bottom_tag=spec.get("bottom_tag", "勝敗の分岐点"),
            bottom_text=spec.get("bottom_text", ""),
            theme_color=theme_color,
            is_vertical=is_vertical,
        )
        return True
    elif stype in ("domino", "causality", "chain"):
        render_domino_slide(
            out_path=dest,
            title=spec.get("title", ""),
            stages=spec.get("stages", []),
            bottom_tag=spec.get("bottom_tag", "結末"),
            bottom_text=spec.get("bottom_text", ""),
            step_tag=spec.get("step_tag", "因果連鎖"),
            theme_color=theme_color,
            is_vertical=is_vertical,
        )
        return True
    return False
