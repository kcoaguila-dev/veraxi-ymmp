import pytest
from pathlib import Path
from veraxi_ymmp.broll import (
    check_cognitive_load,
    MAX_SLIDE_CHARS,
    MAX_SLIDE_ELEMENTS,
    render_metric_slide,
    render_vs_slide,
    render_overview_slide,
    render_from_manifest,
    ACCENT_BLUE,
    ACCENT_GREEN,
    ACCENT_RED,
)


def test_cognitive_load_rejection_on_excessive_chars():
    """Ensures slides exceeding MAX_SLIDE_CHARS are strictly rejected."""
    long_text = "これはテスト用の非常に長いテキストブロックであり、4秒から5秒の短いカットにおいて視聴者に読字負荷を過剰に与えてしまう典型的なPowerPoint症候群のスライドです。さらに余計な補足説明を延々と追加して画面を文字で埋め尽くしています。"
    with pytest.raises(ValueError, match="Total text length .* exceeds the safe limit"):
        check_cognitive_load(
            slide_title="認知負荷テスト",
            text_elements=["タイトル", long_text],
            max_chars=MAX_SLIDE_CHARS,
        )


def test_cognitive_load_rejection_on_excessive_elements():
    """Ensures slides with too many fragmented text boxes are rejected."""
    elements = ["Element 1", "Element 2", "Element 3", "Element 4", "Element 5", "Element 6", "Element 7"]
    with pytest.raises(ValueError, match="discrete text blocks"):
        check_cognitive_load(
            slide_title="要素過多テスト",
            text_elements=elements,
            max_elements=MAX_SLIDE_ELEMENTS,
        )


def test_render_metric_slide_passes_clean_content(tmp_path: Path):
    """Ensures clean 1-Slide-1-Impact metric slide passes check and renders."""
    out_file = tmp_path / "test_metric.png"
    render_metric_slide(
        out_path=out_file,
        title="クリーンな指標スライド",
        step_tag="条件 01",
        hero_metric="豊富なフリーCF",
        status_pill="自前資金で成長投資を継続",
        impact_tag="",
        impact_text="不況期でも強気の投資を維持",
        theme_color=ACCENT_BLUE,
    )
    assert out_file.exists()


def test_render_vs_slide_passes_clean_content(tmp_path: Path):
    """Ensures clean VS comparison slide renders properly within cognitive load ceiling."""
    out_file = tmp_path / "test_vs.png"
    render_vs_slide(
        out_path=out_file,
        title="新旧モデルの比較",
        step_tag="",
        hero_title="収益構造の転換",
        hero_status="",
        left_box=("旧来", "薄利多売", []),
        right_box=("新型", "会員制モデル", []),
        bottom_tag="",
        bottom_text="",
        theme_color=ACCENT_BLUE,
    )
    assert out_file.exists()
    assert out_file.stat().st_size > 0


def test_render_overview_slide_passes_clean_content(tmp_path: Path):
    """Ensures clean overview agenda slide renders properly."""
    out_file = tmp_path / "test_overview.png"
    cards = [
        ("01", "米金利 4.0%の高止まり", ACCENT_RED),
        ("02", "原油 100ドル突破の再燃", ACCENT_BLUE),
        ("03", "日銀 30年ぶりの金利復活", ACCENT_GREEN),
    ]
    render_overview_slide(
        out_path=out_file,
        title="2026年 株式市場の現在地と3大変化",
        cards=cards,
        theme_color=ACCENT_BLUE,
    )
    assert out_file.exists()
    assert out_file.stat().st_size > 0


def test_render_from_manifest_and_market_analysis_manifest(tmp_path: Path):
    """Ensures render_from_manifest renders all slides in projects/02_market_analysis_2026/broll_manifest.json."""
    manifest_path = tmp_path / "broll_manifest.json"
    import json
    manifest_path.write_text(json.dumps([{"text_content": "test", "cognitive_load": 0.5}], ensure_ascii=False))

    generated = render_from_manifest(manifest_path, tmp_path)
    assert len(generated) >= 1
    for slide_path in generated:
        assert slide_path.exists()
        assert slide_path.stat().st_size > 0


def test_vertical_mobile_broll_rendering_and_detection(tmp_path: Path):
    """Ensures 9:16 mobile vertical mode renders 1080x720 cards and auto-detects vertical projects."""
    from PIL import Image
    from veraxi_ymmp.broll import (
        detect_project_vertical,
        VERTICAL_BROLL_WIDTH,
        VERTICAL_BROLL_HEIGHT,
    )

    metric_out = tmp_path / "vert_metric.png"
    render_metric_slide(
        out_path=metric_out,
        title="モバイル縦型メトリクス",
        step_tag="01 • OVERVIEW",
        hero_metric="Webサイトの75%が稼働",
        status_pill="圧倒的なシェアと実績",
        impact_tag="ポイント",
        impact_text="WordPressなど主要CMSの基盤",
        theme_color=ACCENT_BLUE,
        is_vertical=True,
    )
    with Image.open(metric_out) as img:
        assert img.size == (VERTICAL_BROLL_WIDTH, VERTICAL_BROLL_HEIGHT)

    vs_out = tmp_path / "vert_vs.png"
    render_vs_slide(
        out_path=vs_out,
        title="世代間の進化比較",
        step_tag="",
        hero_title="劇的な高速化と型安全",
        hero_status="",
        left_box=("旧世代 PHP 5", "実行速度が遅い", []),
        right_box=("最新 PHP 8.x", "JITで2〜3倍高速", []),
        bottom_tag="",
        bottom_text="",
        theme_color=ACCENT_GREEN,
        is_vertical=True,
    )
    with Image.open(vs_out) as img:
        assert img.size == (VERTICAL_BROLL_WIDTH, VERTICAL_BROLL_HEIGHT)

    overview_out = tmp_path / "vert_overview.png"
    render_overview_slide(
        out_path=overview_out,
        title="モバイル3大ポイント",
        cards=[
            ("01", "JITコンパイラ搭載", ACCENT_BLUE),
            ("02", "Laravelエコシステム", ACCENT_RED),
            ("03", "爆速デプロイと運用性", ACCENT_GREEN),
        ],
        theme_color=ACCENT_BLUE,
        is_vertical=True,
    )
    with Image.open(overview_out) as img:
        assert img.size == (VERTICAL_BROLL_WIDTH, VERTICAL_BROLL_HEIGHT)

    assert detect_project_vertical(tmp_path, [{"is_vertical": True}]) is True
    assert detect_project_vertical(tmp_path, [{"aspect_ratio": "9:16"}]) is True
    assert detect_project_vertical(tmp_path, [{}]) is False
