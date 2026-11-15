"""Outlier corpus builder: the "start from data" step of thumbnail/title
packaging, rebuilt locally instead of depending on a proprietary database.

Method (the documented "Outlier Method" used by tools like 1of10, which
offers no developer API): for each benchmark channel, take the recent
uploads, compute the channel's baseline views (mean/median of the newest
``baseline_window`` videos), and flag videos whose views exceed the
baseline by ``min_ratio`` (3x = worth a look, 5x = worth studying).

Data comes only from the official YouTube Data API v3 (free key, 10,000
quota units/day; this tool uses a few dozen units per run) plus the
public thumbnail image URLs the API itself returns. No HTML scraping.

The API key is read from the YOUTUBE_API_KEY environment variable and is
never written to disk or logged. The corpus is written atomically: if any
API call fails, no partial corpus.json is left behind.

Output layout under --out DIR:
    corpus.json            index: channel baselines + ranked outliers
    thumbnails/<id>.jpg    outlier thumbnails for study / pattern work

Thumbnails remain their creators' copyrighted work; the corpus is for
internal analysis and design-pattern extraction only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import requests

API_BASE = "https://www.googleapis.com/youtube/v3"
API_KEY_ENV = "YOUTUBE_API_KEY"
DEFAULT_PER_CHANNEL = 60
DEFAULT_BASELINE_WINDOW = 20
DEFAULT_MIN_RATIO = 3.0
DEFAULT_MIN_DURATION_SEC = 60

_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?)?$"
)


class CorpusError(RuntimeError):
    """Raised when the corpus cannot be built (API error, bad input)."""


@dataclass
class VideoRecord:
    """One video's public metadata, as returned by videos.list."""

    video_id: str
    title: str
    views: int
    published_at: str
    duration_sec: int
    thumbnail_url: str


@dataclass
class ChannelData:
    """A benchmark channel and its recent uploads (newest first)."""

    channel_id: str
    title: str
    handle: str
    videos: List[VideoRecord] = field(default_factory=list)


def parse_iso8601_duration(text: str) -> int:
    """Parse an ISO-8601 duration (e.g. PT1H2M3S, PT45S, P1DT2H) to seconds."""
    match = _DURATION_RE.match(text.strip())
    if not match:
        return 0
    parts = {k: int(v) if v else 0 for k, v in match.groupdict().items()}
    return (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


def compute_baseline(views_newest_first: Sequence[int], window: int) -> Tuple[float, float]:
    """Return (mean, median) views over the newest ``window`` videos."""
    sample = list(views_newest_first[:window])
    if not sample:
        return 0.0, 0.0
    return float(mean(sample)), float(median(sample))


class YouTubeDataClient:
    """Minimal YouTube Data API v3 client (channels/playlistItems/videos)."""

    def __init__(
        self,
        api_key: str,
        session: Optional[requests.Session] = None,
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise CorpusError(f"{API_KEY_ENV} is not set")
        self._api_key = api_key
        self._session = session or requests.Session()
        self._timeout = timeout

    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        query = dict(params)
        query["key"] = self._api_key
        try:
            resp = self._session.get(
                f"{API_BASE}/{path}", params=query, timeout=self._timeout
            )
        except requests.RequestException as exc:
            raise CorpusError(f"YouTube API request failed: {exc}") from exc
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        if resp.status_code != 200:
            message = (
                payload.get("error", {}).get("message")
                if isinstance(payload, dict)
                else None
            ) or f"HTTP {resp.status_code}"
            raise CorpusError(f"YouTube API error on {path}: {message}")
        if not isinstance(payload, dict):
            raise CorpusError(f"YouTube API returned a non-object payload on {path}")
        return payload

    def resolve_channel(self, ref: str) -> Tuple[str, str, str]:
        """Resolve a handle (@name) or channel ID to (id, title, uploads)."""
        ref = ref.strip()
        if not ref:
            raise CorpusError("Empty channel reference")
        if ref.startswith("UC") and len(ref) == 24 and " " not in ref:
            params: Dict[str, Any] = {"part": "snippet,contentDetails", "id": ref}
        else:
            handle = ref if ref.startswith("@") else f"@{ref}"
            params = {"part": "snippet,contentDetails", "forHandle": handle}
        payload = self._get("channels", params)
        items = payload.get("items") or []
        if not items:
            raise CorpusError(f"Channel not found: {ref}")
        item = items[0]
        uploads = (
            item.get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("uploads", "")
        )
        if not uploads:
            raise CorpusError(f"Channel {ref} has no uploads playlist")
        title = item.get("snippet", {}).get("title", "")
        return str(item.get("id", "")), title, uploads

    def list_recent_video_ids(self, uploads_playlist: str, limit: int) -> List[str]:
        """Return up to ``limit`` video IDs from the uploads playlist."""
        ids: List[str] = []
        page_token: Optional[str] = None
        while len(ids) < limit:
            params: Dict[str, Any] = {
                "part": "contentDetails",
                "playlistId": uploads_playlist,
                "maxResults": min(50, limit - len(ids)),
            }
            if page_token:
                params["pageToken"] = page_token
            payload = self._get("playlistItems", params)
            for item in payload.get("items") or []:
                video_id = (
                    item.get("contentDetails", {}).get("videoId")
                    if isinstance(item, dict)
                    else None
                )
                if video_id:
                    ids.append(str(video_id))
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
        return ids[:limit]

    def fetch_videos(self, video_ids: Sequence[str]) -> List[VideoRecord]:
        """Fetch metadata for videos in batches of 50 (order preserved)."""
        records: List[VideoRecord] = []
        for start in range(0, len(video_ids), 50):
            batch = list(video_ids[start : start + 50])
            payload = self._get(
                "videos",
                {
                    "part": "snippet,statistics,contentDetails",
                    "id": ",".join(batch),
                    "maxResults": 50,
                },
            )
            by_id: Dict[str, Dict[str, Any]] = {}
            for item in payload.get("items") or []:
                if isinstance(item, dict) and item.get("id"):
                    by_id[str(item["id"])] = item
            for video_id in batch:
                item = by_id.get(video_id)
                if item is None:
                    continue
                records.append(_record_from_item(item))
        return records


def _record_from_item(item: Dict[str, Any]) -> VideoRecord:
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})
    details = item.get("contentDetails", {})
    thumbnails = snippet.get("thumbnails", {}) if isinstance(snippet, dict) else {}
    thumb_url = ""
    for quality in ("maxres", "standard", "high", "medium", "default"):
        entry = thumbnails.get(quality) if isinstance(thumbnails, dict) else None
        if isinstance(entry, dict) and entry.get("url"):
            thumb_url = str(entry["url"])
            break
    try:
        views = int(statistics.get("viewCount", 0))
    except (TypeError, ValueError):
        views = 0
    return VideoRecord(
        video_id=str(item.get("id", "")),
        title=str(snippet.get("title", "")),
        views=views,
        published_at=str(snippet.get("publishedAt", "")),
        duration_sec=parse_iso8601_duration(str(details.get("duration", ""))),
        thumbnail_url=thumb_url,
    )


def collect_channel(
    client: YouTubeDataClient, ref: str, per_channel: int
) -> ChannelData:
    """Resolve one benchmark channel and fetch its recent uploads."""
    channel_id, title, uploads = client.resolve_channel(ref)
    video_ids = client.list_recent_video_ids(uploads, per_channel)
    videos = client.fetch_videos(video_ids)
    handle = ref if ref.startswith("@") else ""
    return ChannelData(
        channel_id=channel_id, title=title, handle=handle, videos=videos
    )


def build_corpus(
    channels: Sequence[ChannelData],
    *,
    baseline_window: int = DEFAULT_BASELINE_WINDOW,
    min_ratio: float = DEFAULT_MIN_RATIO,
    min_duration_sec: int = DEFAULT_MIN_DURATION_SEC,
) -> Dict[str, Any]:
    """Compute baselines and flag outliers across collected channels.

    Videos shorter than ``min_duration_sec`` (Shorts by default) are
    excluded from both baselines and outliers: their view counts follow
    a different distribution and would poison the comparison.
    """
    channel_rows: List[Dict[str, Any]] = []
    outliers: List[Dict[str, Any]] = []
    for channel in channels:
        eligible = [
            v for v in channel.videos if v.duration_sec >= min_duration_sec
        ]
        views = [v.views for v in eligible]
        base_mean, base_median = compute_baseline(views, baseline_window)
        channel_rows.append(
            {
                "channel_id": channel.channel_id,
                "title": channel.title,
                "handle": channel.handle,
                "videos_fetched": len(channel.videos),
                "videos_eligible": len(eligible),
                "baseline_window": min(baseline_window, len(eligible)),
                "baseline_mean_views": round(base_mean, 1),
                "baseline_median_views": round(base_median, 1),
            }
        )
        if base_mean <= 0:
            continue
        for video in eligible:
            ratio = video.views / base_mean
            if ratio < min_ratio:
                continue
            outliers.append(
                {
                    "video_id": video.video_id,
                    "channel_id": channel.channel_id,
                    "channel_title": channel.title,
                    "title": video.title,
                    "url": f"https://www.youtube.com/watch?v={video.video_id}",
                    "views": video.views,
                    "ratio_vs_mean": round(ratio, 2),
                    "ratio_vs_median": round(video.views / base_median, 2)
                    if base_median > 0
                    else None,
                    "published_at": video.published_at,
                    "duration_sec": video.duration_sec,
                    "thumbnail_url": video.thumbnail_url,
                    "thumbnail_file": None,
                    "thumbnail_error": None,
                }
            )
    outliers.sort(key=lambda row: row["ratio_vs_mean"], reverse=True)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": (
            "Outlier ratio = video views / channel baseline (mean of newest "
            f"{baseline_window} eligible uploads); flagged at >= {min_ratio}x. "
            "Ratios are study signals, not performance predictions."
        ),
        "channels": channel_rows,
        "outliers": outliers,
    }


def _download_bytes(url: str, session: requests.Session, timeout: float) -> bytes:
    resp = session.get(url, timeout=timeout)
    if resp.status_code != 200:
        raise CorpusError(f"HTTP {resp.status_code} for {url}")
    return resp.content


def download_thumbnails(
    corpus: Dict[str, Any],
    out_dir: Path,
    session: Optional[requests.Session] = None,
    timeout: float = 30.0,
    fetch: Optional[Callable[[str], bytes]] = None,
) -> None:
    """Download each outlier's thumbnail into out_dir/thumbnails/.

    A failed download is recorded on the row (thumbnail_error) and never
    aborts the corpus: the index is the deliverable, images are study aids.
    """
    thumb_dir = out_dir / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    sess = session or requests.Session()

    def _fetch(url: str) -> bytes:
        if fetch is not None:
            return fetch(url)
        return _download_bytes(url, sess, timeout)

    for row in corpus.get("outliers", []):
        video_id = row["video_id"]
        candidates = []
        if row.get("thumbnail_url"):
            candidates.append(str(row["thumbnail_url"]))
        candidates.append(f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg")
        candidates.append(f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg")
        seen = set()
        data: Optional[bytes] = None
        last_error = ""
        for url in candidates:
            if url in seen:
                continue
            seen.add(url)
            try:
                data = _fetch(url)
                if data:
                    break
            except Exception as exc:  # per-image failure must not abort
                last_error = str(exc)
                data = None
        if data:
            target = thumb_dir / f"{video_id}.jpg"
            target.write_bytes(data)
            row["thumbnail_file"] = f"thumbnails/{video_id}.jpg"
            row["thumbnail_error"] = None
        else:
            row["thumbnail_file"] = None
            row["thumbnail_error"] = last_error or "download failed"


def write_corpus(corpus: Dict[str, Any], out_dir: Path) -> Path:
    """Write corpus.json atomically (temp file + rename)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "corpus.json"
    tmp = out_dir / "corpus.json.tmp"
    tmp.write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(target)
    return target


def load_channel_refs(channels_arg: Optional[str], config_path: Optional[str]) -> List[str]:
    """Collect channel references from --channels CSV and/or a config file.

    Config file format: {"channels": ["@handle", "UC..."]} or a bare list.
    """
    refs: List[str] = []
    if config_path:
        raw = Path(config_path).read_text(encoding="utf-8")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CorpusError(f"Invalid JSON in {config_path}: {exc}") from exc
        entries = parsed.get("channels") if isinstance(parsed, dict) else parsed
        if not isinstance(entries, list) or not all(
            isinstance(e, str) for e in entries
        ):
            raise CorpusError(
                f"{config_path} must be a JSON list of channel refs or "
                '{"channels": [...]}'
            )
        refs.extend(e.strip() for e in entries if e.strip())
    if channels_arg:
        refs.extend(p.strip() for p in channels_arg.split(",") if p.strip())
    deduped: List[str] = []
    for ref in refs:
        if ref not in deduped:
            deduped.append(ref)
    if not deduped:
        raise CorpusError("No channels given (use --channels and/or --config)")
    return deduped


def get_api_key() -> str:
    """Read the YouTube Data API key from the environment (never stored)."""
    key = os.getenv(API_KEY_ENV, "").strip()
    if not key:
        raise CorpusError(
            f"{API_KEY_ENV} is not set. Create a free key: Google Cloud "
            "Console -> enable 'YouTube Data API v3' -> Credentials -> "
            f"API key, then set {API_KEY_ENV} in your shell environment."
        )
    return key


def cmd_corpus(argv: List[str]) -> None:
    """CLI: veraxi-ymmp corpus --channels @a,@b --out DIR"""
    parser = argparse.ArgumentParser(
        prog="veraxi-ymmp corpus",
        description=(
            "Build a niche outlier corpus from benchmark channels using the "
            "official YouTube Data API (key from YOUTUBE_API_KEY env var)."
        ),
    )
    parser.add_argument("--channels", help="Comma-separated handles (@name) or channel IDs")
    parser.add_argument("--config", help="JSON file with channel refs ({\"channels\": [...]})")
    parser.add_argument("--out", required=True, help="Output directory for corpus.json + thumbnails/")
    parser.add_argument("--per-channel", type=int, default=DEFAULT_PER_CHANNEL,
                        help=f"Recent uploads to fetch per channel (default {DEFAULT_PER_CHANNEL})")
    parser.add_argument("--baseline", type=int, default=DEFAULT_BASELINE_WINDOW,
                        help=f"Baseline window in newest videos (default {DEFAULT_BASELINE_WINDOW})")
    parser.add_argument("--min-ratio", type=float, default=DEFAULT_MIN_RATIO,
                        help=f"Outlier threshold vs baseline mean (default {DEFAULT_MIN_RATIO})")
    parser.add_argument("--min-duration", type=int, default=DEFAULT_MIN_DURATION_SEC,
                        help=f"Exclude videos shorter than this many seconds (default {DEFAULT_MIN_DURATION_SEC}; 0 keeps Shorts)")
    parser.add_argument("--no-thumbnails", action="store_true",
                        help="Skip downloading outlier thumbnails")
    args = parser.parse_args(argv)

    try:
        refs = load_channel_refs(args.channels, args.config)
        client = YouTubeDataClient(get_api_key())
        channels = [collect_channel(client, ref, args.per_channel) for ref in refs]
        corpus = build_corpus(
            channels,
            baseline_window=args.baseline,
            min_ratio=args.min_ratio,
            min_duration_sec=args.min_duration,
        )
        out_dir = Path(args.out)
        if not args.no_thumbnails:
            download_thumbnails(corpus, out_dir)
        target = write_corpus(corpus, out_dir)
    except CorpusError as exc:
        print(f"corpus: error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(f"Corpus written: {target}")
    for row in corpus["channels"]:
        print(
            f"  {row['title'] or row['channel_id']}: baseline mean "
            f"{row['baseline_mean_views']:,.0f} views "
            f"({row['videos_eligible']} eligible of {row['videos_fetched']} fetched)"
        )
    print(f"  Outliers (>={args.min_ratio}x): {len(corpus['outliers'])}")
    for row in corpus["outliers"][:10]:
        print(f"    {row['ratio_vs_mean']:.1f}x  {row['views']:,} views  {row['title']}")
