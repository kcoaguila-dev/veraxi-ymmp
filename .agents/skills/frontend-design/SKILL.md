---
name: frontend-design
description: Create distinctive, production-grade frontend interfaces with intentional typography, color systems, and layouts. Avoids generic AI boilerplate ("AI slop") by enforcing opinionated design tokens and real craft.
---

# Frontend Design Skill

This skill enforces high-craft, professional visual design standards for web and desktop applications, preventing generic AI templates (purple gradients on white cards, cookie-cutter layouts, and default font pairings).

## 1. Core Philosophy: Anti-"AI Slop"

- **No Generic Templates:** Avoid centered cards with floating pastel drop-shadows and purple gradients.
- **Context-Driven Aesthetics:** Ground design strictly in the product domain. For `veraxi-ymmp`, this means:
  - **Pro NLE Studio Palette:** Deep obsidian/slate canvas (`#090D16`, `#0F172A`), structural borders (`#1E293B`, `#334155`), high-legibility text (`#F8FAFC`).
  - **Semantic Character Branding:**
    - Zundamon Green: Emerald accent (`#10B981`, `#059669`).
    - Shikoku Metan Pink: Rose accent (`#F43F5E`, `#E11D48`).
    - Kasukabe Tsumugi Gold: Amber accent (`#F59E0B`, `#D97706`).
  - **High-Density Information Architecture:** Video editors need data density (compact rows, precise millisecond timecodes, audio decibel meters, scrubber tracks).

## 2. Design Token System

### Surfaces & Elevation
- Canvas Background: `#0B0F19`
- Sidebar & Panels: `#111827`
- Card / Track Layer: `#1F2937`
- Active / Hover State: `#374151`
- Structural Hairline Border: `rgba(255, 255, 255, 0.08)` or `#1E293B`

### Typography Hierarchy
- Font Family: `system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Hiragino Kaku Gothic ProN", "Yu Gothic UI", sans-serif`
- Code / Timecode: JetBrains Mono, Fira Code, or `monospace` with `font-variant-numeric: tabular-nums`
- Microcopy: Concrete, actionable verbs (`"1-Click Build"`, `"Open in YMM4"`, `"Test Voicevox"`, `"Scrub QA Video"`)

## 3. Component Craft
- **Timeline & Waveform:** Continuous track visualization with playhead scrubber, millisecond readouts, and EBU R128 (-14.0 LUFS) volume indicators.
- **Script Table:** High-density spreadsheet grid with character portrait badges, emotion tags, character-count warning indicators ($\ge 35$ chars warning).
- **Video Preview Canvas:** 16:9 aspect-ratio frame with timecode overlay, playback controls, and speech bubble safe-zone margins.
