from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def draw_rounded_rect(draw, bbox, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(bbox, radius=radius, fill=fill, outline=outline, width=width)

def create_board_base(width=1280, height=720, border_color=(0, 240, 255, 230)):
    # Create canvas with drop shadow
    canvas_w, canvas_h = width + 40, height + 40
    img = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    
    # Shadow
    shadow = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle([20, 20, canvas_w - 20, canvas_h - 20], radius=32, fill=(0, 0, 0, 160))
    shadow = shadow.filter(ImageFilter.GaussianBlur(16))
    img.alpha_composite(shadow)
    
    # Main board body
    draw = ImageDraw.Draw(img)
    board_bbox = [20, 20, canvas_w - 20, canvas_h - 20]
    draw.rounded_rectangle(board_bbox, radius=28, fill=(18, 22, 34, 245), outline=border_color, width=4)
    
    return img, draw, board_bbox

def get_fonts():
    font_bold = "meiryob.ttc"
    font_reg = "meiryo.ttc"
    try:
        return {
            "title": ImageFont.truetype(font_bold, 44),
            "h2": ImageFont.truetype(font_bold, 30),
            "body": ImageFont.truetype(font_bold, 24),
            "footer": ImageFont.truetype(font_bold, 32),
            "small": ImageFont.truetype(font_reg, 22)
        }
    except Exception:
        default = ImageFont.load_default()
        return {"title": default, "h2": default, "body": default, "footer": default, "small": default}

def generate_market_regime(out_path: Path):
    fonts = get_fonts()
    img, draw, bbox = create_board_base(border_color=(0, 210, 255, 255))
    
    # Header Title
    title_text = "【2026年最新】 株式市場の現在地"
    draw.text((660, 65), title_text, font=fonts["title"], fill=(255, 225, 80), anchor="mt")
    draw.line([(80, 125), (1240, 125)], fill=(60, 80, 110, 200), width=2)
    
    cards = [
        ("① 米国政策金利：3.75〜4.00%", "粘着質なインフレを背景に高金利が長期化（Higher for Longer）", (255, 90, 95)),
        ("② 原油高騰（1バレル100ドル突破）", "地政学リスクとエネルギー高が世界的なコスト圧迫要因に", (255, 175, 50)),
        ("③ 日銀の利上げ（1.25%到達）", "日本も30年ぶりの「金利のある世界」へ完全に移行", (60, 200, 255)),
    ]
    
    y = 150
    for title, desc, col in cards:
        card_bbox = [80, y, 1240, y + 120]
        # Dark subtle fill
        draw.rounded_rectangle(card_bbox, radius=16, fill=(28, 36, 52, 230), outline=col, width=3)
        # Left color pill
        draw.rounded_rectangle([80, y, 92, y + 120], radius=6, fill=col)
        # Text
        draw.text((115, y + 18), title, font=fonts["h2"], fill=col)
        draw.text((115, y + 68), desc, font=fonts["body"], fill=(240, 245, 255))
        y += 140
        
    # Footer
    draw.text((660, 610), "結論：「低金利ジャブジャブバブル」は完全終了！", font=fonts["footer"], fill=(255, 230, 90), anchor="mt")
    img.save(out_path)
    print(f"Saved: {out_path}")

def generate_ai_phase_shift(out_path: Path):
    fonts = get_fonts()
    img, draw, bbox = create_board_base(border_color=(200, 80, 255, 255))
    
    # Header Title
    title_text = "AI相場の地殻変動：選別の第２期へ"
    draw.text((660, 60), title_text, font=fonts["title"], fill=(255, 130, 240), anchor="mt")
    draw.line([(80, 120), (1240, 120)], fill=(120, 60, 150, 200), width=2)
    
    # Card 1: Phase 1
    y1 = 145
    card1 = [80, y1, 1240, y1 + 185]
    draw.rounded_rectangle(card1, radius=18, fill=(35, 28, 55, 230), outline=(170, 120, 240), width=3)
    draw.rounded_rectangle([80, y1, 92, y1 + 185], radius=6, fill=(170, 120, 240))
    draw.text((115, y1 + 15), "【フェーズ１：2024〜2025年】 設備投資の熱狂", font=fonts["h2"], fill=(210, 170, 255))
    draw.text((120, y1 + 65), "• 半導体チップやデータセンターを買い漁る初期インフラ構築フェーズ", font=fonts["body"], fill=(230, 230, 245))
    draw.text((120, y1 + 115), "➔ 『AI』と名のつく銘柄なら何でも資金が集まり急騰した時代", font=fonts["body"], fill=(245, 245, 255))
    
    # Card 2: Phase 2
    y2 = 355
    card2 = [80, y2, 1240, y2 + 215]
    draw.rounded_rectangle(card2, radius=18, fill=(45, 25, 45, 230), outline=(255, 80, 120), width=3)
    draw.rounded_rectangle([80, y2, 92, y2 + 215], radius=6, fill=(255, 80, 120))
    draw.text((115, y2 + 15), "【フェーズ２：2026年〜現在】 投資回収（ROI）の試練", font=fonts["h2"], fill=(255, 100, 140))
    draw.text((120, y2 + 65), "• 年間5000億ドル超の巨大支出に対し、本物の利益創出を要求", font=fonts["body"], fill=(240, 240, 250))
    draw.text((120, y2 + 110), "• 借金頼みのAIスタートアップ・ハイテク企業は容赦なく急落！", font=fonts["body"], fill=(255, 110, 110))
    draw.text((120, y2 + 155), "➔ 『AIで実際に営業利益率を改善させた本物』だけが生き残る", font=fonts["body"], fill=(255, 235, 90))
    
    # Footer
    draw.text((660, 605), "「AI期待」から「実績と稼ぐ力」の時代へ", font=fonts["footer"], fill=(80, 230, 255), anchor="mt")
    img.save(out_path)
    print(f"Saved: {out_path}")

def generate_expert_checklist(out_path: Path):
    fonts = get_fonts()
    img, draw, bbox = create_board_base(border_color=(40, 220, 130, 255))
    
    # Header Title
    title_text = "高金利時代に勝つ「優良企業の３条件」"
    draw.text((660, 65), title_text, font=fonts["title"], fill=(80, 255, 160), anchor="mt")
    draw.line([(80, 125), (1240, 125)], fill=(40, 110, 80, 200), width=2)
    
    cards = [
        ("１. 豊富なフリーキャッシュフロー（無借金経営）", "借金の借り換え金利に苦しまず、自前キャッシュで研究開発・成長投資ができる企業", (60, 230, 150)),
        ("２. 圧倒的な「価格転嫁力」（ブランド・堀 / Moat）", "原材料・人件費高騰でも確実に値上げでき、顧客が離れない独占的シェア", (255, 210, 60)),
        ("３. 「AI活用による経費削減」が機能する実力派", "派手な開発競争ではなく、AIで実務工数・販管費を削り利益率を押し上げる企業", (60, 210, 255)),
    ]
    
    y = 150
    for title, desc, col in cards:
        card_bbox = [80, y, 1240, y + 120]
        draw.rounded_rectangle(card_bbox, radius=16, fill=(24, 38, 32, 230), outline=col, width=3)
        draw.rounded_rectangle([80, y, 92, y + 120], radius=6, fill=col)
        draw.text((115, y + 18), title, font=fonts["h2"], fill=col)
        draw.text((115, y + 68), desc, font=fonts["body"], fill=(240, 250, 245))
        y += 140
        
    draw.text((660, 610), "ブームに飛びつかず、「本物のキャッシュ創出力」を見よ", font=fonts["footer"], fill=(255, 230, 90), anchor="mt")
    img.save(out_path)
    print(f"Saved: {out_path}")

if __name__ == "__main__":
    out_dir = Path("projects/02_market_analysis_2026/broll")
    generate_market_regime(out_dir / "market_regime_2026.png")
    generate_ai_phase_shift(out_dir / "ai_phase_shift.png")
    generate_expert_checklist(out_dir / "expert_checklist_2026.png")
