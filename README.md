# veraxi_ymmp

**Disclaimer: Output has not been validated by opening in a real YMM4 install. Before trusting this for real work, open a generated `output.ymmp` in YMM4 and confirm it loads and plays correctly.**

A Python tool that generates YMM4 `.ymmp` dialogue timelines by cloning real template items.

## Usage and TTS (VOICEVOX)

By default, without `--tts`, `veraxi-ymmp` uses a placeholder heuristic (`max(30, len(text) * 5)`) for frame timing.

When `--tts` is enabled, `veraxi-ymmp` generates audio via a local VOICEVOX engine and calculates exact frame lengths based on the generated audio and your template's configured `FPS`.

### Important Note on Audio Playback
**`VoiceCache` is left empty; synthesized `.wav` files are saved to `{output}/audio/` for manual reference. How to wire real audio into a `VoiceItem` so YMM4 uses it directly is still unverified — this needs to be confirmed against a real YMM4 install before it's solved. Open the generated `.ymmp` in YMM4 and check whether it detects/needs the WAV manually assigned.**

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
