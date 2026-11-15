"""Tests for the outlier corpus builder (all network access faked)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from veraxi_ymmp.app.outlier_corpus import (
    ChannelData,
    CorpusError,
    VideoRecord,
    YouTubeDataClient,
    build_corpus,
    collect_channel,
    compute_baseline,
    download_thumbnails,
    get_api_key,
    load_channel_refs,
    parse_iso8601_duration,
    write_corpus,
)


def _video(video_id: str, views: int, duration: int = 600) -> VideoRecord:
    return VideoRecord(
        video_id=video_id,
        title=f"title {video_id}",
        views=views,
        published_at="2026-11-01T00:00:00Z",
        duration_sec=duration,
        thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
    )


def test_parse_iso8601_duration() -> None:
    assert parse_iso8601_duration("PT1H2M3S") == 3723
    assert parse_iso8601_duration("PT45S") == 45
    assert parse_iso8601_duration("PT10M") == 600
    assert parse_iso8601_duration("P1DT2H") == 93600
    assert parse_iso8601_duration("") == 0
    assert parse_iso8601_duration("garbage") == 0


def test_compute_baseline_uses_newest_window() -> None:
    mean_v, median_v = compute_baseline([100, 200, 300, 99999], window=3)
    assert mean_v == 200.0
    assert median_v == 200.0
    assert compute_baseline([], window=20) == (0.0, 0.0)


def test_build_corpus_flags_outliers_and_excludes_shorts() -> None:
    videos = [_video(f"v{i}", 1000) for i in range(20)]
    videos.insert(0, _video("hit", 9500))
    videos.insert(1, _video("short_hit", 999999, duration=30))
    channel = ChannelData(channel_id="UCx", title="Chan", handle="@chan", videos=videos)
    corpus = build_corpus([channel], min_ratio=3.0)
    ids = [row["video_id"] for row in corpus["outliers"]]
    assert ids == ["hit"]
    assert corpus["outliers"][0]["ratio_vs_mean"] >= 3.0
    row = corpus["channels"][0]
    # Baseline: newest 20 eligible = hit(9500) + 19 x 1000 -> mean 1425
    assert row["videos_eligible"] == 21
    assert row["baseline_mean_views"] == pytest.approx((9500 + 19 * 1000) / 20, abs=0.1)


def test_build_corpus_zero_baseline_yields_no_outliers() -> None:
    channel = ChannelData(
        channel_id="UCx", title="Chan", handle="", videos=[_video("a", 0)]
    )
    corpus = build_corpus([channel])
    assert corpus["outliers"] == []


class _FakeResponse:
    def __init__(self, payload: Dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def json(self) -> Dict[str, Any]:
        return self._payload


class _FakeSession:
    """Routes Data API calls by path suffix, from canned payloads."""

    def __init__(self, routes: Dict[str, Any]) -> None:
        self.routes = routes
        self.calls: List[str] = []

    def get(self, url: str, params: Dict[str, Any] | None = None, timeout: float = 0) -> _FakeResponse:
        self.calls.append(url)
        for suffix, payload in self.routes.items():
            if url.endswith(suffix):
                if isinstance(payload, _FakeResponse):
                    return payload
                return _FakeResponse(payload)
        raise AssertionError(f"unexpected URL {url}")


def _routes() -> Dict[str, Any]:
    playlist_items = [
        {"contentDetails": {"videoId": f"vid{i}"}} for i in range(10)
    ]
    video_items = []
    for i in range(10):
        views = "50000" if i == 9 else "1000"
        video_items.append(
            {
                "id": f"vid{i}",
                "snippet": {
                    "title": f"Video {i}",
                    "publishedAt": "2026-11-10T00:00:00Z",
                    "thumbnails": {"maxres": {"url": f"https://img/vid{i}max.jpg"}},
                },
                "statistics": {"viewCount": views},
                "contentDetails": {"duration": "PT10M"},
            }
        )
    return {
        "/channels": {
            "items": [
                {
                    "id": "UCaaaaaaaaaaaaaaaaaaaaaa",
                    "snippet": {"title": "Bench Channel"},
                    "contentDetails": {"relatedPlaylists": {"uploads": "UUbench"}},
                }
            ]
        },
        "/playlistItems": {"items": playlist_items},
        "/videos": {"items": video_items},
    }


def test_collect_channel_end_to_end_with_fake_api() -> None:
    client = YouTubeDataClient("test-key", session=_FakeSession(_routes()))  # type: ignore[arg-type]
    channel = collect_channel(client, "@bench", per_channel=10)
    assert channel.channel_id.startswith("UC")
    assert len(channel.videos) == 10
    assert channel.videos[9].views == 50000
    assert channel.videos[0].thumbnail_url == "https://img/vid0max.jpg"
    corpus = build_corpus([channel], baseline_window=20, min_ratio=3.0)
    # Baseline mean = (9 x 1000 + 50000) / 10 = 5900; vid9 ratio = 8.47x.
    assert [r["video_id"] for r in corpus["outliers"]] == ["vid9"]


def test_api_error_surfaces_message() -> None:
    routes = {"/channels": _FakeResponse({"error": {"message": "quota exceeded"}}, status=403)}
    client = YouTubeDataClient("k", session=_FakeSession(routes))  # type: ignore[arg-type]
    with pytest.raises(CorpusError, match="quota exceeded"):
        client.resolve_channel("@bench")


def test_resolve_channel_not_found() -> None:
    routes = {"/channels": {"items": []}}
    client = YouTubeDataClient("k", session=_FakeSession(routes))  # type: ignore[arg-type]
    with pytest.raises(CorpusError, match="not found"):
        client.resolve_channel("@nope")


def test_download_thumbnails_records_failures_without_aborting(tmp_path: Path) -> None:
    corpus: Dict[str, Any] = {
        "outliers": [
            {"video_id": "ok1", "thumbnail_url": "https://img/ok.jpg"},
            {"video_id": "bad1", "thumbnail_url": "https://img/bad.jpg"},
        ]
    }

    def fetch(url: str) -> bytes:
        if "bad" in url:
            raise RuntimeError("boom")
        return b"\xff\xd8jpeg"

    download_thumbnails(corpus, tmp_path, fetch=fetch)
    ok_row, bad_row = corpus["outliers"]
    assert ok_row["thumbnail_file"] == "thumbnails/ok1.jpg"
    assert (tmp_path / "thumbnails" / "ok1.jpg").read_bytes() == b"\xff\xd8jpeg"
    assert bad_row["thumbnail_file"] is None
    assert bad_row["thumbnail_error"]


def test_write_corpus_is_valid_json(tmp_path: Path) -> None:
    target = write_corpus({"channels": [], "outliers": []}, tmp_path)
    assert json.loads(target.read_text(encoding="utf-8")) == {"channels": [], "outliers": []}
    assert not (tmp_path / "corpus.json.tmp").exists()


def test_load_channel_refs_from_arg_config_and_dedupe(tmp_path: Path) -> None:
    cfg = tmp_path / "channels.json"
    cfg.write_text(json.dumps({"channels": ["@a", "@b"]}), encoding="utf-8")
    refs = load_channel_refs("@b, @c", str(cfg))
    assert refs == ["@a", "@b", "@c"]
    with pytest.raises(CorpusError):
        load_channel_refs(None, None)
    bad = tmp_path / "bad.json"
    bad.write_text('{"channels": [1]}', encoding="utf-8")
    with pytest.raises(CorpusError):
        load_channel_refs(None, str(bad))


def test_get_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(CorpusError, match="YOUTUBE_API_KEY"):
        get_api_key()
    monkeypatch.setenv("YOUTUBE_API_KEY", "  secret  ")
    assert get_api_key() == "secret"
