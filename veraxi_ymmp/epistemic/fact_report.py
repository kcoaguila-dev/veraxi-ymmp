"""Per-video source dossier ("sources.md") built from the claim ledger.

Mirrors how expert channels publish research: a verdict summary, an annotated
claim table (claim -> verbatim quote -> source/page), a deduplicated bibliography,
and a ready-to-paste description source list.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from veraxi_ymmp.epistemic.facts import ClaimResult, ClaimWeight, Evidence, Stance, Verdict, gate_failures
from veraxi_ymmp.epistemic.dialectical import DialecticalAuditOutcome

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
    parts: List[str] = []
    if e.page is not None:
        parts.append(f"p.{e.page}")
    if e.source_id:
        parts.append(f"source: {e.source_id}")
    if parts:
        return f"{e.url} ({', '.join(parts)})"
    return f"{e.url}"


def _badge_for_evidence(e: Evidence, quote_errors: Sequence[str]) -> str:
    if not e.source_id:
        if e.manual:
            return "[✋ manual verified]"
        return "[⚪ unlinked]"
    if any(e.source_id in err for err in quote_errors):
        return "[🔴 quote mismatch]"
    return "[🟢 disk verified]"


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
    live_verified: bool = False,
    dialectical_outcome: Optional[DialecticalAuditOutcome] = None,
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
        grounding_str = f" [grounding: {int(r.grounding_score * 100)}%]" if r.grounding_score is not None else ""
        if c.axiom and not c.evidence:
            ev = "[✋ common knowledge axiom]"
        else:
            ev = "<br>".join(
                f"“{_cell(e.quote)}” → {_loc(e)} [{_TIER.get(e.tier, 'Other')}, {e.stance.value}] {_badge_for_evidence(e, r.quote_errors)}{grounding_str}"
                for e in c.evidence
            ) or ("_none_" if not c.axiom else "[✋ common knowledge axiom]")
        weight_str = f"{c.weight.value}{f' (derived: {_cell(c.derivation)})' if c.derived and c.derivation else (' (derived)' if c.derived else '')}"
        lines.append(
            f"| {c.id} | {_fmt_time(times.get(c.cut_index))} | {c.cut_index} | {_cell(c.text)} "
            f"| {weight_str} | {_BADGE[r.verdict]} | {ev} |"
        )

    central_results = [r for r in results if r.claim.weight is ClaimWeight.CENTRAL]
    if central_results:
        lines += [
            "",
            "## Central Claim Stance Review (Human Checklist)",
            "",
            "> ⚠️ **Epistemic Invariant:** Disk verification confirms the quote appears verbatim in source text. "
            "A human editor must verify that the source snippet genuinely supports the claim's interpretation.",
            "",
            "| Cut | ID | Claim Assertion | Confirmed Stance | Verbatim Quote in Source | Source / Location |",
            "|---|---|---|---|---|---|",
        ]
        for r in central_results:
            c = r.claim
            if not c.evidence:
                lines.append(f"| {c.cut_index} | {c.id} | {_cell(c.text)} | ⚠️ _no evidence_ | _none_ | _none_ |")
            else:
                for e in c.evidence:
                    lines.append(
                        f"| {c.cut_index} | {c.id} | {_cell(c.text)} | **{e.stance.value.upper()}** | "
                        f"“{_cell(e.quote)}” | {_loc(e)} {_badge_for_evidence(e, r.quote_errors)} |"
                    )

    lines += ["", "## Bibliography", ""]
    for i, e in enumerate(bibliography(results), 1):
        lines.append(f"{i}. [{_TIER.get(e.tier, 'Other')}] {_loc(e)}" + (f" — retrieved {e.retrieved_at}" if e.retrieved_at else ""))

    if dialectical_outcome:
        lines += [
            "",
            "## Adversarial & Dialectical Balance Audit",
            "",
            "> 🛡️ **Anti-Cherry-Picking Gate:** Automated adversarial inspection checking for scope inflation, uncontextualized metrics, and one-sided echo chambers.",
            "",
        ]
        if dialectical_outcome.scope_inflation_issues:
            lines.append("### 🚨 Scope Inflation Violations")
            for sif in dialectical_outcome.scope_inflation_issues:
                lines.append(f"- **Cut #{sif.cut_index} (`{sif.claim_id}`)**: {sif.message}")
            lines.append("")
        else:
            lines += ["### ✅ Scope Inflation Guard: PASSED (No universal over-generalization)", ""]

        if dialectical_outcome.baseline_warnings:
            lines.append("### ⚠️ Contextual Baseline Warnings")
            for bf in dialectical_outcome.baseline_warnings:
                lines.append(f"- **Cut #{bf.cut_index} (`{bf.claim_id}`)**: {bf.message}")
            lines.append("")
        else:
            lines += ["### ✅ Contextual Baseline Guard: PASSED (Scale/denominators verified)", ""]

        if dialectical_outcome.adversarial_critique:
            lines.append("### 🔍 Adversarial Red-Team Critique (Potential Bias Attack Surfaces)")
            for crit in dialectical_outcome.adversarial_critique:
                lines.append(f"- {crit}")
            lines.append("")

    lines += ["", "## Description source list (paste into YouTube)", ""]
    for r in results:
        sup = [e for e in r.claim.evidence if e.stance is Stance.CONFIRMS]
        if r.verdict is Verdict.SUPPORTED and sup:
            lines.append(f"{_fmt_time(times.get(r.claim.cut_index))} {_cell(r.claim.text)}: {sup[0].url}")
    lines.append("")
    return "\n".join(lines)
