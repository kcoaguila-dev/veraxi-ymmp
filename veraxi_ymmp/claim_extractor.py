"""Check-worthiness filter: separate verifiable factual assertions from banter.

Heuristic, deliberately conservative first pass that *drafts* a ledger. A human or
LLM reviewer confirms kinds/weights; jokes, reactions and hyperbole are tagged
COMMENTARY so they can never be "wrong" or block a render. Draft claims never get
evidence from here, so they start UNVERIFIED rather than falsely supported.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

from .facts import Claim, ClaimKind, ClaimWeight

# Digits (incl. full-width), currency/scale words, percentages, years, quantities.
_FACT_SIGNAL = re.compile(r"[0-9０-９]|[億兆万]|[%％]|ドル|円|年間|四半期|決算|シェア|倍")
_REACTION_END = re.compile(r"[！？!?…]+$")
_MAX_REACTION_LEN = 12


def classify_text(text: str) -> ClaimKind | None:
    """Return the claim kind, or None when the cut contains nothing to fact-check."""
    stripped = text.strip()
    if not stripped:
        return None
    # Short punctuated beats ("はぁ！？", "25兆円！？") echo a fact; the source cut owns it.
    if len(stripped) <= _MAX_REACTION_LEN and _REACTION_END.search(stripped):
        return ClaimKind.COMMENTARY
    if not _FACT_SIGNAL.search(stripped):
        return None
    return ClaimKind.NUMBER


def extract_draft_claims(script: Sequence[Dict[str, Any]], existing: Sequence[Claim] = ()) -> List[Claim]:
    """Draft claims for factual dialogue cuts, keeping any existing human-curated claims.

    Existing claims win (by cut_index + text) so reviewed evidence is never overwritten.
    """
    known = {(c.cut_index, c.text) for c in existing}
    next_id = len(existing) + 1
    drafts: List[Claim] = []
    for idx, entry in enumerate(script):
        text = entry.get("text")
        if not isinstance(text, str) or ("type" in entry and "character" not in entry):
            continue
        if classify_text(text) is not ClaimKind.NUMBER or (idx, text) in known:
            continue
        drafts.append(Claim(f"d{next_id:02d}", idx, text, ClaimKind.NUMBER, ClaimWeight.MINOR))
        next_id += 1
    return list(existing) + drafts
