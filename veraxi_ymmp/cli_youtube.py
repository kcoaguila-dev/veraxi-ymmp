"""YouTube CLI subcommands."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from typing import Any, List, Optional
from .logging import logger

def _cmd_youtube_upload(args: argparse.Namespace) -> None:
    """Handle the 'youtube upload' subcommand."""
    target_path = Path(args.video_path)
    if not target_path.exists():
        logger.error(f"Path not found: {target_path}")
        sys.exit(1)

    video_path: Optional[Path] = None
    thumbnail_path: Optional[Path] = None

    if target_path.is_dir():
        # Resolve project directory artifacts
        candidates = ["final_video_youtube.mp4", "final_video.mp4", "qa_test.mp4"]
        for cand in candidates:
            cand_path = target_path / cand
            if cand_path.exists() and cand_path.is_file():
                video_path = cand_path
                break
        if not video_path:
            # Fallback to any .mp4 file in directory
            mp4s = list(target_path.glob("*.mp4"))
            if mp4s:
                video_path = mp4s[0]

        if not video_path:
            logger.error(f"No video file found in project directory: {target_path}")
            sys.exit(1)

        auto_thumb = target_path / "thumbnail.png"
        if auto_thumb.exists() and auto_thumb.is_file():
            thumbnail_path = auto_thumb
    else:
        video_path = target_path

    title = args.title if args.title is not None else (target_path.name if target_path.is_dir() else video_path.stem)
    description = args.description or ""
    if isinstance(args.tags, str) and args.tags:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    elif isinstance(args.tags, list):
        tags = args.tags
    else:
        tags = []

    if args.thumbnail:
        explicit_thumb = Path(args.thumbnail)
        if not explicit_thumb.exists() or not explicit_thumb.is_file():
            logger.error(f"Thumbnail file not found or is not a regular file: {explicit_thumb}")
            sys.exit(1)
        thumbnail_path = explicit_thumb

    from .ports import VideoPublishMetadata, VideoPublisher

    metadata = VideoPublishMetadata(
        title=title,
        description=description,
        tags=tags,
        category_id=args.category_id or "22",
        privacy_status=args.privacy or "private",
        publish_at=args.publish_at,
        thumbnail_path=thumbnail_path,
    )

    adapter: VideoPublisher
    if args.mock:
        from .youtube_adapter import MockYouTubeAdapter

        adapter = MockYouTubeAdapter()
    else:
        from .youtube_adapter import YouTubeAdapter

        try:
            adapter = YouTubeAdapter()
        except ValueError as e:
            logger.error(str(e))
            sys.exit(2)
        except Exception as e:
            logger.error(f"Failed to initialize adapter: {e}")
            sys.exit(1)

    def on_progress(ratio: float, bytes_done: int, total_bytes: int) -> None:
        logger.info(f"Upload progress: {ratio * 100:.1f}% ({bytes_done}/{total_bytes} bytes)")

    try:
        logger.info(f"Uploading '{video_path.name}' to YouTube...")
        result = adapter.upload_video(video_path, metadata, progress_callback=on_progress)
        if result.status != "uploaded":
            logger.error(f"Upload failed: {result.error_message}")
            sys.exit(1)
        logger.info(
            f"Upload complete! Video ID: {result.video_id}, URL: {result.url}, "
            f"Thumbnail: {'Uploaded' if result.thumbnail_uploaded else 'Skipped'}"
        )
        sys.exit(0)
    except Exception as e:
        logger.error(f"Upload failed with error: {e}")
        sys.exit(1)


def _cmd_youtube_status(args: argparse.Namespace) -> None:
    """Handle the 'youtube status' subcommand."""
    video_id = args.video_id
    if args.mock:
        logger.info(f"Checking status for video '{video_id}' (mock mode)...")
        logger.info(f"Video '{video_id}': status=uploaded, url=https://youtu.be/{video_id}")
        sys.exit(0)
    else:
        from .youtube_adapter import YouTubeAdapter

        try:
            yt_adapter: YouTubeAdapter = YouTubeAdapter()
            resp = yt_adapter.youtube.videos().list(part="snippet,status", id=video_id).execute()
            items = resp.get("items", [])
            if not items:
                logger.error(f"Video not found on YouTube: {video_id}")
                sys.exit(1)
            item = items[0]
            status = item.get("status", {}).get("uploadStatus", "unknown")
            privacy = item.get("status", {}).get("privacyStatus", "unknown")
            title = item.get("snippet", {}).get("title", "")
            logger.info(f"Video '{video_id}' ({title}): status={status}, privacy={privacy}")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Failed to check video status: {e}")
            sys.exit(1)


def _cmd_youtube_qa(args: argparse.Namespace) -> None:
    """Handle the 'youtube qa' subcommand."""
    from .retention_qa import RetentionCorrelationEngine
    from .pipeline import ProjectPipeline

    project_path = Path(args.project)
    if not project_path.exists():
        logger.error(f"Project directory not found: {project_path}")
        sys.exit(1)

    script_path = project_path / "script.json"
    if not script_path.exists():
        logger.error(f"script.json not found in project directory: {project_path}")
        sys.exit(1)

    output_dir = Path(args.output) if args.output else project_path / "qa_reports"
    threshold = float(args.threshold)

    template_candidates = [
        project_path / "template.ymmp",
        Path("examples/full_template.ymmp"),
        Path(__file__).resolve().parent.parent / "examples" / "full_template.ymmp",
        Path("examples/template.ymmp"),
        Path(__file__).resolve().parent.parent / "examples" / "template.ymmp",
    ]
    template_path = None
    for cand in template_candidates:
        if cand.exists():
            template_path = cand
            break

    if template_path is None:
        logger.error("No YMM4 template file found for compiling project timeline.")
        sys.exit(1)

    try:
        pipeline = ProjectPipeline(template_path=template_path, use_tts=False)
        result = pipeline.run(
            project_path=project_path,
            do_premiere=False,
            do_ymmp=False,
            do_qa=False,
            do_thumbnail=False,
            upload_to_youtube=False,
        )
        if not result.success or not result.timeline_ir:
            logger.error(f"Failed to compile TimelineIR for QA: {result.errors}")
            sys.exit(1)
        timeline_ir = result.timeline_ir
    except Exception as e:
        logger.error(f"TimelineIR compilation failed: {e}")
        sys.exit(1)

    analytics_provider: Any = None
    if args.mock:
        from .youtube_adapter import MockYouTubeAdapter

        analytics_provider = MockYouTubeAdapter()
    else:
        from .youtube_adapter import YouTubeAdapter

        try:
            analytics_provider = YouTubeAdapter()
        except Exception as e:
            logger.error(f"Failed to initialize YouTube adapter: {e}")
            sys.exit(1)

    try:
        curve = analytics_provider.fetch_retention_curve(video_id=args.video_id)
    except Exception as e:
        logger.error(f"Failed to fetch retention curve: {e}")
        sys.exit(1)

    engine = RetentionCorrelationEngine()
    try:
        report = engine.correlate(
            timeline_ir=timeline_ir,
            retention_curve=curve,
            video_id=args.video_id,
            threshold=threshold,
        )
        json_file, md_file = engine.save_reports(report, output_dir)
        logger.info(f"Retention QA analysis complete for video '{args.video_id}'.")
        logger.info(
            f"Verdict: {report.summary_verdict} | Score: {report.retention_score:.1f}/100 | "
            f"Drop-off Points: {len(report.dropoff_points)}"
        )
        logger.info(f"Reports successfully generated at: {json_file} and {md_file}")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to execute retention correlation or save reports: {e}")
        sys.exit(1)


def _cmd_youtube_auth(args: argparse.Namespace) -> None:
    """Handle the 'youtube auth' subcommand."""
    from .youtube_auth import (
        authenticate_youtube,
        get_auth_status,
        resolve_client_secrets_path,
        revoke_token,
        save_client_secrets,
    )

    if getattr(args, "status", False):
        status = get_auth_status()
        import json
        print(json.dumps(status, indent=2))
        sys.exit(0 if status.get("authenticated") else 1)

    if getattr(args, "revoke", False):
        revoked = revoke_token()
        if revoked:
            logger.info("Successfully revoked YouTube token.")
        else:
            logger.info("No active token found to revoke.")
        sys.exit(0)

    client_secrets_path: Optional[Path] = None
    if args.client_secrets:
        cs_p = Path(args.client_secrets)
        if cs_p.exists():
            # Automatically save a copy to default location for GUI/future CLI reuse
            try:
                save_client_secrets(cs_p.read_text(encoding="utf-8"))
            except Exception as e:
                logger.debug(f"Could not persist client_secrets to default location: {e}")
            client_secrets_path = cs_p
    else:
        client_secrets_path = resolve_client_secrets_path()

    if not client_secrets_path or not client_secrets_path.exists():
        logger.error(
            "Missing client secrets file. Provide --client-secrets or save client_secrets.json to ~/.veraxi-ymmp/client_secrets.json"
        )
        sys.exit(1)

    token_out_path = Path(args.token_out) if args.token_out else None

    try:
        authenticate_youtube(
            client_secrets_path=client_secrets_path,
            token_out_path=token_out_path,
            monetary=args.monetary,
            no_browser=args.no_browser,
        )
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to authenticate: {e}")
        sys.exit(2)


def _cmd_youtube_stats(args: argparse.Namespace) -> None:
    """Handle the 'youtube stats' subcommand."""
    from datetime import datetime, timedelta, timezone
    from .stats_formatter import format_stats

    adapter: Any = None
    if args.mock:
        from .youtube_adapter import MockYouTubeAdapter
        adapter = MockYouTubeAdapter()
    else:
        from .youtube_adapter import YouTubeAdapter
        try:
            adapter = YouTubeAdapter()
        except ValueError as e:
            logger.error(str(e))
            sys.exit(2)
        except Exception as e:
            logger.error(f"Failed to initialize adapter: {e}")
            sys.exit(1)

    video_ids = args.video_id
    if not video_ids:
        logger.error("At least one --video-id must be specified.")
        sys.exit(1)

    now = datetime.now(timezone.utc)
    # Default end date: 2 days ago
    end_date_obj = now - timedelta(days=2)
    end_date = args.end_date or end_date_obj.strftime("%Y-%m-%d")

    # Default start date: 28 days before end date
    start_date_obj = end_date_obj - timedelta(days=28)
    start_date = args.start_date or start_date_obj.strftime("%Y-%m-%d")

    if start_date > end_date:
        logger.error(f"start_date ({start_date}) cannot be after end_date ({end_date}).")
        sys.exit(1)

    metrics = args.metrics
    if not metrics:
        metrics = [
            "views", "estimatedMinutesWatched", "averageViewDuration",
            "averageViewPercentage", "likes", "comments", "shares",
            "subscribersGained", "subscribersLost"
        ]

    try:
        report = adapter.fetch_stats_report(
            video_ids=video_ids,
            start_date=start_date,
            end_date=end_date,
            metrics=metrics,
            granularity=args.granularity
        )
    except Exception as e:
        if "quotaExceeded" in str(e) or "403" in str(e):
            logger.error(f"Quota error: {e}")
            sys.exit(3)
        logger.error(f"Failed to fetch stats: {e}")
        sys.exit(1)

    fmt = args.format
    if fmt is None:
        fmt = "table" if sys.stdout.isatty() else "json"

    try:
        output_str = format_stats(report, fmt)
    except Exception as e:
        logger.error(f"Formatting failed: {e}")
        sys.exit(1)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # For CSV, use utf-8-sig for Excel compatibility
        encoding = "utf-8-sig" if fmt == "csv" else "utf-8"
        with open(out_path, "w", encoding=encoding, newline="" if fmt == "csv" else None) as f:
            f.write(output_str)
        logger.info(f"Stats written to {out_path}")
    else:
        print(output_str)

    sys.exit(0)


def _cmd_youtube_channel(args: argparse.Namespace) -> None:
    """Handle the 'youtube channel' subcommand."""
    import json

    adapter: Any = None
    if args.mock:
        from .youtube_adapter import MockYouTubeAdapter
        adapter = MockYouTubeAdapter()
    else:
        from .youtube_adapter import YouTubeAdapter
        try:
            adapter = YouTubeAdapter()
        except ValueError as e:
            logger.error(str(e))
            sys.exit(2)
        except Exception as e:
            logger.error(f"Failed to initialize adapter: {e}")
            sys.exit(1)

    try:
        info = adapter.get_channel_info()
        print(json.dumps(info, ensure_ascii=False, indent=2))
        sys.exit(0)
    except Exception as e:
        if "quotaExceeded" in str(e) or "403" in str(e):
            logger.error(f"Quota error: {e}")
            sys.exit(3)
        logger.error(f"Failed to fetch channel info: {e}")
        sys.exit(1)


def _cmd_youtube_ab(args: argparse.Namespace) -> None:
    """Handle the 'youtube ab' subcommand (A/B thumbnail variant switching)."""
    from . import thumbnail_ab as ab

    project = Path(args.project)
    if not project.exists():
        logger.error(f"Project directory not found: {project}")
        sys.exit(1)

    adapter: Any = None
    if args.action != "status":
        if args.mock:
            from .youtube_adapter import MockYouTubeAdapter

            adapter = MockYouTubeAdapter()
        else:
            from .youtube_adapter import YouTubeAdapter

            try:
                adapter = YouTubeAdapter()
            except Exception as e:
                logger.error(f"Failed to initialize YouTube adapter: {e}")
                sys.exit(1)

    try:
        if args.action == "start":
            exp = ab.initialize_experiment(
                project, args.video_id, publisher=adapter,
                min_impressions=args.min_impressions,
                min_observation_hours=args.min_hours,
            )
            print(ab.render_ab_report(exp))
        elif args.action == "rotate":
            ev = ab.rotate_thumbnail(
                project, args.video_id, target_variant_id=args.variant,
                publisher=adapter, reason="manual_cli_rotation" if args.variant else "scheduled_rotation",
            )
            print(f"Rotated thumbnail: {ev.from_variant_id} -> {ev.to_variant_id}")
        elif args.action == "evaluate":
            d = ab.evaluate_performance(
                project, args.video_id, analytics_provider=adapter,
                confidence_level=args.confidence,
            )
            p = f"{d.p_value:.4f}" if d.p_value is not None else "n/a"
            print(f"Leader: {d.winner_variant_id} | significant={d.is_significant} | p={p}")
            print(d.rationale)
        elif args.action == "commit":
            exp = ab.commit_winner(
                project, args.video_id, winner_id=args.variant,
                publisher=adapter, analytics_provider=adapter,
            )
            print(ab.render_ab_report(exp))
        else:  # status
            print(ab.render_ab_report(ab.get_status(project)))
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"A/B thumbnail '{args.action}' failed: {e}")
        sys.exit(1)


def run(argv: List[str]) -> None:
    """YouTube Automation & Retention QA Telemetry subcommands dispatcher."""
    parser = argparse.ArgumentParser(
        prog="veraxi-ymmp youtube",
        description="YouTube Automation & Retention QA Telemetry",
    )
    subparsers = parser.add_subparsers(
        dest="subcommand",
        title="subcommands",
        description="Available YouTube subcommands",
        help="Subcommand to execute",
    )

    # Subcommand: upload
    parser_upload = subparsers.add_parser(
        "upload",
        help="Upload a video to YouTube with resumable streaming",
        description="Upload a video to YouTube with resumable chunked upload and optional thumbnail.",
    )
    parser_upload.add_argument("video_path", type=str, help="Path to the video file to upload")
    parser_upload.add_argument("--title", type=str, default=None, help="Video title (default: video filename stem)")
    parser_upload.add_argument("--description", type=str, default="", help="Video description")
    parser_upload.add_argument("--tags", type=str, default="", help="Comma-separated video tags")
    parser_upload.add_argument("--category-id", type=str, default="22", help="YouTube category ID (default: 22 / People & Blogs)")
    parser_upload.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private", help="Video privacy status")
    parser_upload.add_argument("--thumbnail", type=str, default=None, help="Path to custom thumbnail image (PNG/JPEG <= 2MB)")
    parser_upload.add_argument("--publish-at", type=str, default=None, help="Scheduled publish time (ISO 8601 string, requires privacy=private)")
    parser_upload.add_argument("--mock", action="store_true", help="Run with MockYouTubeAdapter in offline mode")

    # Subcommand: status
    parser_status = subparsers.add_parser(
        "status",
        help="Check the status of a YouTube video",
        description="Check upload and processing status of a YouTube video.",
    )
    parser_status.add_argument("video_id", type=str, help="YouTube video ID")
    parser_status.add_argument("--mock", action="store_true", help="Run in offline mock mode")

    # Subcommand: qa
    parser_qa = subparsers.add_parser(
        "qa",
        help="Run post-publish audience retention QA telemetry and correlation",
        description="Correlate YouTube Analytics retention curves with TimelineIR dialogue cuts and presentation visuals.",
    )
    parser_qa.add_argument("--video-id", required=True, type=str, help="YouTube video ID to analyze")
    parser_qa.add_argument("--project", required=True, type=str, help="Path to project directory containing script.json")
    parser_qa.add_argument("--output", type=str, default=None, help="Directory to save retention QA reports (default: <project>/qa_reports)")
    parser_qa.add_argument("--threshold", type=float, default=0.05, help="Retention drop-off detection threshold (default: 0.05 / 5%%)")
    parser_qa.add_argument("--mock", action="store_true", help="Run with MockYouTubeAdapter synthetic retention curve")

    # Subcommand: ab (A/B thumbnail variant switching)
    parser_ab = subparsers.add_parser(
        "ab",
        help="A/B test thumbnail variants: start, rotate, evaluate, commit, status",
        description="Generate thumbnail variants, rotate them on YouTube, evaluate CTR, and lock in the winner.",
    )
    parser_ab.add_argument("action", choices=["start", "rotate", "evaluate", "commit", "status"])
    parser_ab.add_argument("--project", required=True, type=str, help="Project directory")
    parser_ab.add_argument("--video-id", type=str, default="", help="YouTube video ID (required except for status)")
    parser_ab.add_argument("--variant", type=str, default=None, help="Target variant ID for rotate/commit")
    parser_ab.add_argument("--min-impressions", type=int, default=500, help="Min impressions per variant (start)")
    parser_ab.add_argument("--min-hours", type=float, default=24.0, help="Min observation hours (start)")
    parser_ab.add_argument("--confidence", type=float, default=0.95, help="Confidence level for evaluation")
    parser_ab.add_argument("--mock", action="store_true", help="Run with MockYouTubeAdapter in offline mode")

    # Subcommand: auth
    parser_auth = subparsers.add_parser(
        "auth",
        help="Authenticate with YouTube and generate a token",
    )
    parser_auth.add_argument("--client-secrets", type=str, help="Path to OAuth2 client_secrets.json")
    parser_auth.add_argument("--token-out", type=str, help="Path to save the generated token (defaults to ~/.veraxi-ymmp/youtube_token.json)")
    parser_auth.add_argument("--monetary", action="store_true", help="Include yt-analytics-monetary.readonly scope")
    parser_auth.add_argument("--no-browser", action="store_true", help="Run console auth flow without opening a browser")
    parser_auth.add_argument("--status", action="store_true", help="Check and print current authentication status as JSON")
    parser_auth.add_argument("--revoke", action="store_true", help="Revoke and delete the current saved token")

    # Subcommand: stats
    parser_stats = subparsers.add_parser(
        "stats",
        help="Fetch YouTube Analytics statistics",
    )
    parser_stats.add_argument("--video-id", type=str, action="append", help="YouTube video ID(s) to fetch stats for (can be specified multiple times)")
    parser_stats.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser_stats.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    parser_stats.add_argument("--metrics", type=lambda s: [m.strip() for m in s.split(',')], help="Comma-separated list of metrics to fetch")
    parser_stats.add_argument("--granularity", choices=["total", "day"], default="total", help="Data granularity (default: total)")
    parser_stats.add_argument("--format", choices=["table", "json", "csv"], help="Output format (default: table for TTY, json otherwise)")
    parser_stats.add_argument("--output", type=str, help="Output file path (default: stdout)")
    parser_stats.add_argument("--mock", action="store_true", help="Run with MockYouTubeAdapter in offline mode")

    # Subcommand: channel
    parser_channel = subparsers.add_parser(
        "channel",
        help="Print the authorized YouTube channel info",
    )
    parser_channel.add_argument("--mock", action="store_true", help="Run with MockYouTubeAdapter in offline mode")

    if not argv:
        parser.print_help()
        sys.exit(2)

    args = parser.parse_args(argv)

    if args.subcommand == "ab":
        if args.action != "status" and not args.video_id:
            parser_ab.error("--video-id is required for this action")
        _cmd_youtube_ab(args)
    elif args.subcommand == "upload":
        _cmd_youtube_upload(args)
    elif args.subcommand == "status":
        _cmd_youtube_status(args)
    elif args.subcommand == "qa":
        _cmd_youtube_qa(args)
    elif args.subcommand == "auth":
        _cmd_youtube_auth(args)
    elif args.subcommand == "stats":
        _cmd_youtube_stats(args)
    elif args.subcommand == "channel":
        _cmd_youtube_channel(args)
    else:
        parser.print_help()
        sys.exit(2)
