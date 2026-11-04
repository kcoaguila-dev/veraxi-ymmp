"""Per-video source dossier ("sources.md") built from the claim ledger.

Mirrors how expert channels publish research: a verdict summary, an annotated
claim table (claim -> verbatim quote -> source/page), a deduplicated bibliography,
and a ready-to-paste description source list.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .facts import ClaimResult, Evidence, Stance, Verdict, gate_failures

_BADGE = {
    Verdict.SUPPORTED: "✅ supported",
    Verdict.REFUTED: "❌ refuted",
    Verdict.UNVERIFIED: "⚠️ unverified",
    Verdict.OPINION: "💬 opinion",
}
_TIER = {1: "Primary", 2: "Secondary", 3: "Other"}


def _fmt_time(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _loc(e: Evidence) -> str:
    return f"{e.url}" + (f" (p.{e.page})" if e.page is not None else "")


def bibliography(results: Sequence[ClaimResult]) -> List[Evidence]:
    """Unique confirming sources, primary first."""
    seen: Dict[str, Evidence] = {}
    for r in results:
        for e in r.claim.evidence:
            if e.stance is Stance.CONFIRMS and e.url not in seen:
                seen[e.url] = e
    return sorted(seen.values(), key=lambda e: (e.tier, e.url))


def render_report(
    title: str,
    results: Sequence[ClaimResult],
    cut_times: Optional[Dict[int, float]] = None,
) -> str:
    """Render the dossier as Markdown. `cut_times` maps cut_index -> start seconds."""
    times = cut_times or {}
    counts = {v: sum(1 for r in results if r.verdict is v) for v in Verdict}
    blockers = gate_failures(results)
    lines: List[str] = [f"# Source Dossier: {title}", ""]
    lines.append(
        "**Status: "
        + ("🚫 BLOCKED" if blockers else "✅ CLEAR")
        + "** — "
        + ", ".join(f"{_BADGE[v]}: {n}" for v, n in counts.items())
    )
    lines.append("")
    if blockers:
        lines += ["## Blocking issues", ""]
        for r in blockers:
            lines.append(f"- `{r.claim.id}` (cut {r.claim.cut_index}): {r.claim.text} — {r.reason}")
        lines.append("")

    lines += [
        "## Claim ledger",
        "",
        "| ID | Time | Cut | Claim | Weight | Verdict | Evidence (verbatim quote → source) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        c = r.claim
        ev = "<br>".join(
            f"“{_cell(e.quote)}” → {_loc(e)} [{_TIER.get(e.tier, 'Other')}, {e.stance.value}]"
            for e in c.evidence
        ) or "_none_"
        lines.append(
            f"| {c.id} | {_fmt_time(times.get(c.cut_index))} | {c.cut_index} | {_cell(c.text)} "
            f"| {c.weight.value} | {_BADGE[r.verdict]} | {ev} |"
        )

    lines += ["", "## Bibliography", ""]
    for i, e in enumerate(bibliography(results), 1):
        lines.append(f"{i}. [{_TIER.get(e.tier, 'Other')}] {_loc(e)}" + (f" — retrieved {e.retrieved_at}" if e.retrieved_at else ""))

    lines += ["", "## Description source list (paste into YouTube)", ""]
    for r in results:
        sup = [e for e in r.claim.evidence if e.stance is Stance.CONFIRMS]
        if r.verdict is Verdict.SUPPORTED and sup:
            lines.append(f"{_fmt_time(times.get(r.claim.cut_index))} {_cell(r.claim.text)}: {sup[0].url}")
    lines.append("")
    return "\n".join(lines)
