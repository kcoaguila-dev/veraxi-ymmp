"""Edit-time claim reconciliation, derived-claim synthesis, and hook promotion.

Extracted from ``notebooklm_verify.py`` and ``script_ingest.py`` to keep both
modules well below the 900-line ceiling while preserving 100% backward-compatible
re-exports.
"""

from __future__ import annotations

import dataclasses
import json
import re
import unicodedata
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from veraxi_ymmp.epistemic.epistemic_units import (
    extract_content_lemmas,
    extract_scaled_magnitudes,
    extract_token_magnitudes,
)
from veraxi_ymmp.epistemic.fact_audit import (
    classify_text,
    extract_draft_claims,
)
from veraxi_ymmp.epistemic.facts import (
    Claim,
    ClaimKind,
    ClaimWeight,
    Evidence,
    Stance,
    check_claim_numbers,
    compute_deterministic_grounding,
    extract_claim_numbers,
    normalize_for_quote_match,
    primary_authority_key,
)

_DERIV_UNIT_SUFFIX_RE = re.compile(
    r"^\s*\)?\s*((?:[千万億兆](?:ドル|円|ユーロ|ポンド|元|ウォン|ルピー)?|(?:ドル|円|ユーロ|ポンド|元|ウォン|ルピー))|"
    r"(?:billion|million|trillion|thousand|bn|mn|tn|b|m|k)\b|"
    r"(?:gw|mw|kw|w|tb|gb|mb|kb|ghz|mhz|khz|hz|km|mm|um|nm|kg|mg|ug|kcal)\b|[%％])",
    re.I,
)


def _extract_unit_operands(text: str) -> List[Tuple[str, str, float]]:
    """Extract (num_str, unit_expr, scaled_magnitude) triples from *text*."""
    norm = re.sub(r"(?<=\d),(?=\d)", "", unicodedata.normalize("NFKC", text))
    tok_mags = extract_token_magnitudes(norm)
    out: List[Tuple[str, str, float]] = []
    for n_str in extract_claim_numbers(norm):
        m = re.search(rf"([$¥€£]?)\s*\(?\s*{re.escape(n_str)}(?!\.?\d)", norm)
        pref = m.group(1) if m else ""
        suf_m = _DERIV_UNIT_SUFFIX_RE.match(norm[m.end() :]) if m else None
        suf = suf_m.group(1) if suf_m else ""
        sep = " " if len(suf) > 1 and suf.isascii() and suf[0].isalpha() else ""
        expr = f"{pref}{n_str}{sep}{suf}".strip()
        mags = tok_mags.get(n_str)
        mag = float(n_str) if suf in ("%", "％") else (mags[-1] if mags else float(n_str))
        out.append((n_str, expr, mag))
    return out


def _merge_confirming_evidence(claims: Sequence[Claim]) -> List[Evidence]:
    """Deduplicate confirming Evidence across *claims* preserving order."""
    seen: set[Tuple[str, str, str]] = set()
    merged: List[Evidence] = []
    for cl in claims:
        for e in cl.evidence:
            if e.stance is Stance.CONFIRMS and e.quote:
                key = (e.source_id, e.url, e.quote)
                if key not in seen:
                    seen.add(key)
                    merged.append(replace(e))
    return merged


def _build_derivations_for_pair(
    expr_a: str,
    mag_a: float,
    expr_b: str,
    mag_b: float,
    t_str: str,
    t_expr: str,
    t_mag: float,
) -> List[str]:
    """Generate candidate arithmetic derivation strings for a pair of operands."""
    derivs: List[str] = []
    if t_expr.endswith(("%", "％")):
        for num_e, num_m, den_e, den_m in ((expr_a, mag_a, expr_b, mag_b), (expr_b, mag_b, expr_a, mag_a)):
            if den_m <= 0:
                continue
            ratio_pct = (num_m / den_m) * 100.0
            if abs(ratio_pct - t_mag) / max(abs(t_mag), 1.0) <= 0.05 or abs(ratio_pct - t_mag) <= 1.0:
                derivs.append(f"{num_e} / {den_e} * 100 ~ {t_expr}")
            yoy_pct = ((num_m - den_m) / den_m) * 100.0
            if abs(yoy_pct - t_mag) / max(abs(t_mag), 1.0) <= 0.05:
                derivs.append(f"({num_e} - {den_e}) / {den_e} * 100 ~ {t_expr}")
        return derivs

    if abs((mag_a + mag_b) - t_mag) / max(abs(t_mag), 1.0) <= 0.01:
        derivs.append(f"{expr_a} + {expr_b} = {t_expr}")
    if abs(abs(mag_a - mag_b) - t_mag) / max(abs(t_mag), 1.0) <= 0.01:
        hi, lo = (expr_a, expr_b) if mag_a >= mag_b else (expr_b, expr_a)
        derivs.append(f"{hi} - {lo} = {t_expr}")
    if abs(((mag_a + mag_b) / 2.0) - t_mag) / max(abs(t_mag), 1.0) <= 0.01:
        derivs.append(f"({expr_a} + {expr_b}) / 2 = {t_expr}")
    if t_expr == t_str:
        for num_e, num_m, den_e, den_m in ((expr_a, mag_a, expr_b, mag_b), (expr_b, mag_b, expr_a, mag_a)):
            if den_m > 0 and abs((num_m / den_m) - t_mag) / max(abs(t_mag), 1.0) <= 0.05:
                eq = "=" if abs((num_m / den_m) - t_mag) <= 1e-6 else "~"
                derivs.append(f"{num_e} / {den_e} {eq} {t_expr}")
    return derivs


def _synthesize_derived_claim_from_pool(
    idx: int,
    cut_text: str,
    cid: str,
    confirming: Sequence[Claim],
) -> Optional[Claim]:
    """Pass 4: Synthesize a derived=True Claim from pairwise arithmetic over verified claims."""
    s_ops = _extract_unit_operands(cut_text)
    if not s_ops:
        return None
    quote_blobs: List[Tuple[str, List[float]]] = []
    pool: List[Tuple[str, str, float, Claim, List[str]]] = []
    seen_cl: set[Tuple[str, str]] = set()
    for cl in confirming:
        cl_key = (cl.id, cl.text)
        if cl_key in seen_cl:
            continue
        seen_cl.add(cl_key)
        quotes = [e.quote for e in cl.evidence if e.stance is Stance.CONFIRMS and e.quote]
        if not quotes:
            continue
        qb = re.sub(r"(?<=\d),(?=\d)", "", normalize_for_quote_match(" ".join(quotes)))
        qm = extract_scaled_magnitudes(qb)
        quote_blobs.append((qb, qm))
        cl_ops: List[Tuple[str, str, float]] = []
        for n_str, expr, mag in _extract_unit_operands(cl.text):
            if re.search(rf"(?<![\d.]){re.escape(n_str)}(?!\.?\d)", qb) or any(
                abs(mag - v) / max(abs(mag), abs(v), 1.0) < 0.05 for v in qm
            ):
                cl_ops.append((n_str, expr, mag))
        for q in quotes:
            for n_str, expr, mag in _extract_unit_operands(q):
                if not any(abs(mag - em) / max(abs(mag), abs(em), 1.0) < 0.02 for _, _, em in cl_ops):
                    cl_ops.append((n_str, expr, mag))
        for n_str, expr, mag in cl_ops:
            pool.append((n_str, expr, mag, cl, quotes))

    uncovered = [
        op for op in s_ops if not any(
            re.search(rf"(?<![\d.]){re.escape(op[0])}(?!\.?\d)", qb)
            or any(abs(op[2] - v) / max(abs(op[2]), abs(v), 1.0) < 0.05 for v in qm)
            for qb, qm in quote_blobs
        )
    ]
    if len(uncovered) != 1 or uncovered[0][2] == 0:
        return None
    t_str, t_expr, t_mag = uncovered[0]

    best_score: Optional[Tuple[float, int]] = None
    best_claim: Optional[Claim] = None
    for i, (_na, expr_a, mag_a, cl_a, q_a) in enumerate(pool):
        for j in range(i + 1, len(pool)):
            _nb, expr_b, mag_b, cl_b, q_b = pool[j]
            if cl_a is cl_b and abs(mag_a - mag_b) / max(abs(mag_a), abs(mag_b), 1.0) < 0.02:
                continue
            derivs = _build_derivations_for_pair(expr_a, mag_a, expr_b, mag_b, t_str, t_expr, t_mag)
            if not derivs:
                continue
            combined_quotes = [*q_a, *q_b]
            merged_ev = _merge_confirming_evidence((cl_a, cl_b))
            for derivation in derivs:
                draft_deriv = Claim(
                    id=cid, cut_index=idx, text=cut_text, kind=ClaimKind.NUMBER,
                    weight=ClaimWeight.MINOR, evidence=merged_ev, derived=True, derivation=derivation,
                )
                if check_claim_numbers(draft_deriv, combined_quotes):
                    continue
                ground = compute_deterministic_grounding(cut_text + " " + derivation, " ".join(combined_quotes))
                if ground > 0.0:
                    score = (ground, -(abs(cl_a.cut_index - idx) + abs(cl_b.cut_index - idx)))
                    if best_score is None or score > best_score:
                        best_score, best_claim = score, draft_deriv
    return best_claim


def match_unmatched_cut_to_existing_claims(
    idx: int,
    cut_text: str,
    cid: str,
    candidate_claims: Sequence[Claim],
) -> Optional[Claim]:
    """Match an unmatched numeric cut to an existing Claim (by text or evidence quotes)."""
    draft = Claim(id=cid, cut_index=idx, text=cut_text, kind=ClaimKind.NUMBER, weight=ClaimWeight.MINOR)
    confirming = [
        cl for cl in candidate_claims
        if any(e.stance is Stance.CONFIRMS and e.quote for e in cl.evidence)
    ]

    best_cl: Optional[Claim] = None
    best_score = float("-inf")
    for cl in confirming:
        base = _claims_match_numeric(cut_text, cl)
        if base is not None:
            score = base - abs(cl.cut_index - idx) * 0.05
            if score > best_score:
                best_score = score
                best_cl = cl

    if best_cl is None:
        best_ground = float("-inf")
        for cl in confirming:
            quotes = [e.quote for e in cl.evidence if e.stance is Stance.CONFIRMS and e.quote]
            if check_claim_numbers(draft, quotes):
                continue
            ground = compute_deterministic_grounding(cut_text, " ".join(quotes))
            if ground > 0.0:
                score = ground - abs(cl.cut_index - idx) * 1e-4
                if score > best_ground:
                    best_ground = score
                    best_cl = cl

    if best_cl is None:
        s_mags = extract_scaled_magnitudes(cut_text)
        s_nums = set(extract_claim_numbers(cut_text))
        partials: List[Tuple[int, int, Claim, List[str]]] = []
        for cl in confirming:
            quotes = [e.quote for e in cl.evidence if e.stance is Stance.CONFIRMS and e.quote]
            c_blob = " ".join([cl.text, *quotes])
            c_mags = extract_scaled_magnitudes(c_blob)
            c_nums = set(extract_claim_numbers(c_blob))
            hits = sum(
                1 for sm in s_mags
                if any(abs(sm - cm) / max(abs(sm), abs(cm), 1.0) < 0.05 for cm in c_mags)
            ) + len(s_nums & c_nums)
            if hits > 0:
                partials.append((hits, -abs(cl.cut_index - idx), cl, quotes))
        partials.sort(key=lambda item: (item[0], item[1]), reverse=True)
        selected: List[Claim] = []
        combined_quotes: List[str] = []
        cur_missing = len(check_claim_numbers(draft, combined_quotes))
        for _, _, cl, quotes in partials:
            if len(selected) >= 3 or cur_missing == 0:
                break
            trial_quotes = [*combined_quotes, *quotes]
            new_missing = len(check_claim_numbers(draft, trial_quotes))
            if new_missing < cur_missing:
                selected.append(cl)
                combined_quotes = trial_quotes
                cur_missing = new_missing
        if selected and cur_missing == 0 and compute_deterministic_grounding(cut_text, " ".join(combined_quotes)) > 0.0:
            return Claim(
                id=cid, cut_index=idx, text=cut_text, kind=ClaimKind.NUMBER,
                weight=ClaimWeight.MINOR, evidence=_merge_confirming_evidence(selected),
            )
        if idx > 10:
            return _synthesize_derived_claim_from_pool(idx, cut_text, cid, confirming)
        return None

    best_quotes = [e.quote for e in best_cl.evidence if e.stance is Stance.CONFIRMS and e.quote]
    needs_deriv = bool(best_cl.derived and check_claim_numbers(draft, best_quotes))
    return Claim(
        id=cid,
        cut_index=idx,
        text=cut_text,
        kind=ClaimKind.NUMBER,
        weight=ClaimWeight.MINOR,
        evidence=[replace(e) for e in best_cl.evidence],
        derived=best_cl.derived if needs_deriv else False,
        derivation=best_cl.derivation if needs_deriv else "",
    )


def promote_hook_and_thumbnail_central_claims(
    claims: List[Claim],
    script_entries: Sequence[Any],
    thumbnail_config: Optional[Dict[str, Any]] = None,
) -> List[Claim]:
    """Promote verified claims referenced in hook cuts (0..10) or thumbnail_config to CENTRAL."""
    required_mags: List[float] = []
    for entry in script_entries[:11]:
        if isinstance(entry, dict) and "character" not in entry:
            continue
        c_txt = entry.get("text", "") if isinstance(entry, dict) else getattr(entry, "text", "")
        if c_txt:
            t_mags = extract_token_magnitudes(str(c_txt).strip())
            required_mags.extend(v for vals in t_mags.values() for v in vals if v >= 1e8)

    if isinstance(thumbnail_config, dict):
        thumb_mags = extract_token_magnitudes(json.dumps(thumbnail_config, ensure_ascii=False))
        required_mags.extend(v for vals in thumb_mags.values() for v in vals if v >= 1e8)

    if not required_mags:
        return claims

    cent_mags: List[float] = []
    for cc in claims:
        if cc.weight is ClaimWeight.CENTRAL:
            cent_mags.extend(extract_scaled_magnitudes(cc.text + (" " + cc.derivation if cc.derivation else "")))

    tier1_candidates: List[Tuple[str, Evidence]] = []
    for cl in claims:
        for e in cl.evidence:
            if e.stance is Stance.CONFIRMS and e.tier == 1 and e.source_id and e.sha256:
                key = primary_authority_key(e)
                if key:
                    tier1_candidates.append((key, e))

    for mv in required_mags:
        if any(abs(mv - cm) / max(mv, cm, 1.0) < 0.05 for cm in cent_mags):
            continue
        matches: List[Tuple[int, int, Claim, List[float]]] = []
        for cl in claims:
            if cl.derived:
                continue
            if not any(e.stance is Stance.CONFIRMS and e.tier == 1 and e.source_id and e.sha256 for e in cl.evidence):
                continue
            cl_mags = extract_scaled_magnitudes(cl.text + (" " + cl.derivation if cl.derivation else ""))
            if any(abs(mv - cm) / max(mv, cm, 1.0) < 0.05 for cm in cl_mags):
                matches.append((0 if 0 <= cl.cut_index <= 10 else 1, cl.cut_index, cl, cl_mags))
        if not matches:
            continue
        matches.sort(key=lambda item: (item[0], item[1]))
        _, _, best_cl, best_mags = matches[0]
        best_cl.weight = ClaimWeight.CENTRAL
        existing_keys = {
            primary_authority_key(e)
            for e in best_cl.evidence
            if e.stance is Stance.CONFIRMS and e.source_id
        }
        if len(existing_keys) < 2:
            base_quotes = [e.quote for e in best_cl.evidence if e.stance is Stance.CONFIRMS and e.quote]
            best_ev: Optional[Evidence] = None
            best_ground = 0.0
            for cand_key, cand_ev in tier1_candidates:
                if cand_key in existing_keys:
                    continue
                trial_quotes = [*base_quotes, cand_ev.quote]
                if check_claim_numbers(best_cl, trial_quotes):
                    continue
                ground = compute_deterministic_grounding(best_cl.text, " ".join(trial_quotes))
                if ground > best_ground:
                    best_ground = ground
                    best_ev = cand_ev
            if best_ev is not None:
                best_cl.evidence.append(replace(best_ev))
        cent_mags.extend(best_mags)

    return claims


def _norm_cut_text(text: str) -> str:
    stripped = re.sub(r"\{([^|{}]+)\|([^{}]+)\}", r"\1", str(text))
    return re.sub(r"\s+", " ", stripped).strip()


def _claims_match_numeric(cut_text: str, old_claim: Claim) -> Optional[float]:
    """Score numeric/lemma match between an edited cut and an existing Claim, or None."""
    s_tok_mags = extract_token_magnitudes(cut_text)
    s_mags = [v for vals in s_tok_mags.values() for v in vals]
    s_nums = set(extract_claim_numbers(cut_text))
    s_lemmas = set(extract_content_lemmas(cut_text))

    c_full = old_claim.text + (" " + old_claim.derivation if old_claim.derived and old_claim.derivation else "")
    c_mags = extract_scaled_magnitudes(c_full)
    c_nums = set(extract_claim_numbers(c_full))
    if not s_mags and not (s_nums & c_nums):
        return None
    for s_vals in s_tok_mags.values():
        if not any(abs(sv - cm) / max(abs(sv), abs(cm), 1.0) < 0.05 for sv in s_vals for cm in c_mags):
            return None
    for sn in s_nums:
        if sn not in s_tok_mags and sn not in c_nums:
            return None
    c_lemmas = set(extract_content_lemmas(old_claim.text))
    return len(s_mags) * 5.0 + len(s_nums & c_nums) * 4.0 + len(s_lemmas & c_lemmas)


def _reconcile_unmatched_numeric_cuts(
    unmatched_num_cuts: Sequence[Tuple[int, str]],
    reconciled: Dict[int, Claim],
    evidence_markdown: Optional[str],
    manifest: Optional[Dict[str, Any]],
    sources_dir: Optional[Path],
    existing_claims: Sequence[Claim] = (),
) -> None:
    """Resolve brand-new numeric cuts against existing claims or evidence.md."""
    from veraxi_ymmp.editorial.script_ingest import (
        _build_evidence_for_claim,
        _ensure_notebooklm_sources,
        _match_row_for_claim,
        parse_markdown_evidence_table,
    )

    pool = [*reconciled.values(), *existing_claims]
    covered_mags: List[float] = []
    covered_nums: set[str] = set()
    for cl in pool:
        c_full = " ".join(p for p in [cl.text, cl.derivation if cl.derived else "", *(e.quote for e in cl.evidence)] if p)
        covered_mags.extend(extract_scaled_magnitudes(c_full))
        covered_nums.update(extract_claim_numbers(c_full))

    table_rows = parse_markdown_evidence_table(evidence_markdown) if evidence_markdown else []
    source_meta: Dict[str, Tuple[str, str]] = {}
    manifest_sources: List[Dict[str, str]] = []
    disk_texts: Dict[str, str] = {}
    row_meta: List[Dict[str, Any]] = []
    used_ids = {cl.id for cl in reconciled.values()}
    for idx, cut_text in unmatched_num_cuts:
        cid = f"c_edit_{idx:03d}"
        while cid in used_ids:
            cid = f"{cid}_n"
        used_ids.add(cid)
        matched = match_unmatched_cut_to_existing_claims(idx, cut_text, cid, pool)
        if matched is not None:
            reconciled[idx] = matched
            continue
        if table_rows and not row_meta:
            source_meta, manifest_sources, disk_texts = _ensure_notebooklm_sources(table_rows, manifest, sources_dir)
            row_meta = [
                {"row": r, "mags": set(extract_scaled_magnitudes(t)), "nums": set(extract_claim_numbers(t)), "lemmas": set(extract_content_lemmas(t))}
                for r in table_rows for t in (f"{r['claim']} {r['quote']} {r['metric']}",)
            ]
        s_tok_mags = extract_token_magnitudes(cut_text)
        s_mags = [v for vals in s_tok_mags.values() for v in vals]
        s_nums = set(extract_claim_numbers(cut_text))
        weight = ClaimWeight.CENTRAL if (idx <= 10 or any(m >= 1e8 for m in s_mags)) else ClaimWeight.MINOR
        draft = Claim(id=cid, cut_index=idx, text=cut_text, kind=ClaimKind.NUMBER, weight=weight)
        best_row = _match_row_for_claim(draft, row_meta) if row_meta else None
        if best_row is not None:
            draft.evidence = _build_evidence_for_claim(draft, best_row["row"], weight, source_meta, manifest_sources, disk_texts)
            reconciled[idx] = draft
            continue
        has_new_mag = any(not any(abs(sv - cm) / max(abs(sv), abs(cm), 1.0) < 0.05 for cm in covered_mags) for s_vals in s_tok_mags.values() for sv in s_vals)
        if has_new_mag or any(sn not in s_tok_mags and sn not in covered_nums for sn in s_nums):
            draft.weight = ClaimWeight.CENTRAL
            reconciled[idx] = draft


def reconcile_claims_for_edited_script(
    script_entries: Sequence[Any],
    existing_claims: Sequence[Claim],
    evidence_markdown: Optional[str] = None,
    manifest: Optional[Dict[str, Any]] = None,
    sources_dir: Optional[Path] = None,
) -> List[Claim]:
    """Re-anchor existing Claim ledgers to edited scripts (handling insert/delete/reword)."""
    from veraxi_ymmp.editorial.script_ingest import (
        _CONCRETE_QUANT_FALLBACK_RE,
        ingest_notebooklm_markdown_to_claims,
        parse_markdown_evidence_table,
    )

    raw_dicts: List[Dict[str, Any]] = [
        e if isinstance(e, dict) else dataclasses.asdict(e) for e in script_entries
    ]
    if not existing_claims:
        if evidence_markdown and parse_markdown_evidence_table(evidence_markdown):
            return ingest_notebooklm_markdown_to_claims(
                raw_dicts, evidence_markdown, manifest=manifest, sources_dir=sources_dir
            )
        return extract_draft_claims(raw_dicts, extract_qualitative=True)

    consumed: set[int] = set()
    reconciled: Dict[int, Claim] = {}

    for idx, entry in enumerate(raw_dicts):
        cut_text = str(entry.get("text", "")).strip()
        norm_cut = _norm_cut_text(cut_text)
        matches = [
            (c_idx, cl) for c_idx, cl in enumerate(existing_claims)
            if c_idx not in consumed and _norm_cut_text(cl.text) == norm_cut
        ]
        if matches:
            c_idx, old_cl = min(matches, key=lambda pair: abs(pair[1].cut_index - idx))
            consumed.add(c_idx)
            reconciled[idx] = dataclasses.replace(old_cl, cut_index=idx, text=cut_text)

    for idx, entry in enumerate(raw_dicts):
        if idx in reconciled:
            continue
        cut_text = str(entry.get("text", "")).strip()
        s_mags, s_nums, s_lemmas = (
            extract_scaled_magnitudes(cut_text),
            set(extract_claim_numbers(cut_text)),
            set(extract_content_lemmas(cut_text)),
        )
        is_num_cut = (
            classify_text(cut_text, strict_numbers=True) is ClaimKind.NUMBER
            or bool(s_mags)
            or bool(s_nums and _CONCRETE_QUANT_FALLBACK_RE.search(cut_text))
        )
        best_c: Optional[Tuple[int, Claim, float]] = None
        for c_idx, old_cl in enumerate(existing_claims):
            if c_idx in consumed:
                continue
            if is_num_cut:
                if old_cl.kind is not ClaimKind.NUMBER and not extract_claim_numbers(old_cl.text):
                    continue
                base_score = _claims_match_numeric(cut_text, old_cl)
                if base_score is None:
                    continue
                score = base_score - abs(old_cl.cut_index - idx) * 0.1
            else:
                if old_cl.kind is ClaimKind.NUMBER or extract_scaled_magnitudes(old_cl.text):
                    continue
                overlap = len(s_lemmas & set(extract_content_lemmas(old_cl.text)))
                if overlap < 2 and not (old_cl.cut_index == idx and overlap >= 1):
                    continue
                score = overlap * 2.0 - abs(old_cl.cut_index - idx) * 0.1
            if best_c is None or score > best_c[2]:
                best_c = (c_idx, old_cl, score)
        if best_c is not None:
            consumed.add(best_c[0])
            reconciled[idx] = dataclasses.replace(best_c[1], cut_index=idx, text=cut_text)

    unmatched_num_cuts = [
        (idx, str(entry.get("text", "")).strip())
        for idx, entry in enumerate(raw_dicts)
        if idx not in reconciled
        and classify_text(str(entry.get("text", "")).strip(), strict_numbers=True) is ClaimKind.NUMBER
    ]
    if unmatched_num_cuts:
        _reconcile_unmatched_numeric_cuts(unmatched_num_cuts, reconciled, evidence_markdown, manifest, sources_dir, existing_claims)

    out = sorted(reconciled.values(), key=lambda c: c.cut_index)
    if (
        any(c.weight is ClaimWeight.CENTRAL for c in existing_claims)
        and any(c.kind not in (ClaimKind.OPINION, ClaimKind.COMMENTARY) for c in out)
        and not any(c.weight is ClaimWeight.CENTRAL for c in out)
    ):
        for cl in out:
            if cl.kind not in (ClaimKind.OPINION, ClaimKind.COMMENTARY) and cl.evidence:
                cl.weight = ClaimWeight.CENTRAL
                break
    return out
