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
from veraxi_ymmp.core.ports import (
    DocumentCaptureResult as DocumentCaptureResult,
    DocumentCaptureSpec as DocumentCaptureSpec,
    DocumentProvenance as DocumentProvenance,
    DocumentSourceType as DocumentSourceType,
)
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse
from pydantic import TypeAdapter
import tldextract

from veraxi_ymmp.epistemic.epistemic_units import (
    _PINT_ENV,
    _UREG,
    MULTIPLIERS_EN,
    MULTIPLIERS_JP,
    MULTIPLIERS_SI,
    eval_safe_arithmetic,
    eval_safe_quantity,
    extract_dominant_unit,
    extract_content_lemmas,
    has_clause_negation,
    extract_salient_figures,
    extract_scaled_magnitudes,
    extract_token_magnitudes,
)

__all__ = [
    "EpistemicProfile", "ClaimKind", "NON_CHECKABLE_KINDS", "ClaimWeight",
    "Stance", "Verdict", "Evidence", "Claim",
    "ClaimResult", "canonical_institution", "is_primary_authority_url", "enforce_source_tier",
    "normalize_for_quote_match", "verify_quote_in_source", "has_grammatical_negation", "compute_deterministic_grounding",
    "extract_scoped_table_scale", "extract_claim_numbers", "extract_timeseries_observation", "check_claim_numbers",
    "verdict_for", "audit", "gate_failures", "claims_to_json",
    "claims_from_json", "load_claims", "DocumentSourceType", "DocumentCaptureSpec",
    "DocumentProvenance", "DocumentCaptureResult", "ProvenanceRecord", "_UREG",
    "_PINT_ENV", "MULTIPLIERS_JP", "MULTIPLIERS_EN", "MULTIPLIERS_SI",
    "eval_safe_quantity", "eval_safe_arithmetic", "extract_token_magnitudes", "extract_scaled_magnitudes",
    "extract_salient_figures",
]

_TLD_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=())

class EpistemicProfile(str, Enum):
    """Domain epistemic profile defining trust boundaries and allowed Tier 1 authorities."""

    FINANCE = "finance"
    ACADEMIC = "academic"
    GENERAL = "general"
    LORE = "lore"
    TECH = "tech"

class ClaimKind(str, Enum):
    NUMBER = "number"
    DATE = "date"
    QUOTE = "quote"
    FACT = "fact"
    CAUSAL = "causal"
    OPINION = "opinion"
    COMMENTARY = "commentary"

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
    stance: Stance = Stance.CONFIRMS
    tier: int = 2
    page: int | None = None
    retrieved_at: str = ""
    source_id: str = ""
    sha256: str = ""
    manual: bool = False
    as_of: str = ""

@dataclass
class Claim:
    """Atomic verifiable assertion tied to one script cut."""

    id: str
    cut_index: int
    text: str
    kind: ClaimKind = ClaimKind.NUMBER
    weight: ClaimWeight = ClaimWeight.MINOR
    evidence: List[Evidence] = field(default_factory=list)
    derived: bool = False
    derivation: str = ""
    axiom: bool = False

@dataclass
class ClaimResult:
    claim: Claim
    verdict: Verdict
    reason: str
    quote_errors: List[str] = field(default_factory=list)
    grounding_score: float | None = None

def _load_epistemic_registry() -> Tuple[Dict[str, frozenset[str]], Dict[str, Tuple[str, ...]], Dict[str, str]]:
    res_path = Path(__file__).parent.parent / "resources" / "epistemic_registry.json"
    if res_path.is_file():
        try:
            d = json.loads(res_path.read_text(encoding="utf-8"))
            return (
                {k: frozenset(v) for k, v in d.get("authority_hosts", {}).items()},
                {k: tuple(v) for k, v in d.get("authority_domains", {}).items()},
                dict(d.get("primary_institutions", {})),
            )
        except Exception:
            pass
    return {}, {}, {}

_AUTHORITY_HOSTS, _AUTHORITY_DOMAINS, PRIMARY_INSTITUTIONS = _load_epistemic_registry()
FINANCE_AUTHORITY_HOSTS = _AUTHORITY_HOSTS.get("finance", frozenset())
ACADEMIC_AUTHORITY_HOSTS = _AUTHORITY_HOSTS.get("academic", frozenset())
GENERAL_AUTHORITY_HOSTS = _AUTHORITY_HOSTS.get("general", frozenset())
LORE_AUTHORITY_HOSTS = _AUTHORITY_HOSTS.get("lore", frozenset())
TECH_AUTHORITY_HOSTS = _AUTHORITY_HOSTS.get("tech", frozenset())
PRIMARY_AUTHORITY_HOSTS = FINANCE_AUTHORITY_HOSTS

def _is_gov_domain(ext: tldextract.ExtractResult) -> bool:
    s_parts = ext.suffix.lower().split(".")
    if any(p in ("gov", "go", "gob", "gouv", "gv") for p in s_parts):
        return True
    top = (ext.top_domain_under_public_suffix or "").lower()
    return top in ("europa.eu", "bund.de") or ext.suffix.lower() == "int"

def _is_academic_domain(ext: tldextract.ExtractResult) -> bool:
    s_parts = ext.suffix.lower().split(".")
    if any(p in ("edu", "ac") for p in s_parts):
        return True
    top = (ext.top_domain_under_public_suffix or "").lower()
    return top in ("cern", "mpg.de", "cnrs.fr")

def canonical_institution(url: str) -> str:
    """Return canonical institutional identity for primary source deduplication."""
    if not url:
        return ""
    ext = _TLD_EXTRACTOR(url)
    top_domain = ext.top_domain_under_public_suffix.lower() if ext.top_domain_under_public_suffix else ""
    if not top_domain:
        return (urlparse(url).hostname or url.split("/")[0]).lower().removeprefix("www.")
    clean_host = f"{ext.subdomain}.{top_domain}".strip(".").lower() if ext.subdomain else top_domain

    for domain, inst_key in PRIMARY_INSTITUTIONS.items():
        if top_domain == domain or clean_host.endswith("." + domain):
            return inst_key
    return top_domain

_PROFILE_CATEGORY_MAP = {
    EpistemicProfile.FINANCE: {"finance"},
    EpistemicProfile.ACADEMIC: {"academic"},
    EpistemicProfile.GENERAL: {"general", "academic", "finance", "tech"},
    EpistemicProfile.LORE: {"lore"},
    EpistemicProfile.TECH: {"tech", "academic"},
}

_CATEGORY_HOSTS = {
    "finance": FINANCE_AUTHORITY_HOSTS,
    "academic": ACADEMIC_AUTHORITY_HOSTS,
    "general": GENERAL_AUTHORITY_HOSTS,
    "lore": LORE_AUTHORITY_HOSTS,
}

def is_primary_authority_url(
    url: str,
    profile: EpistemicProfile | str = EpistemicProfile.GENERAL,
    extra_primary_domains: Sequence[str] = (),
) -> bool:
    """Return True if URL host is recognized as an official primary authority for profile."""
    if not url:
        return False
    ext = _TLD_EXTRACTOR(url)
    top_domain = (ext.top_domain_under_public_suffix or "").lower()
    clean_host = f"{ext.subdomain}.{top_domain}".strip(".").lower() if ext.subdomain else top_domain
    if not clean_host:
        clean_host = (urlparse(url).hostname or url.split("/")[0]).lower().removeprefix("www.")

    if extra_primary_domains:
        if any(
            top_domain == d.lower() or clean_host == d.lower() or clean_host.endswith("." + d.lower())
            for d in extra_primary_domains
        ):
            return True

    prof = EpistemicProfile(profile) if isinstance(profile, str) else profile

    # Lore strictly requires lore sources (plus extra_primary_domains); no gov/finance bypass
    if prof is not EpistemicProfile.LORE and _is_gov_domain(ext):
        return True

    allowed_categories = _PROFILE_CATEGORY_MAP.get(prof, {"general"})

    if "academic" in allowed_categories and _is_academic_domain(ext):
        return True

    for cat in allowed_categories:
        hosts = _CATEGORY_HOSTS.get(cat, set())
        if clean_host in hosts or top_domain in hosts:
            return True
        domains = _AUTHORITY_DOMAINS.get(cat, ())
        if any(top_domain == d or clean_host.endswith("." + d) for d in domains):
            return True

    return False

def enforce_source_tier(
    url: str,
    declared_tier: int = 2,
    profile: EpistemicProfile | str = EpistemicProfile.FINANCE,
    extra_primary_domains: Sequence[str] = (),
) -> int:
    """Derive/enforce tier against allowlist."""
    if declared_tier == 1:
        if is_primary_authority_url(url, profile=profile, extra_primary_domains=extra_primary_domains):
            return 1
        return 2
    return max(1, declared_tier)

_QUOTE_CHARS = str.maketrans({
    "“": '"', "”": '"', "„": '"', "‘": "'", "’": "'",
    "「": '"', "」": '"', "『": '"', "』": '"', "«": '"', "»": '"',
})

def normalize_for_quote_match(text: str) -> str:
    """Normalize text strictly for verbatim quote matching."""
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
    if re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", norm_q):
        cjk_q = re.sub(r"\s+", "", norm_q.strip('"\''))
        cjk_src = re.sub(r"\s+", "", norm_src)
        if cjk_q and cjk_q in cjk_src:
            return True
    return False

def _load_entity_aliases() -> Dict[str, Tuple[str, ...]]:
    res_path = Path(__file__).parent.parent / "resources" / "entity_aliases.json"
    try:
        return {k: tuple(v) for k, v in json.loads(res_path.read_text(encoding="utf-8")).items()} if res_path.is_file() else {}
    except Exception:
        return {}

ENTITY_ALIASES: Dict[str, Tuple[str, ...]] = _load_entity_aliases()

def has_grammatical_negation(text: str, target_tokens: Sequence[str] = ()) -> bool:
    """Return True if text contains genuine grammatical negation (excluding affirmative idioms)."""
    return has_clause_negation(text, target_tokens=target_tokens)

_POLARITY_CONFLICT_PAIRS = (
    (frozenset({"増加", "急増", "上昇", "拡大", "プラス", "grew", "growth", "rose", "increase", "surged", "higher"}),
     frozenset({"減少", "急減", "低下", "縮小", "マイナス", "fell", "declined", "drop", "decrease", "slump", "lower"})),
    (frozenset({"真実", "事実", "成功", "確実", "承認", "黒字", "true", "accurate", "proven", "approved", "profit"}),
     frozenset({"誤り", "虚偽", "うそ", "嘘", "失敗", "否定", "却下", "赤字", "false", "inaccurate", "debunked", "rejected", "loss"})),
    (frozenset({"安全", "有効", "safe", "effective", "efficacy"}),
     frozenset({"危険", "有害", "無効", "hazardous", "harmful", "ineffective"})),
)

def extract_scoped_table_scale(quote: str, source_texts: Sequence[str] = ()) -> float:
    """Determine table scale (1.0 vs 1e3/1e6/1e8/1e9/1e12) scoped strictly to quote or local context."""
    if not quote:
        return 1.0
    norm_q = unicodedata.normalize("NFKC", quote).lower()
    if "(in trillions)" in norm_q or "in trillions" in norm_q or "兆円" in norm_q:
        return 1e12
    if "(in billions)" in norm_q or "in billions" in norm_q or "十億円" in norm_q:
        return 1e9
    if "億円" in norm_q:
        return 1e8
    if "(in millions)" in norm_q or "in millions" in norm_q or "百万円" in norm_q:
        return 1e6
    if "(in thousands)" in norm_q or "in thousands" in norm_q or "千円" in norm_q or "千人" in norm_q:
        return 1e3
    if any(term in norm_q for term in ("per share", "share", "headcount", "employee", "件", "人")):
        return 1.0
    for st in source_texts:
        if not st:
            continue
        norm_st = unicodedata.normalize("NFKC", str(st)).lower()
        q_pos = norm_st.find(norm_q)
        if q_pos < 0:
            q_clean = re.sub(r"\s+", " ", norm_q).strip()
            st_clean = re.sub(r"\s+", " ", norm_st)
            q_pos = st_clean.find(q_clean)
            if q_pos >= 0:
                norm_st = st_clean
        if q_pos >= 0:
            start_pos = max(0, q_pos - 1500)
            prefix = norm_st[start_pos:q_pos]
            last_tbl = prefix.rfind("</table>")
            if last_tbl >= 0:
                start_pos += last_tbl + 8
            local_win = norm_st[start_pos : min(len(norm_st), q_pos + len(norm_q) + 300)]
            if "(in trillions)" in local_win or "in trillions" in local_win or "兆円" in local_win:
                return 1e12
            if "(in billions)" in local_win or "in billions" in local_win or "十億円" in local_win:
                return 1e9
            if "億円" in local_win:
                return 1e8
            if "(in millions)" in local_win or "in millions" in local_win or "百万円" in local_win:
                return 1e6
            if "(in thousands)" in local_win or "in thousands" in local_win or "千円" in local_win or "千人" in local_win:
                return 1e3
    return 1.0

def compute_deterministic_grounding(
    claim_text: str,
    context_text: str,
    extra_aliases: Optional[Dict[str, Tuple[str, ...]]] = None,
    table_scale: float = 1.0,
) -> float:
    """Compute deterministic lexical grounding score (0.0 to 1.0) between claim and context."""
    if not claim_text or not context_text:
        return 0.0

    norm_claim = unicodedata.normalize("NFKC", claim_text).lower()
    norm_ctx = unicodedata.normalize("NFKC", context_text).lower()

    all_tokens = extract_content_lemmas(norm_claim)

    # Negation clash check scoped to clauses
    claim_nums = re.findall(r"\d+(?:\.\d+)?", norm_claim)
    ctx_nums = re.findall(r"\d+(?:\.\d+)?", norm_ctx)
    shared_nums = set(claim_nums) & set(ctx_nums)
    if shared_nums:
        c_neg = has_clause_negation(norm_claim, target_tokens=list(shared_nums))
        q_neg = has_clause_negation(norm_ctx, target_tokens=list(shared_nums))
        if c_neg != q_neg:
            return 0.0

    c_mags = extract_scaled_magnitudes(norm_claim)
    q_mags = extract_scaled_magnitudes(norm_ctx, table_scale=table_scale)
    if c_mags and q_mags:
        matching_mags = [
            cm for cm in c_mags
            if any(abs(cm - qm) / max(cm, qm, 1.0) < 0.05 for qm in q_mags)
        ]
        if matching_mags:
            c_neg = has_clause_negation(norm_claim, target_tokens=claim_nums)
            q_neg = has_clause_negation(norm_ctx, target_tokens=claim_nums)
            if c_neg != q_neg:
                return 0.0

    k_tokens = [t for t in all_tokens if re.search(r"[\u4e00-\u9fff\u30a0-\u30ff]", t)]
    shared_k = [kt for kt in k_tokens if kt in norm_ctx]
    if shared_k:
        c_neg = has_clause_negation(norm_claim, target_tokens=shared_k)
        q_neg = has_clause_negation(norm_ctx, target_tokens=shared_k)
        if c_neg != q_neg:
            return 0.0

    active_aliases = dict(ENTITY_ALIASES)
    if extra_aliases:
        active_aliases.update(extra_aliases)
    for a_k, a_vals in active_aliases.items():
        if a_k in norm_claim and any(av in norm_ctx for av in a_vals):
            c_neg = has_clause_negation(norm_claim, target_tokens=[a_k])
            q_neg = has_clause_negation(norm_ctx, target_tokens=list(a_vals))
            if c_neg != q_neg:
                return 0.0

    # Polarity clash check
    for pos_set, neg_set in _POLARITY_CONFLICT_PAIRS:
        c_pos, c_neg_p = any(p in norm_claim for p in pos_set), any(n in norm_claim for n in neg_set)
        q_pos, q_neg_p = any(p in norm_ctx for p in pos_set), any(n in norm_ctx for n in neg_set)
        if (c_pos and not c_neg_p and q_neg_p and not q_pos) or (c_neg_p and not c_pos and q_pos and not q_neg_p):
            return 0.0

    if not all_tokens:
        return 1.0 if norm_claim in norm_ctx else 0.5

    claim_token_mags = extract_token_magnitudes(norm_claim)
    quote_mags = extract_scaled_magnitudes(norm_ctx, table_scale=table_scale)
    ctx_lemmas = set(extract_content_lemmas(norm_ctx))

    matched = 0
    for t in all_tokens:
        if t in norm_ctx or t in ctx_lemmas:
            matched += 1
        elif t in claim_token_mags and quote_mags:
            if any(any(abs(cm - qm) / max(cm, qm, 1.0) < 0.05 for qm in quote_mags) for cm in claim_token_mags[t]):
                matched += 1

    active_aliases = dict(ENTITY_ALIASES)
    if extra_aliases:
        active_aliases.update(extra_aliases)

    for alias_key, expansions in active_aliases.items():
        if alias_key in norm_claim and any(exp in norm_ctx for exp in expansions):
            if not any(t in norm_ctx for t in all_tokens if t in alias_key):
                matched += 1

    return min(1.0, round(matched / len(all_tokens), 2))

def primary_authority_key(e: Evidence) -> str:
    """Canonical identifier for deduplicating primary sources across distinct institutions."""
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

MATH_CONSTANTS = frozenset({"1", "2", "4", "10", "12", "52", "100", "365", "366", "1000"})

def extract_claim_numbers(text: str) -> List[str]:
    """Extract quantitative number tokens from claim text (normalized to ASCII).

    Excludes 4-digit calendar years (1900-2099) when used in temporal contexts
    (e.g. '2024年', 'in 2024', 'FY2023'), while preserving real quantities.
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
                    r"^\s*(?:jobs|people|workers|positions|人|件|円|dollars|units|台|社|個|名|本|万|億|pts|points|shares|votes|users|contracts)\b",
                    after,
                    re.I,
                )
            )
            has_preceding_cue = bool(
                re.search(
                    r"(?:\b(?:in|year|since|from|by|during|fy|fiscal|q[1-4]|h[1-2])\s*|\b(?:平成|令和)\s*)$",
                    before,
                    re.I,
                )
            )
            has_following_cue = bool(
                re.match(
                    r"^\s*(?:年|年度|年代|q[1-4]\b|fy\b|fiscal\b|[-/.](?:0[1-9]|1[0-2])\b)",
                    after,
                    re.I,
                )
            )
            if (has_preceding_cue or has_following_cue) and not has_quantity_unit:
                continue

        quantities.append(val)

    return quantities if quantities else all_nums

def extract_timeseries_observation(csv_or_text: str, as_of: str = "latest") -> Tuple[str, str]:
    """Extract (date, value) observation from time series CSV content."""
    if not csv_or_text:
        return "", ""
    matches = re.findall(r"\b(\d{4}-\d{2}-\d{2})[,\s]+([0-9]+(?:\.[0-9]+)?)\b", csv_or_text)
    if not matches:
        return "", ""
    if not as_of or as_of.lower() == "latest":
        return matches[-1]
    target = as_of.strip()
    candidates = [m for m in matches if m[0] <= target]
    return candidates[-1] if candidates else matches[0]

def check_claim_numbers(claim: Claim, quotes: Sequence[str], source_texts: Sequence[str] = ()) -> List[str]:
    """Verify that numbers asserted in claim.text appear in confirmed evidence quotes."""
    if claim.kind in NON_CHECKABLE_KINDS:
        return []

    all_texts = list(quotes)
    merged_quotes = " ".join(normalize_for_quote_match(q) for q in all_texts if q.strip())
    merged_quotes = re.sub(r"(\d{4}-\d{2}-\d{2}),", r"\1 ", merged_quotes)
    merged_quotes = re.sub(r"(?<=\d),(?=\d)", "", merged_quotes)
    table_scale = max([extract_scoped_table_scale(q, source_texts) for q in (list(quotes) or [""])], default=1.0)

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
        rhs = parts[1] if len(parts) > 1 else ""
        lhs_nums = extract_claim_numbers(lhs)
        if not lhs_nums:
            return ["derived claim formula must contain numeric inputs (e.g. '($85B - $60B) / $60B = 42%')"]

        claim_has_match = False
        rhs_val: Optional[float] = None
        if rhs:
            lhs_qty = eval_safe_quantity(lhs)
            rhs_qty = eval_safe_quantity(rhs)
            if lhs_qty is not None:
                lhs_has_units = hasattr(lhs_qty, "units")
                rhs_has_units = hasattr(rhs_qty, "units") if rhs_qty is not None else False

                if lhs_has_units and rhs_has_units:
                    if not lhs_qty.is_compatible_with(rhs_qty):
                        return [f"derived claim formula '{formula}' unit mismatch: LHS ({lhs_qty.units}) is incompatible with RHS ({rhs_qty.units})"]
                    rhs_conv = rhs_qty.to(lhs_qty.units)
                    lhs_val = float(lhs_qty.magnitude)
                    rhs_val = float(rhs_conv.magnitude)
                elif lhs_has_units and not rhs_has_units:
                    dominant_c_unit = extract_dominant_unit(claim.text)
                    if dominant_c_unit is not None and not lhs_qty.is_compatible_with(dominant_c_unit):
                        return [f"derived claim formula '{formula}' unit mismatch: LHS ({lhs_qty.units}) is incompatible with unit in claim text ({dominant_c_unit})"]
                    lhs_val = float(lhs_qty.magnitude)
                    rhs_val = float(getattr(rhs_qty, "magnitude", rhs_qty)) if rhs_qty is not None else float(lhs_val)
                elif not lhs_has_units and rhs_has_units:
                    dominant_c_unit = extract_dominant_unit(claim.text)
                    if dominant_c_unit is not None and not rhs_qty.is_compatible_with(dominant_c_unit):
                        return [f"derived claim formula '{formula}' unit mismatch: RHS ({rhs_qty.units}) is incompatible with unit in claim text ({dominant_c_unit})"]
                    lhs_val = float(getattr(lhs_qty, "magnitude", lhs_qty))
                    rhs_val = float(rhs_qty.magnitude)
                else:
                    lhs_val = float(getattr(lhs_qty, "magnitude", lhs_qty))
                    rhs_val = float(getattr(rhs_qty, "magnitude", rhs_qty)) if rhs_qty is not None else float(lhs_val)

                tolerance = 0.05 if ("~" in formula or "\u2248" in formula) else 0.01
                diff = abs(lhs_val - rhs_val) / max(abs(lhs_val), abs(rhs_val), 1.0)
                if diff > tolerance:
                    return [f"derived claim formula '{formula}' math mismatch: LHS evaluates to {lhs_val:g}, but RHS asserts {rhs_val:g}"]
                c_nums = extract_claim_numbers(claim.text)
                c_mags = extract_scaled_magnitudes(claim.text)
                claim_has_match = any(abs(rhs_val - cm) / max(abs(rhs_val), abs(cm), 1.0) < 0.05 for cm in c_mags)
                if not claim_has_match:
                    for cn in c_nums:
                        try:
                            cn_f = float(cn)
                            if abs(rhs_val - cn_f) / max(abs(rhs_val), abs(cn_f), 1.0) < 0.05:
                                claim_has_match = True
                                break
                        except ValueError:
                            pass
            elif lhs_qty is None:
                return [f"derived claim formula '{formula}' contains incompatible units or invalid syntax"]

        empirical_inputs = [n for n in lhs_nums if n not in MATH_CONSTANTS]
        inputs_to_verify = empirical_inputs if empirical_inputs else lhs_nums

        quote_floats = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", merged_quotes)]
        quote_mags = extract_scaled_magnitudes(merged_quotes, table_scale=table_scale)
        lhs_mags = extract_token_magnitudes(lhs)
        missing_inputs: List[str] = []
        for n in sorted(set(inputs_to_verify)):
            pattern = rf"(?<![\d.]){re.escape(n)}(?!\.?\d)"
            if re.search(pattern, merged_quotes):
                continue
            if n in lhs_mags and quote_mags:
                if any(any(abs(lm - qm) / max(lm, qm, 1.0) < 0.05 for qm in quote_mags) for lm in lhs_mags[n]):
                    continue
            try:
                n_f = float(n)
                if any(abs(n_f - qf) / max(abs(n_f), abs(qf), 1.0) < 0.05 for qf in quote_floats):
                    continue
            except ValueError:
                pass
            missing_inputs.append(n)

        derivation_errors: List[str] = []
        if missing_inputs:
            derivation_errors.extend([
                f"derivation input number '{m}' not found in confirmed quotes"
                for m in missing_inputs
            ])
        return derivation_errors

    nums = extract_claim_numbers(claim.text)
    if not nums:
        if re.search(
            r"([$¥€£ドル円億万兆%％]|\b(?:billion|million|trillion|thousand|percent|bps)\b|\bper\s+(?:user|month|year|share|person)\b|\s{2,})",
            claim.text,
            re.I,
        ):
            return ["numeric claim contains scale/rate/currency unit but no valid numbers (corrupted text or missing numeric values)"]
        return []

    claim_token_mags = extract_token_magnitudes(claim.text)
    quote_mags = extract_scaled_magnitudes(merged_quotes, table_scale=table_scale)

    missing: List[str] = []
    for n in nums:
        if n in claim_token_mags:
            matched_mag = False
            for cm in claim_token_mags[n]:
                for qm in quote_mags:
                    if abs(cm - qm) / max(cm, qm, 1.0) < 0.05:
                        matched_mag = True
                        break
                if matched_mag:
                    break
            if not matched_mag:
                missing.append(n)
        else:
            pattern = rf"(?<![\d.]){re.escape(n)}(?!\.?\d)"
            if re.search(pattern, merged_quotes):
                continue
            if n == "1" and (
                re.search(r"\bper\s+(?:user|month|share|person|customer|day|year|annum|unit|employee)\b", merged_quotes, re.I)
                or re.search(r"(?:1人あたり|一人当たり|1日あたり|一日当たり|1ヶ月あたり|1年あたり)", claim.text)
            ):
                continue
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

def verdict_for(
    claim: Claim,
    quote_errors: Sequence[str] = (),
    profile: EpistemicProfile | str = EpistemicProfile.FINANCE,
    source_texts: Sequence[str] = (),
    extra_primary_domains: Sequence[str] = (),
) -> ClaimResult:
    """Deterministic verdict. Contradiction from tier<=2 refutes; missing proof is UNVERIFIED."""
    if getattr(claim, "axiom", False):
        if claim.weight is ClaimWeight.CENTRAL:
            return ClaimResult(
                claim,
                Verdict.UNVERIFIED,
                "central claim cannot be bypassed as an axiom; requires Tier 1 primary sources",
                quote_errors=["central claim cannot be designated as axiom"],
            )
        return ClaimResult(claim, Verdict.SUPPORTED, "axiom / common knowledge")

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
        e
        for e in claim.evidence
        if e.stance is Stance.CONTRADICTS and enforce_source_tier(e.url, e.tier, profile=profile, extra_primary_domains=extra_primary_domains) <= 2
    ]
    if contradicts:
        return ClaimResult(claim, Verdict.REFUTED, f"contradicted by {contradicts[0].url}")
    confirms = [e for e in claim.evidence if e.stance is Stance.CONFIRMS and e.quote.strip()]
    if confirms and claim.kind not in NON_CHECKABLE_KINDS:
        has_numbers = bool(extract_claim_numbers(claim.text)) or bool(extract_token_magnitudes(claim.text))
        if has_numbers or claim.kind is ClaimKind.NUMBER:
            if claim.weight is ClaimWeight.CENTRAL:
                primary_confirms = [
                    e
                    for e in confirms
                    if enforce_source_tier(e.url, e.tier, profile=profile, extra_primary_domains=extra_primary_domains) == 1 and bool(e.source_id)
                ]
                check_quotes = [e.quote for e in primary_confirms]
            else:
                check_quotes = [e.quote for e in confirms]
            num_errors = check_claim_numbers(claim, check_quotes, source_texts=source_texts)
            if num_errors:
                return ClaimResult(
                    claim,
                    Verdict.UNVERIFIED,
                    f"number check failed: {'; '.join(num_errors)}",
                    quote_errors=num_errors,
                )
    need = required_primary_sources(claim)
    if claim.weight is ClaimWeight.CENTRAL:
        primary_ev = [
            e for e in confirms
            if enforce_source_tier(e.url, e.tier, profile=profile, extra_primary_domains=extra_primary_domains) == 1 and bool(e.source_id)
        ]
        if claim.derived:
            formula = claim.derivation.strip() if claim.derivation else ""
            parts = re.split(r"\s*(?:=|≈|~|->|→|=>)\s*", formula, maxsplit=1)
            lhs = parts[0] if len(parts) > 1 else formula
            lhs_nums = extract_claim_numbers(lhs)
            lhs_mags = extract_scaled_magnitudes(lhs)
            active_primary = set()
            doc_scale = max([extract_scoped_table_scale(ev.quote, source_texts) for ev in primary_ev], default=1.0)
            for e in primary_ev:
                eq_norm = normalize_for_quote_match(e.quote)
                eq_mags = extract_scaled_magnitudes(eq_norm, table_scale=doc_scale)
                eq_nums = extract_claim_numbers(eq_norm)
                contributes = any(
                    any(abs(lm - qm) / max(lm, qm, 1.0) < 0.05 for qm in eq_mags)
                    for lm in lhs_mags
                ) or any(
                    n not in MATH_CONSTANTS and (n in eq_nums or re.search(rf"(?<![\d.]){re.escape(n)}(?!\.?\d)", eq_norm))
                    for n in lhs_nums
                )
                if contributes:
                    active_primary.add(primary_authority_key(e))
            if len(active_primary) >= need:
                return ClaimResult(claim, Verdict.SUPPORTED, f"{len(active_primary)} primary sources (derived)")
            return ClaimResult(
                claim,
                Verdict.UNVERIFIED,
                f"derived central claim requires {need} distinct primary authorities contributing to derivation LHS, has {len(active_primary)}",
                quote_errors=[f"derived central claim requires {need} distinct primary authorities contributing to derivation LHS, has {len(active_primary)}"],
            )
        primary = {primary_authority_key(e) for e in primary_ev}
        if len(primary) >= need:
            return ClaimResult(claim, Verdict.SUPPORTED, f"{len(primary)} primary sources")
        return ClaimResult(
            claim, Verdict.UNVERIFIED, f"central claim needs {need} primary sources, has {len(primary)}"
        )
    if len({primary_authority_key(e) for e in confirms}) >= need:
        return ClaimResult(claim, Verdict.SUPPORTED, "sourced")
    return ClaimResult(claim, Verdict.UNVERIFIED, "no confirming evidence with quote")

def audit(
    claims: Sequence[Claim],
    profile: EpistemicProfile | str = EpistemicProfile.FINANCE,
) -> List[ClaimResult]:
    return [verdict_for(c, profile=profile) for c in claims]

def gate_failures(results: Sequence[ClaimResult]) -> List[ClaimResult]:
    """Results that must block rendering: refuted anything, or non-supported central claims."""
    return [
        r
        for r in results
        if r.verdict is Verdict.REFUTED
        or bool(r.quote_errors)
        or (r.claim.weight is ClaimWeight.CENTRAL and r.verdict is Verdict.UNVERIFIED)
    ]

def claims_to_json(claims: Sequence[Claim]) -> str:
    return json.dumps([asdict(c) for c in claims], ensure_ascii=False, indent=2)

_CLAIM_LIST_ADAPTER: TypeAdapter[List[Claim]] = TypeAdapter(List[Claim])

def claims_from_json(raw: str) -> List[Claim]:
    data = json.loads(raw)
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "axiom" not in item and "common_knowledge" in item:
                item["axiom"] = item["common_knowledge"]
    return _CLAIM_LIST_ADAPTER.validate_python(data)

def load_claims(path: Path) -> List[Claim]:
    return claims_from_json(path.read_text(encoding="utf-8"))


@dataclass
class ProvenanceRecord:
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
        if str(data.get("schema_version", "")) != "1.0":
            raise ValueError(f"Unsupported provenance schema_version: {data.get('schema_version')}")
        return _PROVENANCE_RECORD_ADAPTER.validate_python(data)

_PROVENANCE_RECORD_ADAPTER: TypeAdapter[ProvenanceRecord] = TypeAdapter(ProvenanceRecord)
