"""Editorial pre-production and NotebookLM dossier generator."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from veraxi_ymmp.epistemic.edgar_capture import KNOWN_CIKS, resolve_sec_direct_filing


ARCHETYPES: Dict[str, Dict[str, str]] = {
    "post_mortem": {
        "title": "The Post-Mortem / Anatomy of a Failure",
        "description": "Engineering failures, software outages, launch disasters, historical collapses.",
        "zundamon": "Assumes it was a minor innocent glitch or simple bad luck.",
        "metan": "Breaks down the cascade failure, skipped safety gates, and systemic negligence.",
        "tsumugi": "Reveals the internal memo, bug report, or engineer warning flagged months prior."
    },
    "myth_vs_reality": {
        "title": "The Myth vs. Documented Reality",
        "description": "Historical misconceptions, scientific fallacies, marketing hype vs physical limits.",
        "zundamon": "Believes the popular internet myth or superficial headline.",
        "metan": "Cites primary peer-reviewed literature or historical records that refute the myth.",
        "tsumugi": "Brings up inconvenient experimental data or overlooked historical letters."
    },
    "david_vs_goliath": {
        "title": "David vs. Goliath / Legal & Technical Battle",
        "description": "Patent lawsuits, copyright disputes, antitrust battles, regulatory clampdowns.",
        "zundamon": "Cheers blindly for the underdog or expects quick market disruption.",
        "metan": "Examines patent claim charts, statutory law, and binding legal precedents.",
        "tsumugi": "Quotes confidential internal emails or deposition transcripts admitted in court."
    },
    "gold_rush": {
        "title": "The Gold Rush & The Bottleneck",
        "description": "Hype bubbles, boom cycles, real estate maturity walls, power grid shortages.",
        "zundamon": "Fantasizes about exponential returns and effortless riches.",
        "metan": "Exposes the thermodynamic, financial, or regulatory bottleneck stalling the boom.",
        "tsumugi": "Presents regional power grid strain notices or debt maturity schedules."
    }
}


def _slugify(text: str) -> str:
    """Create a safe directory name from text."""
    slug = re.sub(r'[^\w\s-]', '', text.lower()).strip()
    slug = re.sub(r'[-\s]+', '_', slug)
    return slug[:50] if slug else "untitled_project"


def generate_dossier_markdown(
    topic: str,
    archetype_key: str,
    direct_filings: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Generate ready-to-paste NotebookLM prompt pack with multi-turn prompt chaining and Reddit warnings."""
    arch = ARCHETYPES.get(archetype_key, ARCHETYPES["post_mortem"])

    filings_block = ""
    if direct_filings:
        filings_block += "3. Primary Authority Filings (Direct Accession Resolved):\n"
        for f in direct_filings:
            filings_block += (
                f"   - **{f['ticker']} {f['form']} (Period Ended {f['report_date']}, Filed {f['filing_date']}):**\n"
                f"     - Interactive iXBRL: {f['ixbrl_url']}\n"
                f"     - Raw Document (HTML): {f['raw_html_url']}\n"
            )
    else:
        filings_block = "3. Upload primary source PDFs/docs into NotebookLM (save copies into `sources/` on disk).\n"

    return f"""# 📋 NotebookLM Interrogation Dossier: {topic}
**Archetype Selected:** {arch['title']}
**Core Theme:** {arch['description']}

---

## 📂 Step 1: Ingest Sources into NotebookLM
1. Open [Google NotebookLM](https://notebooklm.google.com).
2. Create a new notebook titled: `{topic}`.
{filings_block}
> [!WARNING]
> **What Reddit & Financial AI Communities Discovered about SEC Links in NotebookLM:**
> 1. **SEC 403 Bot Block:** SEC EDGAR strictly blocks automated scrapers without a declared compliance User-Agent. Pasting sec.gov URLs as web links into NotebookLM frequently causes 403 Forbidden or blank extracts.
> 2. **The /ix?doc= Client-Side App Trap:** The /ix?doc=... URL is an interactive JavaScript viewer application. Web crawlers only download the outer shell, omitting the dynamic financial tables!
> 3. **The Reddit Best Practice:** Open the direct link in your browser, click **Save as PDF** (or **Save page as HTML**), and upload the file directly into NotebookLM. This guarantees 100% full text and table parsing with zero omission.

---

## 📌 Step 2: Add Pinned Note Inside NotebookLM (System Rules)
*Create a new Note inside the notebook titled `System Rules` so constraints persist across all turns:*
```text
Role: Forensic Investigative Researcher and Fact Auditor.
Rule 1: Ground every answer strictly in verbatim quotes from uploaded documents.
Rule 2: Never generate summaries, promotional marketing fluff, or AI-slop prose.
Rule 3: Enforce temporal and contextual parity across all cited periods and comparative metrics.
Rule 4: Every claim must cite the exact document and section/page number.
Rule 5: For any quantitative figure, include the baseline denominator (sample size, market scale, total spend).
```

---

## 💬 Step 3: Multi-Turn Forensic Extraction (Prompt Chaining Protocol)
*Run each turn as an independent message in NotebookLM chat to avoid context competition and output truncation:*

### Turn 1: Primary Metrics & Stated Claims (Baseline Extraction)
```text
Analyze the primary anchor documents regarding: "{topic}".
What are the official baseline figures, stated timelines, core metrics, or public claims made by the primary parties?
Quote the exact verbatim text, line items, and page/section numbers.
```

### Turn 2: Anomalies, Counter-Evidence & Omissions (Dissecting the Contention)
```text
Now examine the counter-analyses, audit reports, or dissenting findings for: "{topic}".
Where do the official claims conflict with observed data, internal memos, financial disclosures, or external benchmarks?
Extract verbatim quotes showing any discrepancies, omitted costs, or ignored warning signs.
```

### Turn 3: Technical / Root Cause Mechanism (The Domino Effect)
```text
Focusing on the conflict identified in Turn 2:
What is the specific technical, physical, legal, or economic mechanism driving this issue?
Explain the causal chain (how Action A triggered Failure/Bottleneck B) with verbatim citations from the sources.
```

### Turn 4: Forensic Evidence Extraction Matrix Assembly (Structured 5-Column Table)
```text
Synthesize all findings from Turns 1, 2, and 3 into this exact Markdown table:

| # | Point of Contention / Claim | Canonical Period / Scope | Verbatim Quote Refuting or Explaining | Source Doc & Exact Section/Page | Root Cause / Hard Metric |
|---|---|---|---|---|---|

Strict constraints:
1. Output ONLY the Markdown table. No conversational intro, no outro, and NO creative dialogue.
2. Every row must include an exact verbatim quote and page/section number.
3. Highlight contradictions between public claims and documented reality.
4. Include the baseline denominator for every quantitative figure.
5. No filler words, no greetings, and no conversational padding.
```

---

## 💬 Step 4: Bring Evidence Table into Antigravity (The Script-Hygiene Engine)
Save NotebookLM's evidence table into `projects/<project>/evidence.md` or paste it directly into Antigravity.

**Why we never ask NotebookLM to write dialogue:**
NotebookLM defaults to agreeable corporate PR brochure talk ("AI slop") and lacks Japanese manzai timing, 0.0s cold open hooks, and character archetypes.

**Creative Scripting & Direction in Antigravity:**
Antigravity authors the screenplay directly using the extracted evidence table:
- **[ずんだもん] (Naive / Greedy Proxy):** {arch['zundamon']}
- **[四国めたん] (Cold Forensic Realist):** {arch['metan']}
- **[春日部つむぎ] (Trench Whistleblower):** {arch['tsumugi']}
- **Rules:** 0.0s In Media Res cold open, character ping-pong with >= 5-10% micro-reactions, <= 38 chars per cut, 50/30/20 cast ratio.

---

## 💬 Step 5: Compile & Run Static Analysis Gates
Save the finished script + evidence into `projects/<project>/dialogue_raw.md`, then execute:
```powershell
# 1. Ingest dialogue (script.json) and evidence matrix (claims.json) via BudouX phrase tokenizer:
python -m veraxi_ymmp ingest-script projects/<project>/dialogue_raw.md

# 2. Run the deterministic epistemic & audience retention audit:
python -m veraxi_ymmp validate projects/<project>/script.json --audit-facts --audit-pacing
```
"""


def _detect_tickers_in_topic(text: str) -> List[str]:
    """Auto-detect ticker symbols mentioned in topic string or company names."""
    found: List[str] = []
    text_upper = text.upper()

    # Direct ticker symbols
    for t in KNOWN_CIKS.keys():
        if re.search(rf'\b{t}\b', text_upper):
            if t not in found:
                found.append(t)

    # Common company names mapping to tickers
    name_map = {
        "MICROSOFT": "MSFT",
        "AMAZON": "AMZN",
        "NVIDIA": "NVDA",
        "APPLE": "AAPL",
        "GOOGLE": "GOOGL",
        "ALPHABET": "GOOGL",
        "META": "META",
        "FACEBOOK": "META",
        "TESLA": "TSLA",
        "NETFLIX": "NFLX",
        "ORACLE": "ORCL",
        "INTEL": "INTC",
    }
    for name, t in name_map.items():
        if re.search(rf'\b{name}\b', text_upper):
            if t not in found:
                found.append(t)

    return found


def _write_script_seed(proj_dir: Path, topic: str, archetype_key: str) -> Path:
    """Write script_seed.json for the project and return its path."""
    arch = ARCHETYPES[archetype_key]
    seed_data: Dict[str, Any] = {
        "topic": topic,
        "archetype": arch["title"],
        "characters": {
            "ずんだもん": {"role": "The Naive Proxy", "stance": arch["zundamon"]},
            "四国めたん": {"role": "The Cold Realist", "stance": arch["metan"]},
            "春日部つむぎ": {"role": "The Trench Whistleblower", "stance": arch["tsumugi"]}
        },
        "retention_rules": {
            "cold_open": "0.0s In Media Res, zero greeting, cuts 0-2 image: null",
            "ratio": "Metan 50%, Zundamon 30%, Tsumugi 20%",
            "max_lines_per_bubble": 2,
            "max_chars_per_cut": 38
        }
    }
    seed_path = proj_dir / "script_seed.json"
    seed_path.write_text(json.dumps(seed_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return seed_path


def cmd_ideate(argv: List[str]) -> None:
    """Handle 'veraxi-ymmp ideate' subcommand."""
    parser = argparse.ArgumentParser(
        prog="veraxi-ymmp ideate",
        description="Topic-agnostic editorial pre-production and NotebookLM dossier generator."
    )
    parser.add_argument("topic", help="Topic or title for the video/script")
    parser.add_argument(
        "--archetype",
        choices=list(ARCHETYPES.keys()),
        default="post_mortem",
        help="Narrative conflict archetype (default: post_mortem)"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Custom output project directory (default: projects/<topic_slug>)"
    )
    parser.add_argument(
        "--tickers",
        nargs="*",
        default=None,
        help="Optional stock tickers to resolve SEC EDGAR direct filings for (e.g. MSFT AMZN)"
    )
    parser.add_argument(
        "--provider",
        nargs="?",
        const="manual",
        default=None,
        choices=["manual", "api"],
        help="Also generate a validated script.json via this ScriptProvider "
        "(flag alone = manual web-chat handoff; 'api' reserved, needs a key)"
    )

    args = parser.parse_args(argv)

    topic = args.topic.strip()
    archetype_key = args.archetype
    proj_dir = Path(args.output) if args.output else Path("projects") / _slugify(topic)
    sources_dir = proj_dir / "sources"

    sources_dir.mkdir(parents=True, exist_ok=True)

    # Resolve SEC filings systematically
    target_tickers = args.tickers or _detect_tickers_in_topic(topic)
    resolved_filings: List[Dict[str, Any]] = []

    manifest_sources: Dict[str, Any] = {}
    for ticker in target_tickers:
        filing = resolve_sec_direct_filing(ticker, form="10-Q")
        if filing:
            resolved_dict = {
                "ticker": filing.ticker,
                "cik": filing.cik,
                "form": filing.form,
                "filing_date": filing.filing_date,
                "report_date": filing.report_date,
                "accession_number": filing.accession_number,
                "primary_document": filing.primary_document,
                "ixbrl_url": filing.ixbrl_url,
                "raw_html_url": filing.raw_html_url,
            }
            resolved_filings.append(resolved_dict)
            source_key = f"sec_{filing.ticker.lower()}_{filing.form.lower()}"
            manifest_sources[source_key] = {
                "url": filing.ixbrl_url,
                "raw_html_url": filing.raw_html_url,
                "accession_number": filing.accession_number,
                "title": f"{filing.ticker} Form {filing.form} (Report Date: {filing.report_date}, Filed: {filing.filing_date})",
                "canonical_period": "2026-Q3",
                "period_start": "2026-07-01",
                "period_end": filing.report_date,
                "primary": True
            }

    # 1. Generate notebooklm_dossier.md with resolved direct links and Reddit warnings
    dossier_content = generate_dossier_markdown(topic, archetype_key, resolved_filings)
    dossier_path = proj_dir / "notebooklm_dossier.md"
    dossier_path.write_text(dossier_content, encoding="utf-8")

    # 2. Generate sources/manifest.json
    if not manifest_sources:
        manifest_sources = {
            "primary_anchor_doc": {
                "url": "https://www.sec.gov/Archives/edgar/data/0000000000/primary_anchor_doc.pdf",
                "title": "Primary Anchor Doc (Official Report / Whitepaper / Court Filing)",
                "primary": True
            },
            "counter_analysis": {
                "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-0001",
                "title": "Counter-Perspective or Dissenting Analysis",
                "primary": False
            }
        }
    manifest_path = sources_dir / "manifest.json"
    # Top-level provenance metadata sits alongside the source map, like the
    # primary_domains / entity_aliases keys fact_audit reads from this file.
    manifest_data: Dict[str, Any] = {"topic": topic, "archetype": archetype_key, **manifest_sources}
    manifest_path.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # 3. Generate script_seed.json
    seed_path = _write_script_seed(proj_dir, topic, archetype_key)

    sys.stdout.write(f"Created editorial dossier for '{topic}' in {proj_dir}\n")
    if resolved_filings:
        sys.stdout.write(f"  - Resolved {len(resolved_filings)} SEC direct filing accession links!\n")
    sys.stdout.write(f"  - NotebookLM Prompt Pack: {dossier_path}\n")
    sys.stdout.write(f"  - Sources Manifest:       {manifest_path}\n")
    sys.stdout.write(f"  - Script Seed:            {seed_path}\n")
    if args.provider:
        from veraxi_ymmp.app.script_provider import generate_script_file
        generate_script_file(args.provider, topic, dossier_content,
                             proj_dir / "script.json", proj_dir / "script_prompt.md")
        sys.stdout.write(f"  - Validated Script:       {proj_dir / 'script.json'}\n")
