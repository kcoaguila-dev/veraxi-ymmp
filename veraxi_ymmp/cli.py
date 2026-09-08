"""
Command-line interface for veraxi-ymmp.

Provides a CLI for generating YMM4 .ymmp dialogue timelines from templates and scripts.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .compiler import YMMPCompiler, CompilerError
from .voicevox import VoicevoxClient, VoicevoxError

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

    args = parser.parse_args()

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

    # Validate script structure
    if not isinstance(script, list):
        print("Error: Script must be a JSON array of objects", file=sys.stderr)
        sys.exit(1)

    for idx, entry in enumerate(script):
        if not isinstance(entry, dict):
            print(f"Error: Script entry {idx} must be an object", file=sys.stderr)
            sys.exit(1)
        if "character" not in entry or "text" not in entry:
            print(
                f"Error: Script entry {idx} must have 'character' and 'text' fields",
                file=sys.stderr
            )
            sys.exit(1)

    # Initialize VOICEVOX client if TTS is enabled
    voicevox_client: Optional[VoicevoxClient] = None
    speaker_map: dict = {}

    if args.tts:
        voicevox_client = VoicevoxClient(args.voicevox_url)
        if not voicevox_client.is_available():
            print(
                f"Error: VOICEVOX not available at {args.voicevox_url}",
                file=sys.stderr
            )
            sys.exit(1)

        if args.speaker_map:
            speaker_map_path = Path(args.speaker_map)
            if not speaker_map_path.exists():
                print(f"Error: Speaker map file not found: {speaker_map_path}", file=sys.stderr)
                sys.exit(1)
            try:
                with open(speaker_map_path, 'r', encoding='utf-8') as f:
                    speaker_map = json.load(f)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"Error: Invalid speaker map file: {e}", file=sys.stderr)
                sys.exit(1)

    # Create compiler and compile
    try:
        compiler = YMMPCompiler(
            template_path=str(template_path),
            voicevox_client=voicevox_client,
            speaker_map=speaker_map,
            default_speaker_id=args.default_speaker
        )
        compiler.compile(script, str(output_path), use_bom=args.bom)
    except (CompilerError, ValueError) as e:
        print(f"Compilation error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
