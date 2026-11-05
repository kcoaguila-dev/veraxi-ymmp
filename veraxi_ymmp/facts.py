"""Fact-check domain model: claims, evidence, deterministic verdicts.

Pure domain module (no outer-layer imports). Verdicts are computed by code from
structured evidence flags, never by an LLM-produced score.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Sequence
from urllib.parse import urlparse


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
    source_id: str = ""  # ID/filename under projects/<project>/sources/<source_id>.*
    sha256: str = ""  # Expected SHA-256 digest of stored source file
    manual: bool = False  # Explicitly human-verified override when raw file is not in sources/


@dataclass
class Claim:
    """Atomic, decontextualized, independently checkable assertion."""

    id: str
    cut_index: int
    text: str
    kind: ClaimKind = ClaimKind.NUMBER
    weight: ClaimWeight = ClaimWeight.MINOR
    evidence: List[Evidence] = field(default_factory=list)
    derived: bool = False  # True when quantity is calculated/derived rather than quoted verbatim
    derivation: str = ""  # Mathematical formula or derivation explanation when derived is True


@dataclass
class ClaimResult:
    claim: Claim
    verdict: Verdict
    reason: str
    quote_errors: List[str] = field(default_factory=list)


# Official primary authority domains permitted to qualify as Tier 1 evidence
PRIMARY_AUTHORITY_HOSTS = frozenset({
    "sec.gov",
    "www.sec.gov",
    "fred.stlouisfed.org",
    "federalreserve.gov",
    "www.federalreserve.gov",
    "boj.or.jp",
    "www.boj.or.jp",
    "e-stat.go.jp",
    "www.e-stat.go.jp",
    "bls.gov",
    "www.bls.gov",
    "bea.gov",
    "www.bea.gov",
    "treasury.gov",
    "www.treasury.gov",
})


PRIMARY_INSTITUTIONS: Dict[str, str] = {
    "sec.gov": "sec",
    "stlouisfed.org": "federalreserve",
    "federalreserve.gov": "federalreserve",
    "boj.or.jp": "boj",
    "e-stat.go.jp": "estat",
    "bls.gov": "bls",
    "bea.gov": "bea",
    "treasury.gov": "treasury",
    "census.gov": "census",
    "imf.org": "imf",
    "worldbank.org": "worldbank",
    "oecd.org": "oecd",
    "bis.org": "bis",
}


def canonical_institution(url: str) -> str:
    """Return canonical institutional identity for primary source deduplication.

    Maps all sub-agencies, endpoints, and www variations of the same institution
    (e.g. sec.gov, data.sec.gov, and www.sec.gov -> 'sec') to a single canonical
    institution key.
    """
    if not url:
        return ""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host and ("://" in url or "." in url):
        host = url.split("/")[0].split(":")[0].lower()
    if not host:
        return ""
    clean_host = host.removeprefix("www.")

    # Match known primary institutions by domain or subdomain suffix
    for domain, inst_key in PRIMARY_INSTITUTIONS.items():
        if clean_host == domain or clean_host.endswith("." + domain):
            return inst_key

    # For other government agencies (.gov, .go.jp, .gov.uk), collapse subdomains to agency domain
    parts = clean_host.split(".")
    if len(parts) >= 2 and (
        clean_host.endswith(".gov") or clean_host.endswith(".go.jp") or clean_host.endswith(".gov.uk")
    ):
        if clean_host.endswith(".go.jp") or clean_host.endswith(".gov.uk"):
            if len(parts) >= 3:
                return ".".join(parts[-3:])
        else:
            return ".".join(parts[-2:])

    return clean_host


def is_primary_authority_url(url: str) -> bool:
    """Return True if URL host is recognized as an official primary authority."""
    if not url:
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host and ("://" in url or "." in url):
        host = url.split("/")[0].split(":")[0].lower()
    if not host:
        return False
    clean_host = host.removeprefix("www.")
    if clean_host in PRIMARY_AUTHORITY_HOSTS or host in PRIMARY_AUTHORITY_HOSTS:
        return True
    for domain in PRIMARY_INSTITUTIONS:
        if clean_host == domain or clean_host.endswith("." + domain):
            return True
    return clean_host.endswith(".gov") or clean_host.endswith(".go.jp") or clean_host.endswith(".gov.uk")


def enforce_source_tier(url: str, declared_tier: int = 2) -> int:
    """Derive/enforce tier.

    A source is only Tier 1 if its domain matches the primary authority allowlist.
    Adapters or prompts declaring Tier 1 for non-whitelisted sources are downgraded to Tier 2.
    """
    if declared_tier == 1:
        if is_primary_authority_url(url):
            return 1
        return 2  # Downgrade non-whitelisted source to Tier 2
    return max(1, declared_tier)


_QUOTE_CHARS = str.maketrans({
    "“": '"',
    "”": '"',
    "„": '"',
    "‘": "'",
    "’": "'",
    "「": '"',
    "」": '"',
    "『": '"',
    "』": '"',
    "«": '"',
    "»": '"',
})


def normalize_for_quote_match(text: str) -> str:
    """Normalize text strictly for verbatim quote matching.

    Normalizes Unicode NFKC (standardizing character width and zenkaku/hankaku spaces),
    collapses contiguous whitespace, and unifies quotation marks.
    Does NOT perform fuzzy matching or drop words.
    """
    if not text:
        return ""
    norm = unicodedata.normalize("NFKC", text)
    norm = norm.translate(_QUOTE_CHARS)
    return re.sub(r"\s+", " ", norm).strip()


def verify_quote_in_source(quote: str, source_text: str) -> bool:
    """Deterministic, strict substring check between normalized quote and source text."""
    norm_q = normalize_for_quote_match(quote)
    if not norm_q:
        return False
    norm_src = normalize_for_quote_match(source_text)
    if norm_q in norm_src:
        return True
    inner_q = norm_q.strip('"\'')
    if inner_q and inner_q in norm_src:
        return True
    # Strip whitespace only for CJK character sequences to handle PDF/HTML soft line-breaks.
    # Preserve word boundaries for Latin/ASCII to prevent matches across words (e.g. "a bc" vs "ab c").
    if re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", norm_q):
        cjk_q = re.sub(r"\s+", "", norm_q.strip('"\''))
        cjk_src = re.sub(r"\s+", "", norm_src)
        if cjk_q and cjk_q in cjk_src:
            return True
    return False


def primary_authority_key(e: Evidence) -> str:
    """Canonical identifier for deduplicating primary sources across distinct institutions.

    Uses canonical institution name for primary authorities so multiple files or URLs
    from the same institution (e.g. two SEC documents) cannot count as two independent
    primary authorities for central claims.
    """
    inst = canonical_institution(e.url)
    if inst:
        return f"inst:{inst}"
    if e.source_id:
        return f"src:{e.source_id}"
    parsed = urlparse(e.url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    if host:
        return f"{host}:{path}"
    return e.url.strip()


MATH_CONSTANTS = frozenset({"1", "2", "4", "12", "52", "100", "365", "366", "1000"})


def extract_claim_numbers(text: str) -> List[str]:
    """Extract quantitative number tokens from claim text (normalized to ASCII).

    Excludes 4-digit calendar years (1900-2099) when used in temporal contexts
    (e.g. '2024\u5e74', 'in 2024', 'FY2023'), while preserving real quantities
    (e.g. '2000 jobs', '2000\u4eba', '1980 points', '$1950').
    If all extracted numbers in a claim are temporal years, falls back to auditing the year.
    """
    norm = unicodedata.normalize("NFKC", text)
    norm = re.sub(r"(?<=\d),(?=\d)", "", norm)

    raw_matches = list(re.finditer(r"\d+(?:\.\d+)?", norm))
    if not raw_matches:
        return []

    quantities: List[str] = []
    all_nums: List[str] = []

    for m in raw_matches:
        val = m.group(0)
        all_nums.append(val)
        start, end = m.start(), m.end()

        is_year_range = len(val) == 4 and val.isdigit() and 1900 <= int(val) <= 2099
        if is_year_range:
            before = norm[:start]
            after = norm[end:]

            has_quantity_unit = bool(
                re.match(
                    r"^\s*(?:jobs|people|workers|positions|\u4eba|\u4ef6|\u5186|dollars|units|\u53f0|\u793e|\u500b|\u540d|\u672c|\u4e07|\u5104|pts|points|shares|votes|users|contracts)\b",
                    after,
                    re.I,
                )
            )
            has_preceding_cue = bool(
                re.search(
                    r"(?:\b(?:in|year|since|from|by|during|fy|fiscal|q[1-4]|h[1-2])\s*|\b(?:\u5e73\u6210|\u4ee4\u548c)\s*)$",
                    before,
                    re.I,
                )
            )
            has_following_cue = bool(
                re.match(
                    r"^\s*(?:\u5e74|\u5e74\u5ea6|\u5e74\u4ee3|q[1-4]\b|fy\b|fiscal\b|[-/.](?:0[1-9]|1[0-2])\b)",
                    after,
                    re.I,
                )
            )
            if (has_preceding_cue or has_following_cue) and not has_quantity_unit:
                continue

        quantities.append(val)

    return quantities if quantities else all_nums


def check_claim_numbers(claim: Claim, quotes: Sequence[str]) -> List[str]:
    """Verify that numbers asserted in claim.text appear in confirmed evidence quotes.

    If claim.derived is True, numbers may be calculated from evidence, but:
    1. Central claims cannot be derived (must be directly stated by primary sources).
    2. claim.derivation must be non-empty and contain numeric calculation inputs.
    3. Input numbers on LHS of claim.derivation must appear in confirmed quotes
       (common scaling constants such as 100 or 12 are excluded).
    """
    if claim.kind is not ClaimKind.NUMBER:
        return []

    merged_quotes = " ".join(normalize_for_quote_match(q) for q in quotes if q.strip())
    merged_quotes = re.sub(r"(?<=\d),(?=\d)", "", merged_quotes)

    if claim.derived:
        if claim.weight is ClaimWeight.CENTRAL:
            return [
                "central claims cannot be derived; central claims require direct verbatim primary source verification (downgrade weight to supporting or minor if calculated)"
            ]
        if not (claim.derivation and claim.derivation.strip()):
            return ["derived number claim requires non-empty derivation formula or explanation"]

        formula = claim.derivation.strip()
        parts = re.split(r"\s*(?:=|\u2248|~|->|\u2192|=>)\s*", formula, maxsplit=1)
        lhs = parts[0] if len(parts) > 1 else formula
        lhs_nums = extract_claim_numbers(lhs)
        if not lhs_nums:
            return ["derived claim formula must contain numeric inputs (e.g. '($85B - $60B) / $60B = 42%')"]

        empirical_inputs = [n for n in lhs_nums if n not in MATH_CONSTANTS]
        inputs_to_verify = empirical_inputs if empirical_inputs else lhs_nums

        missing_inputs: List[str] = []
        for n in sorted(set(inputs_to_verify)):
            pattern = rf"(?<![\d.]){re.escape(n)}(?!\.?\d)"
            if not re.search(pattern, merged_quotes):
                missing_inputs.append(n)

        if missing_inputs:
            return [
                f"derivation input number '{m}' not found in confirmed quotes"
                for m in missing_inputs
            ]
        return []

    nums = extract_claim_numbers(claim.text)
    if not nums:
        return []

    missing: List[str] = []
    for n in nums:
        # Require numeric token boundary (neither preceded by digits/dot nor followed by dot-then-digit or digits)
        pattern = rf"(?<![\d.]){re.escape(n)}(?!\.?\d)"
        if not re.search(pattern, merged_quotes):
            missing.append(n)

    if missing:
        return [
            f"number '{m}' in claim text not found in confirmed quotes (set derived=true if calculated)"
            for m in missing
        ]
    return []


def required_primary_sources(claim: Claim) -> int:
    """Central claims need 2 independent primary sources; others need 1 source."""
    return 2 if claim.weight is ClaimWeight.CENTRAL else 1


def verdict_for(claim: Claim, quote_errors: Sequence[str] = ()) -> ClaimResult:
    """Deterministic verdict. Any contradiction from tier<=2 refutes; missing proof is UNVERIFIED."""
    q_errors = list(quote_errors)
    if q_errors:
        return ClaimResult(
            claim,
            Verdict.UNVERIFIED,
            f"quote check failed: {'; '.join(q_errors)}",
            quote_errors=q_errors,
        )
    if claim.kind in NON_CHECKABLE_KINDS:
        return ClaimResult(claim, Verdict.OPINION, f"{claim.kind.value}; not fact-checked")
    contradicts = [
        e for e in claim.evidence
        if e.stance is Stance.CONTRADICTS and enforce_source_tier(e.url, e.tier) <= 2
    ]
    if contradicts:
        return ClaimResult(claim, Verdict.REFUTED, f"contradicted by {contradicts[0].url}")
    confirms = [e for e in claim.evidence if e.stance is Stance.CONFIRMS and e.quote.strip()]
    if confirms and claim.kind is ClaimKind.NUMBER:
        # For central claims, check numbers strictly against verified primary evidence quotes
        if claim.weight is ClaimWeight.CENTRAL:
            primary_confirms = [
                e for e in confirms
                if enforce_source_tier(e.url, e.tier) == 1 and bool(e.source_id)
            ]
            check_quotes = [e.quote for e in primary_confirms]
        else:
            check_quotes = [e.quote for e in confirms]
        num_errors = check_claim_numbers(claim, check_quotes)
        if num_errors:
            return ClaimResult(
                claim,
                Verdict.UNVERIFIED,
                f"number check failed: {'; '.join(num_errors)}",
                quote_errors=num_errors,
            )
    need = required_primary_sources(claim)
    if claim.weight is ClaimWeight.CENTRAL:
        # Central claims strictly require linked disk sources (source_id),
        # NEVER accepting manual override alone, and require deduplication
        # across >= 2 independent primary institutions.
        primary = {
            primary_authority_key(e)
            for e in confirms
            if enforce_source_tier(e.url, e.tier) == 1 and bool(e.source_id)
        }
        if len(primary) >= need:
            return ClaimResult(claim, Verdict.SUPPORTED, f"{len(primary)} primary sources")
        return ClaimResult(
            claim, Verdict.UNVERIFIED, f"central claim needs {need} primary sources, has {len(primary)}"
        )
    if len({primary_authority_key(e) for e in confirms}) >= need:
        return ClaimResult(claim, Verdict.SUPPORTED, "sourced")
    return ClaimResult(claim, Verdict.UNVERIFIED, "no confirming evidence with quote")


def audit(claims: Sequence[Claim]) -> List[ClaimResult]:
    return [verdict_for(c) for c in claims]


def gate_failures(results: Sequence[ClaimResult]) -> List[ClaimResult]:
    """Results that must block rendering: refuted anything, quote errors, or non-supported central claims."""
    return [
        r
        for r in results
        if r.verdict is Verdict.REFUTED
        or bool(r.quote_errors)
        or (r.claim.weight is ClaimWeight.CENTRAL and r.verdict is Verdict.UNVERIFIED)
    ]


def claims_to_json(claims: Sequence[Claim]) -> str:
    return json.dumps([asdict(c) for c in claims], ensure_ascii=False, indent=2)


def claims_from_json(raw: str) -> List[Claim]:
    data: List[Dict[str, Any]] = json.loads(raw)
    out: List[Claim] = []
    for d in data:
        ev: List[Evidence] = []
        for e in d.get("evidence", []):
            ev.append(
                Evidence(
                    url=str(e.get("url", "")),
                    quote=str(e.get("quote", "")),
                    stance=Stance(e["stance"]),
                    tier=int(e.get("tier", 2)),
                    page=int(e["page"]) if e.get("page") is not None else None,
                    retrieved_at=str(e.get("retrieved_at", "")),
                    source_id=str(e.get("source_id", "")),
                    sha256=str(e.get("sha256", "")),
                    manual=bool(e.get("manual", False)),
                )
            )
        out.append(
            Claim(
                id=d["id"],
                cut_index=int(d["cut_index"]),
                text=d["text"],
                kind=ClaimKind(d.get("kind", "number")),
                weight=ClaimWeight(d.get("weight", "minor")),
                evidence=ev,
                derived=bool(d.get("derived", False)),
                derivation=str(d.get("derivation", "")),
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
