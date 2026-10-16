"""
High-Definition B-Roll Presentation Board Generator (Architecture B: 1-Slide-1-Impact-Metric)
Benchmarked against top Japanese finance/economics YouTube channels.
Features:
  - Morisawa BIZ UDP Gothic Bold typography (mobile-first legibility)
  - Giant Hero Metrics (72pt) for instant smartphone comprehension
  - High-retention progressive slides (1 Slide = 1 Key Message)
  - Seamless presenter framing (no awkward character box)
  - Subtitle Safe Zone: strictly leaves Y >= 780 clear for dialogue
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def get_fonts():
    """Returns BIZ UDP Gothic Bold fonts with proper proportional kerning."""
    fb = "BIZ-UDGothicB.ttc"
    fr = "BIZ-UDGothicR.ttc"
    
    # Try loading proportional index 1
    try:
        return {
            "hero": ImageFont.truetype(fb, 70, index=1),
            "hero_sub": ImageFont.truetype(fb, 30, index=1),
            "title": ImageFont.truetype(fb, 38, index=1),
            "card_title": ImageFont.truetype(fb, 32, index=1),
            "body": ImageFont.truetype(fb, 26, index=1),
            "footer": ImageFont.truetype(fb, 28, index=1),
            "badge": ImageFont.truetype(fb, 22, index=1),
            "num": ImageFont.truetype(fb, 32, index=1),
            "small": ImageFont.truetype(fr, 22, index=1)
        }
    except Exception:
        # Fallback to standard truetype
        try:
            return {
                "hero": ImageFont.truetype(fb, 70),
                "hero_sub": ImageFont.truetype(fb, 30),
                "title": ImageFont.truetype(fb, 38),
                "card_title": ImageFont.truetype(fb, 32),
                "body": ImageFont.truetype(fb, 26),
                "footer": ImageFont.truetype(fb, 28),
                "badge": ImageFont.truetype(fb, 22),
                "num": ImageFont.truetype(fb, 32),
                "small": ImageFont.truetype(fr, 22)
            }
        except Exception:
            default = ImageFont.load_default()
            return {k: default for k in ["hero", "hero_sub", "title", "card_title", "body", "footer", "badge", "num", "small"]}

def create_slide_base(category_tag: str, step_tag: str, title: str, theme_color=(37, 99, 235)):
    """
    Creates a 1920x1080 Television Studio Presentation Slide.
    Leaves X: 1350 to 1920 seamless for the character presenter (no boxed-in border).
    Leaves Y: 780 to 1080 clear for subtitles.
    """
    img = Image.new("RGBA", (1920, 1080), (248, 250, 252, 255)) # Slate 50
    draw = ImageDraw.Draw(img)
    fonts = get_fonts()

    # Studio Top Header Bar
    header_bbox = [60, 24, 1860, 116]
    draw.rounded_rectangle(header_bbox, radius=18, fill=(255, 255, 255, 255), outline=(226, 232, 240, 255), width=2)
    # Left accent indicator on header
    draw.rounded_rectangle([60, 24, 76, 116], radius=6, fill=theme_color)

    # Category Tag Pill
    cur_x = 96
    cat_w = draw.textlength(category_tag, font=fonts["badge"]) + 36
    draw.rounded_rectangle([cur_x, 42, cur_x + cat_w, 98], radius=12, fill=(15, 23, 42, 255))
    draw.text((cur_x + cat_w / 2, 70), category_tag, font=fonts["badge"], fill=(255, 255, 255, 255), anchor="mm")
    cur_x += cat_w + 14

    # Step Tag Pill (e.g. POINT 01)
    if step_tag:
        step_w = draw.textlength(step_tag, font=fonts["badge"]) + 32
        draw.rounded_rectangle([cur_x, 42, cur_x + step_w, 98], radius=12, fill=theme_color)
        draw.text((cur_x + step_w / 2, 70), step_tag, font=fonts["badge"], fill=(255, 255, 255, 255), anchor="mm")
        cur_x += step_w + 20
    else:
        cur_x += 10

    # Title text
    draw.text((cur_x, 70), title, font=fonts["title"], fill=(15, 23, 42, 255), anchor="lm")

    return img, draw, fonts

def render_hero_metric_card(draw, fonts, bbox, badge_text, hero_metric, status_pill, accent_color):
    """
    Renders the dominant Hero Metric Card (Architecture B).
    X1: 70, Y1: 140, X2: 1340, Y2: 450
    """
    x1, y1, x2, y2 = bbox
    # Card Background with crisp border
    draw.rounded_rectangle([x1, y1, x2, y2], radius=20, fill=(255, 255, 255, 255), outline=(203, 213, 225, 255), width=2)
    # Left vertical accent line
    draw.rounded_rectangle([x1, y1, x1 + 12, y2], radius=6, fill=accent_color)

    # Top Context Badge
    badge_w = draw.textlength(badge_text, font=fonts["badge"]) + 32
    draw.rounded_rectangle([x1 + 36, y1 + 26, x1 + 36 + badge_w, y1 + 68], radius=10, fill=(241, 245, 249, 255), outline=(226, 232, 240, 255), width=1)
    draw.text((x1 + 36 + badge_w / 2, y1 + 47), badge_text, font=fonts["badge"], fill=(71, 85, 105, 255), anchor="mm")

    # The Giant Hero Metric Number (70pt bold)
    draw.text((x1 + 36, y1 + 140), hero_metric, font=fonts["hero"], fill=accent_color, anchor="lm")

    # Status Pill / Takeaway Subtitle
    status_w = draw.textlength(status_pill, font=fonts["hero_sub"]) + 36
    draw.rounded_rectangle([x1 + 36, y1 + 220, x1 + 36 + status_w, y1 + 282], radius=12, fill=(254, 242, 242, 255) if accent_color == (220, 38, 38) else (254, 243, 199, 255) if accent_color == (217, 119, 6) else (239, 246, 255, 255))
    draw.text((x1 + 36 + status_w / 2, y1 + 251), status_pill, font=fonts["hero_sub"], fill=accent_color, anchor="mm")

def render_takeaway_cards(draw, fonts, card_a, card_b):
    """
    Renders two high-legibility takeaway cards stacked below the hero metric.
    """
    x1, x2 = 70, 1340
    
    # Card A: Y 476 to 598
    y1, y2 = 476, 598
    tag_a, text_a, color_a = card_a
    draw.rounded_rectangle([x1, y1, x2, y2], radius=16, fill=(255, 255, 255, 255), outline=(226, 232, 240, 255), width=2)
    draw.rounded_rectangle([x1, y1, x1 + 8, y2], radius=4, fill=color_a)
    
    tag_w = draw.textlength(tag_a, font=fonts["badge"]) + 28
    draw.rounded_rectangle([x1 + 28, y1 + 20, x1 + 28 + tag_w, y2 - 20], radius=10, fill=color_a)
    draw.text((x1 + 28 + tag_w / 2, (y1 + y2) / 2), tag_a, font=fonts["badge"], fill=(255, 255, 255, 255), anchor="mm")
    draw.text((x1 + 44 + tag_w, (y1 + y2) / 2), text_a, font=fonts["card_title"], fill=(15, 23, 42, 255), anchor="lm")

    # Card B: Y 622 to 744
    y1, y2 = 622, 744
    tag_b, text_b, color_b = card_b
    draw.rounded_rectangle([x1, y1, x2, y2], radius=16, fill=(255, 255, 255, 255), outline=(226, 232, 240, 255), width=2)
    draw.rounded_rectangle([x1, y1, x1 + 8, y2], radius=4, fill=color_b)
    
    tag_w = draw.textlength(tag_b, font=fonts["badge"]) + 28
    draw.rounded_rectangle([x1 + 28, y1 + 20, x1 + 28 + tag_w, y2 - 20], radius=10, fill=color_b)
    draw.text((x1 + 28 + tag_w / 2, (y1 + y2) / 2), tag_b, font=fonts["badge"], fill=(255, 255, 255, 255), anchor="mm")
    draw.text((x1 + 44 + tag_w, (y1 + y2) / 2), text_b, font=fonts["card_title"], fill=(15, 23, 42, 255), anchor="lm")

# -------------------------------------------------------------
# 1. Market Regime Slides
# -------------------------------------------------------------
def generate_market_regime_pt1(out_path: Path):
    img, draw, fonts = create_slide_base(
        category_tag="【マクロ経済】",
        step_tag="POINT 01",
        title="世界最高峰の金融引き締めが長期化",
        theme_color=(220, 38, 38) # Red
    )
    render_hero_metric_card(
        draw, fonts, [70, 140, 1340, 445],
        badge_text="米国連邦準備制度（FRB） 政策金利",
        hero_metric="米国政策金利： 3.75 〜 4.00 ％",
        status_pill="【警告】 Higher for Longer（インフレ粘着で高金利が固定化）",
        accent_color=(220, 38, 38)
    )
    render_takeaway_cards(
        draw, fonts,
        ("借入コスト激増", "企業の利払い負担が倍増し、財務体質による淘汰が加速", (220, 38, 38)),
        ("相場の二極化", "低金利頼みの赤字企業は急落、潤沢キャッシュ企業へ資金集中", (15, 23, 42))
    )
    img.save(out_path)
    print(f"Saved: {out_path}")

def generate_market_regime_pt2(out_path: Path):
    img, draw, fonts = create_slide_base(
        category_tag="【マクロ経済】",
        step_tag="POINT 02",
        title="地政学リスクによるエネルギー価格の再燃",
        theme_color=(217, 119, 6) # Amber
    )
    render_hero_metric_card(
        draw, fonts, [70, 140, 1340, 445],
        badge_text="ニューヨーク原油先物（WTI 原油）",
        hero_metric="原油価格： 1バレル 100ドル突破",
        status_pill="【急騰】 世界的なコストプッシュ・インフレの脅威が再来",
        accent_color=(217, 119, 6)
    )
    render_takeaway_cards(
        draw, fonts,
        ("業績圧迫の直撃", "エネルギー・物流費高騰が世界企業の利益率を直撃圧迫", (217, 119, 6)),
        ("選別の分かれ目", "価格転嫁できない薄利多売企業から容赦なく業績悪化が表面化", (15, 23, 42))
    )
    img.save(out_path)
    print(f"Saved: {out_path}")

def generate_market_regime_pt3(out_path: Path):
    img, draw, fonts = create_slide_base(
        category_tag="【マクロ経済】",
        step_tag="POINT 03",
        title="30年ぶりの「金利のある世界」が完全定着",
        theme_color=(37, 99, 235) # Blue
    )
    render_hero_metric_card(
        draw, fonts, [70, 140, 1340, 445],
        badge_text="日本銀行（BOJ） 金融政策決定会合",
        hero_metric="日銀利上げ： 政策金利 1.25 ％到達",
        status_pill="【大転換】 ゼロ金利ジャブジャブ時代は完全に終焉を迎えた",
        accent_color=(37, 99, 235)
    )
    render_takeaway_cards(
        draw, fonts,
        ("ゾンビ企業の退場", "借金頼みで延命してきたゾンビ企業が市場から淘汰", (37, 99, 235)),
        ("本物の実力派へ", "自前の利益で稼ぎ続ける本物の実力派企業へ投資資金が集中", (15, 23, 42))
    )
    img.save(out_path)
    print(f"Saved: {out_path}")

def generate_market_regime_overview(out_path: Path):
    """Keep overview slide for introductory line."""
    img, draw, fonts = create_slide_base(
        category_tag="【マクロ経済】",
        step_tag="OVERVIEW",
        title="【2026年最新】株式市場の現在地と重要データ",
        theme_color=(37, 99, 235)
    )
    cards = [
        ("01", "米国政策金利：3.75〜4.00%", "インフレ高止まりにより高金利が長期化（Higher for Longer）", (220, 38, 38)),
        ("02", "原油高騰：1バレル100ドル突破", "地政学リスクによりエネルギー・物流コストが激増", (217, 119, 6)),
        ("03", "日銀利上げ：1.25%到達", "30年ぶりの「金利のある世界」へ移行、借金体質企業が淘汰", (37, 99, 235)),
    ]
    x1, x2 = 70, 1340
    y = 140
    for num, title, desc, col in cards:
        draw.rounded_rectangle([x1, y, x2, y + 155], radius=18, fill=(255, 255, 255, 255), outline=(226, 232, 240, 255), width=2)
        draw.rounded_rectangle([x1, y, x1 + 10, y + 155], radius=4, fill=col)
        # Num Badge
        draw.rounded_rectangle([x1 + 32, y + 26, x1 + 100, y + 74], radius=10, fill=col)
        draw.text((x1 + 66, y + 50), num, font=fonts["num"], fill=(255, 255, 255, 255), anchor="mm")
        # Title
        draw.text((x1 + 120, y + 50), title, font=fonts["card_title"], fill=(15, 23, 42, 255), anchor="lm")
        # Desc
        draw.text((x1 + 36, y + 110), f"• {desc}", font=fonts["body"], fill=(71, 85, 105, 255), anchor="lm")
        y += 180

    # Conclusion Banner
    draw.rounded_rectangle([x1, 670, x2, 755], radius=14, fill=(15, 23, 42, 255))
    draw.rounded_rectangle([x1, 670, x1 + 8, 755], radius=4, fill=(245, 158, 11))
    draw.rounded_rectangle([x1 + 20, 688, x1 + 165, 737], radius=10, fill=(245, 158, 11))
    draw.text((x1 + 92, 712), "本日の結論", font=fonts["badge"], fill=(15, 23, 42, 255), anchor="mm")
    draw.text((x1 + 185, 712), "「低金利ジャブジャブバブル」は完全終了！", font=fonts["footer"], fill=(255, 255, 255, 255), anchor="lm")

    img.save(out_path)
    print(f"Saved: {out_path}")

# -------------------------------------------------------------
# 2. AI Phase Shift Slides
# -------------------------------------------------------------
def generate_ai_phase_pt1(out_path: Path):
    img, draw, fonts = create_slide_base(
        category_tag="【相場の地殻変動】",
        step_tag="PHASE 01",
        title="【2024〜2025年】設備投資の熱狂相場",
        theme_color=(124, 58, 237) # Violet
    )
    render_hero_metric_card(
        draw, fonts, [70, 140, 1340, 445],
        badge_text="初期インフラ構築フェーズ（2024〜2025）",
        hero_metric="半導体・サーバーの買い漁り熱狂",
        status_pill="【熱狂】 『AI』と名がつけば何でも株価が急騰したお祭り相場",
        accent_color=(124, 58, 237)
    )
    render_takeaway_cards(
        draw, fonts,
        ("無制限の調達", "ハイパースケーラー各社が競ってGPUチップを爆買い", (124, 58, 237)),
        ("期待PERの膨張", "実際の利益や回収計画を問わず、将来の夢だけで株価が急騰", (15, 23, 42))
    )
    img.save(out_path)
    print(f"Saved: {out_path}")

def generate_ai_phase_pt2(out_path: Path):
    img, draw, fonts = create_slide_base(
        category_tag="【相場の地殻変動】",
        step_tag="PHASE 02",
        title="【2026年〜現在】投資回収（ROI）の過酷な試練",
        theme_color=(220, 38, 38) # Red
    )
    render_hero_metric_card(
        draw, fonts, [70, 140, 1340, 445],
        badge_text="資本効率・投資対効果の検証期（2026〜）",
        hero_metric="年間5000億ドルの回収要求",
        status_pill="【試練】 『で、そのAIで実際にいくら純利益が増えたの？』",
        accent_color=(220, 38, 38)
    )
    render_takeaway_cards(
        draw, fonts,
        ("冷徹な選別開始", "巨額支出に見合う利益創出ができない企業は容赦なく急落", (220, 38, 38)),
        ("真の勝者へ", "AIを実務に組み込んで営業利益率を改善させた企業だけが急伸", (15, 23, 42))
    )
    img.save(out_path)
    print(f"Saved: {out_path}")

def generate_ai_phase_overview(out_path: Path):
    img, draw, fonts = create_slide_base(
        category_tag="【相場の地殻変動】",
        step_tag="OVERVIEW",
        title="AI相場の地殻変動：『選別の第２期』へ",
        theme_color=(124, 58, 237)
    )
    x1, x2 = 70, 1340
    # Phase 1
    draw.rounded_rectangle([x1, 140, x2, 360], radius=18, fill=(255, 255, 255, 255), outline=(226, 232, 240, 255), width=2)
    draw.rounded_rectangle([x1, 140, x1 + 10, 360], radius=4, fill=(124, 58, 237))
    draw.rounded_rectangle([x1 + 32, 160, x1 + 180, 206], radius=10, fill=(243, 232, 255))
    draw.text((x1 + 106, 183), "PHASE 1", font=fonts["badge"], fill=(126, 34, 206), anchor="mm")
    draw.text((x1 + 200, 183), "【2024〜2025年】設備投資の熱狂（お祭り相場）", font=fonts["card_title"], fill=(15, 23, 42), anchor="lm")
    draw.text((x1 + 36, 240), "• 半導体やデータセンターを買い漁る初期インフラ構築フェーズ", font=fonts["body"], fill=(51, 65, 85), anchor="lm")
    draw.text((x1 + 36, 285), "• 実績や利益に関係なく「AI関連」なら何でも買われた時代", font=fonts["body"], fill=(126, 34, 206), anchor="lm")

    # Phase 2
    draw.rounded_rectangle([x1, 385, x2, 640], radius=18, fill=(255, 255, 255, 255), outline=(254, 202, 202, 255), width=2)
    draw.rounded_rectangle([x1, 385, x1 + 10, 640], radius=4, fill=(220, 38, 38))
    draw.rounded_rectangle([x1 + 32, 405, x1 + 180, 451], radius=10, fill=(254, 226, 226))
    draw.text((x1 + 106, 428), "PHASE 2", font=fonts["badge"], fill=(185, 28, 28), anchor="mm")
    draw.text((x1 + 200, 428), "【2026年〜現在】投資回収（ROI）の試練と選別", font=fonts["card_title"], fill=(185, 28, 28), anchor="lm")
    draw.text((x1 + 36, 485), "• 年間5000億ドル超の巨額支出に対し、冷徹な利益創出を要求", font=fonts["body"], fill=(51, 65, 85), anchor="lm")
    draw.text((x1 + 36, 530), "• 『AIで営業利益率を改善させた実力企業』だけが市場の真の勝者に", font=fonts["body"], fill=(220, 38, 38), anchor="lm")
    draw.text((x1 + 36, 575), "• 夢を語るだけの企業は淘汰され、ハイテク銘柄の明暗が完全に二極化", font=fonts["body"], fill=(71, 85, 105), anchor="lm")

    # Conclusion Banner
    draw.rounded_rectangle([x1, 670, x2, 755], radius=14, fill=(15, 23, 42, 255))
    draw.rounded_rectangle([x1, 670, x1 + 8, 755], radius=4, fill=(124, 58, 237))
    draw.rounded_rectangle([x1 + 20, 688, x1 + 165, 737], radius=10, fill=(124, 58, 237))
    draw.text((x1 + 92, 712), "相場の結論", font=fonts["badge"], fill=(255, 255, 255, 255), anchor="mm")
    draw.text((x1 + 185, 712), "「AI期待」から「実績と稼ぐ力」の時代へ完全シフト！", font=fonts["footer"], fill=(255, 255, 255, 255), anchor="lm")

    img.save(out_path)
    print(f"Saved: {out_path}")

# -------------------------------------------------------------
# 3. Expert Checklist Slides
# -------------------------------------------------------------
def generate_checklist_pt1(out_path: Path):
    img, draw, fonts = create_slide_base(
        category_tag="【プロの選別基準】",
        step_tag="条件 01",
        title="高金利下で最も強靭な「自前キャッシュ力」",
        theme_color=(16, 185, 129) # Emerald
    )
    render_hero_metric_card(
        draw, fonts, [70, 140, 1340, 445],
        badge_text="バランスシートの健全性 ＆ キャッシュフロー",
        hero_metric="豊富なフリーCF ＆ 無借金経営",
        status_pill="【最強】 金利上昇のダメージを一切受けず自前資金で成長",
        accent_color=(16, 185, 129)
    )
    render_takeaway_cards(
        draw, fonts,
        ("金利高騰への耐性", "銀行融資や社債市場に依存せず、不況期でも強気の研究開発", (16, 185, 129)),
        ("攻めの資本戦略", "株価急落局面で自社株買いや有利なM&Aを仕掛けられる強靭さ", (15, 23, 42))
    )
    img.save(out_path)
    print(f"Saved: {out_path}")

def generate_checklist_pt2(out_path: Path):
    img, draw, fonts = create_slide_base(
        category_tag="【プロの選別基準】",
        step_tag="条件 02",
        title="インフレ下でも利益率を維持する「経済的な堀」",
        theme_color=(217, 119, 6) # Amber
    )
    render_hero_metric_card(
        draw, fonts, [70, 140, 1340, 445],
        badge_text="独占的シェア ＆ ブランド力（Moat）",
        hero_metric="圧倒的な「価格転嫁力」の保持",
        status_pill="【独占】 原材料・人件費が高騰しても顧客が離れず値上げ可能",
        accent_color=(217, 119, 6)
    )
    render_takeaway_cards(
        draw, fonts,
        ("マージン防衛力", "インフレのコスト増を確実に販売価格へ転嫁し高利益率を維持", (217, 119, 6)),
        ("代替不能な地位", "他社に乗り換えられない強力なエコシステムを持つ企業の独壇場", (15, 23, 42))
    )
    img.save(out_path)
    print(f"Saved: {out_path}")

def generate_checklist_pt3(out_path: Path):
    img, draw, fonts = create_slide_base(
        category_tag="【プロの選別基準】",
        step_tag="条件 03",
        title="派手なAI開発ではなく「実業の利益率改善」",
        theme_color=(37, 99, 235) # Blue
    )
    render_hero_metric_card(
        draw, fonts, [70, 140, 1340, 445],
        badge_text="実業へのAI実装 ＆ コスト削減力",
        hero_metric="実務の「AI効率化」で利益率拡大",
        status_pill="【実利】 AIを作る側ではなく、AIを使いこなして販管費を削る側",
        accent_color=(37, 99, 235)
    )
    render_takeaway_cards(
        draw, fonts,
        ("現実主義の勝ち組", "人件費や実務工数を削り、営業利益率を押し上げる実力企業", (37, 99, 235)),
        ("利益の最大化", "既存の巨大顧客基盤にAIを組み込み着実に増益を達成する企業", (15, 23, 42))
    )
    img.save(out_path)
    print(f"Saved: {out_path}")

def generate_checklist_overview(out_path: Path):
    img, draw, fonts = create_slide_base(
        category_tag="【投資の鉄則】",
        step_tag="OVERVIEW",
        title="高金利時代に勝つ「優良企業の３条件」",
        theme_color=(16, 185, 129)
    )
    cards = [
        ("01", "豊富なフリーキャッシュフロー（無借金経営）", "借金金利に苦しまず、自前キャッシュで成長投資ができる企業", (16, 185, 129)),
        ("02", "圧倒的な「価格転嫁力」（ブランド・堀 / Moat）", "原材料・人件費高騰でも確実に値上げでき顧客が離れない企業", (217, 119, 6)),
        ("03", "「AI活用による経費削減」が機能する実力派", "派手な開発競争ではなく、AIで実務コストを削り増益する企業", (37, 99, 235)),
    ]
    x1, x2 = 70, 1340
    y = 140
    for num, title, desc, col in cards:
        draw.rounded_rectangle([x1, y, x2, y + 155], radius=18, fill=(255, 255, 255, 255), outline=(226, 232, 240, 255), width=2)
        draw.rounded_rectangle([x1, y, x1 + 10, y + 155], radius=4, fill=col)
        draw.rounded_rectangle([x1 + 32, y + 26, x1 + 100, y + 74], radius=10, fill=col)
        draw.text((x1 + 66, y + 50), num, font=fonts["num"], fill=(255, 255, 255, 255), anchor="mm")
        draw.text((x1 + 120, y + 50), title, font=fonts["card_title"], fill=(15, 23, 42, 255), anchor="lm")
        draw.text((x1 + 36, y + 110), f"• {desc}", font=fonts["body"], fill=(71, 85, 105, 255), anchor="lm")
        y += 180

    # Conclusion Banner
    draw.rounded_rectangle([x1, 670, x2, 755], radius=14, fill=(15, 23, 42, 255))
    draw.rounded_rectangle([x1, 670, x1 + 8, 755], radius=4, fill=(16, 185, 129))
    draw.rounded_rectangle([x1 + 20, 688, x1 + 165, 737], radius=10, fill=(16, 185, 129))
    draw.text((x1 + 92, 712), "最終結論", font=fonts["badge"], fill=(255, 255, 255, 255), anchor="mm")
    draw.text((x1 + 185, 712), "ブームに飛びつかず、「本物のキャッシュ創出力」を見よ！", font=fonts["footer"], fill=(255, 255, 255, 255), anchor="lm")

    img.save(out_path)
    print(f"Saved: {out_path}")

def build_all(out_dir: Path):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Market Regime
    generate_market_regime_overview(out_dir / "market_regime_2026.png")
    generate_market_regime_pt1(out_dir / "market_regime_pt1.png")
    generate_market_regime_pt2(out_dir / "market_regime_pt2.png")
    generate_market_regime_pt3(out_dir / "market_regime_pt3.png")

    # AI Phase Shift
    generate_ai_phase_overview(out_dir / "ai_phase_shift.png")
    generate_ai_phase_pt1(out_dir / "ai_phase_pt1.png")
    generate_ai_phase_pt2(out_dir / "ai_phase_pt2.png")

    # Expert Checklist
    generate_checklist_overview(out_dir / "expert_checklist_2026.png")
    generate_checklist_pt1(out_dir / "expert_checklist_pt1.png")
    generate_checklist_pt2(out_dir / "expert_checklist_pt2.png")
    generate_checklist_pt3(out_dir / "expert_checklist_pt3.png")

if __name__ == "__main__":
    target_dir = Path("projects/02_market_analysis_2026/broll")
    build_all(target_dir)
