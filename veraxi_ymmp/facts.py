"""Fact-check domain model: claims, evidence, deterministic verdicts.

Pure domain module (no outer-layer imports). Verdicts are computed by code from
structured evidence flags, never by an LLM-produced score.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Sequence


class ClaimKind(str, Enum):
    NUMBER = "number"
    DATE = "date"
    QUOTE = "quote"
    CAUSAL = "causal"
    OPINION = "opinion"
    COMMENTARY = "commentary"  # jokes, banter, hyperbole, reactions: never fact-checked


NON_CHECKABLE_KINDS = frozenset({ClaimKind.OPINION, ClaimKind.COMMENTARY})


class ClaimWeight(str, Enum):
    CENTRAL = "central"
    MINOR = "minor"


class Stance(str, Enum):
    CONFIRMS = "confirms"
    CONTRADICTS = "contradicts"
    SILENT = "silent"


class Verdict(str, Enum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    UNVERIFIED = "unverified"
    OPINION = "opinion"


@dataclass
class Evidence:
    """One source snippet judged against one claim."""

    url: str
    quote: str
    stance: Stance
    tier: int = 2  # 1 = primary (SEC/FRED/gov), 2 = reputable secondary, 3 = other
    page: int | None = None
    retrieved_at: str = ""


@dataclass
class Claim:
    """Atomic, decontextualized, independently checkable assertion."""

    id: str
    cut_index: int
    text: str
    kind: ClaimKind = ClaimKind.NUMBER
    weight: ClaimWeight = ClaimWeight.MINOR
    evidence: List[Evidence] = field(default_factory=list)


@dataclass
class ClaimResult:
    claim: Claim
    verdict: Verdict
    reason: str


def required_primary_sources(claim: Claim) -> int:
    """Central claims need 2 independent primary sources; others need 1 source."""
    return 2 if claim.weight is ClaimWeight.CENTRAL else 1


def verdict_for(claim: Claim) -> ClaimResult:
    """Deterministic verdict. Any contradiction from tier<=2 refutes; missing proof is UNVERIFIED."""
    if claim.kind in NON_CHECKABLE_KINDS:
        return ClaimResult(claim, Verdict.OPINION, f"{claim.kind.value}; not fact-checked")
    contradicts = [e for e in claim.evidence if e.stance is Stance.CONTRADICTS and e.tier <= 2]
    if contradicts:
        return ClaimResult(claim, Verdict.REFUTED, f"contradicted by {contradicts[0].url}")
    confirms = [e for e in claim.evidence if e.stance is Stance.CONFIRMS and e.quote.strip()]
    need = required_primary_sources(claim)
    if claim.weight is ClaimWeight.CENTRAL:
        primary = {e.url for e in confirms if e.tier == 1}
        if len(primary) >= need:
            return ClaimResult(claim, Verdict.SUPPORTED, f"{len(primary)} primary sources")
        return ClaimResult(
            claim, Verdict.UNVERIFIED, f"central claim needs {need} primary sources, has {len(primary)}"
        )
    if len({e.url for e in confirms}) >= need:
        return ClaimResult(claim, Verdict.SUPPORTED, "sourced")
    return ClaimResult(claim, Verdict.UNVERIFIED, "no confirming evidence with quote")


def audit(claims: Sequence[Claim]) -> List[ClaimResult]:
    return [verdict_for(c) for c in claims]


def gate_failures(results: Sequence[ClaimResult]) -> List[ClaimResult]:
    """Results that must block rendering: refuted anything, or non-supported central claims."""
    return [
        r
        for r in results
        if r.verdict is Verdict.REFUTED
        or (r.claim.weight is ClaimWeight.CENTRAL and r.verdict is Verdict.UNVERIFIED)
    ]


def claims_to_json(claims: Sequence[Claim]) -> str:
    return json.dumps([asdict(c) for c in claims], ensure_ascii=False, indent=2)


def claims_from_json(raw: str) -> List[Claim]:
    data: List[Dict[str, Any]] = json.loads(raw)
    out: List[Claim] = []
    for d in data:
        ev = [Evidence(**{**e, "stance": Stance(e["stance"])}) for e in d.get("evidence", [])]
        out.append(
            Claim(
                id=d["id"],
                cut_index=int(d["cut_index"]),
                text=d["text"],
                kind=ClaimKind(d.get("kind", "number")),
                weight=ClaimWeight(d.get("weight", "minor")),
                evidence=ev,
            )
        )
    return out


def load_claims(path: Path) -> List[Claim]:
    return claims_from_json(path.read_text(encoding="utf-8"))
