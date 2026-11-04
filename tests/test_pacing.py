"""
Unit tests for the Retention Pacing Engine (veraxi_ymmp/pacing.py).
"""

from __future__ import annotations

from veraxi_ymmp.pacing import (
    audit_script_pacing,
    format_pacing_report_markdown,
)


def test_audit_empty_script() -> None:
    report = audit_script_pacing([])
    assert not report.is_healthy
    assert report.total_cuts == 0
    assert report.retention_score == 0
    assert any(v.rule_name == "EMPTY_SCRIPT" for v in report.violations)


def test_audit_healthy_trio() -> None:
    # 20 cuts: 10 Metan (50%), 6 Zundamon (30%), 4 Tsumugi (20%)
    script = []
    # Hook window (first 4 cuts: Metan and Zundamon only)
    script.append({"character": "ずんだもん", "text": "大変なのだ！2026年の相場なのだ！"})
    script.append({"character": "四国めたん", "text": "あら、どのような相場ですの？"})
    script.append({"character": "ずんだもん", "text": "一部の銘柄だけが急騰しているのだ！"})
    script.append({"character": "四国めたん", "text": "二極化が進む今年の大潮流ですわ。"})

    # Cuts 5 - 10 (Midroll approaches)
    for _ in range(3):
        script.append({"character": "四国めたん", "text": "電力と送電網が最強のテーマですわ。"})
        script.append({"character": "ずんだもん", "text": "データセンターに電力が必須なのだ！"})

    # Cut 11: Tsumugi enters at 50% mark
    script.append({"character": "春日部つむぎ", "text": "はいっ！半導体も大激変中ですよ！"})
    script.append({"character": "春日部つむぎ", "text": "独自ASICへの移行が進んでいます！"})
    script.append({"character": "四国めたん", "text": "設計受託企業が大躍進しましたわ。"})
    script.append({"character": "春日部つむぎ", "text": "本気のカスタムチップ戦略ですね！"})

    # Climax and wrap-up
    script.append({"character": "ずんだもん", "text": "なるほどなのだ！"})
    script.append({"character": "四国めたん", "text": "キャッシュフローの確認が鍵ですわ。"})
    script.append({"character": "春日部つむぎ", "text": "物理インフラと自社キャッシュですね！"})
    script.append({"character": "ずんだもん", "text": "まさにその通りなのだ！"})
    script.append({"character": "四国めたん", "text": "チャンネル登録よろしくお願いいたしますわ。"})

    report = audit_script_pacing(script)
    assert report.is_healthy
    assert report.retention_score >= 90
    assert report.num_characters == 3
    assert "春日部つむぎ" in report.character_stats

    tsumugi_stats = report.character_stats["春日部つむぎ"]
    assert 0.15 <= tsumugi_stats.cut_ratio <= 0.22


def test_specialist_ratio_exceeded() -> None:
    # 10 cuts: 5 Tsumugi (50%), 3 Metan (30%), 2 Zundamon (20%)
    script = [
        {"character": "四国めたん", "text": "hook 1"},
        {"character": "ずんだもん", "text": "hook 2"},
        {"character": "四国めたん", "text": "hook 3"},
        {"character": "ずんだもん", "text": "hook 4"},
        {"character": "春日部つむぎ", "text": "tsumugi 1"},
        {"character": "春日部つむぎ", "text": "tsumugi 2"},
        {"character": "四国めたん", "text": "metan 5"},
        {"character": "春日部つむぎ", "text": "tsumugi 3"},
        {"character": "春日部つむぎ", "text": "tsumugi 4"},
        {"character": "春日部つむぎ", "text": "tsumugi 5"},
    ]
    report = audit_script_pacing(script)
    rule_names = [v.rule_name for v in report.violations]
    assert "SPECIALIST_RATIO_EXCEEDED" in rule_names


def test_hook_contamination() -> None:
    # Tsumugi speaks at cut index 0
    script = [
        {"character": "春日部つむぎ", "text": "最初から登場しちゃうのだ！"},
        {"character": "四国めたん", "text": "あら、早すぎますわ。"},
        {"character": "ずんだもん", "text": "ずんだもんなのだ！"},
    ] + [{"character": "四国めたん", "text": f"text {i}"} for i in range(10)]

    report = audit_script_pacing(script)
    rule_names = [v.rule_name for v in report.violations]
    assert "HOOK_CONTAMINATION" in rule_names


def test_grounded_staging_violation() -> None:
    script = [
        {"character": "ずんだもん", "text": "ジャンプするのだ！", "motion": "jump"},
        {"character": "四国めたん", "text": "落ち着きなさい。"},
    ]
    report = audit_script_pacing(script)
    rule_names = [v.rule_name for v in report.violations]
    assert "GROUNDED_STAGING_INVARIANT" in rule_names


def test_specialist_run_length_exceeded() -> None:
    script = [
        {"character": "ずんだもん", "text": "hook 1"},
        {"character": "四国めたん", "text": "hook 2"},
        {"character": "ずんだもん", "text": "hook 3"},
        {"character": "四国めたん", "text": "hook 4"},
        {"character": "春日部つむぎ", "text": "tsumugi 1"},
        {"character": "春日部つむぎ", "text": "tsumugi 2"},
        {"character": "春日部つむぎ", "text": "tsumugi 3"},
        {"character": "春日部つむぎ", "text": "tsumugi 4"},  # 4 cuts in a row
        {"character": "四国めたん", "text": "wrap up"},
        {"character": "ずんだもん", "text": "end"},
    ]
    report = audit_script_pacing(script)
    rule_names = [v.rule_name for v in report.violations]
    assert "SPECIALIST_RUN_LENGTH_EXCEEDED" in rule_names


def test_format_pacing_report_markdown() -> None:
    script = [
        {"character": "ずんだもん", "text": "hook 1"},
        {"character": "四国めたん", "text": "hook 2"},
    ]
    report = audit_script_pacing(script)
    md = format_pacing_report_markdown(report)
    assert "Audience Retention Pacing Audit" in md
    assert "ずんだもん" in md
    assert "四国めたん" in md


def test_anti_slop_and_currency_invariants() -> None:
    script_trailing_dollar = [
        {"character": "ずんだもん", "text": "2200億$も投資するのだ！"},
        {"character": "四国めたん", "text": "莫大な金額ですわ。"},
    ]
    r1 = audit_script_pacing(script_trailing_dollar)
    assert any(v.rule_name == "TRAILING_DOLLAR_SIGN_ERROR" for v in r1.violations)

    script_ai_slop = [
        {"character": "四国めたん", "text": "本日の3つのポイントを解説しますわ。"},
        {"character": "ずんだもん", "text": "楽しみなのだ！"},
    ]
    r2 = audit_script_pacing(script_ai_slop)
    assert any(v.rule_name == "AI_SLOP_TEMPLATE_VIOLATION" for v in r2.violations)

    script_abbrev = [
        {"character": "ずんだもん", "text": "MSの株価はどうなるのだ？"},
        {"character": "四国めたん", "text": "エムエスの動きに注目ですわ。"},
    ]
    r3 = audit_script_pacing(script_abbrev)
    assert any(v.rule_name == "ABBREVIATED_COMPANY_NAME_VIOLATION" for v in r3.violations)


def test_opening_greeting_and_visual_anchor_invariants() -> None:
    # Test greeting violation in first 3 cuts
    script_greeting = [
        {"character": "ずんだもん", "text": "みんな、こんにちはなのだ！", "image": "broll/slide_01.png"},
        {"character": "四国めたん", "text": "ごきげんよう、四国めたんですわ。"},
    ]
    r1 = audit_script_pacing(script_greeting)
    assert any(v.rule_name == "OPENING_GREETING_VIOLATION" for v in r1.violations)

    # Test premature slide overload on cut 0
    script_slide_on_hook = [
        {"character": "ずんだもん", "text": "大変な事実が発覚したのだ！", "image": "broll/slide_01.png"},
        {"character": "四国めたん", "text": "何事ですの？"},
    ]
    r2 = audit_script_pacing(script_slide_on_hook)
    assert any(v.rule_name == "PREMATURE_SLIDE_OVERLOAD" for v in r2.violations)


def test_rival_retention_rules() -> None:
    # 1. Zundamon Persona Contamination
    script_zundamon_slop = [
        {"character": "ずんだもん", "text": "大企業ほど、特定のAIベンダーへの依存を嫌がるのだ！"},
        {"character": "四国めたん", "text": "その通りですわ。"},
    ]
    r1 = audit_script_pacing(script_zundamon_slop)
    assert any(v.rule_name == "ZUNDAMON_PERSONA_CONTAMINATION" for v in r1.violations)

    # 2. Yes-Man Metan
    script_yes_man = [
        {"character": "ずんだもん", "text": "株価が上がるのだ！"},
        {"character": "四国めたん", "text": "はい。上がりますわ。"},
        {"character": "ずんだもん", "text": "買い時なのだ！"},
        {"character": "四国めたん", "text": "その通りですわ。買い時ですわ。"},
        {"character": "ずんだもん", "text": "大儲けなのだ！"},
        {"character": "四国めたん", "text": "はい。大儲けですわ。"},
    ]
    r2 = audit_script_pacing(script_yes_man)
    assert any(v.rule_name == "YES_MAN_METAN_INVARIANT" for v in r2.violations)

    # 3. Rhythmic Syncopation Required
    script_monotone = [
        {"character": "ずんだもん", "text": f"これは非常に重要な解説文のサンプルその{i}なのだ！"}
        if i % 2 == 0
        else {"character": "四国めたん", "text": f"こちらも負けずに長い解説文のサンプルその{i}ですわ。"}
        for i in range(16)
    ]
    r3 = audit_script_pacing(script_monotone)
    assert any(v.rule_name == "RHYTHMIC_SYNCOPATION_REQUIRED" for v in r3.violations)

    # 4. Formulaic Ending Drop Off
    script_ending = [
        {"character": "ずんだもん", "text": f"本編カットその{i}なのだ！"} for i in range(5)
    ] + [
        {"character": "四国めたん", "text": "チャンネル登録と高評価もぜひよろしくねー！"},
        {"character": "ずんだもん", "text": "また次回の分析動画で会おうなのだ！"},
    ]
    r4 = audit_script_pacing(script_ending)
    assert any(v.rule_name == "FORMULAIC_ENDING_DROP_OFF" for v in r4.violations)

    # 5. Naked Pricing Ambiguity
    script_naked_pricing = [
        {"character": "ずんだもん", "text": "いくらで契約できるのだ？"},
        {"character": "四国めたん", "text": "月額30ドルで世界中から集金できますわ。"},
        {"character": "ずんだもん", "text": "高いのだ！"},
    ]
    r5 = audit_script_pacing(script_naked_pricing)
    assert any(v.rule_name == "NAKED_PRICING_AMBIGUITY" for v in r5.violations)

    script_qualified_pricing = [
        {"character": "ずんだもん", "text": "いくらで契約できるのだ？"},
        {"character": "四国めたん", "text": "法人向けに社員1人あたり月30ドルの追加課金ですわ。"},
        {"character": "ずんだもん", "text": "1人月30ドルの追加は高いのだ！"},
    ]
    r6 = audit_script_pacing(script_qualified_pricing)
    assert not any(v.rule_name == "NAKED_PRICING_AMBIGUITY" for v in r6.violations)
