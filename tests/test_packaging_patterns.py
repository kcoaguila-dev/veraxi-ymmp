"""Tests for adaptive packaging pattern mining, live editing, and studio corpus routes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from veraxi_ymmp.graphics.packaging import (
    build_axis_configs,
    build_axis_titles,
    generate_packaging,
    update_packaging_pair,
)
from veraxi_ymmp.graphics.packaging_patterns import (
    apply_feedback_to_patterns,
    default_pattern_library,
    extract_patterns_from_corpus,
    is_generic_slop,
    load_patterns,
    save_patterns,
)
from veraxi_ymmp.graphics.thumbnail import ThumbnailConfig


def _sample_corpus() -> dict:
    now = datetime(2026, 11, 15, tzinfo=timezone.utc).isoformat()
    return {
        "outliers": [
            {
                "video_id": "v1",
                "channel_title": "RivalA",
                "title": "なぜ最強だったNvidiaの競合は1年で消えたのか？",
                "views": 250000,
                "ratio_vs_mean": 8.5,
                "published_at": now,
            },
            {
                "video_id": "v2",
                "channel_title": "RivalB",
                "title": "利益率42%の異常値…TSMCに何が起きているのか",
                "views": 180000,
                "ratio_vs_mean": 5.2,
                "published_at": now,
            },
            {
                "video_id": "v3",
                "channel_title": "RivalC",
                "title": "知らないと損するAI半導体の落とし穴",
                "views": 120000,
                "ratio_vs_mean": 4.1,
                "published_at": now,
            },
        ]
    }


def test_extract_patterns_from_corpus_learns_hook_first():
    corpus = _sample_corpus()
    patterns = extract_patterns_from_corpus(
        corpus,
        now_dt=datetime(2026, 11, 15, tzinfo=timezone.utc),
    )
    assert patterns["source_outliers_count"] == 3
    assert patterns["bracket_tag_rate"] == 0.0
    assert patterns["prefer_hook_first"] is True
    assert len(patterns["recent_outlier_hooks"]) == 3


def test_adaptive_titles_and_configs_use_patterns():
    patterns = default_pattern_library()
    titles = build_axis_titles("コストコ", "850億ドル", patterns=patterns)
    assert not titles["curiosity"].startswith("【ずんだもん解説】")
    assert "850億ドル" in titles["result"]
    assert all(len(t) <= 32 for t in titles.values())

    base = ThumbnailConfig(title_line1="コストコ", title_line2="ボロ儲け", highlight_word="ボロ儲け")
    cfgs = build_axis_configs(base, "850億ドル", patterns=patterns)
    assert cfgs["curiosity"].badge == ""
    assert cfgs["curiosity"].title_line2 != cfgs["loss"].title_line2


def test_is_generic_slop_detects_filler():
    assert is_generic_slop("衝撃の真実！？") is True
    assert is_generic_slop("利益率42%の罠") is False


def test_apply_feedback_updates_weights(tmp_path: Path):
    p_path = tmp_path / "patterns.json"
    save_patterns(default_pattern_library(), p_path)
    before = load_patterns(p_path)
    w_before = next(a["weight"] for a in before["title_archetypes"] if a["axis"] == "curiosity")

    after = apply_feedback_to_patterns(p_path, axis="curiosity", layout="clean_impact", won=True, ctr=7.5)
    w_after = next(a["weight"] for a in after["title_archetypes"] if a["axis"] == "curiosity")
    assert w_after > w_before


def test_update_packaging_pair_rerenders_and_persists(tmp_path: Path):
    proj = tmp_path / "demo_proj"
    proj.mkdir()
    (proj / "script.json").write_text(
        json.dumps([{"character": "ずんだもん", "text": "テストなのだ", "emotion": "surprised"}], ensure_ascii=False),
        encoding="utf-8",
    )
    (proj / "broll_manifest.json").write_text(
        json.dumps([{"title": "テスト企業", "hero_metric": "42%"}], ensure_ascii=False),
        encoding="utf-8",
    )
    generate_packaging(proj)
    updated = update_packaging_pair(
        proj,
        axis="curiosity",
        title="なぜテスト企業は急成長したのか？",
        config_patch={"title_line1": "テスト企業", "title_line2": "急成長の秘密", "badge": ""},
    )
    pair = next(p for p in updated["pairs"] if p["axis"] == "curiosity")
    assert pair["title"] == "なぜテスト企業は急成長したのか？"
    assert pair["config"]["badge"] == ""
    with Image.open(proj / pair["thumbnail_file"]) as im:
        assert im.size == (1920, 1080)
