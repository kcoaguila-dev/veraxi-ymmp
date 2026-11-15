"""Tests for graphics/packaging.py — Test & Compare title+thumbnail pairs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from veraxi_ymmp.graphics.packaging import (
    PACKAGING_AXES,
    build_axis_configs,
    build_axis_titles,
    generate_packaging,
    load_packaging,
    score_pair,
    score_title,
    select_packaging_pair,
    thumbnail_text_chars,
    title_thumbnail_overlap,
)
from veraxi_ymmp.graphics.thumbnail import ThumbnailConfig


def _costco_config() -> ThumbnailConfig:
    return ThumbnailConfig(
        title_line1="コストコ",
        title_line2="ボロ儲け！？",
        highlight_word="ボロ儲け",
        badge="【超・裏事情】",
        emotion="surprised",
    )


def _project(tmp_path: Path, with_metric: bool = True) -> Path:
    proj = tmp_path / "costco_project"
    proj.mkdir()
    script = [
        {"character": "ずんだもん", "text": "コストコの裏側を解説するのだ", "emotion": "surprised"},
        {"character": "四国めたん", "text": "年会費モデルが利益の柱よ", "emotion": "normal"},
    ]
    (proj / "script.json").write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    slide = {"title": "コストコの裏側", "slide_type": "metric"}
    if with_metric:
        slide["hero_metric"] = "850億ドル"
    (proj / "broll_manifest.json").write_text(
        json.dumps([slide], ensure_ascii=False), encoding="utf-8"
    )
    return proj


# --- Title building -------------------------------------------------------


def test_axis_titles_three_axes_and_ideal_length():
    titles = build_axis_titles("コストコの裏側", "850億ドル")
    assert set(titles) == set(PACKAGING_AXES)
    for t in titles.values():
        assert t.startswith("【ずんだもん解説】")
        assert len(t) <= 32, t


def test_axis_titles_long_topic_truncated_to_ideal():
    titles = build_axis_titles("あ" * 40)
    for t in titles.values():
        assert len(t) <= 32, t


def test_axis_titles_metric_used_verbatim():
    titles = build_axis_titles("コストコの裏側", "850億ドル")
    assert "850億ドル" in titles["result"]


def test_axis_titles_no_metric_invents_no_number():
    titles = build_axis_titles("コストコの裏側")
    for t in titles.values():
        assert not any(ch.isdigit() for ch in t), t
    # No-metric result axis still carries a curiosity marker (分かれ目).
    assert "分かれ目" in titles["result"]


def test_axis_titles_empty_topic_raises():
    with pytest.raises(ValueError):
        build_axis_titles("  ")


# --- Scoring ---------------------------------------------------------------


def test_overlap_subject_name_shared_is_ok():
    cfg = _costco_config()
    overlap = title_thumbnail_overlap("【ずんだもん解説】コストコの裏側の正体とは？", cfg)
    assert overlap < 0.2


def test_overlap_hook_copy_is_full_duplication():
    cfg = _costco_config()
    overlap = title_thumbnail_overlap("【ずんだもん解説】コストコボロ儲け！？", cfg)
    assert overlap == 1.0


def test_score_pair_good_pair_beats_duplicated_pair():
    cfg = _costco_config()
    good = score_pair("【ずんだもん解説】コストコの裏側の正体とは？", cfg, "コストコの裏側")
    dup = score_pair("【ずんだもん解説】コストコボロ儲け！？", cfg, "コストコ")
    assert good[0]["complementarity"] == 20
    assert dup[0]["complementarity"] == 0
    assert good[1] > dup[1]
    assert any("重複" in i for i in dup[2])


def test_score_pair_long_thumbnail_text_penalized():
    cfg = ThumbnailConfig(
        title_line1="あいうえおかきくけこ",
        title_line2="さしすせそたちつてと",
        highlight_word="",
        badge="",
        emotion="neutral",
    )
    assert thumbnail_text_chars(cfg) == 20
    scores, _total, issues = score_pair("【ずんだもん解説】テストの正体とは？", cfg, "テスト")
    assert scores["thumbnail_text"] < 15
    assert scores["emotion"] < 5
    assert issues


def test_score_title_over_hard_max_gets_no_length_points():
    score, issues = score_title("【ずんだもん解説】" + "あ" * 60)
    assert score <= 40 - 14
    assert any("長すぎ" in i for i in issues)


def test_axis_configs_differ_by_axis():
    base = _costco_config()
    configs = build_axis_configs(base, "850億ドル")
    assert configs["curiosity"].theme == "gold"
    assert configs["result"].theme == "cyan"
    assert configs["loss"].theme == "red"
    assert configs["loss"].emotion == "angry"
    assert "850億ドル" in configs["result"].sub_hook
    assert "850億ドル" not in configs["curiosity"].sub_hook


# --- Generation + selection (integration) ----------------------------------


def test_generate_packaging_writes_three_pairs(tmp_path):
    proj = _project(tmp_path)
    data = generate_packaging(proj)
    assert data["recommended_axis"] in PACKAGING_AXES
    assert data["selected_axis"] is None
    assert data["metric"] == "850億ドル"
    assert len(data["pairs"]) == 3
    for pair in data["pairs"]:
        img = proj / pair["thumbnail_file"]
        assert img.is_file()
        with Image.open(img) as im:
            assert im.size == (1920, 1080)
        assert 0 <= pair["total"] <= 100
        assert pair["image_qa"]["checks"]["dimensions_valid"] is True
    assert (proj / "packaging.json").is_file()
    # Generation must not clobber the main thumbnail.
    assert not (proj / "thumbnail.png").exists()


def test_generate_packaging_without_metric(tmp_path):
    proj = _project(tmp_path, with_metric=False)
    data = generate_packaging(proj)
    result_pair = next(p for p in data["pairs"] if p["axis"] == "result")
    assert not any(ch.isdigit() for ch in result_pair["title"])


def test_select_packaging_pair_promotes_thumbnail(tmp_path):
    proj = _project(tmp_path)
    generate_packaging(proj)
    pair = select_packaging_pair(proj, "loss")
    assert pair["axis"] == "loss"
    assert (proj / "thumbnail.png").is_file()
    assert (proj / "thumbnail.png").read_bytes() == (proj / "packaging" / "thumbnail_loss.png").read_bytes()
    assert load_packaging(proj)["selected_axis"] == "loss"


def test_select_unknown_axis_fails_closed(tmp_path):
    proj = _project(tmp_path)
    generate_packaging(proj)
    with pytest.raises(ValueError):
        select_packaging_pair(proj, "bogus")
    assert not (proj / "thumbnail.png").exists()


def test_select_missing_candidate_fails_closed(tmp_path):
    proj = _project(tmp_path)
    generate_packaging(proj)
    (proj / "thumbnail.png").write_bytes(b"original")
    (proj / "packaging" / "thumbnail_loss.png").unlink()
    with pytest.raises(FileNotFoundError):
        select_packaging_pair(proj, "loss")
    # thumbnail.png must be untouched after the failed selection.
    assert (proj / "thumbnail.png").read_bytes() == b"original"
    assert load_packaging(proj)["selected_axis"] is None


def test_load_packaging_missing_and_corrupt(tmp_path):
    proj = tmp_path / "empty_proj"
    proj.mkdir()
    with pytest.raises(FileNotFoundError):
        load_packaging(proj)
    (proj / "packaging.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_packaging(proj)


# --- Metadata integration ---------------------------------------------------


def test_metadata_uses_selected_packaging_title(tmp_path):
    from veraxi_ymmp.exporters.youtube_metadata import generate_project_youtube_metadata

    proj = _project(tmp_path)
    data = generate_packaging(proj)
    select_packaging_pair(proj, "curiosity")
    expected = next(p["title"] for p in data["pairs"] if p["axis"] == "curiosity")
    bundle = generate_project_youtube_metadata(proj)
    assert bundle.title == expected
    assert len(bundle.title_variants) == 3


def test_metadata_explicit_config_title_wins_over_packaging(tmp_path):
    from veraxi_ymmp.exporters.youtube_metadata import generate_project_youtube_metadata

    proj = _project(tmp_path)
    generate_packaging(proj)
    select_packaging_pair(proj, "loss")
    (proj / "youtube_config.json").write_text(
        json.dumps({"title": "【ずんだもん解説】手動で決めたタイトル"}, ensure_ascii=False),
        encoding="utf-8",
    )
    bundle = generate_project_youtube_metadata(proj)
    assert bundle.title == "【ずんだもん解説】手動で決めたタイトル"
