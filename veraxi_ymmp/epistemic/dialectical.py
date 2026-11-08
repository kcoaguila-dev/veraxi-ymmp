"""Dialectical balance engine, scope-inflation linter, and adversarial red-teaming.

Tier 2 domain module (zero Tier 3/app dependencies).
Combats contextual cherry-picking, confirmation bias, and scope inflation
before explainer videos are compiled:
1. Scope Inflation Guard: Flags claims asserting universal scope from conditionally-scoped studies.
2. Contextual Baseline Linter: Requires central impact metrics to provide denominator context.
3. Adversarial Red-Team Auditor: Inspects one-sided monocultural narratives and generates critique.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Set, Tuple

from veraxi_ymmp.epistemic.facts import (
    Claim,
    ClaimResult,
    ClaimWeight,
    Stance,
)

# Universal / Absolute Quantifiers that claim total applicability
UNIVERSAL_QUANTIFIERS_JA: Tuple[str, ...] = (
    "すべて",
    "全ての",
    "全",
    "全員",
    "絶対に",
    "完全に",
    "全滅",
    "全米",
    "例外なく",
    "どんな環境でも",
    "一切",
    "常に",
    "必ず",
)

UNIVERSAL_QUANTIFIERS_EN: Tuple[str, ...] = (
    r"\bevery\b",
    r"\ball\b",
    r"\balways\b",
    r"\bcompletely\b",
    r"\bentirely\b",
    r"\bwithout exception\b",
    r"\buniversally\b",
    r"\b100%\b",
)

# Conditional / Scope-limiting phrases indicating boundary conditions
SCOPE_LIMITERS_JA: Tuple[str, ...] = (
    "特定の",
    "一部の",
    "の場合",
    "に限る",
    "限定",
    "実験環境",
    "検証環境",
    "ベンチマーク",
    "サンプル",
    "条件付",
    "極端な",
    "稀な",
    "前提として",
    "試験的",
)

SCOPE_LIMITERS_EN: Tuple[str, ...] = (
    r"\bunder condition\b",
    r"\blimited to\b",
    r"\bonly when\b",
    r"\bin vitro\b",
    r"\btested on\b",
    r"\bspecific\b",
    r"\bsubset\b",
    r"\bbenchmark\b",
    r"\bsample\b",
    r"\bisolated\b",
    r"\bedge case\b",
    r"\bpre-release\b",
    r"\bexperimental\b",
)

# Denominator / baseline words indicating proportionality
BASELINE_CUES_JA: Tuple[str, ...] = (
    "全体",
    "総数",
    "のうち",
    "シェア",
    "分母",
    "比率",
    "割合",
    "母集団",
    "中わずか",
    "未満",
)

BASELINE_CUES_EN: Tuple[str, ...] = (
    r"\bout of\b",
    r"\btotal\b",
    r"\bproportion\b",
    r"\bshare\b",
    r"\bbaseline\b",
    r"\bdenominator\b",
    r"\bpopulation\b",
    r"\brepresenting\b",
    r"\bless than\b",
)


@dataclass
class ScopeInflationFinding:
    """Detection of a universal claim supported by a conditionally-limited quote."""

    claim_id: str
    cut_index: int
    claim_quantifier: str
    quote_limiter: str
    message: str


@dataclass
class BaselineFinding:
    """Detection of an uncontextualized massive metric or extreme percentage."""

    claim_id: str
    cut_index: int
    metric_found: str
    message: str


@dataclass
class DialecticalAuditOutcome:
    """Outcome of adversarial and dialectical balance inspection."""

    scope_inflation_issues: List[ScopeInflationFinding] = field(default_factory=list)
    baseline_warnings: List[BaselineFinding] = field(default_factory=list)
    monocultural_risks: List[str] = field(default_factory=list)
    adversarial_critique: List[str] = field(default_factory=list)

    @property
    def has_blocking_bias(self) -> bool:
        """Returns True if severe scope inflation is present."""
        return len(self.scope_inflation_issues) > 0


def detect_scope_inflation(claim: Claim) -> List[ScopeInflationFinding]:
    """Inspect if claim asserts universal applicability from a conditionally-scoped quote."""
    findings: List[ScopeInflationFinding] = []
    text = claim.text

    # 1. Identify universal quantifier in claim text
    matched_quant: Optional[str] = None
    for q in UNIVERSAL_QUANTIFIERS_JA:
        if q in text:
            matched_quant = q
            break
    if not matched_quant:
        for pat in UNIVERSAL_QUANTIFIERS_EN:
            m = re.search(pat, text, re.I)
            if m:
                matched_quant = m.group(0)
                break

    if not matched_quant:
        return []

    # 2. Check if confirming evidence quote contains conditional limiters
    for ev in claim.evidence:
        if ev.stance is not Stance.CONFIRMS or not ev.quote:
            continue
        quote = ev.quote
        matched_limiter: Optional[str] = None
        for lim in SCOPE_LIMITERS_JA:
            if lim in quote:
                matched_limiter = lim
                break
        if not matched_limiter:
            for pat in SCOPE_LIMITERS_EN:
                m = re.search(pat, quote, re.I)
                if m:
                    matched_limiter = m.group(0)
                    break

        if matched_limiter:
            findings.append(
                ScopeInflationFinding(
                    claim_id=claim.id,
                    cut_index=claim.cut_index,
                    claim_quantifier=matched_quant,
                    quote_limiter=matched_limiter,
                    message=(
                        f"Scope inflation: Claim asserts universal scope ('{matched_quant}') "
                        f"but evidence quote contains conditional boundary ('{matched_limiter}'). "
                        f"Scope must be qualified in dialogue."
                    ),
                )
            )

    return findings


def check_contextual_baseline(claim: Claim) -> Optional[BaselineFinding]:
    """Check if central extreme metrics are accompanied by baseline/proportionality context."""
    if claim.weight is not ClaimWeight.CENTRAL:
        return None

    # Check for extreme counts (>= 1,000,000 / 100万) or extreme proportions (>= 80% / <= 5%)
    has_large_metric = bool(
        re.search(r"(\d+(?:\.\d+)?\s*(?:[億兆万]|million|billion|trillion|台|人|件|ドル|円))", claim.text, re.I)
        or re.search(r"(\b(?:9[0-9]|100|[0-4])%|[0-4]％|9[0-9]％|100％)", claim.text)
    )
    if not has_large_metric:
        return None

    # Check if derivation provides formulaic baseline
    if claim.derived and claim.derivation.strip():
        return None

    # Check if claim text itself carries baseline cues
    for cue in BASELINE_CUES_JA:
        if cue in claim.text:
            return None
    for pat in BASELINE_CUES_EN:
        if re.search(pat, claim.text, re.I):
            return None

    # Check if any confirming evidence quote provides baseline cues
    for ev in claim.evidence:
        if ev.stance is Stance.CONFIRMS and ev.quote:
            for cue in BASELINE_CUES_JA:
                if cue in ev.quote:
                    return None
            for pat in BASELINE_CUES_EN:
                if re.search(pat, ev.quote, re.I):
                    return None

    return BaselineFinding(
        claim_id=claim.id,
        cut_index=claim.cut_index,
        metric_found=claim.text[:40],
        message=(
            "Contextual baseline missing: Central claim asserts extreme metric without "
            "baseline or denominator context in derivation or evidence quotes (e.g. specify "
            "sample size, market total, or percentage baseline to prevent viewer bias criticism)."
        ),
    )


def audit_dialectical_balance(
    claims: Sequence[Claim],
    results: Sequence[ClaimResult],
    adversarial_mode: bool = False,
) -> DialecticalAuditOutcome:
    """Run comprehensive adversarial red-teaming and dialectical balance audit on claim set."""
    outcome = DialecticalAuditOutcome()

    # 1. Scope Inflation Checks
    for claim in claims:
        findings = detect_scope_inflation(claim)
        outcome.scope_inflation_issues.extend(findings)

    # 2. Contextual Baseline Checks on Central Claims
    for claim in claims:
        bf = check_contextual_baseline(claim)
        if bf:
            outcome.baseline_warnings.append(bf)

    # 3. Monocultural / Echo-Chamber Risk Detection
    # If >= 4 claims exist, all confirmed, but 100% come from a single authority host
    confirming_sources: Set[str] = set()
    for c in claims:
        for ev in c.evidence:
            if ev.stance is Stance.CONFIRMS:
                confirming_sources.add(ev.source_id or ev.url)

    if len(claims) >= 4 and len(confirming_sources) == 1:
        single_src = next(iter(confirming_sources))
        outcome.monocultural_risks.append(
            f"Monocultural Source Risk: All {len(claims)} claims rely exclusively on single source "
            f"'{single_src}'. Expert audiences and critics can dismiss this as one-sided vendor/author narrative."
        )

    # 4. Adversarial Red-Team Critique (if requested or if risks found)
    if adversarial_mode or outcome.has_blocking_bias or outcome.monocultural_risks:
        if outcome.scope_inflation_issues:
            outcome.adversarial_critique.append(
                f"🚨 Reddit Critique Vulnerability: {len(outcome.scope_inflation_issues)} claims over-generalize "
                f"isolated laboratory/edge-case findings into universal statements. Top comments will point out missing conditions."
            )
        if outcome.baseline_warnings:
            outcome.adversarial_critique.append(
                f"⚠️ Baseline Attack Surface: {len(outcome.baseline_warnings)} central metrics lack scale context. "
                f"Audiences cannot tell if {outcome.baseline_warnings[0].claim_id} represents an apocalyptic crisis or <1% routine noise."
            )
        if outcome.monocultural_risks:
            outcome.adversarial_critique.append(
                "💬 Lack of Counter-Perspective: Script contains 0 cited boundary conditions or alternative viewpoints. "
                "Consider adding a skeptical reaction line (e.g. Metan citing mitigating factors or industry averages)."
            )

    return outcome
