---
name: teamwork-orchestrator
description: >-
  Use this skill whenever launching or participating in multi-agent workflows, `/teamwork-preview` sessions, or complex video production runs in veraxi-ymmp. It outlines the squad roles, execution protocol, and handoff criteria.
---

# Teamwork Orchestrator Skill

This skill defines the multi-agent orchestration protocol for `veraxi-ymmp` tasks invoked via `/teamwork-preview` or subagent delegation.

## When to Activate

- Full end-to-end video generation projects (script $\to$ audio $\to$ assets $\to$ exports $\to$ QA).
- Core architectural refactoring or adding new target platform exporters (e.g., DaVinci Resolve, Final Cut Pro).
- Batch generation campaigns (producing multiple Shorts or episodes concurrently).

---

## 5-Phase Execution Protocol

### Phase 1: Interactive Scoping & Blueprinting
The Lead Orchestrator must not jump straight to generating code or assets.
1. Interview the user for target topic, target duration, persona styles, and export targets.
2. Produce a **Team Sheet Blueprint** defining:
   - Target output directory (`projects/<name>/`).
   - Assigned subagent roles and non-overlapping workspace boundaries.
   - Measurable acceptance criteria.

### Phase 2: Scripting & Staging
Subagent: **Script Specialist**
1. Draft factual content into `WriterScript`.
2. Enrich with staging metadata in `DirectorScript` (motions, emotions, B-roll triggers).
3. Validate typography constraints:
   - Max 2 lines per speech bubble.
   - Max 35–40 characters per cut.
   - Natural interjections (e.g., `「はい、」`, `「その通りですわ、」`).

### Phase 3: Asset Creation & Sound Design
Subagents: **Creative Designer** & **Pipeline Engineer** (Parallel Execution)
- **Creative Designer**: Generates B-roll slides (`veraxi_ymmp.broll`, Pro Dark Slate `#0F172A`, $\le 100$ chars total, zero nested bullets) and YouTube thumbnail (`veraxi_ymmp.thumbnail`).
- **Pipeline Engineer**: Connects to VoiceVox API, generates `.wav` audio and phonemes into `artifacts/audio/`, and builds `TimelineIR`.

### Phase 4: Compilation & Rendering
Subagent: **Pipeline Engineer**
- Exports to all requested target formats via public interfaces:
  - `YMMPRenderer` $\to$ `final_video.ymmp`
  - `PremiereExporter` $\to$ `sequence.xml`
  - `MoviePyRenderer` $\to$ `qa_test.mp4`
  - `audio_normalizer` $\to$ EBU R128 loudness normalized MP4.

### Phase 5: Autonomous QA & Handover
Subagent: **QA Sentinel**
1. Execute `pytest tests/test_architectural_fitness.py` to ensure zero domain or adapter violations.
2. Execute `python scripts/check_no_local_paths.py` to ensure zero privacy leaks.
3. Review `qa_test.mp4` using `view_file` to confirm:
   - Voice audio is audible and synced.
   - Character layout (Zundamon left, Metan right) and themed bubble colors.
   - Subtitle bubbles are centered and do not clip.
4. Deliver finalized project directory to the user.
