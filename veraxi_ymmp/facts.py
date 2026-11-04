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


class DocumentSourceType(str, Enum):
    """Type of official primary authority document source."""

    SEC_EDGAR = "sec_edgar"
    FRED = "fred"
    GOVERNMENT_STAT = "government_stat"
    CUSTOM = "custom"


@dataclass
class DocumentCaptureSpec:
    """Specification for official document passage capture, highlighting, and citation."""

    source_type: DocumentSourceType = DocumentSourceType.SEC_EDGAR
    identifier: str = ""  # Ticker symbol (e.g. 'MSFT'), CIK ('0000789019'), or series ID ('WALCL')
    target_text: str = ""  # Text, figure, or line-item substring to locate and highlight
    document_url: str = ""  # Explicit URL to the document HTML or local path
    citation_label: str = ""  # Authoritative citation display text
    context_padding_px: int = 40  # Context padding around matched bounding box
    highlight_color: str = "#fef08a"  # Fluorescent yellow highlight (#fef08a default)
    device_scale_factor: int = 2  # High-DPI Retina multiplier (2x default for 4K video clarity)
    source_params: Dict[str, Any] = field(default_factory=dict)


class DocumentProvenance(str, Enum):
    """Provenance origin of a captured document."""

    LIVE = "live"
    SYNTHETIC = "synthetic"


@dataclass
class DocumentCaptureResult:
    """Result of an official document capture operation."""

    success: bool
    image_path: Path
    citation_label: str
    source_url: str
    verified: bool = False
    provenance: DocumentProvenance = DocumentProvenance.LIVE
    error_message: str = ""
    matched_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)



@dataclass
class ProvenanceRecord:
    """Audit trail and cryptographic verification record stored alongside captured document images."""

    schema_version: str
    image_path: str
    image_sha256: str
    content_sha256: str
    source_type: DocumentSourceType
    identifier: str
    citation_label: str
    source_url: str
    final_url: str
    http_status: int
    verified: bool
    provenance: DocumentProvenance
    retrieved_at: str
    matched_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "image_path": self.image_path,
            "image_sha256": self.image_sha256,
            "content_sha256": self.content_sha256,
            "source_type": self.source_type.value,
            "identifier": self.identifier,
            "citation_label": self.citation_label,
            "source_url": self.source_url,
            "final_url": self.final_url,
            "http_status": self.http_status,
            "verified": self.verified,
            "provenance": self.provenance.value,
            "retrieved_at": self.retrieved_at,
            "matched_text": self.matched_text,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ProvenanceRecord:
        schema_version = str(data.get("schema_version", ""))
        if schema_version != "1.0":
            raise ValueError(f"Unsupported provenance schema_version: {schema_version}")
        return cls(
            schema_version=schema_version,
            image_path=str(data.get("image_path", "")),
            image_sha256=str(data.get("image_sha256", "")),
            content_sha256=str(data.get("content_sha256", "")),
            source_type=DocumentSourceType(str(data.get("source_type", "sec_edgar"))),
            identifier=str(data.get("identifier", "")),
            citation_label=str(data.get("citation_label", "")),
            source_url=str(data.get("source_url", "")),
            final_url=str(data.get("final_url", "")),
            http_status=int(data.get("http_status", 200)),
            verified=bool(data.get("verified", False)),
            provenance=DocumentProvenance(str(data.get("provenance", "synthetic"))),
            retrieved_at=str(data.get("retrieved_at", "")),
            matched_text=str(data.get("matched_text", "")),
            metadata=dict(data.get("metadata", {})),
        )
