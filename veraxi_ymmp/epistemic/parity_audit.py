"""Visual/metadata parity auditing, check-worthiness classification, and proof-card helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from veraxi_ymmp.epistemic.facts import (
    Claim,
    ClaimKind,
    ClaimResult,
    ClaimWeight,
    EpistemicProfile,
    Evidence,
    Stance,
    Verdict,
    compute_deterministic_grounding,
    enforce_source_tier,
    eval_safe_arithmetic,
    extract_scaled_magnitudes,
    extract_token_magnitudes,
    primary_authority_key,
    verdict_for,
)


def _check_macro_parity(
    raw_text: str,
    claim_id: str,
    label_prefix: str,
    filename: str,
    approved_mags: Sequence[float],
) -> List[ClaimResult]:
    """Check macro figures (>= 1e8) in visual/metadata text against approved claim magnitudes."""
    out: List[ClaimResult] = []
    tok_mags = extract_token_magnitudes(raw_text)
    for tok, vals in tok_mags.items():
        for v in vals:
            if v >= 1e8 and not any(abs(v - av) / max(v, av, 1.0) < 0.05 for av in approved_mags):
                cl = Claim(
                    id=claim_id,
                    cut_index=0,
                    text=f"{label_prefix} '{tok}' ({v:g})",
                    kind=ClaimKind.NUMBER,
                    weight=ClaimWeight.MINOR,
                )
                out.append(
                    ClaimResult(
                        claim=cl,
                        verdict=Verdict.UNVERIFIED,
                        reason=(
                            f"{filename} contains quantitative figure '{tok}' ({v:g}) "
                            "which contradicts verified claims in claims.json"
                        ),
                    )
                )
    return out


def audit_visual_and_metadata_parity(
    project_dir: Path,
    claims: Sequence[Claim],
    sources: Dict[str, Any],
    results: Optional[Sequence[ClaimResult]] = None,
    profile: Optional[EpistemicProfile | str] = None,
    extra_primary_domains: Sequence[str] = (),
) -> List[ClaimResult]:
    """Verify that financial figures in broll_manifest, thumbnail_config, and youtube_metadata match claims.json."""
    if results is not None:
        supported_claim_ids = {r.claim.id for r in results if r.verdict is Verdict.SUPPORTED and not r.quote_errors}
    else:
        active_profile = EpistemicProfile(profile) if profile else EpistemicProfile.FINANCE
        distinct_tier1_authorities = {
            primary_authority_key(Evidence(url=getattr(src, "url", ""), quote="", tier=1, source_id=sid))
            for sid, src in sources.items()
            if getattr(src, "url", "")
            and enforce_source_tier(
                getattr(src, "url", ""), 1, profile=active_profile, extra_primary_domains=extra_primary_domains
            ) == 1
        }
        single_tier1_project = len(distinct_tier1_authorities) == 1
        supported_claim_ids = {
            c.id for c in claims
            if verdict_for(
                c,
                profile=active_profile,
                extra_primary_domains=extra_primary_domains,
                single_primary_ok=single_tier1_project or any(
                    e.stance is Stance.CONFIRMS
                    and e.source_id
                    and e.source_id in sources
                    and getattr(sources[e.source_id], "provenance", "") == "notebooklm_evidence"
                    for e in c.evidence
                ),
            ).verdict is Verdict.SUPPORTED
        }

    approved_mags: List[float] = []
    for c in claims:
        if c.id not in supported_claim_ids:
            continue
        c_text = c.text + (" " + c.derivation if c.derived and c.derivation else "")
        approved_mags.extend(extract_scaled_magnitudes(c_text))
        for e in c.evidence:
            if e.quote:
                approved_mags.extend(extract_scaled_magnitudes(e.quote))
        if c.derived and c.derivation:
            parts = re.split(r"\s*(?:=|≈|~|->|→|=>)\s*", c.derivation.strip(), maxsplit=1)
            lhs_val = eval_safe_arithmetic(parts[0])
            if lhs_val is not None:
                approved_mags.append(lhs_val)
            for sub_expr in re.findall(r"\([^)]+\)", c.derivation):
                sub_val = eval_safe_arithmetic(sub_expr)
                if sub_val is not None:
                    approved_mags.append(sub_val)

    blockers: List[ClaimResult] = []

    for fname, cid, prefix in (
        ("broll_manifest.json", "parity_broll_mismatch", "B-roll figure"),
        ("thumbnail_config.json", "parity_thumbnail_mismatch", "Thumbnail figure"),
    ):
        fpath = project_dir / fname
        if fpath.is_file():
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
                raw_text = json.dumps(data, ensure_ascii=False)
                blockers.extend(_check_macro_parity(raw_text, cid, prefix, fname, approved_mags))
            except Exception:
                pass

    for meta_name in ("youtube_metadata.json", "youtube_metadata.txt"):
        meta_p = project_dir / meta_name
        if meta_p.is_file():
            try:
                m_text = meta_p.read_text(encoding="utf-8", errors="replace")
                blockers.extend(
                    _check_macro_parity(
                        m_text, f"parity_{meta_name}_mismatch", "YouTube metadata figure", meta_name, approved_mags
                    )
                )
            except Exception:
                pass

    return blockers


# --- Check-worthiness classification & claim drafting ---

_UNITS_PATTERN = (
    r"\b(?:gw|mw|kw|tw|w|tb|gb|mb|kb|pb|nm|um|mm|km|ghz|mhz|khz|hz|"
    r"kg|mg|ug|kcal|fps|bps|billion|million|trillion|thousand)\b"
)
_FACT_SIGNAL = re.compile(
    rf"[0-9０-９]|[億兆万]|[%％]|[$¥€£]|ドル|円|ユーロ|ポンド|年間|四半期|決算|シェア|倍|半額|半分|倍増|半減|"
    rf"\d+\s*分の\s*\d+|ギガワット|メガワット|テラバイト|ギガバイト|ナノメートル|{_UNITS_PATTERN}",
    re.I,
)
_REACTION_END = re.compile(r"[！？!?…]+$")
_MAX_REACTION_LEN = 12
_CONCRETE_NUM_PATT = re.compile(
    rf"[0-9０-９]+(?:\.[0-9０-９]+)?\s*(?:[億兆万%％倍$¥€£ドル円]|{_UNITS_PATTERN})|"
    r"\d+\s*分の\s*\d+|半額|半分|倍増|半減",
    re.I,
)
_DECLARATIVE_JP_END = re.compile(r"(?:です|だ|である|ました|だった|となる|となった|と言われています|とされています)[。.]?$")
_DECLARATIVE_EN_END = re.compile(r"[a-zA-Z0-9)]\.$")


def classify_text(
    text: str,
    extract_qualitative: bool = False,
    strict_numbers: bool = False,
) -> ClaimKind | None:
    """Return the claim kind, or None when the cut contains nothing to fact-check."""
    stripped = text.strip()
    if not stripped:
        return None
    if len(stripped) <= _MAX_REACTION_LEN and _REACTION_END.search(stripped):
        return ClaimKind.COMMENTARY
    if strict_numbers:
        if _CONCRETE_NUM_PATT.search(stripped):
            return ClaimKind.NUMBER
        return None
    if _FACT_SIGNAL.search(stripped):
        return ClaimKind.NUMBER
    if extract_qualitative and len(stripped) >= 10:
        if _DECLARATIVE_JP_END.search(stripped) or _DECLARATIVE_EN_END.search(stripped):
            return ClaimKind.FACT
    return None


def extract_draft_claims(
    script: Sequence[Dict[str, Any]],
    existing: Sequence[Claim] = (),
    extract_qualitative: bool = False,
    strict_numbers: bool = False,
) -> List[Claim]:
    """Draft claims for factual dialogue cuts, keeping any existing human-curated claims."""
    known = {(c.cut_index, c.text) for c in existing}
    next_id = len(existing) + 1
    drafts: List[Claim] = []
    for idx, entry in enumerate(script):
        text = entry.get("text")
        if not isinstance(text, str) or ("type" in entry and "character" not in entry):
            continue
        kind = classify_text(text, extract_qualitative=extract_qualitative, strict_numbers=strict_numbers)
        if kind not in (ClaimKind.NUMBER, ClaimKind.FACT) or (idx, text) in known:
            continue
        drafts.append(Claim(f"d{next_id:02d}", idx, text, kind, ClaimWeight.MINOR))
        next_id += 1
    return list(existing) + drafts


# --- Veraxi Proof Card & Grounding Helpers ---

_PASSAGES = re.compile(r"\((\d+)\s+passages?\s+retrieved\)")
_ROW = re.compile(r"^\|\s*(\d+)\s*\|(?P<doc>[^|]*)\|(?P<loc>[^|]*)\|(?P<quote>.*)\|\s*$")
_PAGE = re.compile(r"(?:p\.?|page)\s*(\d+)", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s)\]>]+")


def parse_proof_card(card: str, tier: int = 2, retrieved_at: str = "") -> List[Evidence]:
    """Parse a proof card into confirming Evidence; returns [] for vacuous/empty cards."""
    m = _PASSAGES.search(card)
    if not m or int(m.group(1)) == 0:
        return []
    out: List[Evidence] = []
    for line in card.splitlines():
        row = _ROW.match(line.strip())
        if not row:
            continue
        quote = row.group("quote").strip().strip('*_"“”')
        if not quote:
            continue
        doc, loc = row.group("doc").strip(), row.group("loc").strip()
        url = _URL.search(doc) or _URL.search(loc)
        page = _PAGE.search(loc)
        out.append(
            Evidence(
                url=url.group(0) if url else doc,
                quote=quote,
                stance=Stance.CONFIRMS,
                tier=tier,
                page=int(page.group(1)) if page else None,
                retrieved_at=retrieved_at,
            )
        )
    return out


class ManualChecker:
    """FactChecker backed by a pre-collected evidence ledger (CI / reruns)."""

    def check(self, claim: Claim) -> List[Evidence]:
        return list(claim.evidence)


def evaluate_grounding_safe(
    claim_text: str,
    context_text: str,
    mcp_client: Any = None,
) -> float:
    """Safely evaluate grounding with Veraxi MCP if available, falling back to deterministic."""
    if mcp_client is not None:
        try:
            if hasattr(mcp_client, "evaluate_grounding"):
                res = mcp_client.evaluate_grounding(
                    context_text=context_text,
                    response_text=claim_text,
                )
                if isinstance(res, (int, float)):
                    return float(res)
        except Exception:
            pass
    return compute_deterministic_grounding(claim_text, context_text)
