"""
Command-line interface for veraxi-ymmp.

Provides a CLI for generating YMM4 .ymmp dialogue timelines from templates and scripts.
"""

import argparse
import asyncio
import json
import logging
import sys
from typing import Any, List, Optional
from pathlib import Path

from .compiler import YMMPCompiler, CompilerError
from .async_compiler import AsyncYMMPCompiler
from .config import CompilerConfig
from .voicevox import VoicevoxClient, VoicevoxError, NullTTSBackend, TTSBackend
from .logging import setup_logging, logger
from .script import validate_writer_script, validate_director_script, validate_director_against_writer

def _cmd_run(argv: List[str]) -> None:
    """Run the end-to-end ProjectPipeline for a project directory."""
    from .pipeline import ProjectPipeline

    parser = argparse.ArgumentParser(
        prog="veraxi-ymmp run",
        description="Run end-to-end Veraxi YMMP project pipeline.",
    )
    parser.add_argument("project_dir", type=str, help="Path to project directory")
    parser.add_argument("--no-tts", action="store_true", help="Disable VOICEVOX TTS synthesis")
    parser.add_argument("--no-premiere", action="store_true", help="Skip Premiere XML export")
    parser.add_argument("--no-ymmp", action="store_true", help="Skip YMM4 export")
    parser.add_argument("--no-qa", action="store_true", help="Skip MoviePy QA render")
    parser.add_argument("--qa-duration", type=float, default=30.0, help="Duration for QA render in seconds")
    parser.add_argument("--no-thumbnail", action="store_true", help="Skip YouTube thumbnail generation")

    args = parser.parse_args(argv)
    pipeline = ProjectPipeline(use_tts=not args.no_tts)
    result = pipeline.run(
        project_path=args.project_dir,
        do_premiere=not args.no_premiere,
        do_ymmp=not args.no_ymmp,
        do_qa=not args.no_qa,
        qa_duration=args.qa_duration,
        do_thumbnail=not args.no_thumbnail,
    )
    if not result.success:
        for err in result.errors:
            print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


def _cmd_normalize(argv: List[str]) -> None:
    """Normalize video audio loudness for one or all target platforms."""
    from .audio_normalizer import (
        PLATFORM_TARGETS,
        normalize_all_platforms,
        normalize_video_audio,
    )

    parser = argparse.ArgumentParser(
        prog="veraxi-ymmp normalize",
        description="Normalize video audio loudness to platform LUFS targets.",
    )
    parser.add_argument("input", type=str, help="Path to input video file")
    parser.add_argument("-o", "--output", type=str, default=None, help="Output file or directory path")
    parser.add_argument(
        "-p",
        "--platform",
        choices=list(PLATFORM_TARGETS.keys()),
        default="youtube",
        help="Target platform (default: youtube)",
    )
    parser.add_argument("--all", action="store_true", help="Normalize for all configured platforms")

    args = parser.parse_args(argv)
    input_path = Path(args.input)
    try:
        if args.all:
            outputs = normalize_all_platforms(input_path, output_dir=args.output)
            for plat, out_p in outputs.items():
                print(f"Normalized ({plat}): {out_p}")
        else:
            target = PLATFORM_TARGETS[args.platform]
            out_path = (
                Path(args.output)
                if args.output
                else input_path.parent / f"{input_path.stem}_{args.platform}{input_path.suffix}"
            )
            res_path = normalize_video_audio(
                input_video=input_path,
                output_video=out_path,
                target_i=target["I"],
                target_tp=target["TP"],
                target_lra=target["LRA"],
            )
            print(f"Normalized ({args.platform}): {res_path}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_broll(argv: List[str]) -> None:
    """Render B-Roll slides from a declarative JSON manifest."""
    from .broll import render_from_manifest

    parser = argparse.ArgumentParser(
        prog="veraxi-ymmp broll",
        description="Render B-Roll slides from a declarative JSON manifest.",
    )
    parser.add_argument("manifest", type=str, help="Path to broll_manifest.json")
    parser.add_argument("-o", "--output-dir", type=str, default=None, help="Output directory for slides")

    args = parser.parse_args(argv)
    manifest_path = Path(args.manifest)
    out_dir = Path(args.output_dir) if args.output_dir else manifest_path.parent / "broll"
    try:
        generated = render_from_manifest(manifest_path, out_dir)
        print(f"Generated {len(generated)} B-roll slides in {out_dir}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_thumbnail(argv: List[str]) -> None:
    """Generate a high-CTR YouTube thumbnail for a project directory."""
    from .thumbnail import generate_project_thumbnail

    parser = argparse.ArgumentParser(
        prog="veraxi-ymmp thumbnail",
        description="Generate a high-CTR YouTube thumbnail for a project directory.",
    )
    parser.add_argument("project_dir", type=str, help="Path to project directory")
    parser.add_argument("-o", "--output", type=str, default=None, help="Output PNG path")

    args = parser.parse_args(argv)
    proj_path = Path(args.project_dir)
    out_path = Path(args.output) if args.output else proj_path / "thumbnail.png"
    try:
        res = generate_project_thumbnail(proj_path, out_path=out_path)
        print(f"Thumbnail generated at: {res}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Main entry point for the CLI."""
    # Ensure stdout uses UTF-8 encoding for proper display of non-ASCII characters
    if hasattr(sys.stdout, "reconfigure") and getattr(sys.stdout, "encoding", None) != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    if len(sys.argv) > 1 and sys.argv[1] in {"run", "normalize", "broll", "thumbnail"}:
        subcmd = sys.argv[1]
        sub_argv = sys.argv[2:]
        if subcmd == "run":
            _cmd_run(sub_argv)
        elif subcmd == "normalize":
            _cmd_normalize(sub_argv)
        elif subcmd == "broll":
            _cmd_broll(sub_argv)
        elif subcmd == "thumbnail":
            _cmd_thumbnail(sub_argv)
        return

    parser = argparse.ArgumentParser(
        description="Generate YMM4 .ymmp timelines from a template and script."
    )
    parser.add_argument("template", nargs='?', help="Path to the template .ymmp file")
    parser.add_argument("script", nargs='?', help="Path to the script .json file")
    parser.add_argument("output", nargs='?', help="Path to write the output .ymmp file")
    parser.add_argument("--writer-script", type=str, help="Path to the writer script .json file to validate against")
    parser.add_argument("--bom", action="store_true", help="Add UTF-8 BOM to the output file")

    # TTS features
    parser.add_argument(
        "--tts",
        action="store_true",
        help="Enable real VOICEVOX-backed timing instead of placeholder heuristic"
    )
    parser.add_argument(
        "--voicevox-url",
        default="http://localhost:50021",
        help="Base URL for VOICEVOX Engine (default: http://localhost:50021)"
    )
    parser.add_argument(
        "--speaker-map",
        type=str,
        help="Path to a JSON file mapping CharacterName to speaker_id"
    )
    parser.add_argument(
        "--default-speaker",
        type=int,
        default=3,
        help="Default speaker ID (default: 3 / Zundamon)"
    )
    parser.add_argument(
        "--list-speakers",
        action="store_true",
        help="Queries GET /speakers and prints the list, then exits"
    )

    # New architecture arguments
    parser.add_argument("--no-cache", action="store_true", help="Disable TTS caching")
    parser.add_argument("--cache-dir", type=str, help="Directory for disk caching")
    parser.add_argument("--async", dest="use_async", action="store_true", help="Use async compilation for parallel TTS")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose debug logging")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress info logging, only show warnings/errors")
    parser.add_argument("--log-file", type=str, help="Write logs to file")

    # YMM4 Export Feature
    parser.add_argument("--export-mp4", type=str, help="Automatically render to MP4 using YMM4 CLI (requires YMM4_PATH env var)")

    # YouTube Thumbnail Feature
    parser.add_argument(
        "--thumbnail",
        nargs="?",
        const="default",
        help="Automatically generate high-CTR YouTube thumbnail PNG (optional: specify custom output path)"
    )

    args = parser.parse_args()

    # Setup logging based on args
    level = logging.INFO
    if getattr(args, 'verbose', False):
        level = logging.DEBUG
    elif getattr(args, 'quiet', False):
        level = logging.WARNING

    setup_logging(level=level, log_file=getattr(args, 'log_file', None))

    if args.list_speakers:
        _list_speakers(args)
        return

    if not args.template or not args.script or not args.output:
        parser.error(
            "template, script, and output are required unless using --list-speakers"
        )

    _compile(args)


def _list_speakers(args: argparse.Namespace) -> None:
    """List available VOICEVOX speakers."""
    client = VoicevoxClient(args.voicevox_url)
    try:
        speakers = client.get_speakers()
        print(json.dumps(speakers, indent=2, ensure_ascii=False))
    except VoicevoxError as e:
        print(f"Error fetching speakers: {e}", file=sys.stderr)
        sys.exit(1)


def _compile(args: argparse.Namespace) -> None:
    """Compile a script using the template."""
    # Validate input files exist
    template_path = Path(args.template)
    script_path = Path(args.script)
    output_path = Path(args.output)

    if not template_path.exists():
        print(f"Error: Template file not found: {template_path}", file=sys.stderr)
        sys.exit(1)

    if not script_path.exists():
        print(f"Error: Script file not found: {script_path}", file=sys.stderr)
        sys.exit(1)

    # Load script
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            script = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in script file: {e}", file=sys.stderr)
        sys.exit(1)
    except UnicodeDecodeError as e:
        print(f"Error: Script file is not UTF-8 encoded: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine if script should be validated as Director script
    is_director = False
    if getattr(args, "writer_script", None):
        is_director = True
    else:
        # Check if any entry has director-specific metadata
        for entry in script:
            if isinstance(entry, dict) and any(key in entry for key in ("emotion", "motion", "bgm", "sfx")):
                is_director = True
                break

    validated_script: List[Any]
    if is_director:
        try:
            validated_script = list(validate_director_script(script))
        except ValueError as e:
            print(f"Error: Invalid director script schema: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            validated_script = list(validate_writer_script(script))
        except ValueError as e:
            print(f"Error: Invalid writer script schema: {e}", file=sys.stderr)
            sys.exit(1)

    # If a writer script is provided, validate the script against it
    if getattr(args, "writer_script", None):
        writer_script_path = Path(args.writer_script)
        if not writer_script_path.exists():
            print(f"Error: Writer script file not found: {writer_script_path}", file=sys.stderr)
            sys.exit(1)

        try:
            with open(writer_script_path, 'r', encoding='utf-8') as f:
                writer_script_raw = json.load(f)
            writer_script = validate_writer_script(writer_script_raw)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in writer script file: {e}", file=sys.stderr)
            sys.exit(1)
        except UnicodeDecodeError as e:
            print(f"Error: Writer script file is not UTF-8 encoded: {e}", file=sys.stderr)
            sys.exit(1)
        except ValueError as e:
            print(f"Error: Invalid writer script schema: {e}", file=sys.stderr)
            sys.exit(1)

        try:
            validate_director_against_writer(validated_script, writer_script)  # type: ignore
        except ValueError as e:
            print(f"Error: Director script validation failed: {e}", file=sys.stderr)
            sys.exit(1)

    script = validated_script  # type: ignore

    config = CompilerConfig.from_cli_args(args)

    if args.speaker_map:
        speaker_map_path = Path(args.speaker_map)
        if not speaker_map_path.exists():
            logger.error(f"Speaker map file not found: {speaker_map_path}")
            sys.exit(1)
        try:
            with open(speaker_map_path, 'r', encoding='utf-8') as f:
                config.speaker_map = json.load(f)
        except Exception as e:
            logger.error(f"Invalid speaker map file: {e}")
            sys.exit(1)

    tts_backend: Optional[TTSBackend] = None
    if config.use_tts:
        client = VoicevoxClient(config.voicevox_url)
        if not client.is_available():
            logger.error(f"VOICEVOX not available at {config.voicevox_url}")
            sys.exit(1)
        tts_backend = client
    else:
        tts_backend = NullTTSBackend()

    try:
        if getattr(args, 'use_async', False):
            async_compiler = AsyncYMMPCompiler(
                template_path=template_path,
                config=config,
                tts_backend=tts_backend,
            )
            result = asyncio.run(async_compiler.compile_async(validated_script, output_path, use_bom=config.use_bom))
        else:
            compiler = YMMPCompiler(
                template_path=template_path,
                config=config,
                tts_backend=tts_backend,
            )
            result = compiler.compile(validated_script, output_path, use_bom=config.use_bom)

        logger.info(f"Compilation complete: {result.total_frames} frames ({result.total_duration_seconds:.2f}s)")
        logger.info(f"Items: {result.item_count} total, {result.voice_item_count} voice, {result.tachie_item_count} tachie")
        if not getattr(args, 'quiet', False):
            print(f"Compilation complete: saved to {result.output_path}")
            if result.warnings:
                print(f"Encountered {len(result.warnings)} warnings")

        # Auto-Export using YMM4 CLI
        if getattr(args, 'export_mp4', None):
            import os
            import subprocess
            mp4_path = Path(args.export_mp4).resolve()

            ymm4_exe_path = os.environ.get("YMM4_PATH")
            if not ymm4_exe_path:
                print("Error: YMM4_PATH environment variable is not set.", file=sys.stderr)
                print("Please set it to the path of your YukkuriMovieMaker.exe to use --export-mp4", file=sys.stderr)
                sys.exit(1)

            ymm4_exe = Path(ymm4_exe_path)
            if not ymm4_exe.exists():
                print(f"Error: YMM4 not found at {ymm4_exe}", file=sys.stderr)
                sys.exit(1)

            if mp4_path.exists():
                mp4_path.unlink()

            print(f"Exporting {output_path} to {mp4_path} using YMM4 CLI...")
            subprocess.run([
                str(ymm4_exe),
                "--project", str(output_path.resolve()),
                "--output", str(mp4_path),
                "--export"
            ], check=True)
            print("Export finished successfully!")

        # Thumbnail Generation Feature
        if getattr(args, "thumbnail", None):
            from .thumbnail import generate_thumbnail, auto_extract_thumbnail_config
            if args.thumbnail != "default":
                thumb_target = Path(args.thumbnail)
            else:
                thumb_target = output_path.with_name(f"{output_path.stem}_thumbnail.png")

            print(f"Generating high-CTR YouTube thumbnail to {thumb_target}...")
            t_config = auto_extract_thumbnail_config(script_path.parent if script_path.exists() else validated_script)
            generate_thumbnail(t_config, thumb_target)
            print(f"Thumbnail generated successfully at: {thumb_target}")

    except (CompilerError, ValueError) as e:
        logger.error(f"Compilation error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
