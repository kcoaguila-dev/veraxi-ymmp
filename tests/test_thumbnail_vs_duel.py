"""
Unit tests for Advanced VS Duel Layout and Visual QA Sentinel
Verifies rival-grade layout generation, dual character staging, and YouTube safe-zone compliance.
"""

from pathlib import Path
from PIL import Image

from veraxi_ymmp.graphics.thumbnail import (
    ThumbnailConfig,
    generate_thumbnail,
    auto_extract_thumbnail_config,
    auto_extract_variant_configs,
    validate_thumbnail_visual_qa,
)


def test_generate_vs_duel_thumbnail(tmp_path: Path):
    out_img = tmp_path / "vs_duel_thumb.png"
    config = ThumbnailConfig(
        title_line1="マイクロソフト vs アマゾン",
        title_line2="勝つのはどっち！？",
        highlight_word="勝つのはどっち！？",
        sub_hook="▶ 4000億ドルのAI戦争で笑う企業・沈む企業",
        badge="【宿命の対決】",
        character="ずんだもん",
        emotion="surprised",
        layout="vs_duel",
        opponent_character="四国めたん",
        opponent_emotion="neutral",
        left_label="マイクロソフト",
        right_label="アマゾン",
        speech_bubble="大波乱なのだ！？",
        zabuton_color="red",
    )
    res_path = generate_thumbnail(config, out_img)
    assert res_path.exists()
    assert res_path.stat().st_size > 0

    with Image.open(res_path) as im:
        assert im.size == (1920, 1080)
        assert im.mode == "RGBA"


def test_visual_qa_sentinel(tmp_path: Path):
    out_img = tmp_path / "qa_test_thumb.png"
    config = ThumbnailConfig(
        title_line1="マイクロソフト vs アマゾン",
        title_line2="勝つのはどっち！？",
        badge="【宿命の対決】",
        character="ずんだもん",
        layout="vs_duel",
        opponent_character="四国めたん",
        left_label="マイクロソフト",
        right_label="アマゾン",
        speech_bubble="大波乱なのだ！？",
        zabuton_color="red",
    )
    generate_thumbnail(config, out_img)

    report = validate_thumbnail_visual_qa(out_img)
    assert report["passed"] is True, f"Visual QA failed: {report}"
    assert report["score"] >= 80
    assert report["checks"]["dimensions_valid"] is True
    assert report["checks"]["file_size_valid"] is True
    assert report["checks"]["timestamp_deadzone_safe"] is True


def test_auto_extract_msft_vs_amzn_preset(tmp_path: Path):
    proj_dir = tmp_path / "09_msft_vs_amzn_ai_war_2026"
    proj_dir.mkdir(parents=True, exist_ok=True)

    cfg = auto_extract_thumbnail_config(proj_dir)
    assert cfg.layout == "vs_duel"
    assert "マイクロソフト" in cfg.title_line1
    assert "アマゾン" in cfg.title_line1
    assert cfg.opponent_character == "四国めたん"
    assert cfg.character == "ずんだもん"
    assert cfg.zabuton_color == "red"


def test_vs_duel_variant_configs(tmp_path: Path):
    proj_dir = tmp_path / "09_msft_vs_amzn_ai_war_2026"
    proj_dir.mkdir(parents=True, exist_ok=True)

    variants = auto_extract_variant_configs(proj_dir)
    assert "A" in variants
    assert "B" in variants
    assert variants["A"].layout == "vs_duel"
    assert variants["B"].layout == "vs_duel"
    # Variant A has red zabuton, Variant B has gold zabuton / urgent hook
    assert variants["A"].zabuton_color == "red"
    assert variants["B"].zabuton_color == "gold"
    assert "完全敗北" in variants["B"].title_line2
