from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def get_fonts():
    """Returns high-legibility Japanese fonts, preferring Morisawa BIZ UD Gothic Bold, Noto Sans JP, or Meiryo Bold."""
    font_candidates = [
        ("BIZ-UDGothicB.ttc", "BIZ-UDGothicR.ttc"),
        ("NotoSansJP-VF.ttf", "NotoSansJP-VF.ttf"),
        ("meiryob.ttc", "meiryo.ttc"),
        ("YuGothB.ttc", "YuGothM.ttc")
    ]
    
    font_bold = "meiryob.ttc"
    font_reg = "meiryo.ttc"
    
    for fb, fr in font_candidates:
        try:
            ImageFont.truetype(fb, 30)
            font_bold = fb
            font_reg = fr
            break
        except Exception:
            continue

    try:
        return {
            "title": ImageFont.truetype(font_bold, 42),
            "card_title": ImageFont.truetype(font_bold, 33),
            "body": ImageFont.truetype(font_bold, 26),
            "footer": ImageFont.truetype(font_bold, 29),
            "badge": ImageFont.truetype(font_bold, 25),
            "num": ImageFont.truetype(font_bold, 32),
            "small": ImageFont.truetype(font_reg, 22)
        }
    except Exception:
        default = ImageFont.load_default()
        return {k: default for k in ["title", "card_title", "body", "footer", "badge", "num", "small"]}

def create_fullscreen_slide_base(category_tag: str, title: str, theme_color=(37, 99, 235)):
    """
    Creates a 1920x1080 Full-Screen Presentation Board.
    Eliminates awkward classroom background borders during explanation slides.
    Enforces strict safe zones:
      - Main Content Zone: X: 70 to 1350, Y: 135 to 765
      - Character Safe Zone: X: 1380 to 1920, Y: 135 to 1080 (No text/content)
      - Subtitle Safe Zone: Y: 830 to 1080 (No text/content)
    """
    img = Image.new("RGBA", (1920, 1080), (246, 248, 251, 255))
    draw = ImageDraw.Draw(img)
    fonts = get_fonts()

    # Studio Top Header Bar
    header_bbox = [60, 24, 1860, 114]
    draw.rounded_rectangle(header_bbox, radius=16, fill=(255, 255, 255, 255), outline=(226, 232, 240, 255), width=2)
    draw.rounded_rectangle([60, 24, 74, 114], radius=6, fill=theme_color)

    # Category Tag Pill
    tag_w = draw.textlength(category_tag, font=fonts["badge"]) + 36
    draw.rounded_rectangle([90, 40, 90 + tag_w, 98], radius=12, fill=theme_color)
    draw.text((90 + tag_w / 2, 69), category_tag, font=fonts["badge"], fill=(255, 255, 255, 255), anchor="mm")

    # Title text
    draw.text((115 + tag_w, 69), title, font=fonts["title"], fill=(15, 23, 42, 255), anchor="lm")

    # Character Safe Zone Stage (Clean solid studio framing on the right side)
    char_stage_bbox = [1385, 135, 1860, 810]
    draw.rounded_rectangle(char_stage_bbox, radius=20, fill=(238, 242, 247, 255), outline=(226, 232, 240, 255), width=2)

    return img, draw, fonts

def render_content_card(draw, fonts, bbox, num_str, title, desc_lines, accent_color=(37, 99, 235)):
    x1, y1, x2, y2 = bbox
    # Pure white card with soft border
    draw.rounded_rectangle([x1, y1, x2, y2], radius=16, fill=(255, 255, 255, 255), outline=(226, 232, 240, 255), width=2)
    
    # Left accent indicator
    draw.rounded_rectangle([x1, y1, x1 + 8, y2], radius=4, fill=accent_color)

    # Number Circle Badge
    badge_x = x1 + 42
    badge_y = y1 + 38
    draw.ellipse([badge_x - 22, badge_y - 22, badge_x + 22, badge_y + 22], fill=accent_color)
    draw.text((badge_x, badge_y - 2), num_str, font=fonts["num"], fill=(255, 255, 255, 255), anchor="mm")

    # Card Title
    draw.text((x1 + 80, y1 + 38), title, font=fonts["card_title"], fill=(15, 23, 42, 255), anchor="lm")

    # Body lines
    cur_y = y1 + 78
    for line in desc_lines:
        draw.text((x1 + 36, cur_y), line, font=fonts["body"], fill=(51, 65, 85, 255), anchor="lm")
        cur_y += 34

def render_conclusion_banner(draw, fonts, bbox, conclusion_text, accent_color=(245, 158, 11)):
    x1, y1, x2, y2 = bbox
    # Deep Charcoal background for high-contrast authoritative conclusion
    draw.rounded_rectangle([x1, y1, x2, y2], radius=14, fill=(15, 23, 42, 255))
    draw.rounded_rectangle([x1, y1, x1 + 8, y2], radius=4, fill=accent_color)

    # Conclusion Pill Badge
    draw.rounded_rectangle([x1 + 20, y1 + 18, x1 + 165, y2 - 18], radius=10, fill=accent_color)
    draw.text((x1 + 92, (y1 + y2) / 2), "本日の結論", font=fonts["badge"], fill=(15, 23, 42, 255), anchor="mm")

    # Conclusion Text
    draw.text((x1 + 185, (y1 + y2) / 2), conclusion_text, font=fonts["footer"], fill=(255, 255, 255, 255), anchor="lm")

def generate_market_regime(out_path: Path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img, draw, fonts = create_fullscreen_slide_base(
        category_tag="【マクロ経済】",
        title="【2026年最新】株式市場の現在地",
        theme_color=(37, 99, 235) # Royal Blue
    )

    cards = [
        ("1", "米国政策金利：3.75〜4.00%", [
            "• 粘着質なインフレを背景に高金利が長期化（Higher for Longer）",
            "• 企業の借入コストが増加し、財務体質による二極化が加速"
        ], (220, 38, 38)), # Red
        ("2", "原油高騰（1バレル100ドル突破）", [
            "• 地政学リスクとエネルギー高が世界的なコスト圧迫要因に",
            "• 価格転嫁できない薄利多売企業から業績悪化が表面化"
        ], (217, 119, 6)), # Gold
        ("3", "日銀の利上げ（1.25%到達）", [
            "• 日本も30年ぶりの「金利のある世界」へ完全に移行",
            "• 借金頼みのゾンビ企業が淘汰され、本物の実力派へ資金集中"
        ], (37, 99, 235)), # Blue
    ]

    x1, x2 = 70, 1350
    y = 138
    card_h = 152
    for num, title, desc, col in cards:
        render_content_card(draw, fonts, [x1, y, x2, y + card_h], num, title, desc, col)
        y += 172

    # Conclusion banner ends at Y=755, safely above Subtitle Safe Zone (Y >= 830)
    render_conclusion_banner(draw, fonts, [x1, 670, x2, 755], "「低金利ジャブジャブバブル」は完全終了！")

    img.save(out_path)
    print(f"Saved Full-Screen Slide: {out_path}")

def generate_ai_phase_shift(out_path: Path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img, draw, fonts = create_fullscreen_slide_base(
        category_tag="【相場の地殻変動】",
        title="AI相場の地殻変動：選別の第２期へ",
        theme_color=(124, 58, 237) # Violet
    )

    x1, x2 = 70, 1350

    # Phase 1 Card
    y1, h1 = 138, 220
    draw.rounded_rectangle([x1, y1, x2, y1 + h1], radius=16, fill=(255, 255, 255, 255), outline=(226, 232, 240, 255), width=2)
    draw.rounded_rectangle([x1, y1, x1 + 8, y1 + h1], radius=4, fill=(147, 51, 234))
    
    # Phase 1 Badge
    draw.rounded_rectangle([x1 + 30, y1 + 22, x1 + 175, y1 + 62], radius=10, fill=(243, 232, 255))
    draw.text((x1 + 102, y1 + 42), "PHASE 1", font=fonts["badge"], fill=(126, 34, 206), anchor="mm")
    draw.text((x1 + 195, y1 + 42), "【2024〜2025年】設備投資の熱狂", font=fonts["card_title"], fill=(15, 23, 42), anchor="lm")
    draw.text((x1 + 36, y1 + 95), "• 半導体チップやデータセンターを買い漁る初期インフラ構築フェーズ", font=fonts["body"], fill=(51, 65, 85), anchor="lm")
    draw.text((x1 + 36, y1 + 135), "➔ 『AI』と名のつく銘柄なら何でも資金が集まり急騰したお祭り相場", font=fonts["body"], fill=(126, 34, 206), anchor="lm")
    draw.text((x1 + 36, y1 + 175), "• 実績や利益に関係なく、バリュエーション（期待PER）が極限まで拡大", font=fonts["small"], fill=(100, 116, 139), anchor="lm")

    # Phase 2 Card
    y2, h2 = 380, 265
    draw.rounded_rectangle([x1, y2, x2, y2 + h2], radius=16, fill=(255, 255, 255, 255), outline=(254, 202, 202, 255), width=2)
    draw.rounded_rectangle([x1, y2, x1 + 8, y2 + h2], radius=4, fill=(220, 38, 38))
    
    # Phase 2 Badge
    draw.rounded_rectangle([x1 + 30, y2 + 22, x1 + 175, y2 + 62], radius=10, fill=(254, 226, 226))
    draw.text((x1 + 102, y2 + 42), "PHASE 2", font=fonts["badge"], fill=(185, 28, 28), anchor="mm")
    draw.text((x1 + 195, y2 + 42), "【2026年〜現在】投資回収（ROI）の試練", font=fonts["card_title"], fill=(185, 28, 28), anchor="lm")
    draw.text((x1 + 36, y2 + 95), "• 年間5000億ドル超の巨額支出に対し、冷徹な利益創出を要求", font=fonts["body"], fill=(51, 65, 85), anchor="lm")
    draw.text((x1 + 36, y2 + 135), "• 借金頼みのハイテク・AIスタートアップは容赦なく急落！", font=fonts["body"], fill=(220, 38, 38), anchor="lm")
    draw.text((x1 + 36, y2 + 175), "➔ 『AIを社内実務に組み込んで営業利益率を改善させた企業』が真の勝者に", font=fonts["body"], fill=(15, 23, 42), anchor="lm")
    draw.text((x1 + 36, y2 + 215), "• 夢を語る企業は淘汰され、本物のキャッシュ創出企業へ選別が完了", font=fonts["small"], fill=(100, 116, 139), anchor="lm")

    # Conclusion banner ends at Y=755
    render_conclusion_banner(draw, fonts, [x1, 670, x2, 755], "「AI期待」から「実績と稼ぐ力」の時代へ", accent_color=(147, 51, 234))

    img.save(out_path)
    print(f"Saved Full-Screen Slide: {out_path}")

def generate_expert_checklist(out_path: Path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img, draw, fonts = create_fullscreen_slide_base(
        category_tag="【投資の鉄則】",
        title="高金利時代に勝つ「優良企業の３条件」",
        theme_color=(16, 185, 129) # Emerald Green
    )

    cards = [
        ("1", "豊富なフリーキャッシュフロー（無借金経営）", [
            "• 借金の借り換え金利に苦しまず、自前キャッシュで研究開発・成長投資ができる企業",
            "• 銀行や社債市場に依存せず、不況期にも自社株買いやM&Aを仕掛けられる強靭さ"
        ], (16, 185, 129)), # Green
        ("2", "圧倒的な「価格転嫁力」（ブランド・堀 / Moat）", [
            "• 原材料・人件費高騰でも確実に値上げでき、顧客が離れない独占的シェア",
            "• インフレのコスト増をそのまま価格に転嫁し、高い営業利益率を維持できる"
        ], (217, 119, 6)), # Gold
        ("3", "「AI活用による経費削減」が機能する実力派", [
            "• 派手なAI開発競争ではなく、AIで実務工数・販管費を削り利益率を押し上げる企業",
            "• 既存の巨大顧客基盤にAIを組み込み、確実に増益を達成する現実主義の勝ち組"
        ], (37, 99, 235)), # Royal Blue
    ]

    x1, x2 = 70, 1350
    y = 138
    card_h = 152
    for num, title, desc, col in cards:
        render_content_card(draw, fonts, [x1, y, x2, y + card_h], num, title, desc, col)
        y += 172

    # Conclusion banner ends at Y=755
    render_conclusion_banner(draw, fonts, [x1, 670, x2, 755], "ブームに飛びつかず、「本物のキャッシュ創出力」を見よ", accent_color=(16, 185, 129))

    img.save(out_path)
    print(f"Saved Full-Screen Slide: {out_path}")

if __name__ == "__main__":
    out_dir = Path("projects/02_market_analysis_2026/broll")
    generate_market_regime(out_dir / "market_regime_2026.png")
    generate_ai_phase_shift(out_dir / "ai_phase_shift.png")
    generate_expert_checklist(out_dir / "expert_checklist_2026.png")
