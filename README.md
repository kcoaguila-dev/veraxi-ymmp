# veraxi-ymmp

Clean-architecture multi-target video production engine and visual studio for YukkuriMovieMaker4 (`.ymmp`), Adobe Premiere Pro (FCPXML), Adobe After Effects (`.jsx`), MoviePy, B-Roll graphics, and publication-ready YouTube thumbnails.

> For an in-depth breakdown of Clean Architecture layers, data flow diagrams, dependency rules, and fitness guardrails, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Architecture & Pipeline

`veraxi-ymmp` implements a clean two-stage authoring pipeline and multi-target compilation engine:

1. **Writer Stage:** Generates a purely factual dialogue script (`WriterScriptEntry`).
2. **Director Stage:** Enriches dialogue with staging metadata (`emotion`, `motion`, `bgm`, `sfx`, `image`, `subtitle_position`) without altering factual text (`DirectorScriptEntry`).
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

## veraxi Studio GUI (Visual NLE & Web AI Bridge)

`veraxi-ymmp` includes **veraxi Studio**, a desktop-grade visual editing interface designed with high-density NLE aesthetics (`#0B0F19` obsidian canvas, `#111827` panels, and semantic character branding).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ veraxi Studio   [01_costco_business_model ▾]  [VOICEVOX OK]  [⚡動画を生成]  │
├────────────────────────────────────────┬────────────────────────────────────┤
│ 1. 台本・スライド編集                  │ 2. プレビュー確認 (qa_test.mp4)    │
│  • Scene 1: イントロ (Slide 1 Preview) │   ┌──────────────────────────────┐ │
│    [ずんだ] 笑顔 | 23文字              │   │   16:9 Video Canvas          │ │
│    [めたん] 通常 | 28文字              │   └──────────────────────────────┘ │
│  • Scene 2: 収益解説 (Slide 2 Preview) │   [▶ 再生] 00:14/01:30 [Scrubber]  │
│    [めたん] ✂ 38文字 (分割推奨)       ├────────────────────────────────────┤
│                                        │ 3. YouTubeサムネイル・投稿         │
│ [ずんだもん ▾] 手動セリフ追加 [＋追加] │   [3分割サムネ] タイトル / 投稿    │
└────────────────────────────────────────┴────────────────────────────────────┘
```

### Key Features
- **Scene-Grouped Storyboard Editor:** Dialogue lines are grouped into cohesive visual scene blocks with inline slide thumbnails (`SLIDE N`), background/BGM indicators, and one-click slide changing.
- **Real-Time Guardrails:** Automatic character length counter (`23文字 ✓`), warning states for readability (`✂ 38文字 — 2行に分割を推奨` with 1-click splitting), and rule enforcement (e.g. flagging bare `「ええ、」`).
- **Instant Voicevox Auditioning:** 1-click circular audition buttons on dialogue cards to test speech synthesis and pronunciation immediately.
- **Zero API Key Web AI Bridge:**
  - `📋 AI用プロンプトをコピー`: Copies the universal structured prompt formatted for ChatGPT, Claude, or Gemini Web.
  - `📥 JSON貼り付け`: Pastes generated JSON arrays directly into the project with automated schema validation and self-healing re-prompt diagnostics.
- **Built-in Studio Transport & Loudness Normalization:** Integrated 16:9 player with custom transport bar, millisecond timecode, scene scrubber, and one-click EBU R128 (-14.0 LUFS) normalization.
- **YouTube Thumbnail & Direct Upload:** Fixed 3-split thumbnail preview with timestamp dead-zone protection, thumbnail regeneration, privacy controls, scheduling, and direct YouTube upload (or offline test mock).
- **One-Click NLE Handoff:** Dedicated header buttons to immediately launch projects in **YMM4** (`.ymmp`) or download Adobe **Premiere Pro** (`.xml`).

### Launching the Studio GUI
```bash
# Terminal 1: Start the backend API server (runs on port 8000)
veraxi-ymmp serve

# Terminal 2: Start the frontend dev server (runs on port 1420)
cd frontend
npm install
npm run dev
```
Open **`http://localhost:1420`** in your browser.

---

## Supported Exporters & Target Platforms

| Target Format | Implementation | Description |
|---|---|---|
| **YMM4 Project (`.ymmp`)** | [`YMMPRenderer`](veraxi_ymmp/ymmp_renderer.py) | Clones template timeline items, embeds Brotli-compressed voice caches, and configures phonetic mouth animations. |
| **Premiere Pro (`.xml`)** | [`PremiereExporter`](veraxi_ymmp/premiere_exporter.py) | Generates Final Cut Pro XML (xmeml) with 4 video tracks (BG, Tachie, B-Roll, Subtitle speech bubbles) and 3 audio tracks. |
| **MoviePy Preview (`.mp4`)** | [`MoviePyRenderer`](veraxi_ymmp/moviepy_renderer.py) | High-speed software renderer producing 1080p preview videos with speech bubbles and audio ducking for CI/CD and pre-flight QA. |
| **After Effects (`.jsx`)** | [`AfterEffectsRenderer`](veraxi_ymmp/ae_renderer.py) | Generates ExtendScript automation files with slider-driven lip-sync and character bounce effects. |
| **SRT Subtitles (`.srt`)** | [`generate_srt`](veraxi_ymmp/srt_generator.py) | Generates standard SRT subtitle files with millisecond precision for Premiere Pro caption tracks. |
| **YouTube Thumbnail (`.png`)** | [`ThumbnailGenerator`](veraxi_ymmp/thumbnail.py) | 1920x1080 publication-ready thumbnails using 3-split rule (3分割法), outline typography (袋文字), and timestamp dead-zone protection. |

---

## Quality Assurance & Architectural Fitness Guardrails

`veraxi-ymmp` enforces systematic architectural and privacy invariants verified by automated fitness tests in [`tests/test_architectural_fitness.py`](tests/test_architectural_fitness.py):

- **Domain Layer Purity:** Domain modules (`ir.py`, `script.py`, `constants.py`) have zero dependencies on infrastructure, rendering, or delivery adapters.
- **Cross-Adapter Isolation:** Exporter adapters never import directly from peer exporter adapters, preventing coupling and circular dependencies.
- **Module Size Ceilings:** Strict 900-line limit per module preventing monolithic God objects.
- **Privacy & Local Path Scanner:** Automated scanner ([`scripts/check_no_local_paths.py`](scripts/check_no_local_paths.py)) guarantees zero hardcoded developer usernames or local machine paths in repository source code.
- **Secret Detection:** Gitleaks and Yelp detect-secrets guard commit history and staging against credential leakage.
- **EBU R128 Audio Normalization:** Automated loudness leveling via FFmpeg loudnorm targeting YouTube (-14 LUFS), TikTok/Instagram (-13 LUFS), and broadcast standards ([`veraxi_ymmp/audio_normalizer.py`](veraxi_ymmp/audio_normalizer.py)).

---

## Prerequisites & Installation

### 1. System Requirements
- **Python:** 3.10, 3.11, 3.12, 3.13, or 3.14
- **Node.js & npm:** 18+ (required for building and running `veraxi Studio` frontend)
- **FFmpeg:** Installed and available on system `PATH` (required for MoviePy rendering and audio normalization).
- **VOICEVOX Engine (Local):** Running on `http://127.0.0.1:50021` (required for speech synthesis). Download free at [voicevox.hiroshiba.jp](https://voicevox.hiroshiba.jp/).
- **YukkuriMovieMaker4 (Optional):** If rendering final `.ymmp` projects via hardware acceleration on Windows.

### 2. Setup Virtual Environment
```bash
git clone https://github.com/kcoaguila-dev/veraxi-ymmp.git
cd veraxi-ymmp
python -m venv venv

# Windows
.\venv\Scripts\activate
# Linux / macOS
source venv/bin/activate

# Install base engine + dev tools + youtube + mcp
pip install -e ".[dev,mcp,youtube]"
```

---

## End-to-End Workflow (Manual / No AI Required)

`veraxi-ymmp` is a deterministic code engine. You do not need any AI agent to produce videos from start to finish. A human creator can execute the complete workflow using standard configuration files:

```
Step 1: Write script.json (Writer / Director dialogue)
   │
Step 2: (Optional) Define broll_manifest.json for visual slides
   │
Step 3: Run pipeline: `veraxi-ymmp run projects/my_video/`
   │    ├── Generates audio via local VoiceVox
   │    ├── Builds TimelineIR
   │    ├── Exports Premiere XML + YMM4 (.ymmp)
   │    ├── Renders fast QA preview video (qa_test.mp4)
   │    └── Generates high-CTR thumbnail (thumbnail.png)
   │
Step 4: Review qa_test.mp4 or polish in YMM4 / Premiere Pro
   │
Step 5: Normalize audio loudness (-14.0 LUFS)
   │
Step 6: Publish & Schedule to YouTube with synced SRT captions
   │
Step 7: Analyze retention telemetry & A/B test thumbnails
```

### Step 1: Create Project Directory & `script.json`
Create a folder under `projects/my_video/` and write your dialogue in `script.json`:

```json
[
  {
    "character": "ずんだもん",
    "text": "みんな、こんにちはなのだ！今日はClean Architectureについて解説するのだ！",
    "emotion": "happy"
  },
  {
    "character": "四国めたん",
    "text": "よろしくお願いいたしますわ。基礎からしっかり学びましょう。",
    "emotion": "normal"
  }
]
```
> Supported characters out-of-the-box: `ずんだもん` (Speaker ID 3), `四国めたん` (Speaker ID 2), `春日部つむぎ` (Speaker ID 8). Run `veraxi-ymmp --help` or inspect `veraxi_ymmp/constants.py` for speaker registries.

### Step 2: (Optional) Create B-Roll Slide Graphics
If your video contains informative slides or diagrams, define a `broll_manifest.json`:

```json
[
  {
    "slide_index": 1,
    "headline": "Clean Architectureの4層構造",
    "points": [
      "Enterprise Business Rules",
      "Application Business Rules",
      "Interface Adapters",
      "Frameworks & Drivers"
    ],
    "theme": "dark_slate"
  }
]
```
Render slide assets into high-resolution PNGs:
```bash
veraxi-ymmp broll projects/my_video/broll_manifest.json -o projects/my_video/broll/
```

### Step 3: Run the Unified Pipeline
Make sure the VOICEVOX engine is running on `127.0.0.1:50021`, then compile:

```bash
veraxi-ymmp run projects/my_video/
```

**Common Flags:**
- `--no-tts`: Skip VOICEVOX synthesis and use pre-recorded `.wav` files located in `projects/my_video/audio/`.
- `--no-premiere`: Skip Adobe Premiere Pro XML export.
- `--no-ymmp`: Skip YMM4 `.ymmp` project compilation.
- `--no-qa`: Skip software rendering of `qa_test.mp4`.
- `--qa-duration 15.0`: Render only the first 15 seconds for rapid visual inspection.
- `--no-thumbnail`: Skip automatic thumbnail generation.

**Outputs generated in `projects/my_video/`:**
- `audio/`: Synthesized `.wav` voice tracks with exact phoneme timing.
- `premiere/final_video.xml`: Multi-track sequence ready to import into Adobe Premiere Pro.
- `ymmp/final_video.ymmp`: Fully configured YMM4 project file with lip-sync mouth animations and subtitle plates.
- `qa_test.mp4`: Rendered preview MP4 with speech bubbles and audio ducking.
- `thumbnail.png`: 1080p YouTube thumbnail with 3-split layout and high-contrast outline text.

### Step 4: Final Editorial Polish (Optional)
- **In YMM4:** Double-click `ymmp/final_video.ymmp` to review animations, adjust voice pitch, or export via GPU hardware encoder.
- **In Premiere Pro:** File -> Import -> select `premiere/final_video.xml` to edit transitions, add color grading, or apply custom overlays.

### Step 5: Audio Normalization
Before uploading to YouTube, conform your final audio to YouTube's **-14.0 LUFS** loudness standard:
```bash
veraxi-ymmp normalize projects/my_video/final_video.mp4 -p youtube
```
Produces `projects/my_video/final_video_normalized.mp4`.

---

## MCP Server Integration (LLM Agent Tools)

`veraxi-ymmp` provides an official Model Context Protocol (MCP) server that exposes video generation tools, project management, and Voicevox speech auditioning directly to AI assistants:

```bash
# Start MCP server directly over STDIO
veraxi-ymmp-mcp
```

### Exposed MCP Tools
- `list_projects`: Discover active project folders in `projects/`.
- `load_project`: Read script, broll manifest, and media status for a project.
- `save_project_script`: Validate and persist script and broll entries with self-healing feedback.
- `audition_voice`: Synthesize single-line speech clips for character auditioning.
- `generate_thumbnail_tool`: Produce 3-split 1080p YouTube thumbnails.
- `normalize_project_audio`: Conform audio to EBU R128 (-14.0 LUFS).
- `launch_ymm4_desktop`: Launch the generated project directly in YukkuriMovieMaker4 on Windows.
- `upload_project_to_youtube`: Upload video and metadata directly to YouTube.

---

## YouTube Publishing, Automation & Analytics

`veraxi-ymmp` provides an end-to-end suite for publishing videos, scheduling releases, and correlating retention metrics with script dialogue.

### 1. Initial Google Cloud / OAuth Setup
1. **Google Cloud Console:** Create a new project at [console.cloud.google.com](https://console.cloud.google.com/).
2. **Enable APIs:** Enable both **YouTube Data API v3** and **YouTube Analytics API**.
3. **OAuth Consent Screen:**
   - User Type: **External**
   - Add your Google account under **Test Users**.
   - Set Publishing Status to **In production** (to avoid the 7-day token expiration limit).
4. **Create Credentials:** Create an OAuth client ID of type **Desktop app**, then download `client_secret.json`.
5. **Authenticate Once:**
   ```bash
   veraxi-ymmp youtube auth --client-secrets /path/to/client_secret.json
   ```
   This opens your browser to authorize access, then securely writes your credentials to `~/.veraxi-ymmp/youtube_token.json` with restricted OS permissions (`0600`).

### 2. Verify Channel Connection
Check that your authenticated channel is detected properly:
```bash
veraxi-ymmp youtube channel
```

### 3. Upload & Scheduled Publishing
Upload any video with resumable streaming, automatic retry on rate limits, and thumbnail attachment:

```bash
veraxi-ymmp youtube upload projects/my_video/final_video_normalized.mp4 \
    --title "Clean Architecture 解説【ずんだもん＆四国めたん】" \
    --description "Clean Architectureの基本原則を初心者向けに解説します。" \
    --tags "ずんだもん,VOICEVOX,CleanArchitecture,プログラミング" \
    --privacy private \
    --publish-at "2026-10-30T18:00:00Z" \
    --thumbnail projects/my_video/thumbnail.png
```

You can also run synthesis and upload in a single automated step:
```bash
veraxi-ymmp run projects/my_video/ \
    --upload-to-youtube \
    --normalize \
    --privacy private \
    --publish-at "2026-10-30T18:00:00Z"
```

### 4. Check Upload & Processing Status
Inspect processing status and privacy on YouTube servers:
```bash
veraxi-ymmp youtube status <VIDEO_ID>
```

### 5. Fetch Performance Analytics
Query the YouTube Analytics API v2 directly from your terminal:

```bash
# Terminal table format
veraxi-ymmp youtube stats --video-id <VIDEO_ID>

# Day-by-day time-series export to Excel-ready CSV (UTF-8 BOM)
veraxi-ymmp youtube stats --video-id <VIDEO_ID> --granularity day --format csv --output stats.csv

# Machine-readable JSON output for automated dashboards
veraxi-ymmp youtube stats --video-id <VIDEO_ID> --format json
```
**Metrics tracked:** `views`, `estimatedMinutesWatched`, `averageViewDuration`, `averageViewPercentage`, `likes`, `comments`, `shares`, `subscribersGained`, `subscribersLost`.

### 6. Post-Publish Retention QA (Dialogue Drop-off Correlation)
Correlate your YouTube audience watch curve against your dialogue cuts to see where viewers lose interest:
```bash
veraxi-ymmp youtube qa --video-id <VIDEO_ID> --project projects/my_video/
```
Generates a detailed correlation report in `projects/my_video/qa_reports/` highlighting the exact dialogue lines and timestamps associated with sharp retention drop-offs.

### 7. Thumbnail A/B Testing
Scientifically test multiple thumbnail variants:
```bash
# Initialize A/B experiment
veraxi-ymmp youtube ab start --project projects/my_video/ --video-id <VIDEO_ID>

# Rotate variants or evaluate current winner by CTR
veraxi-ymmp youtube ab rotate --project projects/my_video/ --video-id <VIDEO_ID>
veraxi-ymmp youtube ab evaluate --project projects/my_video/ --video-id <VIDEO_ID>
veraxi-ymmp youtube ab commit --project projects/my_video/ --video-id <VIDEO_ID>
```

### 8. Headless / CI/CD Authentication
For headless servers or GitHub Actions runners where browser login isn't possible:
1. Copy the content of `~/.veraxi-ymmp/youtube_token.json`.
2. Add it as an environment variable or repository secret named `VERAXI_YOUTUBE_AUTHORIZED_USER_JSON`.
3. The adapter discovers this environment variable automatically with zero configuration.

---

## CLI Reference Summary

| Command | Usage | Description |
|---|---|---|
| `veraxi-ymmp serve` | `veraxi-ymmp serve [--port 8000]` | Starts the local API server for the `veraxi Studio` frontend. |
| `veraxi-ymmp run` | `veraxi-ymmp run <project_dir>` | Runs the full end-to-end compilation pipeline. |
| `veraxi-ymmp normalize` | `veraxi-ymmp normalize <video> -p youtube` | Conforms audio loudness to EBU R128 (-14.0 LUFS). |
| `veraxi-ymmp broll` | `veraxi-ymmp broll <manifest> -o <out_dir>` | Generates high-resolution presentation slide graphics. |
| `veraxi-ymmp thumbnail` | `veraxi-ymmp thumbnail <project_dir>` | Generates publication-ready 3-split YouTube thumbnails. |
| `veraxi-ymmp youtube` | `veraxi-ymmp youtube <auth\|upload\|stats\|ab>` | YouTube OAuth, upload, stats analysis, and A/B experiments. |
| `veraxi-ymmp validate` | `veraxi-ymmp validate <script.json>` | Validates script schema and character dialogue constraints. |
| `veraxi-ymmp export-spec`| `veraxi-ymmp export-spec` | Exports schema and prompt templates for LLM consumption. |
| `veraxi-ymmp-mcp` | `veraxi-ymmp-mcp` | Starts the Model Context Protocol (MCP) server over STDIO. |

---

## Development & Testing

```bash
# Install development dependencies
pip install -e ".[dev,mcp,youtube]"

# Run architectural fitness tests
pytest tests/test_architectural_fitness.py -v

# Run full test suite
pytest

# Code quality & privacy scans
ruff check veraxi_ymmp/ tests/ scripts/
mypy veraxi_ymmp
python scripts/check_no_local_paths.py --all
```
