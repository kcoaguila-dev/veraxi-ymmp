"""Editorial pre-production and NotebookLM dossier generator."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Any


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


def generate_dossier_markdown(topic: str, archetype_key: str) -> str:
    """Generate ready-to-paste NotebookLM prompt pack."""
    arch = ARCHETYPES.get(archetype_key, ARCHETYPES["post_mortem"])
    return f"""# 📋 NotebookLM Interrogation Dossier: {topic}
**Archetype Selected:** {arch['title']}
**Core Theme:** {arch['description']}

---

## 📂 Step 1: Ingest Sources into NotebookLM
1. Open [Google NotebookLM](https://notebooklm.google.com).
2. Create a new notebook titled: `{topic}`.
3. Upload primary source PDFs/docs into NotebookLM (save copies into `sources/` on disk).

---

## 💬 Step 2: Copy-Paste Extraction Prompt (The Evidence Extraction Matrix)
*Paste this prompt into NotebookLM chat to extract factual bedrock without corporate fluff:*

```text
Act as an investigative forensic analyst. Analyze all attached sources regarding:
"{topic}"

Extract the key evidence into this exact Markdown table:
| # | Point of Contention / Claim | Verbatim Quote Refuting or Explaining | Source Doc & Page # | Root Cause / Hard Metric |
|---|---|---|---|---|

Strict constraints:
1. Output ONLY the table. No conversational intro, no outro.
2. Every single row must cite an exact verbatim quote and page/section number.
3. Highlight any contradictions between public claims and actual data.
4. Baseline & Denominator Context: For every quantitative figure, extract the baseline denominator (sample size, total market, global population).
5. Counter-Evidence & Boundary Conditions: Extract any cited dissenting view, vendor mitigation, or boundary limitation to prevent cherry-picking.
```

---

## 💬 Step 3: Copy-Paste Dialogue Tension Prompt
*Paste this second prompt to structure Zundamon, Metan, and Tsumugi dialogue turns:*

```text
Based on the extracted table above, write a fast-paced dialogue between Zundamon, Metan, and Tsumugi.
Format each line strictly as:
[Character Name]: Dialogue text

Perspectives & Roles:
1. [ずんだもん] (The Naive / Greedy Proxy):
   {arch['zundamon']}
2. [四国めたん] (The Cold Forensic Realist):
   {arch['metan']}
3. [春日部つむぎ] (The Trench Whistleblower):
   {arch['tsumugi']}

Strict constraints:
1. Zero greeting cold open (start directly with character conflict).
2. Maximum 38 characters per line.
3. Every hard metric and verbatim fact must be spoken by Metan or Tsumugi.
4. No filler words ("fascinating", "game changer", "deep dive", "vital to remember"). Keep tone sharp and analytical.
5. Anti-Cherry-Picking Constraint: For every extreme or sensational metric, Metan must explicitly state the baseline scale or total denominator (e.g. "out of total X" / "<1% of all systems").
6. Boundary Condition Requirement: Do not generalize an edge case into a universal rule. If a finding only applies under specific conditions, explicitly state the condition.
```

---

## 💬 Step 4: After NotebookLM Answers
Copy NotebookLM's response (both the Evidence Extraction Table and the Dialogue cuts) and paste them directly into `projects/<project>/dialogue_raw.md`.

Then run the automated compiler and audit:
```powershell
# 1. Ingest both dialogue (script.json) and evidence matrix (claims.json) in one step:
python -m veraxi_ymmp ingest-script projects/<project>/dialogue_raw.md

# 2. Run the deterministic epistemic & audience retention audit:
python -m veraxi_ymmp validate projects/<project>/script.json --audit-facts --audit-pacing
```
"""


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

    args = parser.parse_args(argv)

    topic = args.topic.strip()
    archetype_key = args.archetype
    proj_dir = Path(args.output) if args.output else Path("projects") / _slugify(topic)
    sources_dir = proj_dir / "sources"

    sources_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate notebooklm_dossier.md
    dossier_content = generate_dossier_markdown(topic, archetype_key)
    dossier_path = proj_dir / "notebooklm_dossier.md"
    dossier_path.write_text(dossier_content, encoding="utf-8")

    # 2. Generate sources/manifest.json
    manifest_data: Dict[str, Any] = {
        "topic": topic,
        "archetype": archetype_key,
        "required_sources": [
            {
                "name": "Primary Anchor Doc (Official Report / Whitepaper / Court Filing)",
                "filename": "primary_anchor.pdf",
                "status": "pending_download"
            },
            {
                "name": "Counter-Perspective or Dissenting Analysis",
                "filename": "counter_analysis.pdf",
                "status": "pending_download"
            }
        ]
    }
    manifest_path = sources_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # 3. Generate script_seed.json
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

    sys.stdout.write(f"Created editorial dossier for '{topic}' in {proj_dir}\n")
    sys.stdout.write(f"  - NotebookLM Prompt Pack: {dossier_path}\n")
    sys.stdout.write(f"  - Sources Manifest:       {manifest_path}\n")
    sys.stdout.write(f"  - Script Seed:            {seed_path}\n")
