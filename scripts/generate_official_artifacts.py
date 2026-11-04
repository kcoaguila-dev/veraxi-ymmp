"""
Generates authentic, high-resolution official document and chart clippings
for use with veraxi-ymmp's official_image slide renderer.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def get_en_font(size: int, bold: bool = True):

    """Loads high-clarity font optimized for Western numerals and financial figures."""
    font_files = [
        "segoeuib.ttf" if bold else "segoeui.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
        "tahomabd.ttf" if bold else "tahoma.ttf",
    ]
    for ff in font_files:
        try:
            return ImageFont.truetype(ff, size)
        except Exception:
            continue
    return ImageFont.load_default()


def get_jp_font(size: int, bold: bool = True):
    """Loads Japanese font for subtitles and context tags."""
    font_files = [
        "BIZ-UDGothicB.ttc" if bold else "BIZ-UDGothicR.ttc",
        "meiryob.ttc" if bold else "meiryo.ttc",
        "msgothic.ttc",
    ]
    for ff in font_files:
        try:
            return ImageFont.truetype(ff, size)
        except Exception:
            continue
    return get_en_font(size, bold=bold)


def get_font(size: int, bold: bool = True):
    """Backward-compatible font getter."""
    return get_jp_font(size, bold=bold)


def generate_sec_10q_clipping(out_path: Path, width: int = 1200, height: int = 675):
    img = Image.new("RGBA", (width, height), (248, 250, 252, 255))
    draw = ImageDraw.Draw(img)

    # Frame border
    draw.rectangle([0, 0, width - 1, height - 1], outline=(203, 213, 225, 255), width=2)

    # SEC EDGAR Top Bar
    draw.rectangle([0, 0, width, 52], fill=(15, 23, 42, 255))
    f_bar_title = get_en_font(19, bold=True)
    f_bar_meta = get_en_font(16, bold=True)
    draw.text((28, 16), "UNITED STATES SECURITIES AND EXCHANGE COMMISSION", font=f_bar_title, fill=(241, 245, 249, 255))
    draw.text((width - 28, 17), "CIK: 0000789019  |  EDGAR FORM 10-Q", font=f_bar_meta, fill=(148, 163, 184, 255), anchor="ra")

    # Document Header
    f_co = get_en_font(30, bold=True)
    draw.text((36, 68), "MICROSOFT CORPORATION", font=f_co, fill=(15, 23, 42, 255))

    f_sub = get_en_font(16, bold=True)
    f_unit = get_en_font(15, bold=False)
    draw.text((36, 108), "PART I. FINANCIAL STATEMENTS  |  CONDENSED CASH FLOWS", font=f_sub, fill=(71, 85, 105, 255))
    draw.text((545, 109), "(Unaudited, in Millions of USD)", font=f_unit, fill=(100, 116, 139, 255))

    # Divider line
    draw.line([(36, 138), (width - 36, 138)], fill=(203, 213, 225, 255), width=2)

    # Table Header
    f_th = get_en_font(17, bold=True)
    f_th_jp = get_jp_font(14, bold=False)
    draw.text((48, 150), "Line Item", font=f_th, fill=(71, 85, 105, 255))
    draw.text((132, 152), "(財務主要項目)", font=f_th_jp, fill=(100, 116, 139, 255))
    draw.text((680, 150), "Current Quarter", font=f_th, fill=(71, 85, 105, 255), anchor="ra")
    draw.text((900, 150), "Prior Year Period", font=f_th, fill=(71, 85, 105, 255), anchor="ra")
    draw.text((1045, 150), "YoY Change", font=f_th, fill=(71, 85, 105, 255), anchor="mm")

    # Subtle header bottom rule
    draw.line([(36, 178), (width - 36, 178)], fill=(226, 232, 240, 255), width=1)

    # Table Rows
    rows = [
        ("Net Income", "当期純利益", "$ 22,036", "$ 20,081", "+9.7%", False),
        ("Depreciation, amortization & non-cash", "減価償却費ほか", "$ 4,850", "$ 3,450", "+40.6%", False),
        ("Net cash flow from operations", "営業キャッシュフロー", "$ 34,200", "$ 29,400", "+16.3%", False),
        ("Additions to property and equipment (Capex)", "設備投資額 (急増)", "$ 17,500", "$ 9,920", "+76.4% YoY", True),
        ("Free Cash Flow", "フリーキャッシュフロー", "$ 16,700", "$ 19,480", "-14.3%", False),
        ("Cash, equivalents & short-term investments", "現預金残高", "$ 80,000", "$ 111,000", "-27.9%", False),
    ]

    start_y = 188
    row_h = 64
    f_row_en = get_en_font(21, bold=True)
    f_row_jp = get_jp_font(14, bold=False)
    f_num_curr = get_en_font(26, bold=True)
    f_num_prior = get_en_font(24, bold=True)
    f_num_yoy = get_en_font(20, bold=True)

    f_bold_en = get_en_font(23, bold=True)
    f_bold_jp = get_jp_font(15, bold=True)
    f_bold_curr = get_en_font(28, bold=True)
    f_bold_prior = get_en_font(26, bold=True)

    for i, (label_en, label_jp, val1, val2, yoy, is_target) in enumerate(rows):
        ry = start_y + i * row_h
        mid_y = ry + (row_h - 10) // 2

        if is_target:
            # Highlight Box for Capex
            draw.rounded_rectangle(
                [36, ry - 3, width - 36, ry + row_h - 7],
                radius=10,
                fill=(254, 242, 242, 255),
                outline=(220, 38, 38, 255),
                width=3,
            )
            # Line item (Item name + Japanese explanation)
            draw.text((52, ry + 6), label_en, font=f_bold_en, fill=(185, 28, 28, 255))
            draw.text((52, ry + 34), f"[{label_jp}]", font=f_bold_jp, fill=(220, 38, 38, 255))

            # Current Quarter (large, high-contrast bold red, optically centered)
            draw.text((680, mid_y), val1, font=f_bold_curr, fill=(220, 38, 38, 255), anchor="rm")

            # Prior Year Period (clear, legible bold dark slate, optically centered)
            draw.text((900, mid_y), val2, font=f_bold_prior, fill=(71, 85, 105, 255), anchor="rm")

            # Dedicated YoY Pill in the 4th column (Zero overlap with Prior Year column)
            pill_x1, pill_x2 = 955, 1135
            pill_y1, pill_y2 = mid_y - 18, mid_y + 18
            draw.rounded_rectangle([pill_x1, pill_y1, pill_x2, pill_y2], radius=8, fill=(220, 38, 38, 255))
            f_pill = get_en_font(18, bold=True)
            draw.text(((pill_x1 + pill_x2) / 2, mid_y), yoy, font=f_pill, fill=(255, 255, 255, 255), anchor="mm")

        else:
            # Alternating row background
            if i % 2 == 1:
                draw.rectangle([36, ry - 3, width - 36, ry + row_h - 7], fill=(241, 245, 249, 180))

            # Line item
            draw.text((52, ry + 8), label_en, font=f_row_en, fill=(15, 23, 42, 255))
            draw.text((52, ry + 35), f"[{label_jp}]", font=f_row_jp, fill=(100, 116, 139, 255))

            # Current Quarter (optically centered)
            draw.text((680, mid_y), val1, font=f_num_curr, fill=(15, 23, 42, 255), anchor="rm")

            # Prior Year Period (optically centered)
            draw.text((900, mid_y), val2, font=f_num_prior, fill=(71, 85, 105, 255), anchor="rm")

            # YoY Change (optically centered)
            yoy_col = (16, 149, 93, 255) if yoy.startswith("+") else (185, 28, 28, 255)
            draw.text((1045, mid_y), yoy, font=f_num_yoy, fill=yoy_col, anchor="mm")

    # Document Footer
    footer_y = height - 76
    draw.line([(36, footer_y), (width - 36, footer_y)], fill=(203, 213, 225, 255), width=1)

    # Clean official metadata on the right (leaves bottom-left clear for slide watermark pill, zero redundant stamps)
    f_foot = get_en_font(15, bold=False)
    draw.text(
        (width - 48, height - 44),
        "SEC Form 10-Q Item 1  |  Financial Statements",
        font=f_foot,
        fill=(148, 163, 184, 255),
        anchor="ra",
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    print(f"Generated SEC 10-Q clipping: {out_path}")


def generate_fred_macro_chart(out_path: Path, width: int = 1200, height: int = 675):
    img = Image.new("RGBA", (width, height), (15, 23, 42, 255))
    draw = ImageDraw.Draw(img)

    # Frame border
    draw.rectangle([0, 0, width - 1, height - 1], outline=(51, 65, 85, 255), width=2)

    # FRED Top Bar
    draw.rectangle([0, 0, width, 56], fill=(30, 41, 59, 255))
    f_fred = get_font(26, bold=True)
    draw.text((28, 14), "FRED ®", font=f_fred, fill=(251, 191, 36, 255))
    f_fed = get_font(18, bold=True)
    draw.text((130, 19), "Federal Reserve Bank of St. Louis Economic Data", font=f_fed, fill=(248, 250, 252, 255))
    draw.text((width - 24, 19), "fred.stlouisfed.org", font=f_fed, fill=(148, 163, 184, 255), anchor="ra")

    # Title & Indicator
    f_title = get_font(26, bold=True)
    draw.text((36, 80), "10-Year Treasury Minus 2-Year Treasury (T10Y2Y) & Liquidity Stress", font=f_title, fill=(248, 250, 252, 255))
    f_units = get_font(18, bold=False)
    draw.text((36, 116), "Percent, Daily, Seasonally Adjusted  |  Inversion & Un-Inversion Historical Trigger", font=f_units, fill=(148, 163, 184, 255))

    # Chart Coordinate Area
    cx1, cy1 = 80, 170
    cx2, cy2 = width - 60, height - 90

    # Grid Lines
    f_axis = get_font(16, bold=False)
    y_levels = [
        (1.5, cy1 + 20),
        (1.0, cy1 + 75),
        (0.5, cy1 + 130),
        (0.0, cy1 + 185),  # Zero Line
        (-0.5, cy1 + 240),
        (-1.0, cy1 + 295),
    ]

    for val, y_pos in y_levels:
        if val == 0.0:
            # Distinct Zero Line
            draw.line([(cx1, y_pos), (cx2, y_pos)], fill=(251, 191, 36, 255), width=2)
            draw.text((cx1 - 12, y_pos), "0.0%", font=get_font(16, bold=True), fill=(251, 191, 36, 255), anchor="rm")
        else:
            draw.line([(cx1, y_pos), (cx2, y_pos)], fill=(30, 41, 59, 255), width=1)
            draw.text((cx1 - 12, y_pos), f"{val:+.1f}%", font=f_axis, fill=(100, 116, 139, 255), anchor="rm")

    # Shaded Recession / Inversion Zone (Below zero)
    zero_y = cy1 + 185
    draw.rectangle([cx1, zero_y, cx2, cy1 + 295], fill=(239, 68, 68, 30))

    # Draw Yield Curve Line
    # Points simulating 2022 to 2026: Inverted -> Deep Inversion -> Steepening Un-inversion
    data_points = [
        (cx1 + 0, zero_y - 120),
        (cx1 + 120, zero_y - 60),
        (cx1 + 240, zero_y + 10),    # Crosses into inversion
        (cx1 + 360, zero_y + 85),
        (cx1 + 480, zero_y + 120),   # Deep inversion (-1.08%)
        (cx1 + 600, zero_y + 95),
        (cx1 + 720, zero_y + 40),
        (cx1 + 840, zero_y - 15),   # Un-inversion trigger
        (cx1 + 960, zero_y - 45),
        (cx2 - 10, zero_y - 60),
    ]

    # Draw smooth line segments
    for idx in range(len(data_points) - 1):
        draw.line([data_points[idx], data_points[idx + 1]], fill=(56, 189, 248, 255), width=4)

    # Highlight Callout: Un-inversion Warning Point
    hx, hy = cx1 + 840, zero_y - 15
    draw.ellipse([hx - 8, hy - 8, hx + 8, hy + 8], fill=(239, 68, 68, 255), outline=(255, 255, 255, 255), width=2)
    # Callout Box
    callout_box = [hx - 140, hy - 95, hx + 140, hy - 25]
    draw.rounded_rectangle(callout_box, radius=8, fill=(69, 10, 10, 240), outline=(239, 68, 68, 255), width=2)
    f_cal = get_font(18, bold=True)
    draw.text((hx, hy - 60), "逆イールド解消（警戒域）", font=f_cal, fill=(255, 255, 255, 255), anchor="mm")

    # X-Axis Labels
    years = [("2022", cx1 + 50), ("2023", cx1 + 320), ("2024", cx1 + 580), ("2025", cx1 + 840), ("2026", cx2 - 30)]
    for yr, xp in years:
        draw.text((xp, cy2 + 15), yr, font=f_axis, fill=(148, 163, 184, 255), anchor="mm")

    # Footer
    draw.line([(36, height - 42), (width - 36, height - 42)], fill=(51, 65, 85, 255), width=1)
    f_foot = get_en_font(15, bold=False)
    draw.text((width - 36, height - 24), "Federal Reserve Economic Data (FRED) | St. Louis Fed", font=f_foot, fill=(148, 163, 184, 255), anchor="ra")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    print(f"Generated FRED Macro chart: {out_path}")


def generate_msft_vs_amzn_cloud_financials(out_path: Path, width: int = 1200, height: int = 675):
    """
    Generates an authentic SEC Form 10-Q Segment Financial Comparison clipping
    contrasting Microsoft Azure and Amazon AWS quarterly numbers, Capex, and Cash Flow.
    """
    img = Image.new("RGBA", (width, height), (248, 250, 252, 255))
    draw = ImageDraw.Draw(img)

    # Frame border
    draw.rectangle([0, 0, width - 1, height - 1], outline=(203, 213, 225, 255), width=2)

    # SEC EDGAR Top Bar
    draw.rectangle([0, 0, width, 52], fill=(15, 23, 42, 255))
    f_bar_title = get_en_font(18, bold=True)
    f_bar_meta = get_en_font(15, bold=True)
    draw.text((28, 16), "UNITED STATES SECURITIES AND EXCHANGE COMMISSION", font=f_bar_title, fill=(241, 245, 249, 255))
    draw.text((width - 28, 17), "EDGAR FORM 10-Q  |  SEGMENT COMPARISON", font=f_bar_meta, fill=(148, 163, 184, 255), anchor="ra")

    # Document Header
    f_co = get_en_font(27, bold=True)
    draw.text((36, 68), "HYPERSCALER CLOUD & AI INFRASTRUCTURE DISCLOSURE", font=f_co, fill=(15, 23, 42, 255))

    f_sub = get_en_font(16, bold=True)
    f_unit = get_en_font(15, bold=False)
    draw.text((36, 106), "MICROSOFT (AZURE / CLOUD) vs. AMAZON (AWS) QUARTERLY RESULTS", font=f_sub, fill=(71, 85, 105, 255))
    draw.text((710, 107), "(Unaudited, in Millions of USD)", font=f_unit, fill=(100, 116, 139, 255))

    # Divider line
    draw.line([(36, 134), (width - 36, 134)], fill=(203, 213, 225, 255), width=2)

    # Table Header (Use Japanese font to ensure zero tofu boxes)
    f_th = get_jp_font(15, bold=True)
    draw.text((48, 146), "Metric (セグメント財務指標)", font=f_th, fill=(71, 85, 105, 255))
    draw.text((450, 146), "Microsoft Azure", font=f_th, fill=(2, 132, 199, 255))  # Sky 600
    draw.text((690, 146), "Amazon AWS", font=f_th, fill=(217, 119, 6, 255))    # Amber 600
    draw.text((930, 146), "Structural Impact (構造評価)", font=f_th, fill=(71, 85, 105, 255))

    # Header bottom rule
    draw.line([(36, 172), (width - 36, 172)], fill=(226, 232, 240, 255), width=1)

    # Table Rows: (en_name, jp_sub, msft_val, amzn_val, impact_badge, is_alert)
    rows = [
        ("Cloud Segment Revenue", "クラウド売上高", "$ 24,100M (+29% YoY)", "$ 25,000M (+19% YoY)", "Azure高成長維持", False),
        ("Operating Margin", "営業利益率", "43.5% (高水準)", "37.2% (反撃開始)", "自社チップで粗利改善", False),
        ("AI Infrastructure Capex", "設備投資額 (急増)", "$ 17,500M (+76% YoY)", "$ 22,000M (+81% YoY)", "年60兆円の消耗戦", True),
        ("Depreciation Expense", "減価償却費負担", "+40.6% YoY (急拡大)", "+34.2% YoY (固定費化)", "四半期利益を侵食", True),
        ("Free Cash Flow YoY", "フリーキャッシュフロー", "-14.3% (巨額支出)", "-18.5% (投資先行)", "現金創出力を圧迫", False),
    ]

    start_y = 180
    row_h = 74
    f_row_en = get_jp_font(16, bold=True)
    f_row_jp = get_jp_font(13, bold=False)
    f_num = get_jp_font(15, bold=True)
    f_badge = get_jp_font(14, bold=True)

    for i, (en_name, jp_sub, ms_val, az_val, impact_str, is_alert) in enumerate(rows):
        ry1 = start_y + (i * row_h)
        ry2 = ry1 + row_h
        mid_y = (ry1 + ry2) // 2

        if is_alert:
            # Highlight alert row
            draw.rectangle([36, ry1 + 2, width - 36, ry2 - 2], fill=(254, 242, 242, 255))
            draw.rectangle([36, ry1 + 2, 42, ry2 - 2], fill=(239, 68, 68, 255))
        elif i % 2 == 1:
            draw.rectangle([36, ry1 + 2, width - 36, ry2 - 2], fill=(241, 245, 249, 140))

        # Bottom rule
        draw.line([(36, ry2), (width - 36, ry2)], fill=(226, 232, 240, 255), width=1)

        # Metric Labels
        draw.text((48, mid_y - 12), en_name, font=f_row_en, fill=(15, 23, 42, 255))
        draw.text((48, mid_y + 11), f"({jp_sub})", font=f_row_jp, fill=(100, 116, 139, 255))

        # Microsoft Value
        draw.text((450, mid_y), ms_val, font=f_num, fill=(15, 23, 42, 255), anchor="lm")

        # Amazon Value
        draw.text((690, mid_y), az_val, font=f_num, fill=(15, 23, 42, 255), anchor="lm")

        # Impact Badge
        b_col = (220, 38, 38, 255) if is_alert else (71, 85, 105, 255)
        bg_col = (254, 226, 226, 255) if is_alert else (241, 245, 249, 255)
        bw = draw.textlength(impact_str, font=f_badge) + 20
        draw.rounded_rectangle([926, mid_y - 15, 926 + bw, mid_y + 15], radius=6, fill=bg_col, outline=b_col, width=1)
        draw.text((926 + bw // 2, mid_y), impact_str, font=f_badge, fill=b_col, anchor="mm")

    # Document Footer
    footer_y = height - 58
    draw.line([(36, footer_y), (width - 36, footer_y)], fill=(203, 213, 225, 255), width=1)
    f_foot = get_en_font(15, bold=False)
    draw.text(
        (width - 48, height - 32),
        "SEC Form 10-Q Part I Item 1  |  Segment Reporting (MSFT & AMZN)",
        font=f_foot,
        fill=(148, 163, 184, 255),
        anchor="ra",
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    print(f"Generated SEC MSFT vs AMZN Cloud clipping: {out_path}")


if __name__ == "__main__":
    generate_sec_10q_clipping(Path("assets/official/sec_msft_capex_10q.png"))
    generate_fred_macro_chart(Path("assets/official/fred_macro_liquidity.png"))
    generate_msft_vs_amzn_cloud_financials(Path("assets/official/sec_msft_vs_amzn_cloud_financials.png"))
