# Veraxi YMMP: Agent Workspace Guidelines & Teamwork Blueprint

Welcome to `veraxi-ymmp`. This document governs agent behavior, Clean Architecture invariants, and multi-agent coordination patterns (`/teamwork-preview`).

---

## 1. Architectural Invariants (Non-Negotiable)

Any agent or subagent modifying this codebase must adhere to the Clean Architecture rules verified by `tests/test_architectural_fitness.py`:

1. **Dependency Inversion:** Dependencies flow strictly inwards:
   - `Domain` (`ir.py`, `script.py`, `constants.py`) has **zero dependencies** on outer layers.
   - `Ports` (`ports.py`) defines abstract protocols (`TimelineExporter`, `TTSBackend`).
   - `Application` (`pipeline.py`, `compiler.py`, `ir_builder.py`) coordinates domain models and ports.
   - `Infrastructure Adapters` (`ymmp_renderer.py`, `premiere_exporter.py`, `moviepy_renderer.py`, etc.) implement ports.
2. **Adapter Isolation:** Infrastructure adapters must **never import from peer adapters** directly.
3. **Module Size Ceiling:** No Python file in `veraxi_ymmp/` may exceed 900 lines.
4. **Privacy & Security:** Zero hardcoded local machine paths or developer usernames (`scripts/check_no_local_paths.py`). Zero committed API keys or secrets.

---

## 2. Multi-Agent Teamwork Topology (`/teamwork-preview`)

When executing complex tasks via `/teamwork-preview`, the orchestrator must structure the subagent squad into five decoupled roles:

```
                  ┌───────────────────────────────┐
                  │  Lead Orchestrator / Director │
                  └───────────────┬───────────────┘
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ Script & Staging │    │ Creative Designer│    │ Audio & Compiler │
│  (Dialogue/Cues) │    │ (B-Roll / Thumb) │    │ (VoiceVox / IR)  │
└────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
         └────────────────────────┼────────────────────────┘
                                  ▼
                     ┌──────────────────────────┐
                     │    QA / Test Sentinel    │
                     │ (Runs ymmp-qa & fitness) │
                     └──────────────────────────┘
```

### Role Specializations

#### 1. Lead Orchestrator
- **Scope:** Conducts user interview, defines boundaries, generates the Team Sheet artifact, and gates milestones.
- **Rules:** Ensures tasks are modular and subagents do not overwrite each other's outputs.

#### 2. Script & Staging Specialist
- **Scope:** Creates factual dialogue (`WriterScriptEntry`) and staging metadata (`DirectorScriptEntry`).
- **Hygiene & Retention Rules:**
  - Must strictly follow `.agents/skills/script-hygiene/SKILL.md` for all dialogue authoring.
  - Hard limit: Maximum 2 lines per speech bubble, $\le 35\text{--}40$ characters per cut.
  - Zero-greeting cold open (0.0s In Media Res), character emotional confrontation in Cuts 0–2 (`image: null`), slides enter Cut 3+.
  - The 3 Archetypes: Zundamon (viewer's chaotic greedy proxy), Metan (cold sadistic realist, $\le 35\%$ agreement), Tsumugi (server-room whistleblower).
  - 50/30/20 Retention ratio, hook protection (no Tsumugi in first 3 cuts), mid-roll entrance (30%–50% mark).
  - Ping-pong syncopation: $\ge 5\text{--}10\%$ micro-reaction cuts ($\le 12$ chars). Zero-drop ending (no formulaic goodbyes).
  - Clean audio & grounded staging: `"motion": "none"` or `"nod"` (no `"jump"`), clean ducked instrumental BGM, zero slapstick SFX.

#### 3. Creative & Asset Designer
- **Scope:** Generates B-roll slides and YouTube thumbnails using `veraxi_ymmp.broll` and `veraxi_ymmp.thumbnail`.
- **Slide Guardrails:**
  - Pro Dark Slate Theme (`#0F172A` / `#1E293B`).
  - 1-Slide-1-Impact: Total characters across slide $\le 100$. Maximum 6 text elements. Zero nested bullets.
  - 3-Split Thumbnail Rule: Hero character, high-contrast headline, timestamp dead-zone protected.

#### 4. Audio & Pipeline Engineer
- **Scope:** Generates VoiceVox audio WAVs, compiles `TimelineIR`, and renders target exports.
- **Outputs:** YMM4 (`.ymmp`), Premiere Pro (`.xml`), MoviePy preview (`qa_test.mp4`), and EBU R128 loudness normalization (`audio_normalizer.py`).

#### 5. QA & Fitness Sentinel
- **Scope:** Audits outputs before user delivery.
- **Checklist:**
  - Executes `pytest tests/test_architectural_fitness.py` (all tests must pass).
  - Executes `veraxi-ymmp validate <script.json> --audit-pacing` (Retention Score must be $\ge 80/100$).
  - Verifies audio existence in `artifacts/audio/`.
  - Inspects `qa_test.mp4` for character layout, concentric subtitle alignment, and color theme consistency following `.agents/skills/ymmp-qa/SKILL.md`.

---

## 3. Operational Command Reference

- **Run full project pipeline:** `veraxi-ymmp run projects/<project_name>/`
- **Architectural Fitness Check:** `pytest tests/test_architectural_fitness.py`
- **Privacy Check:** `python scripts/check_no_local_paths.py`
- **Audience Retention Audit:** `veraxi-ymmp validate <script.json> --audit-pacing`
- **Loudness Normalization:** `veraxi-ymmp normalize <video.mp4> -p youtube`

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
