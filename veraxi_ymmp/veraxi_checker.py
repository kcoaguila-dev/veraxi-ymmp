"""Adapter: translate Veraxi `mcp_fact_check` proof cards into domain Evidence.

The agent (or any caller) runs the MCP tool and passes the card text here; this
module never talks to the network. Critical rule: Veraxi can print "PASSED" with
0 passages retrieved (a vacuous pass). That is NOT a confirmation: no quote, no
evidence.
"""

from __future__ import annotations

import re
from typing import List

from .facts import Claim, Evidence, Stance

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
