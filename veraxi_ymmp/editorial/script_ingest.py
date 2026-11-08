"""Parser and compiler converting raw Markdown dialogue into validated DirectorScriptEntry JSON and claims.json."""
from __future__ import annotations

import re
from typing import List, Dict, Any, Optional, Sequence

from veraxi_ymmp.core.script import (
    DirectorScriptEntry,
    validate_director_script,
    CharacterPosition,
    Emotion,
    Motion,
)
from veraxi_ymmp.epistemic.facts import (
    Claim,
    ClaimWeight,
    Evidence,
    Stance,
)
from veraxi_ymmp.epistemic.fact_audit import extract_draft_claims
from veraxi_ymmp.epistemic.epistemic_units import extract_scaled_magnitudes, extract_content_lemmas

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
    if "！？" in text or "?!" in text or "ええっ" in text or "はぁ" in text:
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


def split_text_to_char_limit(text: str, max_chars: int = 38) -> List[str]:
    """Split text into cuts <= max_chars, breaking naturally on punctuation or BudouX semantic phrases."""
    text = text.strip()
    if len(text) <= max_chars:
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
        if len(item) <= max_chars:
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
                if len(c) > max_chars:
                    while len(c) > max_chars:
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
        if len(accum) + len(p) <= max_chars:
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

    raw_cuts: List[Dict[str, Any]] = []

    for line in markdown_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("|") or line.startswith("```"):
            continue

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
                "image": None if cut_idx < 3 else None,  # Cold open hook protection
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


def ingest_notebooklm_markdown_to_claims(
    script_entries: Sequence[Dict[str, Any]],
    markdown_content: str,
    manifest: Optional[Dict[str, Any]] = None,
) -> List[Claim]:
    """Ingest NotebookLM Markdown table and dialogue into a linked Claim ledger."""
    table_rows = parse_markdown_evidence_table(markdown_content)
    draft_claims = extract_draft_claims(script_entries, extract_qualitative=True)

    if not table_rows:
        return draft_claims

    # Build row search signatures
    row_meta: List[Dict[str, Any]] = []
    for r in table_rows:
        combined_text = f"{r['claim']} {r['quote']} {r['metric']}"
        mags = set(extract_scaled_magnitudes(combined_text))
        lemmas = set(extract_content_lemmas(combined_text))
        row_meta.append({
            "row": r,
            "mags": mags,
            "lemmas": lemmas,
        })

    # Match each draft claim against table rows
    for claim in draft_claims:
        c_mags = set(extract_scaled_magnitudes(claim.text))
        c_lemmas = set(extract_content_lemmas(claim.text))

        best_score = 0
        best_row_info: Optional[Dict[str, Any]] = None

        for rm in row_meta:
            score = 0
            # Numeric magnitude intersection
            common_mags = c_mags & rm["mags"]
            if common_mags:
                score += len(common_mags) * 5

            # Morphological lemma intersection
            common_lemmas = c_lemmas & rm["lemmas"]
            if common_lemmas:
                score += len(common_lemmas)

            # Direct quote substring match
            if rm["row"]["quote"] and (rm["row"]["quote"] in claim.text or claim.text in rm["row"]["quote"]):
                score += 10

            if score > best_score:
                best_score = score
                best_row_info = rm

        # Link evidence if match threshold met
        if best_row_info is not None and best_score >= 2:
            r = best_row_info["row"]
            quote = r["quote"]
            source_raw = r["source"]

            # Extract page number
            page: Optional[int] = None
            page_match = re.search(r"(?:page|p\.?|ページ)\s*(\d+)", source_raw, re.I)
            if page_match:
                try:
                    page = int(page_match.group(1))
                except ValueError:
                    pass

            # Extract URL if present in source or manifest
            url = ""
            url_match = re.search(r"https?://\S+", source_raw)
            if url_match:
                url = url_match.group(0).rstrip(")]>\"'")

            source_id = "anchor"
            # Match source against manifest if available
            if manifest:
                manifest_sources = manifest.get("required_sources") or []
                if isinstance(manifest_sources, list):
                    for ms in manifest_sources:
                        if isinstance(ms, dict):
                            fname = str(ms.get("filename", "")).lower()
                            sname = str(ms.get("name", "")).lower()
                            if fname and (fname in source_raw.lower() or source_raw.lower() in fname):
                                source_id = ms.get("filename", source_id)
                                if not url and ms.get("url"):
                                    url = ms["url"]
                                break
                            elif sname and sname in source_raw.lower():
                                source_id = ms.get("filename", source_id)
                                if not url and ms.get("url"):
                                    url = ms["url"]
                                break

            # Weight classification: Cold Open / Hook (cuts 0..10) must be CENTRAL
            weight = ClaimWeight.CENTRAL if claim.cut_index <= 10 else ClaimWeight.MINOR

            claim.weight = weight
            claim.evidence = [
                Evidence(
                    url=url,
                    quote=quote,
                    stance=Stance.CONFIRMS,
                    tier=1 if weight == ClaimWeight.CENTRAL else 2,
                    page=page,
                    source_id=source_id,
                )
            ]

    return draft_claims
