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

## Usage

### 1. Set your YMM4 Path (Optional, for auto-export)
```bash
# Windows
set YMM4_PATH=C:\Users\YourUser\Documents\YukkuriMovieMaker_v4_Lite\YukkuriMovieMaker.exe
```

### 2. Generate and Export
```bash
python -m veraxi_ymmp examples/full_template.ymmp artifacts/script.json artifacts/output.ymmp --export-mp4 artifacts/output.mp4
```

This will:
1. Synthesize all dialogue using VoiceVox (cached).
2. Generate `artifacts/output.ymmp`.
3. Launch YMM4 silently to render `artifacts/output.mp4`.
