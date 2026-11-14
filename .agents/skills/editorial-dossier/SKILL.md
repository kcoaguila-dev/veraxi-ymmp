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

## 2. NotebookLM Web Prompt Pack (Anti-Slop & Multi-Turn Chaining Protocol)
NotebookLM defaults to agreeable corporate PR summaries when asked multiple broad questions in a single turn (due to context competition and truncation limits). Always enforce **multi-turn prompt chaining**:

### Pinned Note inside NotebookLM: System Rules
Create a note inside NotebookLM named `System Rules` to persist constraints across all turns:
```text
Role: Forensic Investigative Researcher and Fact Auditor.
Rule 1: Ground every answer strictly in verbatim quotes from uploaded documents.
Rule 2: Never generate summaries, promotional marketing fluff, or AI-slop prose.
Rule 3: Enforce temporal and contextual parity across all cited periods and comparative metrics.
Rule 4: Every claim must cite the exact document and section/page number.
Rule 5: For any quantitative figure, include the baseline denominator (sample size, market scale, total spend).
```

### Multi-Turn Prompt Chaining Sequence (Topic-Agnostic)
*Run each turn sequentially in NotebookLM chat:*
1. **Turn 1 (Baseline Extraction):** Extract official metrics, baseline figures, stated timelines, or primary claims from anchor sources.
2. **Turn 2 (Dissecting Contention):** Identify discrepancies, omitted costs, internal memos, or dissenting findings from counter-analyses.
3. **Turn 3 (Root Cause & Mechanism):** Explain the technical, physical, legal, or economic mechanism driving the conflict (the domino chain).
4. **Turn 4 (Tabular Synthesis):** Assemble findings into the 5-column Forensic Evidence Matrix:
```text
Synthesize all findings from Turns 1, 2, and 3 into this exact Markdown table:
| # | Point of Contention / Claim | Canonical Period / Scope | Verbatim Quote Refuting or Explaining | Source Doc & Exact Section/Page | Root Cause / Hard Metric |
|---|---|---|---|---|---|
Strict rules: Output ONLY the Markdown table. Every row must include an exact verbatim quote and page reference. No intro/outro.
```

### The Anti-Slop Boundary: Never Delegate Creative Scripting to NotebookLM
> [!IMPORTANT]
> **Why NotebookLM is restricted to Evidence Extraction:**
> As widely observed on Reddit (r/NotebookLM, r/LocalLLaMA) and creator communities, NotebookLM excels at reading dense filings without hallucination, but defaults to bland corporate PR brochure talk ("AI slop") when asked to write dialogue. It lacks Japanese manzai timing, 0.0s cold open hooks, and character archetypes.
>
> **Decoupled Workflow:**
> 1. **NotebookLM (Step 1.5 HITL Gate):** Generates the raw Forensic Evidence Extraction Matrix (Tabular Markdown) grounded in primary source documents.
> 2. **Antigravity / `veraxi-ymmp`:** Authors the Japanese dialogue using `script-hygiene` rules (0.0s cold open, 50/30/20 ratio, BudouX phrase wrapping <= 38 chars).
>
> **Project Source Isolation:**
> Sources placed in `projects/<project_slug>/sources/` must exclusively reflect the current project's primary materials. Never retain stale files from sibling projects. Both short (~50–80 cuts) and long-form (~180–220 cuts, ~10 minutes) projects are supported.

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
