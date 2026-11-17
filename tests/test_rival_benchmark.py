"""Tests for numeric-density cognitive-load auditing and rival transcript benchmarking."""

from __future__ import annotations

from pathlib import Path

from veraxi_ymmp.editorial.pacing import audit_script_pacing
from veraxi_ymmp.editorial.rival_benchmark import (
    audit_script_numeric_density,
    benchmark_rival_source,
    format_benchmark_comparison_markdown,
    parse_subtitle_file,
)


def test_numeric_density_flags_overload_and_streak() -> None:
    """Scripts with >35% numeric cuts and >=5 consecutive numeric cuts trigger violations."""
    cuts = [
        {"character": "四国めたん", "text": "売上は３３２億ドルよ。"},
        {"character": "ずんだもん", "text": "前年比１２０６％で１３倍なのだ！"},
        {"character": "四国めたん", "text": "トークン課金が２６３億ドル。"},
        {"character": "四国めたん", "text": "サブスクが６９億ドルよ。"},
        {"character": "四国めたん", "text": "大口顧客は９５０社から１万１９００社へ。"},
        {"character": "ずんだもん", "text": "すごいのだ！"},
        {"character": "四国めたん", "text": "手元資金は１３１８億ドルよ。"},
    ]
    report, violations = audit_script_numeric_density(cuts)
    names = {v["rule_name"] for v in violations}
    assert report.cuts_with_numbers == 6
    assert report.max_numeric_streak == 5
    assert "NUMERIC_OVERLOAD" in names
    assert "NUMERIC_STREAK_FATIGUE" in names
    assert "MULTI_NUMBER_BUBBLES" in names


def test_numeric_density_healthy_script_passes() -> None:
    """Scripts under 25% numeric cuts with short streaks produce zero numeric violations."""
    cuts = [
        {"character": "四国めたん", "text": "今回は{AI|エーアイ}市場の競争を見るわ。"},
        {"character": "ずんだもん", "text": "どっちが勝つのなのだ？"},
        {"character": "四国めたん", "text": "売上は前年比２倍に伸びているわ。"},
        {"character": "ずんだもん", "text": "なるほどなのだ！"},
        {"character": "四国めたん", "text": "でも利益構造がまったく違うのよ。"},
        {"character": "ずんだもん", "text": "どういうことなのだ？"},
    ]
    report, violations = audit_script_numeric_density(cuts)
    assert report.cuts_with_numbers == 1
    assert violations == []


def test_pacing_audit_includes_numeric_overload() -> None:
    """audit_script_pacing surfaces NUMERIC_OVERLOAD when dialogue is figure-heavy."""
    script = [
        {"character": "四国めたん", "text": f"指標は{i * 10}億ドルよ。", "image": None if i < 3 else "broll/s1.png"}
        for i in range(1, 21)
    ]
    pacing_report = audit_script_pacing(script)
    rule_names = {v.rule_name for v in pacing_report.violations}
    assert "NUMERIC_OVERLOAD" in rule_names
    assert "NUMERIC_STREAK_FATIGUE" in rule_names


def test_parse_srt_and_benchmark_comparison(tmp_path: Path) -> None:
    """Parses SRT timestamps, computes numbers/min + first-number latency, and formats Markdown."""
    srt_path = tmp_path / "rival.srt"
    srt_path.write_text(
        "1\n"
        "00:00:00,000 --> 00:00:15,000\n"
        "Why is everyone talking about this AI stock?\n\n"
        "2\n"
        "00:00:15,000 --> 00:00:30,000\n"
        "The market cap just crossed 2 trillion dollars.\n\n"
        "3\n"
        "00:00:30,000 --> 00:01:00,000\n"
        "Let us look at what actually drives the business.\n",
        encoding="utf-8",
    )
    segments = parse_subtitle_file(srt_path)
    assert len(segments) == 3

    rival = benchmark_rival_source(str(srt_path))
    assert rival.density.total_numbers == 1
    assert rival.density.first_number_seconds == 15.0
    assert rival.density.numbers_per_minute == 1.0

    md = format_benchmark_comparison_markdown("11_anthropic_ipo_2026", rival.density, [rival])
    assert "Rival Numeric-Density & Hook Benchmark" in md
    assert "11_anthropic_ipo_2026 (Ours)" in md
    assert "15.0s" in md


def test_thumbnail_rule_of_three_audit() -> None:
    """Flags cluttered >3-element thumbnails while passing clean 3-element configs."""
    from veraxi_ymmp.graphics.thumbnail_composer import audit_thumbnail_rule_of_three

    cluttered = {
        "layout": "editorial_spotlight",
        "character": "ずんだもん",
        "title_line1": "上場の裏に潜む",
        "title_line2": "9000億ドルの罠！？",
        "eyebrow_text": "【IPOの闇】時価総額2兆ドル",
        "subject_image_path": "ceo.jpg",
        "subject_caption": "Dario Amodei CEO",
        "brand_logo_path": "logo.png",
        "brand_symbol_path": "sym.png",
    }
    res_bad = audit_thumbnail_rule_of_three(cluttered)
    assert not res_bad["passed"]
    assert res_bad["element_count"] == 7

    clean = {
        "layout": "classic_split",
        "character": "ずんだもん",
        "title_line1": "9000億ドルの罠",
        "badge": "【IPOの闇】",
    }
    res_ok = audit_thumbnail_rule_of_three(clean)
    assert res_ok["passed"]
    assert res_ok["element_count"] == 3


def test_thumbnail_title_pairing_and_logo_discovery(tmp_path: Path) -> None:
    """Detects redundant title/thumbnail overlap and auto-discovers brand logos."""
    from veraxi_ymmp.graphics.thumbnail_composer import (
        audit_thumbnail_title_pairing,
        discover_project_brand_logo,
    )

    redundant = audit_thumbnail_title_pairing(
        {"title_line1": "アンソロピック", "title_line2": "9000億ドルの罠"},
        "アンソロピック9000億ドルの罠を解説",
    )
    assert not redundant["passed"]

    complementary = audit_thumbnail_title_pairing(
        {"title_line1": "上場に潜む罠", "title_line2": "9000億ドルの闇"},
        "アンソロピックIPOに潜む巨額債務の正体とは？",
    )
    assert complementary["passed"]

    assets = tmp_path / "sources" / "assets"
    assets.mkdir(parents=True)
    logo = assets / "acme_logo.png"
    logo.write_bytes(b"fake")
    assert discover_project_brand_logo(tmp_path) == str(logo)


def test_analyze_rival_hook_classification() -> None:
    """Classifies rival 30s hooks into loss-aversion vs slow-greeting archetypes."""
    from veraxi_ymmp.editorial.rival_benchmark import analyze_rival_hook

    loss_hook = analyze_rival_hook([
        ("全財産突っ込んで億り人になるのだー！！", 0.0, 3.0),
        ("その全財産、一瞬で蒸発しますわよ。", 3.0, 6.0),
        ("はあ！？養分になるのだ！？", 6.0, 9.0),
        ("ここは30秒以降なので含まれない", 35.0, 38.0),
    ])
    assert loss_hook.archetype == "loss_aversion_in_media_res"
    assert not loss_hook.has_greeting
    assert loss_hook.hook_line_count == 3
    assert "全財産" in loss_hook.loss_aversion_hits
    assert "蒸発" in loss_hook.loss_aversion_hits

    slow_hook = analyze_rival_hook([
        ("皆さんこんにちは！今日は解説します。", 0.0, 4.0),
        ("ゆっくりしていってね。", 4.0, 7.0),
    ])
    assert slow_hook.archetype == "slow_greeting_intro"
    assert slow_hook.has_greeting
