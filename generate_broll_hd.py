"""
High-Definition B-Roll Presentation Board Generator (Project Runner)
Uses the generalized veraxi_ymmp.broll module.
Strictly optimized for 5-6 second YouTube video cuts:
  - 1-Slide-1-Takeaway (Zero reading fatigue)
  - Dominant Hero Card + Full-width Impact Banner
  - ZERO robotic buzzwords (no 【警告】, 【急騰】, etc.)
  - Pro Dark Slate Palette
"""
from pathlib import Path
from veraxi_ymmp.broll import (
    render_metric_slide,
    render_vs_slide,
    render_overview_slide,
    ACCENT_BLUE,
    ACCENT_GREEN,
    ACCENT_AMBER,
    ACCENT_RED,
    ACCENT_VIOLET,
)

def generate_market_regime_overview(out_path: Path):
    cards = [
        ("01", "米金利 4.0%の高止まり", ACCENT_RED),
        ("02", "原油 100ドル突破の再燃", ACCENT_AMBER),
        ("03", "日銀 30年ぶりの金利復活", ACCENT_BLUE),
    ]
    render_overview_slide(
        out_path=out_path,
        title="2026年 株式市場の現在地と3大変化",
        cards=cards,
        theme_color=ACCENT_BLUE
    )

def generate_market_regime_pt1(out_path: Path):
    render_metric_slide(
        out_path=out_path,
        title="世界最高峰の金融引き締めが長期化",
        step_tag="要点 01",
        hero_metric="米国政策金利：3.75〜4.00%",
        status_pill="インフレ高止まりにより「高金利が長期固定化」",
        impact_tag="",
        impact_text="企業の利払い負担が倍増 → 財務脆弱な企業を容赦なく淘汰",
        theme_color=ACCENT_RED
    )

def generate_market_regime_pt2(out_path: Path):
    render_metric_slide(
        out_path=out_path,
        title="地政学リスクによるエネルギー価格の再燃",
        step_tag="要点 02",
        hero_metric="原油価格：1バレル100ドル突破",
        status_pill="エネルギー・物流コストのインフレ圧力が世界的に再燃",
        impact_tag="",
        impact_text="コスト高騰が直撃 → 価格転嫁できない企業から脱落",
        theme_color=ACCENT_AMBER
    )

def generate_market_regime_pt3(out_path: Path):
    render_metric_slide(
        out_path=out_path,
        title="30年ぶりの「金利のある世界」が完全定着",
        step_tag="要点 03",
        hero_metric="日銀利上げ：政策金利1.25%到達",
        status_pill="30年ぶりの「金利ある世界」へ完全移行",
        impact_tag="",
        impact_text="低金利バブルの終焉 → 借金依存のゾンビ企業が退場",
        theme_color=ACCENT_BLUE
    )

def generate_ai_phase_overview(out_path: Path):
    cards = [
        ("第1期", "設備投資の熱狂（2024〜2025年）", ACCENT_VIOLET),
        ("第2期", "投資回収（ROI）の試練（2026年〜現在）", ACCENT_RED),
    ]
    render_overview_slide(
        out_path=out_path,
        title="AI市場は『選別の第2期』へ突入",
        cards=cards,
        theme_color=ACCENT_VIOLET
    )

def generate_ai_phase_pt1(out_path: Path):
    render_metric_slide(
        out_path=out_path,
        title="設備投資の熱狂相場（2024〜2025年）",
        step_tag="第1期",
        hero_metric="半導体・GPUの買い漁り熱狂",
        status_pill="『AI』の看板だけで資金が殺到した初期ブーム",
        impact_tag="",
        impact_text="実際の利益を問わず「期待」だけで巨額マネーが流入",
        theme_color=ACCENT_VIOLET
    )

def generate_ai_phase_pt2(out_path: Path):
    render_metric_slide(
        out_path=out_path,
        title="投資回収（ROI）の過酷な試練（2026年〜現在）",
        step_tag="第2期",
        hero_metric="年間7,000億ドルの回収要求",
        status_pill="米ビッグテック巨額投資の「回収（ROI）」を問う検証期",
        impact_tag="",
        impact_text="支出に見合う利益が出ない企業は急落 → 実力派へ資金集中",
        theme_color=ACCENT_RED
    )

def generate_checklist_overview(out_path: Path):
    cards = [
        ("条件 01", "豊富なフリーキャッシュフロー（無借金経営）", ACCENT_GREEN),
        ("条件 02", "圧倒的な「価格転嫁力」（ブランド・堀）", ACCENT_AMBER),
        ("条件 03", "実務のAI活用による「経費削減力」", ACCENT_BLUE),
    ]
    render_overview_slide(
        out_path=out_path,
        title="高金利時代に勝つ「優良企業の3つの条件」",
        cards=cards,
        theme_color=ACCENT_GREEN
    )

def generate_checklist_pt1(out_path: Path):
    render_metric_slide(
        out_path=out_path,
        title="高金利下で最も強靭な「自前キャッシュ力」",
        step_tag="条件 01",
        hero_metric="豊富なフリーCF ＆ 無借金経営",
        status_pill="金利上昇の打撃を受けず、自前資金で成長投資を継続",
        impact_tag="",
        impact_text="銀行借入に依存せず、不況期でも強気の投資を維持",
        theme_color=ACCENT_GREEN
    )

def generate_checklist_pt2(out_path: Path):
    render_metric_slide(
        out_path=out_path,
        title="インフレ下でも利益率を維持する「経済的な堀」",
        step_tag="条件 02",
        hero_metric="圧倒的な「価格転嫁力」の保持",
        status_pill="原材料が高騰しても顧客が離れず、確実に値上げ可能",
        impact_tag="",
        impact_text="コスト増を即座に価格転嫁し、高い営業利益率を死守",
        theme_color=ACCENT_AMBER
    )

def generate_checklist_pt3(out_path: Path):
    render_metric_slide(
        out_path=out_path,
        title="派手なAI開発ではなく「実業の利益率改善」",
        step_tag="条件 03",
        hero_metric="実務の「AI効率化」で利益率拡大",
        status_pill="開発競争ではなく、社内業務に組み込み販管費を削る側",
        impact_tag="",
        impact_text="巨大顧客基盤 × AI自動化 ＝ 確実な増益体質を実現",
        theme_color=ACCENT_BLUE
    )

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
