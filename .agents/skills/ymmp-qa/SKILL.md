---
name: ymmp-qa
description: >-
  Use this skill whenever the user asks to generate a new video, YouTube Shorts script, or .ymmp project. It defines the strict Autonomous AI Quality Assurance workflow you must follow before handing the final project to the user.
---

# Video Generation Workflow (Autonomous QA)

When asked to generate a video, you MUST follow this autonomous pipeline. Do NOT simply generate the `.ymmp` and hand it to the user. You must QA it yourself first.

## Pipeline Steps

### 1. Script Generation & B-Roll Assets
- Write the JSON script (e.g. `artifacts/script.json`).
- Ensure it uses the new features: `"image"` (for dynamic B-roll) and `"motion"` (`"none"` or `"nod"`) when appropriate.
- Refer to `assets/bg/` and `assets/bgm/` for backgrounds and music.
- **Epistemic Grounding & Audience Retention Standard (`veraxi_ymmp.epistemic.fact_audit` & `veraxi_ymmp.editorial.pacing`)**:
  - Run preflight epistemic + pacing validation: `veraxi-ymmp validate <script.json> --audit-facts --audit-pacing` (Epistemic Audit must pass with 0 unsupported claims; Retention Score must be $\ge 80/100$).
  - **Fail-Closed Epistemic Parity**: Every salient figure across Cold Open cuts (`0..10`), B-roll slides (`broll_manifest.json`), thumbnail (`thumbnail_config.json`), and YouTube metadata must match a `Verdict.SUPPORTED` claim in `claims.json` backed by verbatim primary source quotes (`sources/*.pdf`, `.html`, `.md`).
  - **0-Second Cold Open & Zero-Greeting Invariant**:
    - Strictly ZERO generic greetings (`「みんな、こんにちは」`, `「ごきげんよう」`, `「よろしく」`) in the first 3 dialogue cuts.
    - **No Premature Slide Dump:** The opening hook window (first 2-3 cuts) strictly keeps `"image": null` so characters carry the emotional confrontation without slide clutter. Slides enter as evidence around Cut 4+ when transitioning to core data.
    - Open In Media Res with high-stakes cognitive dissonance (The Public Illusion / Shocking Metric).
  - **50/30/20 Retention Golden Ratio**: In 3-character casts, Main Explainer (四国めたん) holds 45%–55%, Lead Inquirer (ずんだもん) holds 30%–35%, and 3rd Specialist (春日部つむぎ) holds **15%–20%**. Hard ceiling $\le 25\%$ to prevent acoustic fatigue and group-banter derailment.
  - **Hook Protection Rule**: 3rd character must NEVER speak in the opening hook (first 10% or first 3 cuts). Premise must be cleanly established by the core duo to prevent early viewer bounce.
  - **Mid-Roll Attention Spike**: 3rd character's first entrance must occur during the mid-roll attention decay window (30%–50% timeline mark) to reset audience focus.
  - **2-Position Stage Convention**: Screen layout strictly maintains Left Anchor (Explainer at `x=80`) and Right Alternating (Lead Inquirer $\leftrightarrow$ Guest Specialist at `x=1180`), keeping center screen open for presentation slides.
- **B-Roll Presentation Boards Standard (`veraxi_ymmp.graphics.broll`)**:
  - Always use **Pro Dark Slate Theme** (`#0F172A` / `#1E293B`) for explanatory slides.
  - Apply **1-Slide-1-Impact Architecture** (VS comparisons, big impact metric, or 3-card overview).
  - Strictly **NO redundant category badges** (e.g. no `【マクロ経済】`), **NO English jargon** (`OVERVIEW`, `Higher for Longer`), **NO robotic brackets** (`【警告】`, `【急騰】`), and **NO premature conclusion labels** (`本日の結論` in video intro).
  - Strictly **NO AI-slop presentation cliches**: Ban `「3つのポイント」`, `「3大視点」`, `「3大潮流」`, `「3大原則」`. Build narrative tension through dramatic contrast (世間の誤解 vs 冷酷な現場・決算の真実).
  - Strictly **NO trailing dollar signs**: Write `2200億ドル` or `$220B`, never `2200億$`.
  - Spoken dialogue: Always pronounce full names like `「マイクロソフト」` rather than abbreviations like `「MS」` or `「エムエス」`.
  - **Overview / Agenda Slides**: Strictly **single-line headlines only** (no sub-bullet points, no premature conclusion boxes). 4-5 second cuts only allow scanning 3 clear headlines without cognitive overload.
  - **Systematic Cognitive Load & Text Density Rule**:
    - Hard ceiling: **<= 100 characters total** across all text on any slide.
    - Maximum **6 discrete text elements** (title, step tag, hero, status pill, impact text, optional badge).
    - **Zero nested bullet lists** on presentation cuts (causes severe reading fatigue and fights with subtitles/characters).
    - Maintain visual symmetry across related sequences (e.g. Condition 01, 02, 03 must share the same clean `render_metric_slide` structure).
  - Use `veraxi_ymmp.graphics.broll` (`render_metric_slide`, `render_vs_slide`, `render_overview_slide`) to generate all slide assets.
- **Dialogue & Subtitle Hygiene Standard (`veraxi_ymmp.graphics.typography`)**:
  - **Hard Ceiling: Max 2 lines per speech bubble**: Dialogue cuts must NEVER produce 3 lines. 3 lines crowd the screen, obstruct character bodies, and risk vertical clipping.
  - **Character Length Ceiling: <= 35-40 characters per dialogue cut**: If an explanation contains compound thoughts or multiple sentences, split them into distinct, well-paced cuts (2-3 seconds each).
  - **Pronunciation & Interjection Rule**: NEVER start dialogue lines with bare `「ええ、」` (which causes OpenJTalk/VOICEVOX to assign an unnatural questioning Atamadaka pitch accent). Write natural character-themed affirmations such as `「はい、」`, `「その通りですわ、」`, `「そうですわね、」`, or `「まさにその通りなのだ！」`.
  - **Grounded Staging Invariant**: NEVER use `"motion": "jump"` in technical or explanatory videos. Keep characters grounded (`"none"` or subtle `"nod"`). Expressiveness is carried by facial emotion keys and rapid camera cuts.
  - **Clean Audio & Zero-SFX Invariant**: Zero cartoon slapstick SFX (`pon.wav` is banned). Zero murky or vocal BGM loops. Use only clean instrumental tracks (`assets/bgm/2_23_AM.mp3`) ducked low (<= 0.08) to preserve voice clarity.
  - **Concentric Subtitle Layout**: All speech bubble plates and VoiceItem subtitles must be aligned concentrically using `BasePoint: "CenterCenter"`.

### 2. Internal MP4 Render & Unified Project Pipeline
- Run the end-to-end project pipeline via CLI (`veraxi-ymmp run <project_dir>`) or `ProjectPipeline`:
  ```bash
  veraxi-ymmp run projects/01_costco_business_model/
  ```
- Or use the compiler directly to build `TimelineIR` via public `compiler.build_ir` and render an internal `.mp4` video:
  ```python
  from veraxi_ymmp.app.compiler import YMMPCompiler
  from veraxi_ymmp.exporters.moviepy_renderer import MoviePyRenderer
  import json
  from pathlib import Path

  script = json.loads(Path("artifacts/script.json").read_text(encoding="utf-8-sig"))
  compiler = YMMPCompiler("examples/full_template.ymmp")
  timeline_ir, _ = compiler.build_ir(script, Path("artifacts/audio"))
  renderer = MoviePyRenderer(timeline_ir)
  renderer.render("artifacts/qa_test.mp4")
  ```

### 3. Audio & Visual QA (AI Multimodal Inspection)
- Use your `view_file` tool to watch `artifacts/qa_test.mp4`.
- **CRITICAL**: Ensure the MP4 render is long enough to cover *every single character's* first spoken line. (Do not rely on a 2-second truncation if a character speaks later).
- **Review Criteria**:
  - **Audio Check**: Verify that Voicevox actually ran and generated `.wav` files in `artifacts/audio/`. Do not assume the audio exists just because the video rendered! Check the directory contents or the MP4 metadata.
  - Do ALL characters appear on screen in the correct layout? (e.g., Metan on left, Zundamon on right).
  - Are the speech bubble colors correctly themed for the speaker? (e.g., Green for Zundamon, Pink for Metan).
  - Does the B-roll image pop up at the correct time?
  - Are the subtitles readable and correctly positioned?
  - Is the pacing (TTS duration) correct?

### 4. High-CTR YouTube Thumbnail Generation & QA
- Every generated video project MUST have a publication-grade YouTube thumbnail (`thumbnail.png`).
- Auto-generate using `veraxi_ymmp.graphics.thumbnail`:
  ```python
  from veraxi_ymmp.graphics.thumbnail import generate_project_thumbnail
  generate_project_thumbnail(proj_dir, out_path=proj_dir / "thumbnail.png")
  ```
- **Thumbnail Review Criteria (Multimodal Inspection via `view_file`)**:
  - **3-Split Composition**: Prominent character reaction face on the right (Zundamon/Metan), punchy copy on the left.
  - **YouTube Safe Zone**: Bottom-right corner strictly clear of text or critical facial features (protected against duration badge `12:34`).
  - **Multi-layer Outline (袋文字)**: Text has thick black stroke + drop shadow and is easily readable on mobile.
  - **Jump Rate**: Key trigger word (e.g. 「ボロ儲け」「大波乱」) is highlighted in gold/red.
  - **Character Cutout (白フチ)**: Clean white sticker rim stroke separating character from the dark blurred background.

### 5. Revision Loop
- If ANY QA check fails (missing audio, off-center text, overlapping characters, speech bubble outline mismatch), fix the script/code and re-render.
- Re-inspect until the video is publication-ready.
- Hand off the final artifacts to the user only after passing autonomous QA.
