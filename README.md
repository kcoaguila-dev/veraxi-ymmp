# veraxi_ymmp

**Disclaimer:** The generated `.ymmp` outputs have NOT been validated by opening in a real YMM4 install. Before trusting this for real work, open a generated `output.ymmp` in YMM4 and confirm it loads and plays correctly. The `VoiceCache` field wiring and YMM4 CLI encoding are **unverified guesses**.

A Python tool that generates YMM4 `.ymmp` dialogue timelines by cloning real template items.

## Usage and TTS (VOICEVOX)

By default, without `--tts`, `veraxi-ymmp` uses a placeholder heuristic (`max(30, len(text) * 5)`) for frame timing.

When `--tts` is enabled, `veraxi-ymmp` generates audio via a local VOICEVOX engine and calculates exact frame lengths based on the generated audio and your template's configured `FPS`.

### Audio Playback Integration (UNVERIFIED)
The `VoiceCache` field is **attempted** to be populated with the relative path to the generated synthesized `.wav` files in the `{output}/audio/` directory. This has NOT been confirmed to work with real YMM4 — it may require a different path format or approach.

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
