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
- **Hygiene Guardrails:**
  - Hard limit: Maximum 2 lines per speech bubble.
  - Character ceiling: $\le 35\text{--}40$ characters per dialogue cut.
  - Natural interjections: NEVER begin with bare `「ええ、」`. Use character-specific affirmations (`「はい、」`, `「その通りですわ、」`, `「まさにその通りなのだ！」`).

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
  - Verifies audio existence in `artifacts/audio/`.
  - Inspects `qa_test.mp4` for character layout, concentric subtitle alignment, and color theme consistency following `.agents/skills/ymmp-qa/SKILL.md`.

---

## 3. Operational Command Reference

- **Run full project pipeline:** `veraxi-ymmp run projects/<project_name>/`
- **Architectural Fitness Check:** `pytest tests/test_architectural_fitness.py`
- **Privacy Check:** `python scripts/check_no_local_paths.py`
- **Loudness Normalization:** `veraxi-ymmp normalize <video.mp4> -p youtube`
