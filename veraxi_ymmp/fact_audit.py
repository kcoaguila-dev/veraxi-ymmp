"""Application service: audit a project's claim ledger and write its source dossier."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .claim_extractor import extract_draft_claims
from .fact_report import render_report
from .facts import ClaimResult, audit, claims_to_json, gate_failures, load_claims

CLAIMS_FILENAME = "claims.json"
REPORT_FILENAME = "sources.md"


@dataclass
class FactAuditOutcome:
    results: List[ClaimResult]
    blockers: List[ClaimResult]
    report_path: Path

    @property
    def blocked(self) -> bool:
        return bool(self.blockers)


def audit_project_facts(script_path: Path, title: str = "") -> FactAuditOutcome:
    """Read `claims.json` beside the script, write `sources.md`, return the outcome.

    Raises FileNotFoundError when no ledger exists: a video with no ledger is unaudited.
    """
    project_dir = script_path.parent
    claims_path = project_dir / CLAIMS_FILENAME
    if not claims_path.is_file():
        raise FileNotFoundError(f"No claim ledger found: {claims_path}")
    results = audit(load_claims(claims_path))
    report_path = project_dir / REPORT_FILENAME
    report_path.write_text(render_report(title or project_dir.name, results), encoding="utf-8")
    return FactAuditOutcome(results, gate_failures(results), report_path)


def draft_project_claims(script_path: Path, script: List[Dict[str, Any]]) -> Tuple[Path, int]:
    """Create or extend `claims.json` with draft claims; returns (path, number added)."""
    claims_path = script_path.parent / CLAIMS_FILENAME
    existing = load_claims(claims_path) if claims_path.is_file() else []
    merged = extract_draft_claims(script, existing)
    claims_path.write_text(claims_to_json(merged), encoding="utf-8")
    return claims_path, len(merged) - len(existing)
