# veraxi-ymmp

A Python tool that generates YMM4 `.ymmp` dialogue timelines by cloning real template items and intelligently orchestrating layout logic.

## Pipeline Architecture

This tool uses a two-stage script pipeline:

1. **Writer Stage:** Generates a purely factual dialogue script.
2. **Director Stage:** Enriches the dialogue with execution metadata (`emotion`, `image`, `bg`) without altering the factual text or character sequence.

The `veraxi-ymmp` compiler takes these scripts, communicates with your local VoiceVox API to generate audio, and mathematically positions characters, subtitles, and B-Roll to construct a perfect `.ymmp` project.

## Features
- **Autonomous Layout Engine:** Zundamon is automatically anchored to the bottom-left, subtitles to the bottom center, and B-Roll imagery dynamically scales and anchors to the right.
- **Dynamic SFX Injection:** "Pon!" pop sound effects are autonomously injected into the timeline whenever a new image appears.
- **Lip-Sync Ready:** Forces YMM4 waveform analysis on output so character mouths sync with VoiceVox.
- **Auto-Export:** Capable of hooking into your local YMM4 Lite installation to hardware-encode the `.mp4` natively on your GPU without ever opening the GUI!
- **High-CTR YouTube Thumbnail Engine:** Automatically generates 1920x1080 publication-ready YouTube thumbnails using the rival 3-split rule (3分割法), multi-layer outline typography (袋文字 + ドロップシャドウ), keyword jump-rate scaling, and character cutout sticker effects with YouTube timestamp dead-zone protection.

## Usage

### 1. Unified Project Runner (Recommended)
Runs audio synthesis, Premiere Pro FCPXML, YMM4 project compilation, MoviePy preview video, and auto-generates the high-CTR YouTube thumbnail in one command:
```bash
python run_project.py projects/01_costco_business_model/
```
Output artifacts generated in project directory:
- `audio/` - Synthesized VoiceVox audio WAV files & phoneme metadata
- `premiere/` - Adobe Premiere Pro FCPXML sequence
- `ymmp/final_video.ymmp` - Ready-to-render YMM4 project
- `qa_test.mp4` - Full fast-preview video
- `thumbnail.png` - Publication-ready 1920x1080 YouTube thumbnail

### 2. Standalone Thumbnail Generation
Generate custom thumbnails directly from script or with custom configurations:
```bash
# Auto-derive from project script
python -m veraxi_ymmp.thumbnail projects/01_costco_business_model/

# Or specify custom thumbnail output in compiler CLI
python -m veraxi_ymmp examples/full_template.ymmp artifacts/script.json artifacts/output.ymmp --thumbnail artifacts/thumbnail.png
```

### 3. Set your YMM4 Path (Optional, for auto-export)
```bash
# Windows
set YMM4_PATH=C:\Users\YourUser\Documents\YukkuriMovieMaker_v4_Lite\YukkuriMovieMaker.exe
```

