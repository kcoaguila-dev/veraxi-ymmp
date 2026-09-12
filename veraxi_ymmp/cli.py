"""
Command-line interface for veraxi-ymmp.

Provides a CLI for generating YMM4 .ymmp dialogue timelines from templates and scripts.
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from .compiler import YMMPCompiler, CompilerError
from .async_compiler import AsyncYMMPCompiler
from .config import CompilerConfig
from .voicevox import VoicevoxClient, VoicevoxError, NullTTSBackend
from .logging import setup_logging, logger
from .script import validate_writer_script, validate_director_script, validate_director_against_writer

# Ensure stdout uses UTF-8 encoding for proper display of non-ASCII characters
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')


def main():
    """Main entry point for the CLI."""
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

    if is_director:
        try:
            validated_script = validate_director_script(script)
        except ValueError as e:
            print(f"Error: Invalid director script schema: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            validated_script = validate_writer_script(script)
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

    tts_backend = None
    if config.use_tts:
        tts_backend = VoicevoxClient(config.voicevox_url)
        if not tts_backend.is_available():
            logger.error(f"VOICEVOX not available at {config.voicevox_url}")
            sys.exit(1)
    else:
        tts_backend = NullTTSBackend()

    try:
        CompilerClass = AsyncYMMPCompiler if getattr(args, 'use_async', False) else YMMPCompiler
        compiler = CompilerClass(
            template_path=template_path,
            config=config,
            tts_backend=tts_backend
        )

        if getattr(args, 'use_async', False):
            result = asyncio.run(compiler.compile_async(script, output_path, use_bom=config.use_bom))
        else:
            result = compiler.compile(script, output_path, use_bom=config.use_bom)

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

    except (CompilerError, ValueError) as e:
        logger.error(f"Compilation error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
