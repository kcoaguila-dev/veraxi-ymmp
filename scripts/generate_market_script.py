# -*- coding: utf-8 -*-
"""Generate high-quality 8-12 minute YouTube script for 2026 Stock Market Rotation."""
import json
from pathlib import Path
from veraxi_ymmp.script import validate_production_script

dialogues = [
    # Directive: Clean instrumental BGM ducked low
    {
        "type": "bgm",
        "path": "assets/bgm/2_23_AM.mp3",
        "volume": 8
    },

    # --- Chapter 1: Hook & 2026 Market Paradox ---
    {
        "bg": "assets/bg/clean_classroom.jpg",
        "character": "ずんだもん",
        "emotion": "happy",
        "motion": "none",
        "character_position": "right",
        "text": "みんな、こんにちはなのだ！ずんだもんなのだ！"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "text": "ごきげんよう、四国めたんですわ。"
    },
    {
        "character": "ずんだもん",
        "emotion": "surprised",
        "motion": "none",
        "character_position": "right",
        "text": "めたん！2026年の株式市場がとんでもないことになってるのだ！"
    },
    {
        "character": "ずんだもん",
        "emotion": "confused",
        "motion": "none",
        "character_position": "right",
        "text": "株価指数は最高値圏なのに、持ってる株が全然上がらないのだ…"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "text": "その違和感、極めて正確な洞察ですわ。"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "left",
        "text": "現在の株式市場は、表面上の指数上昇と内部の激変が乖離しています。"
    },
    {
        "character": "ずんだもん",
        "emotion": "surprised",
        "motion": "none",
        "character_position": "right",
        "text": "指数だけ上がって中身がボロボロってことなのだ！？"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "text": "はい、ごく一部の巨大資本に資金が集中し、二極化が進んでいますわ。"
    },
    {
        "character": "ずんだもん",
        "emotion": "scared",
        "motion": "none",
        "character_position": "right",
        "text": "昔みたいにインデックスを買えば安心の相場じゃないのだ！？"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "left",
        "text": "盲目的な集中投資は、今や極めて高いリスクを伴いますの。"
    },
    {
        "character": "ずんだもん",
        "emotion": "excited",
        "motion": "none",
        "character_position": "right",
        "text": "一体、水面下で何が起きているのか徹底的に教えてほしいのだ！"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "image": "broll/slide_01_agenda.png",
        "text": "かしこまりましたわ。まずはこちらの3大潮流をご覧ください。"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "left",
        "image": "broll/slide_01_agenda.png",
        "text": "第1にAI巨額投資の採算性と選別、第2に電力インフラへの資金シフト。"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "left",
        "image": "broll/slide_01_agenda.png",
        "text": "そして第3に、金利高止まり下でのキャッシュフロー重視ですわ。"
    },
    {
        "character": "ずんだもん",
        "emotion": "confused",
        "motion": "none",
        "character_position": "right",
        "image": "broll/slide_01_agenda.png",
        "text": "どれもこれまでの常識を覆すキーワードばかりなのだ！"
    },
    {
        "character": "四国めたん",
        "emotion": "smug",
        "motion": "nod",
        "character_position": "left",
        "text": "順を追って、業界のプロの視点から紐解いてまいりましょう。"
    },

    # --- Chapter 2: The $250B AI Capex Reality Check ---
    {
        "character": "ずんだもん",
        "emotion": "surprised",
        "motion": "none",
        "character_position": "right",
        "text": "まずは第1の潮流、AIへの巨額投資についてなのだ！"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "image": "broll/slide_02_capex.png",
        "text": "こちらのデータをご覧ください。ハイパースケーラーの設備投資額です。"
    },
    {
        "character": "ずんだもん",
        "emotion": "surprised",
        "motion": "none",
        "character_position": "right",
        "image": "broll/slide_02_capex.png",
        "text": "年間2500億ドル！？日本円で約38兆円規模なのだ！？"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "image": "broll/slide_02_capex.png",
        "text": "その通りですわ。マイクロソフトやアルファベット、メタ等の合算です。"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "left",
        "image": "broll/slide_02_capex.png",
        "text": "彼らはAIデータセンターとGPU調達へ過去最大規模の投資を継続しています。"
    },
    {
        "character": "ずんだもん",
        "emotion": "happy",
        "motion": "none",
        "character_position": "right",
        "image": "broll/slide_02_capex.png",
        "text": "それならAI関連株はどこまでも上がり続けるはずなのだ！"
    },
    {
        "character": "四国めたん",
        "emotion": "sad",
        "motion": "none",
        "character_position": "left",
        "image": "broll/slide_02_capex.png",
        "text": "いいえ、市場はすでに次のステージ『投資回収の審判』に入りましたの。"
    },
    {
        "character": "ずんだもん",
        "emotion": "confused",
        "motion": "none",
        "character_position": "right",
        "text": "投資回収の審判って、どういうことなのだ？"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "text": "ウォール街の投資家が、『その巨額投資でいくら儲かったのか』を問い始めたのです。"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "left",
        "text": "期待だけで買われていた時代は終わり、営業利益での証明が求められています。"
    },
    {
        "character": "ずんだもん",
        "emotion": "scared",
        "motion": "none",
        "character_position": "right",
        "text": "儲けを出せていない企業は、いきなり投げ売りされるのだ！？"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "text": "まさにその通りですわ。減価償却費の急増に耐えられない企業は急落しています。"
    },
    {
        "character": "ずんだもん",
        "emotion": "surprised",
        "motion": "none",
        "character_position": "right",
        "text": "サーバーや半導体を買ったぶん、将来の経費負担が重くのしかかるのだね。"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "left",
        "text": "はい、資本効率を示すROIC（投下資本利益率）が厳しく審査される局面です。"
    },
    {
        "character": "ずんだもん",
        "emotion": "confused",
        "motion": "none",
        "character_position": "right",
        "text": "AIと言えば何でも上がった祭り騒ぎは完全に終わったのだね…"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "text": "その通りですわ。真の実益を生み出せるプラットフォーマーだけが残ります。"
    },

    # --- Chapter 3: The Rotation to Power, Grids & Physical Infrastructure ---
    {
        "character": "ずんだもん",
        "emotion": "excited",
        "motion": "none",
        "character_position": "right",
        "text": "じゃあ投資家のマネーは、次にどこへ向かっているのだ！？"
    },
    {
        "character": "四国めたん",
        "emotion": "smug",
        "motion": "nod",
        "character_position": "left",
        "image": "broll/slide_03_infrastructure.png",
        "text": "それが第2の潮流、物理インフラと電力網への大移動ですわ。"
    },
    {
        "character": "ずんだもん",
        "emotion": "confused",
        "motion": "none",
        "character_position": "right",
        "image": "broll/slide_03_infrastructure.png",
        "text": "半導体じゃなくて、電力や送電網なのだ！？"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "left",
        "image": "broll/slide_03_infrastructure.png",
        "text": "AIデータセンターの電力消費量は、従来の2倍以上に膨れ上がっています。"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "image": "broll/slide_03_infrastructure.png",
        "text": "どれだけ最新のチップがあっても、動かす電力がなければただの鉄くずですの。"
    },
    {
        "character": "ずんだもん",
        "emotion": "surprised",
        "motion": "none",
        "character_position": "right",
        "image": "broll/slide_03_infrastructure.png",
        "text": "電力供給がAI開発の最大のボトルネックになってるのだ！"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "text": "はい、そのため米国の独立系発電事業者や原子力発電に熱視線が集まっています。"
    },
    {
        "character": "ずんだもん",
        "emotion": "excited",
        "motion": "none",
        "character_position": "right",
        "text": "大手テックが次々と原子力やクリーンエネルギーと長期契約を結んでいるのだ！"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "left",
        "text": "さらに変圧器や送電設備、データセンターの液冷システム企業も爆発的成長中です。"
    },
    {
        "character": "ずんだもん",
        "emotion": "happy",
        "motion": "none",
        "character_position": "right",
        "text": "ゴールドラッシュでツルハシを売る店が儲かる、あの法則なのだね！"
    },
    {
        "character": "四国めたん",
        "emotion": "happy",
        "motion": "nod",
        "character_position": "left",
        "text": "的確な例えですわ。AIのツルハシは今やチップから物理インフラへ移りました。"
    },
    {
        "character": "ずんだもん",
        "emotion": "surprised",
        "motion": "none",
        "character_position": "right",
        "text": "地味に見えるインフラ企業が、実は一番確実な利益を出しているのだね。"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "left",
        "text": "設備更新には数年のリードタイムが必要なため、価格決定力も極めて強固ですわ。"
    },
    {
        "character": "ずんだもん",
        "emotion": "excited",
        "motion": "none",
        "character_position": "right",
        "text": "ハイテク株の枠組みを超えて、重電や資材銘柄へ資金が流れてる理由がわかったのだ！"
    },

    # --- Chapter 4: Enterprise Software Polarization ---
    {
        "character": "ずんだもん",
        "emotion": "confused",
        "motion": "none",
        "character_position": "right",
        "text": "でもめたん、ソフトウェア企業はどうなってるのだ？"
    },
    {
        "character": "ずんだもん",
        "emotion": "confused",
        "motion": "none",
        "character_position": "right",
        "text": "AIを使えばアプリ会社もウハウハなんじゃないのだ？"
    },
    {
        "character": "四国めたん",
        "emotion": "sad",
        "motion": "nod",
        "character_position": "left",
        "image": "broll/slide_04_software_polarization.png",
        "text": "実はそこに、最も残酷な勝敗の二極化が起きていますの。"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "left",
        "image": "broll/slide_04_software_polarization.png",
        "text": "こちらの比較をご覧ください。勝者と敗者の明暗が分かれています。"
    },
    {
        "character": "ずんだもん",
        "emotion": "surprised",
        "motion": "none",
        "character_position": "right",
        "image": "broll/slide_04_software_polarization.png",
        "text": "単機能SaaSが敗者で、AI統合プラットフォームが勝者なのだ！？"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "image": "broll/slide_04_software_polarization.png",
        "text": "はい、1アカウント月額課金という旧来のビジネスモデルが崩壊しつつあります。"
    },
    {
        "character": "ずんだもん",
        "emotion": "confused",
        "motion": "none",
        "character_position": "right",
        "image": "broll/slide_04_software_polarization.png",
        "text": "どうしてアカウント課金が通用しなくなっているのだ？"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "left",
        "text": "自律型AIエージェントが人間の作業を代替し、必要なID数が激減したからですわ。"
    },
    {
        "character": "ずんだもん",
        "emotion": "scared",
        "motion": "none",
        "character_position": "right",
        "text": "人が減ってAIが動くなら、席ごとの課金売上が落ちちゃうのだ！"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "text": "その通りですわ。単なる機能提供ツールは、AIに丸ごと飲み込まれました。"
    },
    {
        "character": "ずんだもん",
        "emotion": "surprised",
        "motion": "none",
        "character_position": "right",
        "text": "逆に勝っているAI統合プラットフォームは何が違うのだ？"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "left",
        "text": "企業の基幹データと業務フローそのものを握り、成果課金へ移行できていますの。"
    },
    {
        "character": "ずんだもん",
        "emotion": "excited",
        "motion": "none",
        "character_position": "right",
        "text": "業務の土台を押さえている企業だけが、強い価格決定力を保てるのだね！"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "text": "はい、旧型SaaSの株価倍率が暴落し、本物への淘汰が加速しています。"
    },

    # --- Chapter 5: Macro Rates & Valuation Decompression ---
    {
        "character": "ずんだもん",
        "emotion": "confused",
        "motion": "none",
        "character_position": "right",
        "text": "そして第3の潮流、金利高止まりの影響はどうなのだ？"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "image": "broll/slide_05_macro_interest.png",
        "text": "米国の10年債利回りは4%前後で高止まりし、低金利は完全に過去となりました。"
    },
    {
        "character": "ずんだもん",
        "emotion": "surprised",
        "motion": "none",
        "character_position": "right",
        "image": "broll/slide_05_macro_interest.png",
        "text": "無利息の国債でも4%貰えるなら、無理して危険な株を買わないのだ！"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "image": "broll/slide_05_macro_interest.png",
        "text": "その通りですわ。株式益回りとの差が縮小し、割高株が許容されなくなりました。"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "left",
        "image": "broll/slide_05_macro_interest.png",
        "text": "借金で無理やり成長を演出してきたゾンビ企業は次々と資金ショートしています。"
    },
    {
        "character": "ずんだもん",
        "emotion": "scared",
        "motion": "none",
        "character_position": "right",
        "image": "broll/slide_05_macro_interest.png",
        "text": "金利負担の重さに耐えられない会社が脱落していくのだね…"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "text": "さらに日本市場でも日銀の正常化が進み、為替の乱高下が起きていますわ。"
    },
    {
        "character": "ずんだもん",
        "emotion": "surprised",
        "motion": "none",
        "character_position": "right",
        "text": "円高円安のボラティリティに左右される相場が続いてるのだね。"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "left",
        "text": "だからこそ今、自前で潤沢なフリーキャッシュフローを生む企業が選ばれます。"
    },
    {
        "character": "ずんだもん",
        "emotion": "excited",
        "motion": "none",
        "character_position": "right",
        "text": "借金に頼らず、手元に本物の現金を生み出し続ける会社なのだ！"
    },
    {
        "character": "四国めたん",
        "emotion": "happy",
        "motion": "nod",
        "character_position": "left",
        "text": "まさにその通りですわ。現金を生む力こそが、金利ある世界で最強の盾です。"
    },

    # --- Chapter 6: Risk Management & Investor Choice ---
    {
        "character": "ずんだもん",
        "emotion": "excited",
        "motion": "none",
        "character_position": "right",
        "text": "相場に向き合う上で、専門家が重視する着眼点を知りたいのだ！"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "image": "broll/slide_06_action_rules.png",
        "text": "はい、相場のリスクを抑えるための3大分析視点ですわ。"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "left",
        "image": "broll/slide_06_action_rules.png",
        "text": "なお、投資はリスクを伴うため、最終判断は必ずご自身で行ってください。"
    },
    {
        "character": "ずんだもん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "right",
        "image": "broll/slide_06_action_rules.png",
        "text": "第1の視点は、営業キャッシュフローの質を点検することなのだ！"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "image": "broll/slide_06_action_rules.png",
        "text": "はい、見かけの利益だけでなく、実際の入出金を確認することが大切ですわ。"
    },
    {
        "character": "ずんだもん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "right",
        "image": "broll/slide_06_action_rules.png",
        "text": "第2の視点は、特定分野への集中を避けて慎重に分散することなのだ！"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "image": "broll/slide_06_action_rules.png",
        "text": "その通りですわ。一つの話題銘柄に偏りすぎない慎重さが身を守ります。"
    },
    {
        "character": "ずんだもん",
        "emotion": "normal",
        "motion": "none",
        "character_position": "right",
        "image": "broll/slide_06_action_rules.png",
        "text": "第3の視点は、自分自身のリスク許容度を冷静に再確認することなのだ！"
    },
    {
        "character": "四国めたん",
        "emotion": "normal",
        "motion": "nod",
        "character_position": "left",
        "image": "broll/slide_06_action_rules.png",
        "text": "相場の波に慌てないよう、ご自身の生活資金と相談して向き合いましょう。"
    },
    {
        "character": "ずんだもん",
        "emotion": "surprised",
        "motion": "none",
        "character_position": "right",
        "text": "誰かの意見を鵜呑みにせず、自分で納得して判断することが大原則なのだ！"
    },
    {
        "character": "四国めたん",
        "emotion": "happy",
        "motion": "nod",
        "character_position": "left",
        "text": "まさにその通りですわ。無理のない範囲で、冷静に向き合ってまいりましょう。"
    },
    {
        "character": "ずんだもん",
        "emotion": "happy",
        "motion": "none",
        "character_position": "right",
        "text": "今日の動画が役に立ったら、チャンネル登録と高評価をお願いするのだ！"
    },
    {
        "character": "四国めたん",
        "emotion": "happy",
        "motion": "nod",
        "character_position": "left",
        "text": "最後までご視聴いただき、本当にありがとうございましたわ。"
    }
]

# Run validation
validated = validate_production_script(dialogues)
print(f"Validated {len(validated)} script entries successfully.")

# Check all text lengths
max_len = 0
for idx, entry in enumerate(dialogues):
    if "text" in entry:
        text_len = len(entry["text"])
        if text_len > max_len:
            max_len = text_len
        if text_len > 40:
            print(f"WARNING: Entry {idx} has length {text_len}: {entry['text']}")

print(f"Max text length across all entries: {max_len} chars.")

# Save to target project script
out_path = Path("projects/07_ai_capex_market_rotation_2026/script.json")
out_path.write_text(json.dumps(validated, ensure_ascii=False, indent=2), encoding="utf-8-sig")
print(f"Saved script to {out_path}")
