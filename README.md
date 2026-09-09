# veraxi_ymmp

**Disclaimer:** The generated `.ymmp` outputs have NOT been validated by opening in a real YMM4 install with audio playback. Before trusting this for real work, open a generated `output.ymmp` in YMM4 and confirm it loads and plays correctly. WAV files are saved to `{output}/audio/` but audio wiring into YMM4 is NOT implemented.

A Python tool that generates YMM4 `.ymmp` dialogue timelines by cloning real template items.

## Usage and TTS (VOICEVOX)

By default, without `--tts`, `veraxi-ymmp` uses a placeholder heuristic (`max(30, len(text) * 5)`) for frame timing.

When `--tts` is enabled, `veraxi-ymmp` generates audio via a local VOICEVOX engine and calculates exact frame lengths based on the generated audio and your template's configured `FPS`. **Note: The generated WAV files are saved to `{output}/audio/` but are NOT automatically wired into the .ymmp file.**

### Audio Playback (UNVERIFIED)
The `VoiceCache` field is intentionally left empty (following AutoYukkuri's approach). Generated WAV files are saved to `{output}/audio/` for manual use, but automatic audio integration into YMM4 is not yet implemented. How to properly reference external WAV files in YMM4 needs investigation.

### Automation Script (UNVERIFIED)
A convenience script `render_video.py` is included at the project root which **attempts** to chain generating the `.ymmp` and executing the YMM4 CLI for direct `.mp4` video rendering. Neither the YMM4 CLI `--encode` flag nor the full chain have been verified end-to-end:

```bash
python render_video.py <template.ymmp> <script.json> <output.ymmp> <output.mp4> --tts --ymm4 "C:/Users/.../YukkuriMovieMaker.exe"
```


CLI options available for TTS:
- `--tts`: Enable real VOICEVOX-backed timing instead of placeholder heuristic.
- `--voicevox-url`: Base URL for VOICEVOX Engine (default: `http://localhost:50021`).
- `--speaker-map`: Path to a JSON file mapping `CharacterName` to a speaker_id (e.g. `{"ゆっくり霊夢": 10}`).
- `--default-speaker`: Default speaker ID (default: `3` / Zundamon).
- `--list-speakers`: Queries the VOICEVOX instance for all available speakers and prints them, then exits.

## Out of scope
- Building `Characters`, `VideoInfo`, or any top-level structure — these pass through from the template untouched.
- Multi-emotion/expression switching via `TachieFaceParameter` — left exactly as copied from the template.
- Any C#/.NET plugin work, or a `.ymme` distributable.
