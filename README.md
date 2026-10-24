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
- **EBU R128 Audio Normalization:** Automated loudness leveling via FFmpeg loudnorm targeting YouTube (-14 LUFS), TikTok/Instagram (-13 LUFS), and broadcast standards ([`veraxi_ymmp/audio_normalizer.py`](file:///c:/dev/workspace/active/veraxi-ymmp/veraxi_ymmp/audio_normalizer.py)).

---

## Usage

### 1. Unified Project Runner (Recommended)
Synthesizes speech, compiles `TimelineIR`, exports Premiere Pro FCPXML, compiles YMM4 project, renders MoviePy preview video, and auto-generates the YouTube thumbnail:
```bash
veraxi-ymmp run projects/01_costco_business_model/
# or: python -m veraxi_ymmp.cli run projects/01_costco_business_model/
```

Generated project directory artifacts:
- `audio/` - Synthesized VoiceVox audio WAV files & phoneme metadata
- `premiere/` - Adobe Premiere Pro FCPXML sequence
- `ymmp/final_video.ymmp` - Ready-to-render YMM4 project
- `qa_test.mp4` - Full fast-preview video
- `thumbnail.png` - Publication-ready 1920x1080 YouTube thumbnail

### 2. Standalone Thumbnail & B-Roll Generation
```bash
# Auto-derive thumbnail from project directory
veraxi-ymmp thumbnail projects/01_costco_business_model/

# Render B-roll slides from declarative JSON manifest
veraxi-ymmp broll projects/02_market_analysis_2026/broll_manifest.json

# Or specify custom thumbnail output in compiler CLI
veraxi-ymmp examples/full_template.ymmp artifacts/script.json artifacts/output.ymmp --thumbnail artifacts/thumbnail.png
```

### 3. Audio Loudness Normalization
Normalize exported video audio to social media platform standards:
```bash
# Normalize for YouTube (-14 LUFS)
veraxi-ymmp normalize output.mp4 -p youtube

# Generate normalized videos for all platforms
veraxi-ymmp normalize output.mp4 --all
```

### 4. Optional YMM4 Hardware Rendering
```bash
# Windows environment variable for headless GPU export
set YMM4_PATH=C:\Users\YourUser\Documents\YukkuriMovieMaker_v4_Lite\YukkuriMovieMaker.exe
```

### 5. YouTube Integration & Analytics
To publish videos and retrieve stats, you must set up YouTube API access:

1. **Create a GCP Project:** Go to Google Cloud Console and create a new project.
2. **Enable APIs:** Enable both **YouTube Data API v3** and **YouTube Analytics API**.
3. **Configure OAuth Consent:** Setup the OAuth consent screen. Choose "External", add yourself as a test user, and publish the app to "Production" to avoid the 7-day token expiration limit.
4. **Create Credentials:** Create an OAuth 2.0 Client ID for a "Desktop app" and download the `client_secrets.json` file.
5. **Install Extras:** Run `pip install -e ".[youtube]"`.
6. **Authenticate:** Run `veraxi-ymmp youtube auth --client-secrets path/to/client_secrets.json`. This opens a browser to log in and saves your refresh token locally.

*Note on Quotas:* The YouTube Data API has a default quota of 10,000 units/day (~1,600 units per video upload). Unverified API projects can only upload videos as "private" until they pass a YouTube API compliance audit.

**Usage Examples:**
```bash
# Verify authentication setup and channel stats
veraxi-ymmp youtube channel

# Fetch metrics for specific videos as a JSON report
veraxi-ymmp youtube stats --video-id YourVideoID1 --video-id YourVideoID2 --format json

# CI/CD Usage
# Export the token content to VERAXI_YOUTUBE_AUTHORIZED_USER_JSON in your GitHub Secrets
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
