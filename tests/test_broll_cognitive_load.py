import pytest
from pathlib import Path
from veraxi_ymmp.broll import (
    check_cognitive_load,
    MAX_SLIDE_CHARS,
    MAX_SLIDE_ELEMENTS,
    render_metric_slide,
    ACCENT_BLUE,
    ACCENT_RED,
)

def test_cognitive_load_rejection_on_excessive_chars():
    """Ensures slides exceeding MAX_SLIDE_CHARS are strictly rejected."""
    long_text = "これはテスト用の非常に長いテキストブロックであり、4秒から5秒の短いカットにおいて視聴者に読字負荷を過剰に与えてしまう典型的なPowerPoint症候群のスライドです。さらに余計な補足説明を延々と追加して画面を文字で埋め尽くしています。"
    with pytest.raises(ValueError, match="Total text length .* exceeds the safe limit"):
        check_cognitive_load(
            slide_title="認知負荷テスト",
            text_elements=["タイトル", long_text],
            max_chars=MAX_SLIDE_CHARS
        )

def test_cognitive_load_rejection_on_excessive_elements():
    """Ensures slides with too many fragmented text boxes are rejected."""
    elements = ["Element 1", "Element 2", "Element 3", "Element 4", "Element 5", "Element 6", "Element 7"]
    with pytest.raises(ValueError, match="discrete text blocks"):
        check_cognitive_load(
            slide_title="要素過多テスト",
            text_elements=elements,
            max_elements=MAX_SLIDE_ELEMENTS
        )

def test_render_metric_slide_passes_clean_content(tmp_path):
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
        theme_color=ACCENT_BLUE
    )
    assert out_file.exists()
