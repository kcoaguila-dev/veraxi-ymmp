import argparse
import json
import sys
from .compiler import YMMPCompiler
from .voicevox import VoicevoxClient, VoicevoxError

def main():
    parser = argparse.ArgumentParser(description="Generate YMM4 .ymmp timelines from a template and script.")
    parser.add_argument("template", nargs='?', help="Path to the template .ymmp file")
    parser.add_argument("script", nargs='?', help="Path to the script .json file")
    parser.add_argument("output", nargs='?', help="Path to write the output .ymmp file")
    parser.add_argument("--bom", action="store_true", help="Add UTF-8 BOM to the output file")

    # TTS features
    parser.add_argument("--tts", action="store_true", help="Enable real VOICEVOX-backed timing instead of placeholder heuristic")
    parser.add_argument("--voicevox-url", default="http://localhost:50021", help="Base URL for VOICEVOX Engine")
    parser.add_argument("--speaker-map", help="Path to a JSON file mapping CharacterName to speaker_id")
    parser.add_argument("--default-speaker", type=int, default=3, help="Default speaker ID (default: 3)")
    parser.add_argument("--list-speakers", action="store_true", help="Queries GET /speakers and prints the list, then exits")

    args = parser.parse_args()

    if args.list_speakers:
        client = VoicevoxClient(args.voicevox_url)
        try:
            speakers = client.get_speakers()
            print(json.dumps(speakers, indent=2, ensure_ascii=False))
        except VoicevoxError as e:
            print(f"Error fetching speakers: {e}")
            sys.exit(1)
        sys.exit(0)

    if not args.template or not args.script or not args.output:
        parser.error("template, script, and output are required unless using --list-speakers")

    with open(args.script, 'r', encoding='utf-8') as f:
        script = json.load(f)

    voicevox_client = None
    speaker_map = {}

    if args.tts:
        voicevox_client = VoicevoxClient(args.voicevox_url)
        if args.speaker_map:
            with open(args.speaker_map, 'r', encoding='utf-8') as f:
                speaker_map = json.load(f)

    compiler = YMMPCompiler(
        template_path=args.template,
        voicevox_client=voicevox_client,
        speaker_map=speaker_map,
        default_speaker_id=args.default_speaker
    )

    compiler.compile(script, args.output, use_bom=args.bom)

if __name__ == "__main__":
    main()
