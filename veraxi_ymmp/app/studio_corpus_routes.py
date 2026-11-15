"""Tier 3 Studio routes for Rival Radar (outlier corpus + adaptive patterns)
and live packaging pair editing.

Connects `app/outlier_corpus.py` and `graphics/packaging_patterns.py` to the
Studio desktop API without bloating `api_server.py`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from veraxi_ymmp.app.outlier_corpus import (
    API_KEY_ENV,
    CorpusError,
    YouTubeDataClient,
    build_corpus,
    collect_channel,
    download_thumbnails,
    write_corpus,
)
from veraxi_ymmp.core.logging import logger
from veraxi_ymmp.core.utils import get_workspace_root, sanitize_filename
from veraxi_ymmp.graphics.packaging import update_packaging_pair
from veraxi_ymmp.graphics.packaging_patterns import (
    apply_feedback_to_patterns,
    extract_patterns_from_corpus,
    load_patterns,
    save_patterns,
)


def _corpus_dir() -> Path:
    return get_workspace_root() / "artifacts" / "corpus"


def _load_saved_channels(cdir: Path) -> List[str]:
    cfg = cdir / "channels.json"
    if cfg.is_file():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict) and isinstance(data.get("channels"), list):
                return [str(c).strip() for c in data["channels"] if str(c).strip()]
            if isinstance(data, list):
                return [str(c).strip() for c in data if str(c).strip()]
        except Exception:
            pass
    return []


def _save_channels(cdir: Path, channels: List[str]) -> None:
    cdir.mkdir(parents=True, exist_ok=True)
    clean = []
    for ch in channels:
        s = str(ch).strip()
        if s and s not in clean:
            clean.append(s)
    (cdir / "channels.json").write_text(
        json.dumps({"channels": clean}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def handle_get_corpus() -> Tuple[int, Dict[str, Any]]:
    """Return current outlier corpus, extracted patterns, and benchmark channels."""
    cdir = _corpus_dir()
    corpus_file = cdir / "corpus.json"
    corpus: Optional[Dict[str, Any]] = None
    if corpus_file.is_file():
        try:
            corpus = json.loads(corpus_file.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            logger.warning("Failed to read corpus.json: %s", exc)

    patterns = load_patterns(cdir / "patterns.json")
    channels = _load_saved_channels(cdir)
    has_api_key = bool(os.getenv(API_KEY_ENV, "").strip())
    return 200, {
        "success": True,
        "corpus": corpus,
        "patterns": patterns,
        "channels": channels,
        "has_api_key": has_api_key,
    }


def handle_scan_corpus(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    """Fetch outlier videos from YouTube Data API v3 and update patterns.json."""
    cdir = _corpus_dir()
    raw_channels = body.get("channels")
    if isinstance(raw_channels, list):
        channels = [str(c).strip() for c in raw_channels if str(c).strip()]
        _save_channels(cdir, channels)
    elif isinstance(raw_channels, str):
        channels = [c.strip() for c in raw_channels.split(",") if c.strip()]
        _save_channels(cdir, channels)
    else:
        channels = _load_saved_channels(cdir)

    if not channels:
        return 400, {"error": "ベンチマーク対象チャンネル(@handle または UC...)を1つ以上入力してください。"}

    api_key = os.getenv(API_KEY_ENV, "").strip()
    if not api_key:
        return 400, {
            "error": (
                f"{API_KEY_ENV} が設定されていません。Google Cloud Console で "
                f"YouTube Data API v3 キーを取得し、環境変数 {API_KEY_ENV} に設定してください。"
            )
        }

    min_ratio = float(body.get("min_ratio") or 3.0)
    per_channel = int(body.get("per_channel") or 40)

    try:
        client = YouTubeDataClient(api_key)
        collected = [collect_channel(client, ref, per_channel) for ref in channels]
        corpus = build_corpus(collected, min_ratio=min_ratio)
        download_thumbnails(corpus, cdir)
        write_corpus(corpus, cdir)

        patterns_path = cdir / "patterns.json"
        existing = load_patterns(patterns_path) if patterns_path.is_file() else None
        patterns = extract_patterns_from_corpus(corpus, existing=existing)
        save_patterns(patterns, patterns_path)
        return 200, {
            "success": True,
            "corpus": corpus,
            "patterns": patterns,
            "channels": channels,
        }
    except CorpusError as exc:
        return 400, {"error": str(exc)}
    except Exception as exc:
        logger.error("Corpus scan failed: %s", exc, exc_info=True)
        return 500, {"error": str(exc)}


def handle_record_pattern_feedback(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    """Record Test & Compare or Analytics win/loss feedback into patterns.json."""
    axis = str(body.get("axis") or "").strip()
    if not axis:
        return 400, {"error": "axis is required"}
    layout = str(body.get("layout") or "").strip() or None
    won = bool(body.get("won", True))
    ctr_raw = body.get("ctr")
    ctr = float(ctr_raw) if ctr_raw is not None else None
    patterns = apply_feedback_to_patterns(
        _corpus_dir() / "patterns.json",
        axis=axis,
        layout=layout,
        won=won,
        ctr=ctr,
    )
    return 200, {"success": True, "patterns": patterns}


def handle_update_packaging_pair(
    project_name: str,
    axis: str,
    body: Dict[str, Any],
) -> Tuple[int, Dict[str, Any]]:
    """Live-edit a packaging candidate's title or thumbnail slots and re-render."""
    safe_name = sanitize_filename(project_name)
    proj_path = get_workspace_root() / "projects" / safe_name
    if not proj_path.is_dir():
        return 404, {"error": f"Project '{project_name}' not found"}

    title = body.get("title")
    config_patch = body.get("config")
    try:
        updated = update_packaging_pair(
            proj_path,
            axis=axis,
            title=str(title) if title is not None else None,
            config_patch=config_patch if isinstance(config_patch, dict) else None,
        )
        return 200, {"success": True, "packaging": updated}
    except (ValueError, FileNotFoundError) as exc:
        return 400, {"error": str(exc)}
    except Exception as exc:
        logger.error("Packaging pair update failed: %s", exc, exc_info=True)
        return 500, {"error": str(exc)}


def resolve_corpus_thumbnail(filename: str) -> Optional[Path]:
    """Safely resolve a downloaded outlier thumbnail inside artifacts/corpus/thumbnails."""
    safe = Path(filename).name
    if not safe:
        return None
    thumb_dir = (_corpus_dir() / "thumbnails").resolve()
    candidate = (thumb_dir / safe).resolve()
    if candidate.parent != thumb_dir or not candidate.is_file():
        return None
    return candidate
