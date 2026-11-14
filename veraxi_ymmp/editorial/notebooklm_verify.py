"""Post-Script NotebookLM Adversarial Fact-Check Round-Trip ('Epistemic Sandwich').

Extracts a compact checklist of every checkable dialogue cut, B-roll slide,
and thumbnail headline from a project directory, builds an adversarial
verification prompt for Gemini NotebookLM (which holds the full primary PDFs),
and reconciles NotebookLM's 7-column audit table back into ``claims.json``
and ``sources/manifest.json``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from veraxi_ymmp.editorial.script_ingest import (
    _build_evidence_for_claim,
    _ensure_notebooklm_sources,
    _select_two_primary_slots,
)
from veraxi_ymmp.epistemic.fact_audit import (
    CLAIMS_FILENAME,
    classify_text,
    extract_draft_claims,
)
from veraxi_ymmp.epistemic.facts import (
    NON_CHECKABLE_KINDS,
    Claim,
    ClaimKind,
    ClaimWeight,
    Evidence,
    Stance,
    claims_to_json,
    extract_claim_numbers,
    extract_scaled_magnitudes,
    load_claims,
)

_RUBY_RE = re.compile(r"\{([^|{}]+)\|[^|{}]+\}")
_ITEM_ID_RE = re.compile(r"\b((?:cut|slide|thumb)_\d+)\b", re.IGNORECASE)
_TABLE_SEP_RE = re.compile(r"^\|(?:\s*:?-+:?\s*\|)+$")

_SLIDE_SKIP_KEYS = frozenset({
    "type", "filename", "theme_color", "color", "is_vertical",
    "image_path", "image", "asset", "layout", "show_caption",
    "show_header", "show_citation", "chart_type",
})
_COLOR_TOKENS = frozenset({
    "blue", "emerald", "amber", "purple", "rose", "red", "green", "cyan", "gold", "violet",
})
_THUMB_TEXT_KEYS = (
    "badge", "badge_text", "top_tag",
    "title_line1", "title_line2", "main_title", "headline",
    "sub_title", "subheadline", "sub_hook",
    "left_label", "right_label", "vs_left", "vs_right",
    "metric_highlight", "speech_bubble", "text",
)
_VERDICT_ALIASES: Dict[str, str] = {
    "SUPPORTED": "SUPPORTED",
    "PASS": "SUPPORTED",
    "CONFIRMED": "SUPPORTED",
    "OK": "SUPPORTED",
    "VALID": "SUPPORTED",
    "DRIFTED": "DRIFTED",
    "DRIFT": "DRIFTED",
    "SCOPE_DRIFT": "DRIFTED",
    "PARTIAL": "DRIFTED",
    "INACCURATE": "DRIFTED",
    "REFUTED": "REFUTED",
    "CONTRADICTED": "REFUTED",
    "CONTRADICTS": "REFUTED",
    "FALSE": "REFUTED",
    "FAIL": "REFUTED",
    "REJECTED": "REFUTED",
    "UNVERIFIED": "UNVERIFIED",
    "MISSING": "UNVERIFIED",
    "NO_EVIDENCE": "UNVERIFIED",
    "NOT_FOUND": "UNVERIFIED",
    "UNKNOWN": "UNVERIFIED",
}


@dataclass(frozen=True)
class AuditChecklistItem:
    """One dialogue cut, B-roll slide, or thumbnail assertion to audit."""

    item_id: str
    kind: str  # "cut" | "slide" | "thumbnail"
    label: str
    assertion: str
    cut_index: int = 0


@dataclass
class AuditReconcileResult:
    """Outcome of reconciling NotebookLM's post-script audit reply."""

    supported_count: int
    flagged_rows: List[Dict[str, str]] = field(default_factory=list)
    updated_claims: List[Claim] = field(default_factory=list)
    reprompt_block: str = ""

    @property
    def passed(self) -> bool:
        """Return True when zero items were flagged as drifted, refuted, or unverified."""
        return len(self.flagged_rows) == 0


def _strip_ruby(text: str) -> str:
    return _RUBY_RE.sub(r"\1", text).strip()


def _load_json_safe(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _collect_slide_visible_texts(spec: Dict[str, Any]) -> List[str]:
    texts: List[str] = []
    for key, val in spec.items():
        if key in _SLIDE_SKIP_KEYS or val is None:
            continue
        if isinstance(val, str):
            s = _strip_ruby(val)
            if s and s.lower() not in _COLOR_TOKENS:
                texts.append(s)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    s = _strip_ruby(item)
                    if s and s.lower() not in _COLOR_TOKENS:
                        texts.append(s)
                elif isinstance(item, (list, tuple)):
                    for sub in item:
                        if isinstance(sub, str):
                            s = _strip_ruby(sub)
                            if s and s.lower() not in _COLOR_TOKENS:
                                texts.append(s)
                elif isinstance(item, dict):
                    for sub_v in item.values():
                        if isinstance(sub_v, str):
                            s = _strip_ruby(sub_v)
                            if s and s.lower() not in _COLOR_TOKENS:
                                texts.append(s)
    return texts


def _collect_thumbnail_texts(cfg: Dict[str, Any]) -> List[str]:
    texts: List[str] = []
    seen: set[str] = set()
    for key in _THUMB_TEXT_KEYS:
        val = cfg.get(key)
        if isinstance(val, str):
            s = _strip_ruby(val)
            if s and s not in seen and s.lower() not in _COLOR_TOKENS:
                seen.add(s)
                texts.append(s)
    return texts


def extract_audit_checklist(project_dir: Path) -> List[AuditChecklistItem]:
    """Extract checkable cuts, B-roll slides, and thumbnail text from *project_dir*."""
    items: List[AuditChecklistItem] = []

    script_data = _load_json_safe(project_dir / "script.json")
    if isinstance(script_data, list):
        dialogue_cuts: List[Tuple[int, str, str]] = []
        for idx, entry in enumerate(script_data):
            if not isinstance(entry, dict) or "character" not in entry:
                continue
            clean = _strip_ruby(str(entry.get("text", "")))
            if not clean:
                continue
            char = str(entry.get("character", "不明")).strip() or "不明"
            dialogue_cuts.append((idx, char, clean))

        checkable: List[Tuple[int, str, str]] = []
        for idx, char, clean in dialogue_cuts:
            kind = classify_text(clean, extract_qualitative=True)
            if kind not in (None, ClaimKind.COMMENTARY, ClaimKind.OPINION) or re.search(r"\d", clean):
                checkable.append((idx, char, clean))
        for idx, char, clean in (checkable or dialogue_cuts):
            items.append(AuditChecklistItem(
                item_id=f"cut_{idx:02d}",
                kind="cut",
                label=f"Cut #{idx} | {char}",
                assertion=clean,
                cut_index=idx,
            ))

    broll_raw = _load_json_safe(project_dir / "broll_manifest.json")
    slides: List[Any] = []
    if isinstance(broll_raw, list):
        slides = broll_raw
    elif isinstance(broll_raw, dict):
        cand = broll_raw.get("broll_manifest") or broll_raw.get("slides") or []
        if isinstance(cand, list):
            slides = cand
    for s_idx, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        texts = _collect_slide_visible_texts(slide)
        if not texts:
            continue
        fname = str(slide.get("filename") or f"slide_{s_idx:02d}.png")
        stype = str(slide.get("type") or "slide")
        items.append(AuditChecklistItem(
            item_id=f"slide_{s_idx:02d}",
            kind="slide",
            label=f"{fname} ({stype})",
            assertion=" | ".join(texts),
        ))

    thumb_raw = _load_json_safe(project_dir / "thumbnail_config.json")
    if isinstance(thumb_raw, dict):
        t_texts = _collect_thumbnail_texts(thumb_raw)
        if t_texts:
            items.append(AuditChecklistItem(
                item_id="thumb_00",
                kind="thumbnail",
                label="Thumbnail",
                assertion=" / ".join(t_texts),
            ))

    return items


def build_post_script_audit_prompt(project_dir: Path) -> str:
    """Build a compact copy-paste adversarial verification prompt for Gemini NotebookLM."""
    items = extract_audit_checklist(project_dir)
    seed = _load_json_safe(project_dir / "script_seed.json")
    topic = str(seed.get("topic", "")).strip() if isinstance(seed, dict) else ""
    topic_line = f"Topic: **{topic}**\n\n" if topic else ""

    checklist_lines = [
        f"- `[{it.item_id} | {it.label}]`: {it.assertion}" for it in items
    ] or ["- _(No checkable items found in script.json / broll_manifest.json / thumbnail_config.json)_"]

    return (
        "# Post-Script Adversarial Fact-Check (NotebookLM Source Audit)\n\n"
        f"{topic_line}"
        "You hold the full uploaded primary source PDFs/filings. Audit **every item** in the "
        "checklist below strictly against the uploaded primary documents — do NOT rely on "
        "memory or assume the script summary is accurate.\n\n"
        "## Audit Criteria (Check All 5 Dimensions)\n"
        "1. **Numeric, Multiplier & Unit Parity:** Exact figures, currencies, percentages, and "
        "scales (`億` / `billion` / `million` / `(in millions)` table units).\n"
        "2. **Entity, Segment & Denominator Scope:** Flag division-to-parent swaps (e.g., AWS "
        "operating income attributed to total Amazon profit) or missing denominators.\n"
        "3. **Temporal Period Parity:** Exact fiscal quarter/year alignment (e.g., Q3 2026 vs FY2025).\n"
        "4. **Causal & Polarity Fidelity:** Flag invented causal bridges (`だから`/`その結果`) "
        "not stated in the text, or conditional risks flipped into realized losses.\n"
        "5. **Verbatim Quote Backing:** For every `SUPPORTED` item, extract an exact verbatim "
        "quote copied straight from the uploaded primary source.\n\n"
        "## Checklist to Audit\n"
        + "\n".join(checklist_lines)
        + "\n\n## Required Output Format (Strict 7-Column Markdown Table)\n"
        "Return **ONLY** a 7-column Markdown table using these exact headers and allowed `Verdict` "
        "values (`SUPPORTED`, `DRIFTED`, `REFUTED`, `UNVERIFIED`):\n\n"
        "| Item ID | Assertion | Verdict | Verbatim Quote | Source & Page/URL | Discrepancy | Suggested Fix (<=38 chars) |\n"
        "|---|---|---|---|---|---|---|\n"
        "| cut_XX | ... | SUPPORTED | \"...\" | Doc / URL p.12 | - | - |\n"
    )


def _normalize_verdict(raw: str) -> str:
    cleaned = re.sub(r"[`*\[\]]", "", raw).strip("_ ").upper()
    if cleaned in _VERDICT_ALIASES:
        return _VERDICT_ALIASES[cleaned]
    for token, canonical in _VERDICT_ALIASES.items():
        if token in cleaned:
            return canonical
    return "UNVERIFIED"


def _extract_item_id(raw: str) -> str:
    m = _ITEM_ID_RE.search(raw)
    if m:
        return m.group(1).lower()
    return re.sub(r"[`*\[\]]", "", raw).strip("_ ")


def parse_notebooklm_audit_table(markdown_text: str) -> List[Dict[str, str]]:
    """Parse NotebookLM's 7-column Markdown audit table into normalized row dicts."""
    blocks: List[List[str]] = []
    cur: List[str] = []
    for line in markdown_text.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cur.append(s)
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)

    chosen: List[str] = []
    for blk in blocks:
        if len(blk) >= 2:
            hdr = blk[0].lower()
            if any(k in hdr for k in ("verdict", "item", "discrepancy", "quote", "判定", "指摘")):
                chosen = blk
                break
    if not chosen:
        chosen = next((b for b in blocks if len(b) >= 2 and b[0].count("|") >= 5), [])
    if not chosen:
        return []

    raw_headers = [c.strip().lower() for c in chosen[0].strip("|").split("|")]
    col_map: Dict[str, int] = {}
    for idx, h in enumerate(raw_headers):
        if "item" in h or "id" in h or "項目" in h:
            col_map.setdefault("item_id", idx)
        elif "assertion" in h or "claim" in h or "script" in h or "主張" in h:
            col_map.setdefault("assertion", idx)
        elif "verdict" in h or "status" in h or "判定" in h:
            col_map.setdefault("verdict", idx)
        elif "quote" in h or "verbatim" in h or "引用" in h:
            col_map.setdefault("quote", idx)
        elif "source" in h or "page" in h or "url" in h or "出典" in h:
            col_map.setdefault("source", idx)
        elif "discrep" in h or "reason" in h or "issue" in h or "指摘" in h or "乖離" in h:
            col_map.setdefault("discrepancy", idx)
        elif "fix" in h or "suggest" in h or "修正" in h:
            col_map.setdefault("suggested_fix", idx)

    defaults = ("item_id", "assertion", "verdict", "quote", "source", "discrepancy", "suggested_fix")
    for pos, name in enumerate(defaults):
        if name not in col_map and pos < len(raw_headers):
            col_map[name] = pos

    rows: List[Dict[str, str]] = []
    for line in chosen[1:]:
        if _TABLE_SEP_RE.match(line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or all(c == "" for c in cells):
            continue

        def _get(field_name: str) -> str:
            idx = col_map.get(field_name, -1)
            return cells[idx].strip() if 0 <= idx < len(cells) else ""

        item_id = _extract_item_id(_get("item_id"))
        if not item_id:
            continue
        rows.append({
            "item_id": item_id,
            "assertion": _get("assertion"),
            "verdict": _normalize_verdict(_get("verdict")),
            "quote": _get("quote").strip("\"'「」『』"),
            "source": _get("source"),
            "discrepancy": _get("discrepancy"),
            "suggested_fix": _get("suggested_fix"),
        })
    return rows


def _format_reprompt_block(flagged_rows: Sequence[Dict[str, str]]) -> str:
    if not flagged_rows:
        return ""
    lines = [
        "================ LLM RE-PROMPT BLOCK (COPY & PASTE TO AI) ================",
        "NotebookLM post-script audit flagged factual drift or contradictions in your",
        "script/visuals against the primary source PDFs. Fix these exact items:",
    ]
    for row in flagged_rows:
        verdict = row["verdict"]
        item_id = row["item_id"]
        assertion = row["assertion"] or "(see project item)"
        discrep = row["discrepancy"] or "Flagged against primary source documents."
        quote = row["quote"] or "(none extracted)"
        fix = row["suggested_fix"] or "(rewrite to match primary source within 38 chars)"
        lines.append(
            f'  - [{verdict}] {item_id} ("{assertion}"): {discrep} | '
            f'Quote: "{quote}" | Suggested Fix (<=38 chars): {fix}'
        )
    lines.append(
        "Preserve all other entries and return the complete corrected JSON object "
        '{"script": [...], "broll_manifest": [...], "thumbnail_config": {...}}.'
    )
    lines.append("==========================================================================")
    return "\n".join(lines)


def _sync_evidence_hashes(
    claims: Sequence[Claim], source_meta: Dict[str, Tuple[str, str]]
) -> None:
    """Keep sha256/url current on untouched Evidence after source corpus updates."""
    for claim in claims:
        for ev in claim.evidence:
            if ev.source_id and ev.source_id in source_meta:
                surl, ssha = source_meta[ev.source_id]
                ev.sha256 = ssha
                if not ev.url:
                    ev.url = surl


def _ensure_cut_claim(
    claims: List[Claim],
    cut_idx: int,
    fallback_text: str,
    script_data: Sequence[Any],
) -> Claim:
    existing = next((c for c in claims if c.cut_index == cut_idx), None)
    if existing is not None:
        return existing
    text = fallback_text
    if 0 <= cut_idx < len(script_data) and isinstance(script_data[cut_idx], dict):
        text = str(script_data[cut_idx].get("text") or fallback_text).strip()
    kind = classify_text(text, extract_qualitative=True) or ClaimKind.FACT
    if kind in NON_CHECKABLE_KINDS:
        kind = ClaimKind.FACT
    claim = Claim(
        id=f"nlm_cut_{cut_idx:02d}",
        cut_index=cut_idx,
        text=text,
        kind=kind,
        weight=ClaimWeight.CENTRAL if cut_idx <= 10 else ClaimWeight.MINOR,
    )
    claims.append(claim)
    return claim


def _collect_corpus_rows(
    existing_claims: Sequence[Claim],
    audit_rows: Sequence[Dict[str, str]],
    script_data: Sequence[Any],
) -> List[Dict[str, str]]:
    """Gather all existing confirming quotes and new audit quotes into corpus rows."""
    corpus_rows: List[Dict[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for cl in existing_claims:
        for ev in cl.evidence:
            q = ev.quote.strip()
            if q and (cl.text, q) not in seen:
                seen.add((cl.text, q))
                corpus_rows.append({"claim": cl.text, "quote": q, "source": ev.url, "metric": ""})
    for row in audit_rows:
        assertion = row["assertion"]
        m_cut = re.match(r"^cut_(\d+)$", row["item_id"])
        if m_cut:
            idx = int(m_cut.group(1))
            if 0 <= idx < len(script_data) and isinstance(script_data[idx], dict):
                assertion = str(script_data[idx].get("text") or assertion).strip()
        quote = row["quote"] or row["discrepancy"] or assertion
        if quote and (assertion, quote) not in seen:
            seen.add((assertion, quote))
            corpus_rows.append({"claim": assertion, "quote": quote, "source": row["source"], "metric": ""})
    return corpus_rows


def _apply_supported_row(
    row: Dict[str, str],
    claims: List[Claim],
    script_data: Sequence[Any],
    source_meta: Dict[str, Tuple[str, str]],
    manifest_sources: Sequence[Dict[str, str]],
    disk_texts: Dict[str, str],
    non_cut_idx: int,
) -> int:
    """Enrich or create a Claim with confirming Evidence from a SUPPORTED audit row."""
    m_cut = re.match(r"^cut_(\d+)$", row["item_id"])
    if m_cut:
        cut_idx = int(m_cut.group(1))
        claim = _ensure_cut_claim(claims, cut_idx, row["assertion"], script_data)
        has_macro = any(m >= 1e8 for m in extract_scaled_magnitudes(claim.text))
        if cut_idx <= 10 or has_macro:
            claim.weight = ClaimWeight.CENTRAL
        if claim.kind in NON_CHECKABLE_KINDS:
            claim.kind = ClaimKind.NUMBER if extract_claim_numbers(claim.text) else ClaimKind.FACT
        if row["quote"]:
            corp_row = {"claim": claim.text, "quote": row["quote"], "source": row["source"], "metric": ""}
            claim.evidence = _build_evidence_for_claim(
                claim, corp_row, claim.weight, source_meta, manifest_sources, disk_texts
            )
        return non_cut_idx

    assertion = row["assertion"]
    mags = extract_scaled_magnitudes(assertion)
    macro_mags = [m for m in mags if m >= 1e8]
    existing_central_mags = [
        cm for c in claims if c.weight is ClaimWeight.CENTRAL
        for cm in extract_scaled_magnitudes(c.text + (" " + c.derivation if c.derivation else ""))
    ]
    uncovered_macro = any(
        not any(abs(mv - cm) / max(mv, cm, 1.0) < 0.05 for cm in existing_central_mags)
        for mv in macro_mags
    )
    existing_id = f"nlm_{row['item_id']}"
    claim_opt = next((c for c in claims if c.id == existing_id), None)
    if claim_opt is None and not uncovered_macro:
        return non_cut_idx

    if claim_opt is None:
        kind = ClaimKind.NUMBER if extract_claim_numbers(assertion) else ClaimKind.FACT
        claim_opt = Claim(
            id=existing_id,
            cut_index=non_cut_idx,
            text=assertion,
            kind=kind,
            weight=ClaimWeight.CENTRAL if macro_mags else ClaimWeight.MINOR,
        )
        claims.append(claim_opt)
        non_cut_idx += 1
    elif macro_mags:
        claim_opt.weight = ClaimWeight.CENTRAL

    if row["quote"]:
        corp_row = {"claim": claim_opt.text, "quote": row["quote"], "source": row["source"], "metric": ""}
        claim_opt.evidence = _build_evidence_for_claim(
            claim_opt, corp_row, claim_opt.weight, source_meta, manifest_sources, disk_texts
        )
    return non_cut_idx


def _apply_flagged_row(
    row: Dict[str, str],
    claims: List[Claim],
    script_data: Sequence[Any],
    source_meta: Dict[str, Tuple[str, str]],
    non_cut_idx: int,
) -> int:
    """Record a DRIFTED, REFUTED, or UNVERIFIED verdict on its matching Claim."""
    m_cut = re.match(r"^cut_(\d+)$", row["item_id"])
    if m_cut:
        claim = _ensure_cut_claim(claims, int(m_cut.group(1)), row["assertion"], script_data)
    else:
        cid = f"nlm_{row['item_id']}"
        existing = next((c for c in claims if c.id == cid), None)
        if existing is not None:
            claim = existing
        else:
            assertion = row["assertion"] or row["item_id"]
            kind = ClaimKind.NUMBER if extract_claim_numbers(assertion) else ClaimKind.FACT
            claim = Claim(id=cid, cut_index=non_cut_idx, text=assertion, kind=kind, weight=ClaimWeight.MINOR)
            claims.append(claim)
            non_cut_idx += 1

    if row["verdict"] in ("DRIFTED", "REFUTED"):
        contra_quote = row["quote"] or row["discrepancy"] or claim.text
        sid, (surl, ssha) = next(
            iter(source_meta.items()),
            ("primary_anchor_doc", (_select_two_primary_slots([])[0][1], "")),
        )
        claim.evidence = [
            Evidence(
                url=surl,
                quote=contra_quote,
                stance=Stance.CONTRADICTS,
                tier=1,
                source_id=sid,
                sha256=ssha,
            )
        ]
    else:
        claim.evidence = []
    return non_cut_idx


def reconcile_notebooklm_audit(
    project_dir: Path,
    audit_markdown: str,
) -> AuditReconcileResult:
    """Reconcile NotebookLM's post-script audit table into claims.json & sources/."""
    audit_rows = parse_notebooklm_audit_table(audit_markdown)
    if not audit_rows:
        raise ValueError("No valid 7-column NotebookLM audit table rows found in pasted reply.")

    script_raw = _load_json_safe(project_dir / "script.json")
    script_data: List[Any] = script_raw if isinstance(script_raw, list) else []

    claims_path = project_dir / CLAIMS_FILENAME
    existing_claims = load_claims(claims_path) if claims_path.is_file() else []
    claims = extract_draft_claims(script_data, existing_claims, extract_qualitative=True)

    manifest_data = _load_json_safe(project_dir / "sources" / "manifest.json")
    manifest_dict = manifest_data if isinstance(manifest_data, dict) else None
    corpus_rows = _collect_corpus_rows(claims, audit_rows, script_data)
    source_meta, manifest_sources, disk_texts = _ensure_notebooklm_sources(
        corpus_rows, manifest_dict, project_dir / "sources"
    )
    _sync_evidence_hashes(claims, source_meta)

    non_cut_idx = len(script_data)
    supported_rows = [r for r in audit_rows if r["verdict"] == "SUPPORTED"]
    flagged_rows = [r for r in audit_rows if r["verdict"] != "SUPPORTED"]

    row_by_id = {r["item_id"]: r for r in supported_rows}
    for row in supported_rows:
        non_cut_idx = _apply_supported_row(
            row, claims, script_data, source_meta, manifest_sources, disk_texts, non_cut_idx
        )
    for row in flagged_rows:
        non_cut_idx = _apply_flagged_row(row, claims, script_data, source_meta, non_cut_idx)

    # Guarantee at least one central claim when all checkable cuts are supported
    if supported_rows and not any(c.weight is ClaimWeight.CENTRAL for c in claims):
        first_sup = next(
            (c for c in claims if any(e.stance is Stance.CONFIRMS for e in c.evidence)),
            None,
        )
        if first_sup is not None:
            first_sup.weight = ClaimWeight.CENTRAL
            row_hint = row_by_id.get(f"cut_{first_sup.cut_index:02d}")
            quote = row_hint["quote"] if row_hint and row_hint["quote"] else first_sup.evidence[0].quote
            src_col = row_hint["source"] if row_hint else first_sup.evidence[0].url
            first_sup.evidence = _build_evidence_for_claim(
                first_sup,
                {"claim": first_sup.text, "quote": quote, "source": src_col, "metric": ""},
                ClaimWeight.CENTRAL,
                source_meta,
                manifest_sources,
                disk_texts,
            )

    claims.sort(key=lambda c: c.cut_index)
    claims_path.write_text(claims_to_json(claims), encoding="utf-8")

    return AuditReconcileResult(
        supported_count=len(supported_rows),
        flagged_rows=flagged_rows,
        updated_claims=claims,
        reprompt_block=_format_reprompt_block(flagged_rows),
    )
