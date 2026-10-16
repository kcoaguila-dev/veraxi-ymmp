"""
Unit tests for YouTube Thumbnail Generation Engine (veraxi_ymmp.thumbnail)
"""
import json
from pathlib import Path
from PIL import Image

import pytest
from veraxi_ymmp.thumbnail import (
    ThumbnailConfig,
    generate_thumbnail,
    auto_extract_thumbnail_config,
    generate_project_thumbnail,
    get_thumbnail_fonts,
    THEMES,
)


def test_thumbnail_config_serialization():
    config = ThumbnailConfig(
        title_line1="テストタイトル",
        title_line2="急上昇の秘密",
        highlight_word="急上昇",
        sub_hook="▶ 9割が知らない新事実",
        badge="【徹底解説】",
        character="ずんだもん",
        emotion="happy",
        theme="emerald",
    )
    d = config.to_dict()
    assert d["title_line1"] == "テストタイトル"
    assert d["highlight_word"] == "急上昇"
    assert d["theme"] == "emerald"

    reconstructed = ThumbnailConfig.from_dict(d)
    assert reconstructed.title_line1 == config.title_line1
    assert reconstructed.highlight_word == config.highlight_word
    assert reconstructed.theme == config.theme


def test_get_thumbnail_fonts():
    fonts = get_thumbnail_fonts()
    assert "badge" in fonts
    assert "title1" in fonts
    assert "title2" in fonts
    assert "sub" in fonts


def test_generate_thumbnail_file(tmp_path: Path):
    out_img = tmp_path / "test_thumb.png"
    config = ThumbnailConfig(
        title_line1="AI革命で",
        title_line2="激変する近未来",
        highlight_word="激変",
        sub_hook="▶ 乗り遅れると大損する3つの理由",
        badge="【緊急速報】",
        character="ずんだもん",
        emotion="surprised",
        theme="gold",
    )
    res_path = generate_thumbnail(config, out_img)
    assert res_path.exists()
    assert res_path.stat().st_size > 0

    with Image.open(res_path) as im:
        assert im.size == (1920, 1080)
        assert im.mode == "RGBA"


@pytest.mark.parametrize("theme_name", list(THEMES.keys()))
def test_generate_thumbnail_all_themes(tmp_path: Path, theme_name: str):
    out_img = tmp_path / f"thumb_{theme_name}.png"
    config = ThumbnailConfig(
        title_line1="テーマ検証",
        title_line2=f"{theme_name}カラー",
        highlight_word=f"{theme_name}",
        theme=theme_name,
    )
    res_path = generate_thumbnail(config, out_img)
    assert res_path.exists()
    assert res_path.stat().st_size > 0


def test_auto_extract_explicit_config():
    script_with_thumb = [
        {
            "type": "thumbnail",
            "title_line1": "特注見出し",
            "title_line2": "大暴露スペシャル",
            "highlight_word": "大暴露",
            "theme": "red",
        },
        {
            "character": "ずんだもん",
            "text": "こんにちはなのだ！",
        }
    ]
    cfg = auto_extract_thumbnail_config(script_with_thumb)
    assert cfg.title_line1 == "特注見出し"
    assert cfg.title_line2 == "大暴露スペシャル"
    assert cfg.highlight_word == "大暴露"
    assert cfg.theme == "red"


def test_auto_extract_costco_project():
    proj_dir = Path("projects/01_costco_business_model")
    if proj_dir.exists():
        cfg = auto_extract_thumbnail_config(proj_dir)
        assert "コストコ" in cfg.title_line1
        assert "ボロ儲け" in cfg.title_line2
        assert cfg.character == "ずんだもん"
        assert cfg.theme == "gold"


def test_auto_extract_market_project():
    proj_dir = Path("projects/02_market_analysis_2026")
    if proj_dir.exists():
        cfg = auto_extract_thumbnail_config(proj_dir)
        assert "株式市場" in cfg.title_line1 or "2026" in cfg.title_line1
        assert "大暴落" in cfg.title_line2 or "大波乱" in cfg.title_line2
        assert cfg.theme == "red"


def test_generate_project_thumbnail(tmp_path: Path):
    proj_dir = Path("projects/01_costco_business_model")
    if proj_dir.exists():
        out_target = tmp_path / "costco_thumb.png"
        res = generate_project_thumbnail(proj_dir, out_path=out_target)
        assert res.exists()
        assert res.stat().st_size > 0
