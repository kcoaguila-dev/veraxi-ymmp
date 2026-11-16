"""
The thumbnail system is topic-agnostic: there is no dedicated vs style.

Comparison topics are composed with the generic classic_split layout from
the slide's own data, and legacy configs that still carry layout="vs_duel"
or vs-only fields load safely (unknown fields are dropped) and render with
the generic layout.
"""

import json
from pathlib import Path

from PIL import Image

from veraxi_ymmp.graphics.thumbnail import (
    ThumbnailConfig,
    auto_extract_thumbnail_config,
    auto_extract_variant_configs,
    generate_thumbnail,
    validate_thumbnail_visual_qa,
)


def test_config_has_no_vs_specific_fields():
    cfg = ThumbnailConfig(title_line1="テスト")
    for field_name in (
        "opponent_character",
        "left_label",
        "right_label",
        "vs_badge_text",
        "speech_bubble",
        "zabuton_color",
    ):
        assert not hasattr(cfg, field_name), field_name


def test_legacy_vs_config_loads_and_renders_generically(tmp_path: Path):
    legacy = {
        "title_line1": "マイクロソフト vs アマゾン",
        "title_line2": "勝つのはどっち！？",
        "highlight_word": "勝つのはどっち！？",
        "badge": "【宿命の対決】",
        "character": "ずんだもん",
        "emotion": "surprised",
        "layout": "vs_duel",
        "opponent_character": "四国めたん",
        "left_label": "マイクロソフト",
        "right_label": "アマゾン",
        "speech_bubble": "大波乱なのだ！？",
        "zabuton_color": "red",
    }
    cfg = ThumbnailConfig.from_dict(legacy)
    out_img = tmp_path / "legacy_thumb.png"
    res_path = generate_thumbnail(cfg, out_img)
    assert res_path.exists()
    with Image.open(res_path) as im:
        assert im.size == (1920, 1080)
        assert im.mode == "RGBA"


def test_visual_qa_sentinel_on_generic_layout(tmp_path: Path):
    out_img = tmp_path / "qa_test_thumb.png"
    config = ThumbnailConfig(
        title_line1="コストコ",
        title_line2="ボロ儲け！？",
        highlight_word="ボロ儲け",
        badge="【超・裏事情】",
        character="ずんだもん",
        emotion="surprised",
    )
    generate_thumbnail(config, out_img)
    report = validate_thumbnail_visual_qa(out_img)
    assert report["passed"] is True, f"Visual QA failed: {report}"
    assert report["score"] >= 80
    assert report["checks"]["dimensions_valid"] is True
    assert report["checks"]["file_size_valid"] is True
    assert report["checks"]["timestamp_deadzone_safe"] is True


def test_comparison_slide_uses_generic_layout(tmp_path: Path):
    proj_dir = tmp_path / "comparison_project"
    proj_dir.mkdir(parents=True)
    (proj_dir / "script.json").write_text(
        json.dumps(
            [{"character": "ずんだもん", "text": "比較するのだ", "emotion": "surprised"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (proj_dir / "broll_manifest.json").write_text(
        json.dumps(
            [
                {
                    "slide_type": "comparison",
                    "title": "",
                    "left_box": ["マイクロソフト"],
                    "right_box": ["アマゾン"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    cfg = auto_extract_thumbnail_config(proj_dir)
    assert cfg.layout == "classic_split"
    assert "マイクロソフト" in cfg.title_line1
    assert "アマゾン" in cfg.title_line1


def test_variant_configs_are_generic(tmp_path: Path):
    proj_dir = tmp_path / "09_msft_vs_amzn_ai_war_2026"
    proj_dir.mkdir(parents=True)
    variants = auto_extract_variant_configs(proj_dir)
    assert set(variants) == {"A", "B"}
    assert variants["A"].layout != "vs_duel"
    assert variants["B"].layout != "vs_duel"
    assert variants["A"].theme == "gold"
    assert variants["B"].theme == "red"


def test_visual_qa_above_mobile_limit_passes_with_warning(tmp_path: Path):
    """A >2MB but <50MB master is uploadable on desktop/API (Oct 2025 rules).

    Regression: the visual QA gate hard-failed any file over the old 2MB
    limit, which is now only the mobile-app upload limit.
    """
    import random

    random.seed(11)
    img = Image.effect_noise((1920, 1080), 80).convert("RGB")
    out_img = tmp_path / "big_master.png"
    img.save(out_img)
    size = out_img.stat().st_size
    assert 2 * 1024 * 1024 < size < 50 * 1024 * 1024

    report = validate_thumbnail_visual_qa(out_img)
    assert report["checks"]["file_size_valid"] is True
    assert any("mobile" in w for w in report["warnings"])


def test_visual_qa_over_desktop_limit_fails(tmp_path: Path):
    """The 50MB desktop limit remains a hard QA failure."""
    img = Image.new("RGB", (1920, 1080), color=(10, 10, 10))
    out_img = tmp_path / "small.png"
    img.save(out_img)

    report = validate_thumbnail_visual_qa(out_img, max_bytes=1024)
    assert report["checks"]["file_size_valid"] is False
    assert report["passed"] is False
