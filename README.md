# veraxi-ymmp

**Multi-target media compiler and visual studio** for YukkuriMovieMaker4 (`.ymmp`), Adobe Premiere Pro (FCPXML), Adobe After Effects (`.jsx`), MoviePy (`.mp4`), SRT captions, Pro Dark Slate B-Roll graphics, and 3-split YouTube thumbnails — with deterministic **epistemic fact-checking**, **Japanese typography/retention linting**, **EBU R128 loudness normalization**, and **Web-AI / MCP workflows**.

> For detailed layer diagrams and dependency rules, see [ARCHITECTURE.md](ARCHITECTURE.md). For step-by-step web-chat copy/paste workflows, see [docs/WEB_CHAT_RUNBOOK.md](docs/WEB_CHAT_RUNBOOK.md).

---

## Quick Navigation

- [Prerequisites & Installation](#prerequisites--installation)
- [Quick Start: 5-Step Video Production](#quick-start-5-step-video-production)
- [Core Features & Compiler Gates](#core-features--compiler-gates)
- [veraxi Studio GUI (Browser-Only Web UI Workflow)](#veraxi-studio-gui-visual-nle--web-ai-bridge)
- [Web-AI Only Workflow (CLI + Web Chat)](#web-ai-only-workflow-no-local-coding-agent--no-api-key-required)
- [Agent Environment Workflow (Antigravity / Claude Code + MCP)](#agent-environment-workflow--mcp-server)
- [Supported Exporters](#supported-exporters)
- [YouTube Publishing, Retention QA & A/B Testing](#youtube-publishing-retention-qa--ab-testing)
- [CLI Reference](#cli-reference)
- [Development & Architectural Fitness](#development--architectural-fitness)

---

## Prerequisites & Installation

### 1. System Requirements
- **Python:** 3.10 – 3.14
- **Node.js & npm:** 18+ (required only for running the `veraxi Studio` frontend)
- **FFmpeg:** Installed and available on `PATH` (required for MoviePy rendering, `ingest-clips`, `qa`, and `normalize`)
- **VOICEVOX Engine (Local):** Running on `http://127.0.0.1:50021` for speech synthesis ([voicevox.hiroshiba.jp](https://voicevox.hiroshiba.jp/))
- **YukkuriMovieMaker4 (Optional):** Windows desktop editor for final `.ymmp` polishing and GPU rendering

### 2. Setup
```bash
git clone https://github.com/kcoaguila-dev/veraxi-ymmp.git
cd veraxi-ymmp
python -m venv venv

# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Linux / macOS
source venv/bin/activate

# Install engine + dev tools + MCP + YouTube support
pip install -e ".[dev,mcp,youtube]"
```

---

## Quick Start: 5-Step Video Production

`veraxi-ymmp` can be driven end-to-end with **no AI API key** (manual JSON or Web-AI copy/paste) or via an AI agent. Every project lives in its own isolated directory under `projects/<slug>/`.

### Step 1: Topic Ideation & Source Dossier (Optional for manual scripts)
Generate a topic dossier and NotebookLM prompt sequence (with optional SEC EDGAR filing lookup):
```bash
veraxi-ymmp ideate "Your Video Topic" --archetype post_mortem
# Optional: --tickers MSFT AMZN  |  -o projects/my_video
```
Place primary sources in `projects/<slug>/sources/` and your NotebookLM Forensic Evidence table in `projects/<slug>/evidence.md`, then verify:
```bash
veraxi-ymmp verify-notebooklm projects/<slug>/
```

### Step 2: Author or Ingest the Script (`script.json`)
Either convert a Markdown dialogue draft + evidence table into `script.json` and `claims.json`:
```bash
veraxi-ymmp ingest-script projects/<slug>/dialogue_raw.md -o projects/<slug>/script.json
```
Or author `projects/<slug>/script.json` directly:
```json
[
  {
    "character": "四国めたん",
    "text": "みんな、今日はクリーンアーキテクチャの核心を解説するわ。",
    "emotion": "normal",
    "motion": "none",
    "bgm": null,
    "sfx": null,
    "image": null
  },
  {
    "character": "ずんだもん",
    "text": "よろしくなのだ！",
    "emotion": "happy",
    "motion": "jump",
    "bgm": null,
    "sfx": null,
    "image": null
  }
]
```
> Default speakers: `四国めたん` (ID 2), `ずんだもん` (ID 3), `春日部つむぎ` (ID 8). See [`veraxi_ymmp/core/constants.py`](veraxi_ymmp/core/constants.py) for speaker registries.

### Step 3: Validate Epistemic Grounding & Retention Pacing
Run fail-closed static analysis before rendering:
```bash
veraxi-ymmp validate projects/<slug>/script.json --audit-facts --audit-pacing
```
This checks schema validity, BudouX typography limits, retention pacing score (`>= 80/100`), and `claims.json` source grounding.

### Step 4: Compile All Targets & Normalize Audio
Ensure VOICEVOX is running on `127.0.0.1:50021`, then run the unified compiler:
```bash
veraxi-ymmp run projects/<slug>/
```
**Useful flags:**
- `--no-tts`: Reuse existing `.wav` files in `projects/<slug>/audio/` instead of calling VOICEVOX
- `--no-premiere` / `--no-ymmp` / `--no-qa` / `--no-thumbnail`: Skip specific export targets
- `--qa-duration 15.0`: Render only the first 15 seconds of `qa_test.mp4` for fast inspection
- `--normalize`: Automatically normalize audio loudness after rendering
- `--upload-to-youtube`: Publish directly after compilation

Or normalize any rendered video separately to YouTube's loudness standard:
```bash
veraxi-ymmp normalize projects/<slug>/qa_test.mp4 -p youtube
```

### Step 5: Autonomous Multimodal QA
Extract narrative milestone keyframes (Cold Open hook, first slide, 3rd speaker entrance, ending) and verify 100% TTS audio coverage:
```bash
veraxi-ymmp qa projects/<slug>/
```
Inspect the generated frames in `projects/<slug>/qa_frames/` and `projects/<slug>/thumbnail.png` before publishing.

---

## Core Features & Compiler Gates

`veraxi-ymmp` is organized as a **3-Tier Compiler DAG** (`Tier 3: app/` -> `Tier 2: epistemic/, editorial/, graphics/, audio/, exporters/` -> `Tier 1: core/`):

- **Epistemic Fact-Checking & Grounding (`epistemic/`):**
  - `pint` dimensional and unit compatibility checks
  - `mecab` morphological lemma & clause-scoped negation verification
  - `pypdf`, HTML, and SEC iXBRL table-scale extraction with SHA-256 primary source provenance (`claims.json` + `sources/manifest.json`)
  - Multi-entity temporal parity via `CanonicalPeriod`
- **Editorial Typography & Retention Linting (`editorial/`):**
  - Google `budoux` Japanese phrase segmentation that protects inline `{Kanji|ruby}` tags (`<= 40` visible chars/cut, `<= 2` lines/bubble)
  - Retention pacing linter targeting `>= 80/100`: zero-greeting cold open, `image: null` in Cuts `0..2`, 50/30/20 cast ratio (`四国めたん` / `ずんだもん` / `春日部つむぎ`) with mid-roll 3rd-speaker entrance (`30%–50%`), and `>= 5%` micro-reaction cuts (`<= 12` chars)
- **Audio, Phonetics & Loudness (`audio/`):**
  - VOICEVOX TTS synthesis with `hatsuon` pitch-accent and reading overrides
  - FFmpeg EBU R128 loudness normalization (`-14.0 LUFS` YouTube, `-13.0 LUFS` TikTok/Instagram, broadcast targets)
- **Pro Dark Slate B-Roll, Infographics & Video Clip Ingest (`graphics/`, `ingest-clips`):**
  - Declarative `broll_manifest.json` slide renderer (`metric`, `vs`, `overview`, `official_data`, `clash`, `domino`, `architecture`, `matrix` layouts) with strict character ceilings
  - 3-split 1080p YouTube thumbnails (`thumbnail.py`) with high-contrast outline text and bottom-right timestamp dead-zone protection
  - `veraxi-ymmp ingest-clips <inbox>` to probe, normalize FPS/resolution, and manifest external video clips into `clip_id` references

---

## veraxi Studio GUI (Visual NLE & Web AI Bridge)

`veraxi Studio` is a browser-based NLE workspace (`#0B0F19` obsidian canvas) with a **Zero-API-Key Web AI Copy-Paste Bridge**:

- **Scene-Grouped Storyboard Editor:** Groups cuts into visual scenes with inline slide thumbnails, BGM/background indicators, and 1-click slide assignment.
- **Real-Time Script Guardrails:** Live character count warnings, 1-click BudouX line splitting, and automatic history snapshots with instant rollback.
- **Instant VOICEVOX Auditioning:** Play individual dialogue lines directly from the storyboard card.
- **Web-AI Copy-Paste Bridge:** Copy the structured AI prompt (`📋 プロンプトのみコピー` / `📋 テーマ付きでコピー`), generate or edit JSON in ChatGPT / Claude / Gemini Web, and paste it back via `📥 JSON貼り付け` with auto-split and self-healing Re-Prompt diagnostics.
- **Integrated Transport & Publishing:** Built-in 16:9 `qa_test.mp4` player, 1-click EBU R128 audio normalization, 3-split thumbnail preview, YouTube upload/scheduling, and 1-click YMM4 / Premiere XML handoff.

### Launching & Step-by-Step Workflow in veraxi Studio
```bash
# Terminal 1: Start the backend API server (default port 8000)
veraxi-ymmp serve

# Terminal 2: Start the frontend dev server (port 1420)
cd frontend
npm install
npm run dev
```
1. **Open `http://localhost:1420`** and select an existing project from the top dropdown (or click `+` to create a new one).
2. **Copy the AI Prompt:** Click `📋 プロンプトのみコピー` (or enter a topic and click `📋 テーマ付きでコピー`) to copy the schema + rules prompt.
3. **Generate or Edit in Web AI:** Paste the prompt (and your existing `script.json` if editing) into ChatGPT, Claude, or Gemini Web.
4. **Paste Back & Auto-Validate:** Click `📥 JSON貼り付け`, paste the returned JSON, and submit. The Studio auto-splits lines `> 40` chars via BudouX, backs up the previous script to history, and surfaces a Re-Prompt block if anything fails validation.
5. **Render & Preview:** Click `⚡動画を生成` in the header, audition individual lines with VOICEVOX, and review `qa_test.mp4` in the 16:9 player.
6. **Normalize, Export & Publish:** Click normalize (`-14.0 LUFS`), then either hand off to **YMM4** / **Premiere Pro** from the header or regenerate the 3-split thumbnail and upload/schedule directly to **YouTube** in the right-hand panel.

---

## Web-AI Only Workflow (No Local Coding Agent / No API Key Required)

You can create, fact-check, edit, and compile complete videos using **only a web chat** (Gemini Web, Claude Web, or ChatGPT) plus this repo's CLI — as detailed in [docs/WEB_CHAT_RUNBOOK.md](docs/WEB_CHAT_RUNBOOK.md).

### A. Create a New Video End-to-End with Web AI Only

1. **Ideate & Extract Evidence in NotebookLM:**
   ```bash
   veraxi-ymmp ideate "Your Video Topic" --archetype post_mortem
   ```
   Open `projects/<slug>/notebooklm_dossier.md`, upload your primary source filings/documents to **Gemini NotebookLM**, run Turns 1–4, and save the Turn 4 Forensic Evidence table as `projects/<slug>/evidence.md`.

2. **Generate Script & B-Roll JSON in Web Chat:**
   ```bash
   veraxi-ymmp ingest-script projects/<slug>/evidence.md --provider manual
   ```
   This writes `projects/<slug>/script_prompt.md` and waits for your paste. Copy `script_prompt.md` into your Web AI, then paste the returned JSON (`{"script": [...], "broll_manifest": [...], "thumbnail_config": {...}}`) back into the terminal ending with `---END---`. The CLI validates schema, `<= 38`-char cuts, ruby/ASCII rules, cognitive load, `>= 80` retention pacing, and scale parity before writing `script.json`, `broll_manifest.json`, `thumbnail_config.json`, and `claims.json`.

3. **Post-Script Fact-Check in NotebookLM:**
   ```bash
   veraxi-ymmp verify-notebooklm projects/<slug>/ --interactive
   ```
   Copy `projects/<slug>/notebooklm_audit_prompt.md` into your NotebookLM notebook, paste the 7-column audit table back ending with `---END---`. All `SUPPORTED` quotes and SHA-256 provenance are reconciled into `claims.json`; any `DRIFTED`/`REFUTED` item prints a targeted `LLM RE-PROMPT BLOCK`.

4. **Validate, Render & Run Multimodal QA:**
   ```bash
   veraxi-ymmp validate projects/<slug>/script.json --audit-facts --audit-pacing
   veraxi-ymmp run projects/<slug>/ --render-video --normalize-loudness
   veraxi-ymmp qa projects/<slug>/
   ```

5. **(Optional) Ingest External AI Video Clips:**
   If you generated video clips in a web app, have the web chat output a `clip-manifest.json` mapping each `clip_id` to the downloaded filename, then run:
   ```bash
   veraxi-ymmp ingest-clips downloads/ --from-manifest clip-manifest.json
   ```

6. **Publish to YouTube (Optional):**
   ```bash
   veraxi-ymmp youtube upload projects/<slug>/qa_test_normalized.mp4 \
     --title "Video Title" --privacy private --thumbnail projects/<slug>/thumbnail.png
   ```

### B. Edit an Existing Video's Dialogue or Slides with Web AI Only

For surgical edits to an existing project (`script.json`, `broll_manifest.json`, `thumbnail_config.json`):

1. **Pack a bundle in `edit` mode:**
   ```bash
   veraxi-ymmp pack --mode edit \
     --task "Modify cuts 10..15 in projects/<slug>/script.json to ..." \
     --files projects/<slug>/script.json projects/<slug>/broll_manifest.json projects/<slug>/evidence.md \
     -o bundle.md
   ```
   When project files are included, `pack` automatically embeds `AGENTS_WEB.md` and the fail-closed **Video Project Editing Rules** (schema, enums, `<= 40` chars/cut, zero raw ASCII in `text`, retention pacing, and epistemic number grounding).
2. **Paste `bundle.md` into your Web AI** and save the `SEARCH/REPLACE` reply to `reply-edit.md`.
3. **Apply atomically & re-compile:**
   ```bash
   veraxi-ymmp apply-edit reply-edit.md --in-place
   veraxi-ymmp run projects/<slug>/ --render-video --normalize-loudness
   veraxi-ymmp qa projects/<slug>/
   ```
   `apply-edit` verifies every `SEARCH` block matches uniquely, enforces schema/typography/pacing/asset gates, re-anchors `claims.json`, and runs `audit_project_facts` before touching disk.

### Worked Example: Complete Web-AI Only Run (`projects/my_topic_2026/`)

```bash
# 1. Create project dossier & NotebookLM prompts
veraxi-ymmp ideate "AI Cloud Pricing 2026" --archetype post_mortem -o projects/my_topic_2026
# -> Upload sources to NotebookLM, run Turns 1-4 from projects/my_topic_2026/notebooklm_dossier.md,
#    and save the Turn 4 table as projects/my_topic_2026/evidence.md

# 2. Generate script + B-roll JSON in Web AI (Gemini / Claude / ChatGPT)
veraxi-ymmp ingest-script projects/my_topic_2026/evidence.md --provider manual
# -> Copy projects/my_topic_2026/script_prompt.md into Web AI, paste JSON reply back, type ---END---

# 3. Fact-check every claim in NotebookLM
veraxi-ymmp verify-notebooklm projects/my_topic_2026/ --interactive
# -> Copy projects/my_topic_2026/notebooklm_audit_prompt.md into NotebookLM, paste 7-col table, type ---END---

# 4. Validate, render MP4/YMM4/Premiere/thumbnail, and run QA
veraxi-ymmp validate projects/my_topic_2026/script.json --audit-facts --audit-pacing
veraxi-ymmp run projects/my_topic_2026/ --render-video --normalize-loudness
veraxi-ymmp qa projects/my_topic_2026/

# 5. (Later) Modify dialogue in cuts 0-3 using Web AI only
veraxi-ymmp pack --mode edit \
  --task "Sharpen the cold open hook in cuts 0-3 while keeping all numbers grounded in evidence.md" \
  --files projects/my_topic_2026/script.json projects/my_topic_2026/broll_manifest.json projects/my_topic_2026/evidence.md \
  -o edit-bundle.md
# -> Paste edit-bundle.md into Web AI, save SEARCH/REPLACE reply as reply-edit.md
veraxi-ymmp apply-edit reply-edit.md --in-place
veraxi-ymmp run projects/my_topic_2026/ --render-video --normalize-loudness
veraxi-ymmp qa projects/my_topic_2026/
```

### C. Code Development with Web AI Only (`session-start` / `pack` / `apply`)

- Run `veraxi-ymmp session-start > session-start.txt` and paste it as the first message of a new web chat to orient the model.
- Use `veraxi-ymmp pack --task "..." --files <paths> -o bundle.md` + `veraxi-ymmp apply reply.md --manifest bundle.md.manifest.json` for full-file replacements (guarded by manifest allowlist, stale-base hash checks, elision detection, and shrink protection).
- Use `pack --mode edit` + `apply-edit reply-edit.md` for large files; changes land on a fresh git branch and run `ruff` / `mypy` / targeted `pytest`.

---

## Supported Exporters

| Target Format | Implementation | Description |
|---|---|---|
| **YMM4 Project (`.ymmp`)** | [`YMMPRenderer`](veraxi_ymmp/exporters/ymmp_renderer.py) | Clones template timeline items, embeds Brotli-compressed voice caches, and configures phonetic mouth animations. |
| **Premiere Pro (`.xml`)** | [`PremiereExporter`](veraxi_ymmp/exporters/premiere_exporter.py) | Generates Final Cut Pro XML (`xmeml`) with 4 video tracks (BG, Tachie, B-Roll, Subtitle speech bubbles) and 3 audio tracks. |
| **MoviePy Preview (`.mp4`)** | [`MoviePyRenderer`](veraxi_ymmp/exporters/moviepy_renderer.py) | Software renderer producing 1080p preview videos with speech bubbles and audio ducking for CI/CD and QA. |
| **After Effects (`.jsx`)** | [`AfterEffectsRenderer`](veraxi_ymmp/exporters/ae_renderer.py) | Generates ExtendScript automation files with slider-driven lip-sync and character bounce effects. |
| **SRT Subtitles (`.srt`)** | [`generate_srt`](veraxi_ymmp/exporters/srt_generator.py) | Generates standard SRT subtitle files with millisecond precision. |
| **YouTube Thumbnail (`.png`)** | [`ThumbnailGenerator`](veraxi_ymmp/graphics/thumbnail.py) | 1920x1080 thumbnails using 3-split layout, outline typography, and timestamp dead-zone protection. |

---

## Agent Environment Workflow & MCP Server

When running inside an AI coding agent environment (such as **Antigravity** or **Claude Code**), [AGENTS.md](AGENTS.md) and the workspace skills in `.agents/skills/` (`editorial-dossier`, `script-hygiene`, `ymmp-qa`, `teamwork-orchestrator`) govern the **end-to-end 5-step Golden Path**:

1. **Topic Ideation & NotebookLM HITL Gate:** The agent runs `veraxi-ymmp ideate "<Topic>" --archetype post_mortem` to scaffold `projects/<slug>/` (`notebooklm_dossier.md` + optional SEC filings in `sources/`). You upload the primary sources to NotebookLM, run the dossier turns, and provide the resulting Forensic Evidence table (`evidence.md`).
2. **Script Authoring & Ingestion:** Following `script-hygiene`, the agent authors `dialogue_raw.md` grounded strictly in `evidence.md` and compiles `script.json` + `claims.json` via `veraxi-ymmp ingest-script`.
3. **Fail-Closed Validation:** The agent runs `veraxi-ymmp validate projects/<slug>/script.json --audit-facts --audit-pacing` (0 unsupported claims, `>= 80/100` retention score) and `pytest tests/test_architectural_fitness.py -q` if code changed.
4. **Multi-Target Compilation & Normalization:** The agent runs `veraxi-ymmp run projects/<slug>/` and `veraxi-ymmp normalize <video.mp4> -p youtube` to produce `.ymmp`, Premiere `.xml`, `qa_test.mp4`, and `thumbnail.png`.
5. **Multimodal Visual QA (Required Before Hand-Off):** The agent runs `veraxi-ymmp qa projects/<slug>/`, visually inspects the extracted milestone keyframes in `qa_frames/` and `thumbnail.png` (checking 100% TTS coverage, subtitle plates, and zero AI-slop brackets), and only then hands off or uploads via `veraxi-ymmp youtube upload`.

### MCP Server (`veraxi-ymmp-mcp`)

`veraxi-ymmp` includes a Model Context Protocol (MCP) server exposing project management, validation, TTS auditioning, thumbnail generation, and YouTube tools over STDIO:

```bash
veraxi-ymmp-mcp
```

**Exposed MCP Tools:** `list_projects`, `load_project`, `save_project_script`, `audition_voice`, `generate_thumbnail_tool`, `normalize_project_audio`, `launch_ymm4_desktop`, and `upload_project_to_youtube`.

---

## YouTube Publishing, Retention QA & A/B Testing

### 1. OAuth Setup (One-Time)
1. Enable **YouTube Data API v3** and **YouTube Analytics API** in [Google Cloud Console](https://console.cloud.google.com/).
2. Create an OAuth **Desktop app** client and download `client_secret.json`.
3. Authenticate once (stores credentials in `~/.veraxi-ymmp/youtube_token.json` with `0600` permissions; for CI/CD, set `VERAXI_YOUTUBE_AUTHORIZED_USER_JSON`):
   ```bash
   veraxi-ymmp youtube auth --client-secrets /path/to/client_secret.json
   veraxi-ymmp youtube channel
   ```

### 2. Upload, Status & Analytics
```bash
# Resumable upload with scheduling and thumbnail
veraxi-ymmp youtube upload projects/<slug>/qa_test_normalized.mp4 \
    --title "Video Title" \
    --description "Video description" \
    --tags "ずんだもん,VOICEVOX" \
    --privacy private \
    --publish-at "2026-11-30T18:00:00Z" \
    --thumbnail projects/<slug>/thumbnail.png

# Check processing status & query analytics
veraxi-ymmp youtube status <VIDEO_ID>
veraxi-ymmp youtube stats --video-id <VIDEO_ID> --granularity day --format csv --output stats.csv
```

### 3. Post-Publish Retention QA & Thumbnail A/B Testing
```bash
# Correlate YouTube retention drop-offs with dialogue cuts -> projects/<slug>/qa_reports/
veraxi-ymmp youtube qa --video-id <VIDEO_ID> --project projects/<slug>/

# Run thumbnail A/B experiments
veraxi-ymmp youtube ab start --project projects/<slug>/ --video-id <VIDEO_ID>
veraxi-ymmp youtube ab rotate --project projects/<slug>/ --video-id <VIDEO_ID>
veraxi-ymmp youtube ab evaluate --project projects/<slug>/ --video-id <VIDEO_ID>
veraxi-ymmp youtube ab commit --project projects/<slug>/ --video-id <VIDEO_ID>
```

---

## CLI Reference

| Command | Usage | Description |
|---|---|---|
| `veraxi-ymmp ideate` | `veraxi-ymmp ideate "<topic>" [--archetype post_mortem]` | Generates topic dossier and NotebookLM pre-production manifest. |
| `veraxi-ymmp verify-notebooklm` | `veraxi-ymmp verify-notebooklm <project_dir>` | Verifies NotebookLM evidence extraction against source files. |
| `veraxi-ymmp ingest-script` | `veraxi-ymmp ingest-script <raw.md> -o <script.json>` | Parses dialogue Markdown and evidence tables into `script.json` + `claims.json`. |
| `veraxi-ymmp validate` | `veraxi-ymmp validate <script.json> [--audit-facts] [--audit-pacing]` | Validates schema, typography, epistemic claims, and retention pacing. |
| `veraxi-ymmp broll` | `veraxi-ymmp broll <manifest.json> -o <out_dir>` | Renders Pro Dark Slate B-Roll slide PNGs. |
| `veraxi-ymmp ingest-clips` | `veraxi-ymmp ingest-clips <inbox> [-o <clips_dir>]` | Probes, normalizes, and manifests external video clips. |
| `veraxi-ymmp thumbnail` | `veraxi-ymmp thumbnail <project_dir>` | Generates 3-split 1080p YouTube thumbnails. |
| `veraxi-ymmp run` | `veraxi-ymmp run <project_dir>` | Runs the full TTS, IR, YMM4, Premiere, MoviePy, and thumbnail pipeline. |
| `veraxi-ymmp render` | `veraxi-ymmp render <project_dir>` | Renders production master video headlessly from a project directory. |
| `veraxi-ymmp normalize` | `veraxi-ymmp normalize <video> -p youtube` | Conforms audio loudness to EBU R128 platform targets. |
| `veraxi-ymmp qa` | `veraxi-ymmp qa <project_dir>` | Checks TTS audio coverage and extracts milestone keyframes for QA. |
| `veraxi-ymmp serve` | `veraxi-ymmp serve [--port 8000]` | Starts the local API server for `veraxi Studio`. |
| `veraxi-ymmp session-start` | `veraxi-ymmp session-start > session-start.txt` | Generates a session-anchoring context bundle for web-chat AI coding. |
| `veraxi-ymmp pack` | `veraxi-ymmp pack --task "..." --files <paths> [--mode edit]` | Emits a single markdown bundle for web-chat AI editing. |
| `veraxi-ymmp apply` | `veraxi-ymmp apply <reply.md> --manifest <manifest.json>` | Applies full-file web-chat replies with safety guards. |
| `veraxi-ymmp apply-edit` | `veraxi-ymmp apply-edit <reply.md>` | Applies anchored `SEARCH/REPLACE` web-chat edit blocks atomically. |
| `veraxi-ymmp youtube` | `veraxi-ymmp youtube <auth\|channel\|upload\|status\|stats\|qa\|ab>` | YouTube OAuth, upload, analytics, retention QA, and A/B testing. |
| `veraxi-ymmp export-spec` | `veraxi-ymmp export-spec` | Exports schema and prompt templates for LLM consumption. |
| `veraxi-ymmp capture` / `capture-sec` | `veraxi-ymmp capture ...` | Screen and SEC filing capture utilities. |
| `veraxi-ymmp-mcp` | `veraxi-ymmp-mcp` | Starts the MCP server over STDIO. |

---

## Development & Architectural Fitness

```bash
# Run architectural fitness tests (DAG purity, adapter isolation, <= 900-line ceiling)
pytest tests/test_architectural_fitness.py -q

# Run full test suite
pytest -q

# Linters, type checks, and privacy/local-path scanner
ruff check veraxi_ymmp/ tests/ scripts/
mypy veraxi_ymmp
python scripts/check_no_local_paths.py --all
```
