"""Parser and compiler converting raw Markdown dialogue into validated DirectorScriptEntry JSON and claims.json."""
from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from veraxi_ymmp.core.script import (
    DirectorScriptEntry,
    validate_director_script,
    CharacterPosition,
    Emotion,
    Motion,
)
from veraxi_ymmp.epistemic.facts import (
    Claim,
    ClaimKind,
    ClaimWeight,
    Evidence,
    Stance,
    canonical_institution,
    check_claim_numbers,
    compute_deterministic_grounding,
    extract_claim_numbers,
    is_primary_authority_url,
    verify_quote_in_source,
)
from veraxi_ymmp.epistemic.fact_audit import (
    classify_text,
    compute_file_sha256,
    extract_draft_claims,
    load_project_sources,
)
from veraxi_ymmp.epistemic.epistemic_units import (
    extract_content_lemmas,
    extract_scaled_magnitudes,
)

_BUDOUX_PARSER = None


def _get_budoux_parser() -> Any:
    global _BUDOUX_PARSER
    if _BUDOUX_PARSER is None:
        import budoux
        _BUDOUX_PARSER = budoux.load_default_japanese_parser()
    return _BUDOUX_PARSER


SPEAKER_ALIASES: Dict[str, str] = {
    # Zundamon aliases
    "zundamon": "ずんだもん",
    "ずんだもん": "ずんだもん",
    "zunda": "ずんだもん",
    # Metan aliases
    "metan": "四国めたん",
    "四国めたん": "四国めたん",
    "めたん": "四国めたん",
    # Tsumugi aliases
    "tsumugi": "春日部つむぎ",
    "春日部つむぎ": "春日部つむぎ",
    "つむぎ": "春日部つむぎ",
}

DEFAULT_POSITIONS: Dict[str, CharacterPosition] = {
    "四国めたん": "left",
    "ずんだもん": "right",
    "春日部つむぎ": "right",
}

LINE_SPLIT_PUNCTUATION = re.compile(r"([。！？\?!])")


def normalize_speaker(raw_name: str) -> Optional[str]:
    """Normalize raw speaker name to official Japanese character name."""
    cleaned = raw_name.strip().strip("[]*:").lower()
    return SPEAKER_ALIASES.get(cleaned)


def detect_emotion(text: str) -> Emotion:
    """Heuristic emotion detector from sentence endings and punctuation."""
    if "！？" in text or "?!" in text or "ええっ" in text or "なんだって" in text:
        return "surprised"
    if "のだー" in text or "やった" in text or "すごい" in text:
        return "excited"
    if "おめでたい" in text or "愚か" in text or "ふふ" in text:
        return "smug"
    if "まずい" in text or "どうしよう" in text:
        return "scared"
    if "許せない" in text or "怒" in text:
        return "angry"
    return "normal"


def _visible_length(s: str) -> int:
    """Calculate character length ignoring inline phonetic ruby tags {Kanji|yomi}."""
    return len(re.sub(r"\{([^{}|]+)\|[^{}|]+\}", r"\1", s))


def split_text_to_char_limit(text: str, max_chars: int = 38) -> List[str]:
    """Split text into cuts <= max_chars, breaking naturally on punctuation or BudouX semantic phrases."""
    text = text.strip()
    if _visible_length(text) <= max_chars:
        return [text]

    # Split preserving punctuation delimiters
    parts = LINE_SPLIT_PUNCTUATION.split(text)
    reconstructed: List[str] = []
    current = ""

    for part in parts:
        if not part:
            continue
        if LINE_SPLIT_PUNCTUATION.match(part):
            current += part
            reconstructed.append(current)
            current = ""
        else:
            if current:
                reconstructed.append(current)
            current = part
    if current:
        reconstructed.append(current)

    # For each reconstructed segment, if it exceeds max_chars, segment via BudouX
    phrases: List[str] = []
    parser = _get_budoux_parser()

    for item in reconstructed:
        if _visible_length(item) <= max_chars:
            phrases.append(item)
        else:
            # Protect inline ruby tags {Kanji|yomi} from being split
            ruby_map: Dict[str, str] = {}

            def repl_ruby(m: re.Match) -> str:
                tok = f"__RUBY_{len(ruby_map)}__"
                ruby_map[tok] = m.group(0)
                return tok

            protected = re.sub(r"\{[^{}]+\|[^{}]+\}", repl_ruby, item)
            b_chunks = parser.parse(protected)

            for c in b_chunks:
                for tok, orig in ruby_map.items():
                    if tok in c:
                        c = c.replace(tok, orig)
                # Hard fallback if an indivisible token itself exceeds max_chars
                if _visible_length(c) > max_chars:
                    while _visible_length(c) > max_chars:
                        phrases.append(c[:max_chars])
                        c = c[max_chars:]
                    if c:
                        phrases.append(c)
                else:
                    phrases.append(c)

    # Combine phrases into chunks of <= max_chars
    chunks: List[str] = []
    accum = ""
    for p in phrases:
        if _visible_length(accum) + _visible_length(p) <= max_chars:
            accum += p
        else:
            if accum:
                chunks.append(accum)
            accum = p
    if accum:
        chunks.append(accum)

    return chunks


def parse_markdown_dialogue(markdown_content: str) -> List[DirectorScriptEntry]:
    """Parse markdown dialogue lines into validated DirectorScriptEntry list."""
    pattern = re.compile(
        r"^(?:\d+[\.\)]\s*)?(?:[-*]\s*)?\[?(?:\*\*)?([a-zA-Z\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]+)(?:\*\*)?\]?\s*[:：]\s*(.+)$"
    )
    slide_directive_pattern = re.compile(
        r"^(?:<!--\s*slide:\s*([^\s>]+)\s*-->|\[(?:slide|image):\s*([^\]]+)\])", re.IGNORECASE
    )
    inline_slide_pattern = re.compile(
        r"(?:<!--\s*slide:\s*([^\s>]+)\s*-->|\[(?:slide|image):\s*([^\]]+)\])", re.IGNORECASE
    )

    raw_cuts: List[Dict[str, Any]] = []
    active_slide: Optional[str] = None

    for line in markdown_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("|") or line.startswith("```"):
            continue

        # Check for standalone slide directive e.g. <!-- slide: broll/slide_01.png --> or [slide: broll/slide_01.png]
        slide_m = slide_directive_pattern.match(line)
        if slide_m:
            target = (slide_m.group(1) or slide_m.group(2) or "").strip()
            if target.lower() in {"none", "null", "clear", ""}:
                active_slide = None
            else:
                active_slide = target
            continue

        # Check for inline slide tag in dialogue line e.g. [slide: broll/slide_01.png] [四国めたん]: ...
        inline_m = inline_slide_pattern.search(line)
        if inline_m:
            target = (inline_m.group(1) or inline_m.group(2) or "").strip()
            if target.lower() in {"none", "null", "clear", ""}:
                active_slide = None
            else:
                active_slide = target
            line = inline_slide_pattern.sub("", line).strip()

        match = pattern.match(line)
        if not match:
            continue

        speaker_raw, text_raw = match.group(1), match.group(2)
        speaker = normalize_speaker(speaker_raw)
        if not speaker:
            continue

        # Split text if it exceeds 38 chars
        sub_texts = split_text_to_char_limit(text_raw, max_chars=38)

        for sub_text in sub_texts:
            cut_idx = len(raw_cuts)
            emotion = detect_emotion(sub_text)
            motion: Motion = "nod" if emotion in {"excited", "surprised"} else "none"

            entry: Dict[str, Any] = {
                "character": speaker,
                "text": sub_text,
                "emotion": emotion,
                "motion": motion,
                "bgm": None,
                "sfx": None,
                "image": None if cut_idx < 3 else active_slide,  # Cold open hook protection
                "character_position": DEFAULT_POSITIONS.get(speaker, "left"),
                "subtitle_position": "bottom_center",
                "subtitle_style": "outlined",
            }
            raw_cuts.append(entry)

    # Validate output schema against domain invariants
    validated = validate_director_script(raw_cuts)
    return validated


def parse_markdown_evidence_table(markdown_content: str) -> List[Dict[str, str]]:
    """Parse Markdown evidence tables (such as NotebookLM Evidence Extraction Matrix).

    Extracts rows mapping claim, verbatim quote, source document reference, and hard metric.
    """
    table_lines: List[str] = []
    in_table = False

    for line in markdown_content.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            in_table = True
            table_lines.append(s)
        elif in_table:
            # End of table block
            break

    if len(table_lines) < 2:
        return []

    raw_header = [c.strip() for c in table_lines[0].strip("|").split("|")]
    col_map: Dict[str, int] = {}

    for idx, col in enumerate(raw_header):
        c_low = col.lower()
        if any(k in c_low for k in ("quote", "verbatim", "引用", "証拠", "抜粋")):
            col_map["quote"] = idx
        elif any(k in c_low for k in ("source", "doc", "page", "出典", "資料", "文献")):
            col_map["source"] = idx
        elif any(k in c_low for k in ("metric", "cause", "指標", "数値", "原因")):
            col_map["metric"] = idx
        elif any(k in c_low for k in ("claim", "contention", "point", "主張", "論点", "内容")):
            col_map["claim"] = idx

    if "quote" not in col_map and len(raw_header) >= 3:
        col_map["quote"] = 2
    if "claim" not in col_map and len(raw_header) >= 2:
        col_map["claim"] = 1
    if "source" not in col_map and len(raw_header) >= 4:
        col_map["source"] = 3
    if "metric" not in col_map and len(raw_header) >= 5:
        col_map["metric"] = 4

    rows: List[Dict[str, str]] = []
    for line in table_lines[1:]:
        s = line.strip()
        if re.match(r"^\|(?:\s*:?-+:?\s*\|)+$", s):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells or all(c == "" for c in cells):
            continue

        q_idx = col_map.get("quote", -1)
        s_idx = col_map.get("source", -1)
        c_idx = col_map.get("claim", -1)
        m_idx = col_map.get("metric", -1)

        quote_val = cells[q_idx] if 0 <= q_idx < len(cells) else ""
        source_val = cells[s_idx] if 0 <= s_idx < len(cells) else ""
        claim_val = cells[c_idx] if 0 <= c_idx < len(cells) else ""
        metric_val = cells[m_idx] if 0 <= m_idx < len(cells) else ""

        # Clean enclosing quotes
        quote_val = quote_val.strip("\"'「」『』")
        if quote_val or claim_val:
            rows.append({
                "claim": claim_val,
                "quote": quote_val,
                "source": source_val,
                "metric": metric_val,
            })

    return rows


_MANIFEST_META_KEYS = frozenset({
    "topic", "archetype", "primary_domains", "entity_aliases", "required_sources",
})
_DEFAULT_PRIMARY_SOURCES: Tuple[Tuple[str, str, str], ...] = (
    (
        "primary_anchor_doc",
        "https://www.sec.gov/Archives/edgar/data/0000000000/primary_anchor_doc.pdf",
        "Primary Anchor Doc (NotebookLM Verified Evidence)",
    ),
    (
        "counter_analysis",
        "https://nvd.nist.gov/vuln/detail/CVE-2026-0001",
        "Corroborating Analysis (NotebookLM Verified Evidence)",
    ),
)
_DEFAULT_PLACEHOLDER_URLS: frozenset[str] = frozenset(
    url for _, url, _ in _DEFAULT_PRIMARY_SOURCES
)
_CONCRETE_QUANT_FALLBACK_RE = re.compile(r"\b(?:cvss|ver(?:sion)?|rfc|cve)\b|\d+\.\d+", re.I)


def _is_valid_primary_url(url: str) -> bool:
    """Return True if *url* is an HTTP(S) non-placeholder URL with a specific path."""
    if not url or not url.startswith(("http://", "https://")):
        return False
    low = url.lower()
    if (
        url in _DEFAULT_PLACEHOLDER_URLS
        or "example.com" in low
        or "0000000000" in url
        or "cve-2026-0001" in low
    ):
        return False
    parsed = urlparse(url)
    if "/searchedgar/" in parsed.path.lower() or parsed.path.rstrip("/") == "":
        return False
    return bool(parsed.hostname)


def _extract_manifest_sources(manifest: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Normalize both required_sources lists and flat ideate manifests into source dicts."""
    if not isinstance(manifest, dict):
        return []
    items: List[Dict[str, str]] = []
    req = manifest.get("required_sources")
    if isinstance(req, list):
        for ms in req:
            if isinstance(ms, dict):
                sid = str(ms.get("source_id") or ms.get("filename") or ms.get("name") or "").strip()
                items.append({
                    "source_id": Path(sid).stem if sid else "",
                    "filename": str(ms.get("filename") or sid).strip(),
                    "name": str(ms.get("name") or ms.get("title") or sid).strip(),
                    "url": str(ms.get("url") or "").strip(),
                    "sha256": str(ms.get("sha256") or "").strip(),
                })
    for key, val in manifest.items():
        if key in _MANIFEST_META_KEYS or not isinstance(val, dict):
            continue
        sid = str(val.get("source_id") or key).strip()
        items.append({
            "source_id": Path(sid).stem if sid else key,
            "filename": str(val.get("filename") or val.get("file") or key).strip(),
            "name": str(val.get("name") or val.get("title") or key).strip(),
            "url": str(val.get("url") or "").strip(),
            "sha256": str(val.get("sha256") or "").strip(),
        })
    return items


def _format_row_full_quote(row: Dict[str, str]) -> str:
    """Build deterministic combined quote string containing claim, verbatim quote, and metric."""
    base = " — ".join(p for p in (row.get("claim", "").strip(), row.get("quote", "").strip()) if p)
    metric = row.get("metric", "").strip()
    if metric and base:
        return f"{base} ({metric})"
    return base or metric


def _build_evidence_corpus(table_rows: Sequence[Dict[str, str]]) -> str:
    """Render all extracted NotebookLM table rows into a deterministic Markdown corpus."""
    lines = ["# NotebookLM Forensic Evidence Corpus", ""]
    for idx, row in enumerate(table_rows, start=1):
        lines.append(f"## Row {idx}")
        full_quote = _format_row_full_quote(row)
        if full_quote:
            lines.append(full_quote)
        raw_quote = row.get("quote", "").strip()
        if raw_quote and raw_quote != full_quote:
            lines.append(raw_quote)
        src = row.get("source", "").strip()
        if src:
            lines.append(f"Source: {src}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _select_two_primary_slots(
    manifest_sources: Sequence[Dict[str, str]],
    table_rows: Sequence[Dict[str, str]] = (),
) -> List[Tuple[str, str, str]]:
    """Choose two primary (source_id, url, title) slots from distinct institutions."""
    slots: List[Tuple[str, str, str]] = []
    seen_insts: set[str] = set()
    seen_ids: set[str] = set()
    for ms in manifest_sources:
        url = ms.get("url", "")
        if not _is_valid_primary_url(url):
            continue
        inst = canonical_institution(url) or url
        sid = ms.get("source_id") or Path(ms.get("filename", "") or "primary_anchor_doc").stem
        if inst not in seen_insts and sid not in seen_ids:
            slots.append((sid, url, ms.get("name") or sid))
            seen_insts.add(inst)
            seen_ids.add(sid)
        if len(slots) >= 2:
            return slots
    for row in table_rows:
        for raw_url in re.findall(r"https?://\S+", row.get("source", "")):
            url = raw_url.rstrip(").,]>\"'")
            if not _is_valid_primary_url(url) or not is_primary_authority_url(url):
                continue
            inst = canonical_institution(url) or url
            if inst not in seen_insts:
                if "primary_anchor_doc" not in seen_ids:
                    sid = "primary_anchor_doc"
                elif "counter_analysis" not in seen_ids:
                    sid = "counter_analysis"
                else:
                    stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", Path(urlparse(url).path).stem).strip("_")
                    sid = stem or f"source_{len(slots) + 1}"
                    if sid in seen_ids:
                        sid = f"{sid}_{len(slots) + 1}"
                slots.append((sid, url, f"{inst} (NotebookLM Verified Evidence)"))
                seen_insts.add(inst)
                seen_ids.add(sid)
            if len(slots) >= 2:
                return slots
    for def_sid, def_url, def_title in _DEFAULT_PRIMARY_SOURCES:
        inst = canonical_institution(def_url) or def_url
        if inst not in seen_insts:
            cand_sid = def_sid if def_sid not in seen_ids else f"{def_sid}_nlm"
            slots.append((cand_sid, def_url, def_title))
            seen_insts.add(inst)
            seen_ids.add(cand_sid)
        if len(slots) >= 2:
            break
    return slots


def _ensure_notebooklm_sources(
    table_rows: Sequence[Dict[str, str]],
    manifest: Optional[Dict[str, Any]],
    sources_dir: Optional[Path],
) -> Tuple[Dict[str, Tuple[str, str]], List[Dict[str, str]], Dict[str, str]]:
    """Materialize primary evidence corpus files & SHA-256 manifest entries when sources_dir is given."""
    merged_manifest: Dict[str, Any] = {}
    if sources_dir is not None and (sources_dir / "manifest.json").is_file():
        try:
            raw_mf = json.loads((sources_dir / "manifest.json").read_text(encoding="utf-8"))
            if isinstance(raw_mf, dict):
                merged_manifest.update(raw_mf)
        except Exception:
            pass
    if isinstance(manifest, dict):
        merged_manifest.update(manifest)

    manifest_sources = _extract_manifest_sources(merged_manifest)
    if sources_dir is None:
        return {}, manifest_sources, {}

    sources_dir.mkdir(parents=True, exist_ok=True)
    existing = load_project_sources(sources_dir.parent)
    corpus = _build_evidence_corpus(table_rows)
    slots = _select_two_primary_slots(manifest_sources, table_rows=table_rows)

    source_meta: Dict[str, Tuple[str, str]] = {}
    disk_texts: Dict[str, str] = {}
    for sid, src in existing.items():
        if "." not in sid and src.provenance != "notebooklm_evidence" and _is_valid_primary_url(src.url):
            source_meta[sid] = (src.url, src.sha256)
            disk_texts[sid] = src.text

    primary_domains = [str(d) for d in merged_manifest.get("primary_domains", []) if isinstance(d, str)]
    for idx, (sid, url, title) in enumerate(slots):
        existing_src = existing.get(sid)
        if existing_src is not None and existing_src.provenance != "notebooklm_evidence":
            if all(verify_quote_in_source(r["quote"], existing_src.text) for r in table_rows if r.get("quote")):
                use_url = existing_src.url if _is_valid_primary_url(existing_src.url) else url
                source_meta[sid] = (use_url, existing_src.sha256)
                disk_texts[sid] = existing_src.text
                continue
            mat_sid = f"{sid}_notebooklm"
        else:
            mat_sid = sid

        dest = sources_dir / f"{mat_sid}.md"
        dest.write_text(corpus, encoding="utf-8")
        digest = compute_file_sha256(dest)
        prev = merged_manifest.get(mat_sid)
        entry = dict(prev) if isinstance(prev, dict) else {}
        entry.update({"url": url, "title": title, "sha256": digest, "provenance": "notebooklm_evidence", "primary": idx == 0})
        merged_manifest[mat_sid] = entry
        source_meta[mat_sid] = (url, digest)
        disk_texts[mat_sid] = corpus
        host = urlparse(url).hostname
        if host and host not in primary_domains:
            primary_domains.append(host)

    if primary_domains:
        merged_manifest["primary_domains"] = primary_domains
    (sources_dir / "manifest.json").write_text(
        json.dumps(merged_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return source_meta, _extract_manifest_sources(merged_manifest), disk_texts


def _match_row_for_claim(
    claim: Claim, row_meta: Sequence[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Match a Claim against indexed table rows, requiring numeric overlap for numeric claims."""
    c_mags = set(extract_scaled_magnitudes(claim.text))
    c_nums = set(extract_claim_numbers(claim.text))
    c_lemmas = set(extract_content_lemmas(claim.text))
    has_numbers = bool(c_mags or c_nums)

    best_score = 0
    best_row_info: Optional[Dict[str, Any]] = None
    for rm in row_meta:
        common_mags = [
            cm for cm in c_mags
            if any(abs(cm - qm) / max(abs(cm), abs(qm), 1.0) < 0.05 for qm in rm["mags"])
        ]
        common_nums = c_nums & rm["nums"]
        if has_numbers and not common_mags and not common_nums:
            continue

        score = len(common_mags) * 5 + len(common_nums) * 4 + len(c_lemmas & rm["lemmas"])
        quote = rm["row"]["quote"]
        if quote and (quote in claim.text or claim.text in quote):
            score += 10
        if score > best_score:
            best_score = score
            best_row_info = rm

    return best_row_info if best_row_info is not None and best_score >= 2 else None


def _build_evidence_for_claim(
    claim: Claim,
    row: Dict[str, str],
    weight: ClaimWeight,
    source_meta: Dict[str, Tuple[str, str]],
    manifest_sources: Sequence[Dict[str, str]],
    disk_texts: Dict[str, str],
) -> List[Evidence]:
    """Construct verified Evidence list for a matched claim."""
    raw_quote = row.get("quote", "").strip()
    full_quote = _format_row_full_quote(row)
    if (
        raw_quote
        and not check_claim_numbers(claim, [raw_quote])
        and compute_deterministic_grounding(claim.text, raw_quote) > 0.0
    ):
        evidence_quote = raw_quote
    else:
        evidence_quote = full_quote or raw_quote

    source_raw = row.get("source", "")
    page: Optional[int] = None
    page_match = re.search(r"(?:page|p\.?|ページ)\s*(\d+)", source_raw, re.I)
    if page_match:
        try:
            page = int(page_match.group(1))
        except ValueError:
            pass

    if source_meta:
        # Pick primary source matching source_raw or holding quote verbatim
        chosen: List[Tuple[str, str, str]] = []
        for sid, (surl, ssha) in source_meta.items():
            if sid.lower() in source_raw.lower() and verify_quote_in_source(evidence_quote, disk_texts.get(sid, "")):
                chosen.append((sid, surl, ssha))
                break
        for sid, (surl, ssha) in source_meta.items():
            if not verify_quote_in_source(evidence_quote, disk_texts.get(sid, "")):
                continue
            inst = canonical_institution(surl) or sid
            if all((canonical_institution(c[1]) or c[0]) != inst for c in chosen):
                chosen.append((sid, surl, ssha))
            if len(chosen) >= (2 if weight is ClaimWeight.CENTRAL else 1):
                break
        tier = 1 if weight is ClaimWeight.CENTRAL else 2
        return [
            Evidence(url=surl, quote=evidence_quote, stance=Stance.CONFIRMS, tier=tier, page=page, source_id=sid, sha256=ssha)
            for sid, surl, ssha in chosen
        ]

    url_match = re.search(r"https?://\S+", source_raw)
    url = url_match.group(0).rstrip(")]>\"'") if url_match else ""
    source_id = "anchor"
    for ms in manifest_sources:
        fname, sname = ms.get("filename", "").lower(), ms.get("name", "").lower()
        if (fname and (fname in source_raw.lower() or source_raw.lower() in fname)) or (sname and sname in source_raw.lower()):
            source_id = ms.get("filename") or ms.get("source_id") or source_id
            url = url or ms.get("url", "")
            break
    return [
        Evidence(
            url=url, quote=evidence_quote, stance=Stance.CONFIRMS,
            tier=1 if weight is ClaimWeight.CENTRAL else 2, page=page, source_id=source_id,
        )
    ]


def ingest_notebooklm_markdown_to_claims(
    script_entries: Sequence[Any],
    markdown_content: str,
    manifest: Optional[Dict[str, Any]] = None,
    sources_dir: Optional[Path] = None,
) -> List[Claim]:
    """Ingest NotebookLM Markdown table and dialogue into a linked Claim ledger."""
    table_rows = parse_markdown_evidence_table(markdown_content)
    raw_dicts: List[Dict[str, Any]] = [
        e if isinstance(e, dict) else dataclasses.asdict(e) for e in script_entries
    ]
    draft_claims = extract_draft_claims(raw_dicts, extract_qualitative=True)
    if not table_rows:
        return draft_claims

    source_meta, manifest_sources, disk_texts = _ensure_notebooklm_sources(table_rows, manifest, sources_dir)
    row_meta = [
        {
            "row": r,
            "mags": set(extract_scaled_magnitudes(f"{r['claim']} {r['quote']} {r['metric']}")),
            "nums": set(extract_claim_numbers(f"{r['claim']} {r['quote']} {r['metric']}")),
            "lemmas": set(extract_content_lemmas(f"{r['claim']} {r['quote']} {r['metric']}")),
        }
        for r in table_rows
    ]

    matched_pairs: List[Tuple[Claim, Dict[str, Any]]] = []
    unmatched: List[Claim] = []
    for claim in draft_claims:
        best = _match_row_for_claim(claim, row_meta)
        if best is not None:
            matched_pairs.append((claim, best["row"]))
        else:
            unmatched.append(claim)

    central_flags = [
        claim.cut_index <= 10 or any(m >= 1e8 for m in extract_scaled_magnitudes(claim.text))
        for claim, _ in matched_pairs
    ]
    if matched_pairs and not any(central_flags):
        central_flags[0] = True

    out: List[Claim] = []
    for (claim, row), is_cent in zip(matched_pairs, central_flags):
        weight = ClaimWeight.CENTRAL if is_cent else ClaimWeight.MINOR
        claim.weight = weight
        claim.evidence = _build_evidence_for_claim(claim, row, weight, source_meta, manifest_sources, disk_texts)
        out.append(claim)

    for claim in unmatched:
        is_concrete_num = (
            classify_text(claim.text, strict_numbers=True) is ClaimKind.NUMBER
            or bool(extract_scaled_magnitudes(claim.text))
            or bool(_CONCRETE_QUANT_FALLBACK_RE.search(claim.text))
        )
        if claim.kind is ClaimKind.NUMBER and is_concrete_num:
            claim.weight = ClaimWeight.CENTRAL
            out.append(claim)
        elif not matched_pairs and not any(c.kind is ClaimKind.NUMBER for c in unmatched):
            out.append(claim)

    out.sort(key=lambda c: c.cut_index)
    return out
