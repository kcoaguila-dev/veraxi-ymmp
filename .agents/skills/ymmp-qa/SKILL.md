---
name: ymmp-qa
description: >-
  Use this skill whenever the user asks to generate a new video, YouTube Shorts script, or .ymmp project. It defines the strict Autonomous AI Quality Assurance workflow you must follow before handing the final project to the user.
---

# Video Generation Workflow (Autonomous QA)

When asked to generate a video, you MUST follow this autonomous pipeline. Do NOT simply generate the `.ymmp` and hand it to the user. You must QA it yourself first.

## Pipeline Steps

### 1. Script Generation
- Write the JSON script (e.g. `artifacts/script.json`).
- Ensure it uses the new features: `"image"` (for dynamic B-roll) and `"motion"` (`"jump"` or `"shake"`) when appropriate.
- Refer to `assets/bg/` and `assets/bgm/` for backgrounds and music.

### 2. Internal MP4 Render
- Use the compiler to build the TimelineIR and render an internal `.mp4` video.
- Example script you can run:
  ```python
  from veraxi_ymmp.compiler import YMMPCompiler
  from veraxi_ymmp.moviepy_renderer import MoviePyRenderer
  import json
  from pathlib import Path
  
  script = json.load(open('artifacts/script.json', encoding='utf-8-sig'))
  compiler = YMMPCompiler('examples/full_template.ymmp')
  timeline_ir, _ = compiler._build_ir(script, Path('artifacts/audio'))
  renderer = MoviePyRenderer(timeline_ir)
  renderer.render('artifacts/qa_test.mp4')
  ```

### 3. Audio & Visual QA (AI Multimodal Inspection)
- Use your `view_file` tool to watch `artifacts/qa_test.mp4`.
- **CRITICAL**: Ensure the MP4 render is long enough to cover *every single character's* first spoken line. (Do not rely on a 2-second truncation if a character speaks later).
- **Review Criteria**:
  - **Audio Check**: Verify that Voicevox actually ran and generated `.wav` files in `artifacts/audio/`. Do not assume the audio exists just because the video rendered! Check the directory contents or the MP4 metadata.
  - Do ALL characters appear on screen in the correct layout? (e.g., Zundamon on left, Metan on right).
  - Are the speech bubble colors correctly themed for the speaker? (e.g., Green for Zundamon, Pink for Metan).
  - Does the B-roll image pop up at the correct time?
  - Are the subtitles readable and correctly positioned?
  - Is the pacing (TTS duration) correct?

### 4. Revision Loop
- If the QA fails (e.g., subtitles cut off, pacing is too fast), edit the JSON script and repeat Steps 2 & 3.

### 5. Final Output
- ONLY when you visually confirm the `.mp4` looks perfect, compile the final `.ymmp` for the user.
- ```python
  compiler._render_ymmp(timeline_ir, Path('artifacts/final_video.ymmp'), False, len(script), [])
  ```
- Notify the user and present the final `.ymmp` path.
