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

### Phase 2: Editorial Scripting, Epistemic Grounding & Staging (`editorial/` & `epistemic/`)
Subagent: **Editorial & Epistemic Specialist**
1. Ingest primary sources (PDFs via `pypdf`, HTML/iXBRL, or Markdown) and NotebookLM Evidence Matrix via `veraxi-ymmp ingest-script <dialogue_raw.md> -o <script.json>` (which uses Google `budoux` phrase segmentation and auto-generates `claims.json`).
2. Enrich with staging metadata in `DirectorScript` (motions, emotions, B-roll triggers).
3. Enforce Epistemic Fact-Audit Invariants (`epistemic/`):
   - Every salient quantitative figure (scales, percentages, multipliers, physical/computing/medical units) in Cold Open cuts (`0..10`), B-roll slides, thumbnail, and metadata must map to a `Verdict.SUPPORTED` claim in `claims.json` backed by verbatim quotes from primary sources in `sources/`.
   - Mathematical derivations must pass two-sided `pint` dimensional compatibility checks; Japanese claims must pass `mecab` morphological lemma and clause-scoped negation checks.
4. Enforce Cold Open & Hook Invariants:
   - Zero-Greeting Cold Open: NEVER open with generic greetings (e.g. `「みんな、こんにちは」`, `「ごきげんよう」`).
   - Character-Driven Hook: First 2-3 cuts keep `image: null` to avoid PowerPoint overload; slides enter as proof at Cut 4+.
   - High-Stakes Hook: Open with the core conflict or cognitive dissonance; hook claims (`cut_index <= 10`) must carry `ClaimWeight.CENTRAL`.
5. Enforce Character & Dialogue Invariants (Anti-AI-Slop):
   - **ずんだもん (Chaotic Proxy):** Never write him as a B2B corporate consultant. He acts as the viewer's surrogate of greed, panic, shock, and naive misconceptions.
   - **四国めたん (Sadistic Realist):** Never make her a passive 'Yes-Man' (`はい`, `その通りですわ` spam). She punctures delusions with dry wit, aristocratic calm, and forensic ruthlessness.
   - **春日部つむぎ (Trench Insider):** Never read PR bullet points. She brings developer gossip and server-room reality checks.
   - **Rhythmic Syncopation:** Avoid uniform 30-38 char sentences. Inject 1-beat micro-reactions ($\le 12$ chars) for rapid ping-pong comedic timing.
   - **Zero-Drop Ending:** NEVER close with generic 'subscribe/like/check description' goodbyes. End on high emotional stakes or an unresolved punchline.
   - **Pricing & Metric Disambiguation:** Never quote naked prices or uncontextualized metrics. Always specify target tier, unit, and denominator.
6. Validate typography constraints:
   - Max 2 lines per speech bubble.
   - Max 35–40 characters per cut (segmented via `budoux` without splitting `{Kanji|ruby}` tags).
   - Natural interjections.

### Phase 3: Asset Creation & Sound Design (`graphics/` & `audio/`)
Subagents: **Graphics Designer** & **Audio/Exporters Engineer** (Parallel Execution)
- **Graphics Designer (`graphics/`)**: Generates B-roll slides (`broll.py`, Pro Dark Slate `#0F172A`, $\le 100$ chars total, zero nested bullets) and YouTube thumbnail (`thumbnail.py`), ensuring 100% numeric parity with `Verdict.SUPPORTED` claims.
- **Audio/Exporters Engineer (`audio/` & `exporters/`)**: Connects to VoiceVox API, generates `.wav` audio and `hatsuon` pitch/phoneme overrides into `artifacts/audio/`, and builds `TimelineIR`.

### Phase 4: Compilation & Rendering (`exporters/` & `app/`)
Subagent: **Audio/Exporters Engineer**
- Exports to all requested target formats via hexagonal ports (`core/ports.py`):
  - `YMMPRenderer` $\to$ `final_video.ymmp`
  - `PremiereExporter` $\to$ `sequence.xml`
  - `MoviePyRenderer` $\to$ `qa_test.mp4`
  - `audio_normalizer` $\to$ `-16 LUFS` EBU R128 loudness normalized MP4.

### Phase 5: Autonomous QA & Handover (`tests/`)
Subagent: **QA & Fitness Sentinel**
1. Execute `pytest tests/test_architectural_fitness.py -q` to ensure zero 3-Tier DAG, sibling stage, or adapter isolation violations.
2. Execute `veraxi-ymmp validate <script.json> --audit-facts --audit-pacing` to verify 100% epistemic grounding and $\ge 80/100$ retention score.
3. Execute `python scripts/check_no_local_paths.py` to ensure zero privacy leaks.
4. Review `qa_test.mp4` using `read_file` to confirm:
   - Voice audio is audible and synced.
   - Character layout (Metan left, Zundamon/Tsumugi right) and themed bubble colors.
   - Subtitle bubbles are centered and do not clip.
5. Deliver finalized project directory to the user.
