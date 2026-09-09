# veraxi_ymmp

**End-to-End Status:** The generated `.ymmp` outputs are confirmed to work with YMM4, and the audio files are automatically wired up.

A Python tool that generates YMM4 `.ymmp` dialogue timelines by cloning real template items.

## Usage and TTS (VOICEVOX)

By default, without `--tts`, `veraxi-ymmp` uses a placeholder heuristic (`max(30, len(text) * 5)`) for frame timing.

When `--tts` is enabled, `veraxi-ymmp` generates audio via a local VOICEVOX engine and calculates exact frame lengths based on the generated audio and your template's configured `FPS`.

### Audio Playback Integration
The `VoiceCache` field is automatically populated with the relative path to the generated synthesized `.wav` files in the `{output}/audio/` directory.

### Full Automation
A full automation script `render_video.py` is included at the project root which chains generating the `.ymmp` and executing the YMM4 CLI for direct `.mp4` video rendering:

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
