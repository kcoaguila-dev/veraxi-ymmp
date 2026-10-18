# veraxi-ymmp

Clean-architecture multi-target video production engine for YukkuriMovieMaker4 (`.ymmp`), Adobe Premiere Pro (FCPXML), Adobe After Effects (`.jsx`), MoviePy, B-Roll graphics, and publication-ready YouTube thumbnails.

> For an in-depth breakdown of Clean Architecture layers, data flow diagrams, dependency rules, and fitness guardrails, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Architecture & Pipeline

`veraxi-ymmp` implements a clean two-stage authoring pipeline and multi-target compilation engine:

1. **Writer Stage:** Generates a purely factual dialogue script (`WriterScriptEntry`).
2. **Director Stage:** Enriches the dialogue with staging metadata (`emotion`, `motion`, `bgm`, `sfx`, `image`, `subtitle_position`) without altering factual text (`DirectorScriptEntry`).
3. **Canonical Intermediate Representation (`TimelineIR`):** Synthesizes timing data, VoiceVox phonemes, and visual layout into an engine-agnostic timeline model.
4. **Target Exporters:** Converts `TimelineIR` into target platform projects through isolated adapters implementing the `TimelineExporter` protocol.

```
Script (Writer/Director) ──> VoiceVox TTS ──> TimelineIR ──┬──> YMM4 (.ymmp)
                                                          ├──> Premiere Pro (FCPXML)
                                                          ├──> MoviePy (Preview MP4)
                                                          ├──> After Effects (.jsx)
                                                          ├──> SRT Subtitles (.srt)
                                                          └──> YouTube Thumbnail (.png)
```

---

## Supported Exporters & Target Platforms

| Target Format | Implementation | Description |
|---|---|---|
| **YMM4 Project (`.ymmp`)** | [`YMMPRenderer`](file:///c:/dev/workspace/active/veraxi-ymmp/veraxi_ymmp/ymmp_renderer.py) | Clones template timeline items, embeds Brotli-compressed voice caches, and configures phonetic mouth animations. |
| **Premiere Pro (`.xml`)** | [`PremiereExporter`](file:///c:/dev/workspace/active/veraxi-ymmp/veraxi_ymmp/premiere_exporter.py) | Generates Final Cut Pro XML (xmeml) with 4 video tracks (BG, Tachie, B-Roll, Subtitle speech bubbles) and 3 audio tracks. |
| **MoviePy Preview (`.mp4`)** | [`MoviePyRenderer`](file:///c:/dev/workspace/active/veraxi-ymmp/veraxi_ymmp/moviepy_renderer.py) | High-speed software renderer producing 1080p preview videos with speech bubbles and audio ducking for CI/CD and pre-flight QA. |
| **After Effects (`.jsx`)** | [`AfterEffectsRenderer`](file:///c:/dev/workspace/active/veraxi-ymmp/veraxi_ymmp/ae_renderer.py) | Generates ExtendScript automation files with slider-driven lip-sync and character bounce effects. |
| **SRT Subtitles (`.srt`)** | [`generate_srt`](file:///c:/dev/workspace/active/veraxi-ymmp/veraxi_ymmp/srt_generator.py) | Generates standard SRT subtitle files with millisecond precision for Premiere Pro caption tracks. |
| **YouTube Thumbnail (`.png`)** | [`ThumbnailGenerator`](file:///c:/dev/workspace/active/veraxi-ymmp/veraxi_ymmp/thumbnail.py) | 1920x1080 publication-ready thumbnails using 3-split rule (3分割法), outline typography (袋文字), and timestamp dead-zone protection. |

---

## Quality Assurance & Architectural Fitness Guardrails

`veraxi-ymmp` enforces systematic architectural and privacy invariants verified by automated fitness tests in [`tests/test_architectural_fitness.py`](file:///c:/dev/workspace/active/veraxi-ymmp/tests/test_architectural_fitness.py):

- **Domain Layer Purity:** Domain modules (`ir.py`, `script.py`, `constants.py`) have zero dependencies on infrastructure, rendering, or delivery adapters.
- **Cross-Adapter Isolation:** Exporter adapters never import directly from peer exporter adapters, preventing coupling and circular dependencies.
- **Module Size Ceilings:** Strict 900-line limit per module preventing monolithic God objects.
- **Privacy & Local Path Scanner:** Automated scanner ([`scripts/check_no_local_paths.py`](file:///c:/dev/workspace/active/veraxi-ymmp/scripts/check_no_local_paths.py)) guarantees zero hardcoded developer usernames or local machine paths in repository source code.
- **Secret Detection:** Gitleaks and Yelp detect-secrets guard commit history and staging against credential leakage.
- **EBU R128 Audio Normalization:** Automated loudness leveling via FFmpeg loudnorm targeting YouTube (-14 LUFS), TikTok/Instagram (-13 LUFS), and broadcast standards ([`normalize_audio.py`](file:///c:/dev/workspace/active/veraxi-ymmp/normalize_audio.py)).

---

## Usage

### 1. Unified Project Runner (Recommended)
Synthesizes speech, compiles `TimelineIR`, exports Premiere Pro FCPXML, compiles YMM4 project, renders MoviePy preview video, and auto-generates the YouTube thumbnail:
```bash
python run_project.py projects/01_costco_business_model/
```

Generated project directory artifacts:
- `audio/` - Synthesized VoiceVox audio WAV files & phoneme metadata
- `premiere/` - Adobe Premiere Pro FCPXML sequence
- `ymmp/final_video.ymmp` - Ready-to-render YMM4 project
- `qa_test.mp4` - Full fast-preview video
- `thumbnail.png` - Publication-ready 1920x1080 YouTube thumbnail

### 2. Standalone Thumbnail Generation
```bash
# Auto-derive from project directory
python -m veraxi_ymmp.thumbnail projects/01_costco_business_model/

# Or specify custom thumbnail output in compiler CLI
python -m veraxi_ymmp examples/full_template.ymmp artifacts/script.json artifacts/output.ymmp --thumbnail artifacts/thumbnail.png
```

### 3. Audio Loudness Normalization
Normalize exported video audio to social media platform standards:
```bash
# Normalize for YouTube (-14 LUFS)
python normalize_audio.py output.mp4 --platform youtube

# Generate normalized videos for all platforms
python normalize_audio.py output.mp4 --all
```

### 4. Optional YMM4 Hardware Rendering
```bash
# Windows environment variable for headless GPU export
set YMM4_PATH=C:\Users\YourUser\Documents\YukkuriMovieMaker_v4_Lite\YukkuriMovieMaker.exe
```

---

## Development & Testing

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run architectural fitness tests
pytest tests/test_architectural_fitness.py -v

# Run full test suite
pytest

# Lint and type check
ruff check veraxi_ymmp/ tests/ scripts/
mypy veraxi_ymmp
python scripts/check_no_local_paths.py --all
```
