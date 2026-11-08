---
name: editorial-dossier
description: >-
  Topic-agnostic editorial pre-production and NotebookLM bridge. Maps any topic (tech, history, gaming, science, business) into 4 universal conflict archetypes, creates source ingestion manifests, and generates zero-GPU NotebookLM copy-paste dossiers with anti-slop filters.
---

# Editorial Dossier & NotebookLM Pre-Production Skill

This skill governs the upstream pre-production phase of `veraxi-ymmp`, preparing primary sources and generating structured prompts for Google NotebookLM (or long-context LLMs).

---

## 1. The 4 Universal Conflict Archetypes
Every topic, regardless of genre, must be mapped to one of 4 narrative conflict archetypes:

1. **The Post-Mortem / Anatomy of a Failure:**
   - *Topics:* CrowdStrike sensor crash, Chernobyl, Boeing 737 MAX, Cyberpunk 2077 launch disaster.
   - *Zundamon (Naive Proxy):* "It was just an honest little mistake! Anyone could do it!"
   - *Metan (Forensic Realist):* Exposes the cascade failure, bypassed safety checks, ignored warnings.
   - *Tsumugi (Trench Whistleblower):* The internal commit, omitted unit test, or unheeded memo from months prior.

2. **The Myth vs. Documented Reality:**
   - *Topics:* Historical misconceptions, "clean energy" battery supply chains, dietary fads.
   - *Zundamon:* Echoes the common internet hype or textbook oversimplification.
   - *Metan:* Cites primary archaeological/scientific studies completely disproving it.
   - *Tsumugi:* Highlights the counter-intuitive lab finding or raw field data.

3. **David vs. Goliath / Controversy:**
   - *Topics:* Nintendo vs. Palworld patent disputes, Apple vs. Epic, indie game clones, antitrust suits.
   - *Zundamon:* "Free market competition! Everyone wins!"
   - *Metan:* Analyzes patent claim charts, copyright statutes, and precedent rulings.
   - *Tsumugi:* Reads direct courtroom cross-examination transcripts or settlement terms.

4. **The Gold Rush & Bottlenecks:**
   - *Topics:* AI data center power grids, space mining, commercial real estate debt cliffs, crypto staking.
   - *Zundamon:* Hyped about overnight riches and exponential growth curves.
   - *Metan:* Details the physical, thermodynamic, regulatory, or debt maturity wall.
   - *Tsumugi:* The municipal grid overload notice or real delinquency numbers.

---

## 2. NotebookLM Web Prompt Pack (Anti-Slop Protocol)
NotebookLM by default produces agreeable, corporate summaries. When generating prompts for NotebookLM chat, always enforce:

### Prompt 1: The Evidence Extraction Matrix (Force Tabular Output)
```text
Act as a forensic auditor and investigative researcher. Analyze all attached sources.
Build an evidence table with exactly these 4 columns:
| Point of Contention / Claim | Verbatim Quote Refuting or Explaining It | Source Document & Exact Page # | Technical / Root Cause |
Strict rules:
1. Do not summarize in paragraphs. Only output the Markdown table.
2. Every row must include an exact verbatim quote and page reference.
3. No introductory greetings or concluding remarks.
```

### The Anti-Slop Boundary: Never Delegate Creative Scripting to NotebookLM
> [!IMPORTANT]
> **Why NotebookLM is restricted to Evidence Extraction:**
> As widely observed on Reddit (r/NotebookLM, r/LocalLLaMA) and creator communities, NotebookLM excels at reading dense filings without hallucination, but defaults to bland corporate PR brochure talk ("AI slop") when asked to write dialogue. It lacks Japanese manzai timing, 0.0s cold open hooks, and character archetypes.
>
> **Decoupled Workflow:**
> 1. **NotebookLM:** Generates the raw Forensic Evidence Extraction Matrix (Tabular Markdown).
> 2. **Antigravity / `veraxi-ymmp`:** Authors the Japanese dialogue using `script-hygiene` rules (0.0s cold open, 50/30/20 ratio, BudouX phrase wrapping <= 38 chars).

---

## 3. Directory Layout Standard
Every ideated project must produce:
```
projects/<project_slug>/
├── sources/
│   └── manifest.json         # URLs and file names of primary sources to download
├── notebooklm_dossier.md      # Copy-paste prompts for NotebookLM web
└── script_seed.json           # Conflict outline ready for veraxi-ymmp compiler
```
