# Veraxi YMMP: Senior Architect Governance & Compiler Blueprint

Welcome to `veraxi-ymmp`. This document governs agent behavior, **3-Tier Compiler Pipeline + Hexagonal Targets** architectural invariants, epistemic anti-slop gates, and multi-agent coordination patterns (`/teamwork-preview`).

---

## 1. Architectural Invariants (Non-Negotiable)

`veraxi-ymmp` is structured as a **Multi-Target Media Compiler with Static Analysis Gates** (modeled after Pandoc / LLVM / Manim), not a flat script dump or CRUD boilerplate. Any agent or subagent modifying this codebase must adhere to the invariants verified by `tests/test_architectural_fitness.py`:

### 1.1 The 3-Tier Compiler DAG & Bounded Subpackages
Dependencies flow strictly downwards (`Tier 3 -> Tier 2 -> Tier 1`):

```text
veraxi_ymmp/
├── core/        [Tier 1] Pure AST, TimelineIR, Script, Staging, Ports & Primitives (0 outer deps)
├── epistemic/   [Tier 2] Fact-Checking, Pint Units, MeCab NLP, PDF/iXBRL/Web Source Grounding
├── editorial/   [Tier 2] Pre-Production, BudouX Ingestion, Pacing & 50/30/20 Retention Linting
├── graphics/    [Tier 2] Pro Dark Slate B-Roll, Infographics, 3-Split Thumbnails, PSD & Typography
├── audio/       [Tier 2] VoiceVox TTS, Hatsuon Pitch Accent, Phonetics, EBU R128 (-16 LUFS) & SFX
├── exporters/   [Tier 2] Hexagonal Targets: YMM4 (.ymmp), Premiere (.xml), MoviePy (.mp4), AE, SRT, YouTube
└── app/         [Tier 3] Orchestration Pipeline, Compiler, CLI, FastAPI Studio & MCP Server
```

1. **Tier 1 Purity (`core/`):** Modules in `core/` (`ir.py`, `script.py`, `staging.py`, `template.py`, `ports.py`, `constants.py`, `config.py`, `logging.py`, `utils.py`) must have **zero dependencies** on Tier 2 or Tier 3.
2. **Tier 2 Pass & Adapter Isolation:**
   - Tier 2 packages (`epistemic/`, `editorial/`, `graphics/`, `audio/`, `exporters/`) must **never import from Tier 3 (`app/`)**.
   - Target exporters inside `exporters/` (`ymmp_renderer.py`, `premiere_exporter.py`, `moviepy_renderer.py`, `ae_renderer.py`, `srt_generator.py`) must **never import from peer exporters**.
3. **Anti-Fragmentation & Module Size Window (100–900 Lines):**
   - **Hard Ceiling:** No Python file in `veraxi_ymmp/` may exceed **900 lines**.
   - **Anti-Splinter Rule:** Never dump single-purpose micro-files (`<100` lines) at the package root to dodge the 900-line ceiling. Cohesive helpers belong inside their bounded subpackage module.
4. **Epistemic & Retention Compiler Gates (Fail-Closed):**
   - No project may compile without passing deterministic static analysis:
     - **Epistemic Gate (`epistemic/`):** `pint` dimensional/unit compatibility, `mecab` morphological lemma & clause-scoped negation verification, `pypdf` / DOM-scoped table scale extraction, and SHA-256 primary source provenance.
     - **Editorial & Typography Gate (`editorial/`):** Google `budoux` Japanese phrase segmentation (protecting `{Kanji|ruby}` tags, $\le 38$ chars/cut, $\le 2$ lines/bubble) and $\ge 80/100$ Retention Score.
5. **Privacy & Security:** Zero hardcoded local machine paths or developer usernames (`scripts/check_no_local_paths.py`). Zero committed API keys or secrets.
6. **Temporal Invariant & Recency Grounding:**
   - **Current Operational Year:** **2026** (Local Anchor: November 2026).
   - **Strict Recency Mandate:** When authoring scripts, claims, and financial sources, default strictly to the latest available filings aligned via `CanonicalPeriod` (e.g. for calendar 2026-Q3: MSFT Q1 FY2027 10-Q [ended Sept 30, 2026], AMZN Q3 2026 10-Q [ended Sept 30, 2026]). Multi-entity comparisons must maintain temporal parity (`assert_temporal_parity()`).
   - **Negative Rule:** Never treat 2023, 2024, or 2025 as the "current year" out of pretraining memory. Any citation older than trailing 12 months requires explicit historical framing.

---

## 2. Multi-Agent Teamwork Topology (`/teamwork-preview`)

When executing complex tasks via `/teamwork-preview`, the orchestrator structures the subagent squad into five decoupled roles aligned with the compiler subpackages:

```
                     ┌──────────────────────────────────┐
                     │   Lead Orchestrator / Architect  │
                     │          (Tier 3: app/)          │
                     └─────────────────┬────────────────┘
            ┌──────────────────────────┼──────────────────────────┐
            ▼                          ▼                          ▼
┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│ Editorial & Epistemic│   │   Graphics Designer  │   │  Audio & Exporters   │
│(editorial/epistemic/)│   │     (graphics/)      │   │ (audio/ & exporters/)│
└───────────┬──────────┘   └───────────┬──────────┘   └───────────┬──────────┘
            └──────────────────────────┼──────────────────────────┘
                                       ▼
                         ┌──────────────────────────┐
                         │    QA & Fitness Sentinel │
                         │ (Fitness + Fact + Video) │
                         └──────────────────────────┘
```

### Role Specializations & Package Ownership

#### 1. Lead Orchestrator / Architect (`app/`)
- **Scope:** Conducts user interview, defines package boundaries, generates the Team Sheet artifact, and gates milestones.
- **Rules:** Ensures subagents operate in isolated subpackages and never create loose root files.

#### 2. Editorial & Epistemic Specialist (`editorial/` & `epistemic/`)
- **Scope:** Authors primary-source-grounded dialogue (`WriterScriptEntry` / `DirectorScriptEntry`) and links verifiable evidence (`claims.json` + `sources/manifest.json`).
- **Hygiene, Epistemic & Retention Rules:**
  - Must strictly follow `.agents/skills/script-hygiene/SKILL.md` and `.agents/skills/editorial-dossier/SKILL.md`.
  - **Epistemic Grounding:** Every salient quantitative figure (scales, percentages, multipliers, physical/computing/medical units) in Cold Open cuts (`0..10`), B-roll slides, thumbnail, and metadata must map to a `Verdict.SUPPORTED` claim backed by verbatim primary source quotes (`pypdf`, HTML/iXBRL, or Markdown).
  - **BudouX & Typography:** Maximum 2 lines per speech bubble, $\le 35\text{--}40$ characters per cut segmented via `budoux` without splitting inline `{Kanji|ruby}` tags.
  - **Retention Architecture:** Zero-greeting cold open (0.0s In Media Res), character confrontation in Cuts 0–2 (`image: null`), slides enter Cut 3+. 50/30/20 cast ratio (Metan / Zundamon / Tsumugi), hook protection (no Tsumugi in Cuts 0–2), mid-roll entrance (30%–50%), $\ge 5\text{--}10\%$ micro-reaction cuts ($\le 12$ chars), zero-drop ending.

#### 3. Creative & Graphics Designer (`graphics/`)
- **Scope:** Generates B-roll slides, infographics, citation cards, and YouTube thumbnails (`broll.py`, `infographic.py`, `thumbnail.py`).
- **Slide & Thumbnail Guardrails:**
  - Pro Dark Slate Theme (`#0F172A` / `#1E293B`).
  - 1-Slide-1-Impact: Total characters across slide $\le 100$. Maximum 6 text elements. Zero nested bullets.
  - Visual Parity: Every number on a slide or thumbnail must match a `Verdict.SUPPORTED` claim in `claims.json`.
  - 3-Split Thumbnail Rule: Hero character cutout, high-contrast headline, bottom-right timestamp dead-zone protected.

#### 4. Audio & Exporters Engineer (`audio/` & `exporters/`)
- **Scope:** Synthesizes VoiceVox audio WAVs with `hatsuon` pitch/reading overrides, compiles `TimelineIR`, and renders target exports.
- **Outputs:** YMM4 (`.ymmp`), Premiere Pro (`.xml`), After Effects (`.jsx`), MoviePy preview (`qa_test.mp4`), SRT captions (`.srt`), and `-16 LUFS` EBU R128 loudness normalization (`audio_normalizer.py`).

#### 5. QA & Fitness Sentinel (`tests/`)
- **Scope:** Audits architectural fitness, epistemic grounding, retention pacing, and multimodal video output before delivery.
- **Checklist:**
  - Executes `pytest tests/test_architectural_fitness.py -q` (all DAG, adapter isolation, mypy, and privacy checks must pass).
  - Executes `veraxi-ymmp validate <script.json> --audit-facts --audit-pacing` (Epistemic Audit must pass with 0 unsupported claims; Retention Score $\ge 80/100$).
  - Verifies `.wav` existence in `artifacts/audio/` and inspects `qa_test.mp4` following `.agents/skills/ymmp-qa/SKILL.md`.

---

## 3. Operational Command Reference (The 5-Step Golden Path)

Every video project MUST be executed continuously through all 5 steps without halting before completion:

1. **Topic Ideation & NotebookLM Dossier:**
   `veraxi-ymmp ideate "<Topic>" --archetype post_mortem`
   - *Step 1.5 NotebookLM Human-in-the-Loop (HITL) Gate:* The user uploads primary source filings/prospectuses into NotebookLM, executes the multi-turn prompt sequence, and inputs the resulting Forensic Evidence Extraction Matrix table into the conversation or `evidence.md`.
   - *Project Source Isolation Invariant:* Every project under `projects/<slug>/` MUST be strictly isolated. Primary sources in `sources/` and evidence tables must exclusively belong to the active project. Never leak or copy stale or unrelated documents from prior projects.
   - *Runtime Scalability:* Supports standard short formats (~50-80 cuts, 3-5 min) as well as long-form deep-dive formats (~180-220 cuts, 8-12 min) with proportional 50/30/20 cast balance and multiple retention checkpoints.
2. **Evidence Table Ingestion & Antigravity Scripting (`script-hygiene` $\rightarrow$ `script.json` & `claims.json`):**
   `veraxi-ymmp ingest-script projects/<slug>/dialogue_raw.md -o projects/<slug>/script.json`
3. **Epistemic Fact Audit & Retention Pacing Gate:**
   `veraxi-ymmp validate projects/<slug>/script.json --audit-facts --audit-pacing`
4. **Full Multi-Target Compilation & Loudness Normalization:**
   `veraxi-ymmp run projects/<slug>/`
   `veraxi-ymmp normalize <video.mp4> -p youtube`
5. **Autonomous Multimodal QA & Visual Inspection Gate (Fail-Closed Delivery Invariant):**
   `veraxi-ymmp qa projects/<slug>/`
   - Use `read_file` to visually audit all extracted narrative milestone keyframes in `qa_frames/` (Cold Open hook, First Slide, 3rd speaker entrance, and Ending) and `thumbnail.png`.
   - Verify: 100% TTS audio coverage, 0 truncated cast entrances, concentric subtitle plates, speaker color theming, and 0 bracket/AI-slop cliches (`【...】`).
   - **Hand-off Prohibition**: Never present completion or deliver final deliverables to the user until Step 5 is executed and visually verified in the same continuous turn sequence.

- **Architectural Fitness Check:** `pytest tests/test_architectural_fitness.py -q`
- **Privacy & Secret Scan:** `python scripts/check_no_local_paths.py`

---

## 4. Token Optimization & Structural Inspection Protocol

To prevent context window bloat and unnecessary token consumption:
1. **Probe Before Reading (Goal over Tool):**
   - Locate the target symbol or line number first; read only the target slice (`start_line`/`end_line`).
   - Never read files >150 lines in full.
   - Probing hierarchy:
     - Tier 1: Symbol index (`ctags -x --kinds-python=fm <file>`)
     - Tier 2: Search (`rg -n -C 2 'pattern' <path>` or PowerShell `Select-String`)
     - Tier 3: AST query (`ast-grep run -l python -p 'class $CLASS' <file>`)
2. **Terminal Output Discipline:**
   - Always run tests and linters with quiet flags (`pytest -q`).
   - Tail failure logs (`| Select-Object -Last 10`). Never dump raw JSON timelines or build logs.
   - Use `git status -s` and `git diff --stat` instead of full diffs.
3. **Execution Hygiene:**
   - Run targeted test files first, and the full suite only at final handoff.
   - Batch independent reads, searches, and commands in a single turn.
   - Do not re-run checks whose inputs have not changed.
