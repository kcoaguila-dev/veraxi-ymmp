"""Application service: audit a project's claim ledger and write its source dossier."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .claim_extractor import extract_draft_claims
from .fact_report import render_report
from .facts import (
    ClaimResult,
    ClaimWeight,
    canonical_institution,
    claims_to_json,
    enforce_source_tier,
    gate_failures,
    load_claims,
    verdict_for,
    verify_quote_in_source,
)

CLAIMS_FILENAME = "claims.json"
REPORT_FILENAME = "sources.md"

SOURCES_DIRNAME = "sources"


@dataclass
class StoredSource:
    text: str
    sha256: str
    url: str = ""

    def __iter__(self) -> Any:
        yield self.text
        yield self.sha256
        yield self.url


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 hexadecimal digest of a local file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_project_sources(project_dir: Path) -> Dict[str, StoredSource]:
    """Load text, SHA-256 checksums, and URL metadata for files in projects/<project>/sources/.

    Supports:
    - Sidecar metadata: <source_id>.meta.json with {"url": "https://..."}
    - Manifest file: sources/manifest.json or sources/sources.json mapping source_id to {"url": ...}
    - Document frontmatter: line starting with 'URL: https://...' or '<!-- URL: https://... -->'
    """
    sources_dir = project_dir / SOURCES_DIRNAME
    if not sources_dir.is_dir():
        return {}

    manifest: Dict[str, Any] = {}
    for mf_name in ("manifest.json", "sources.json"):
        mf_path = sources_dir / mf_name
        if mf_path.is_file():
            try:
                manifest = json.loads(mf_path.read_text(encoding="utf-8"))
                break
            except Exception:
                pass

    out: Dict[str, StoredSource] = {}
    valid_exts = {".txt", ".md", ".json", ".html", ".htm", ".csv"}
    for p in sources_dir.iterdir():
        if not p.is_file() or p.suffix.lower() not in valid_exts or p.name.endswith(".meta.json"):
            continue
        if p.name in ("manifest.json", "sources.json"):
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            digest = compute_file_sha256(p)
            source_url = ""

            # Check sidecar metadata <stem>.meta.json or <name>.meta.json
            meta_path = sources_dir / f"{p.stem}.meta.json"
            if not meta_path.is_file():
                meta_path = sources_dir / f"{p.name}.meta.json"
            if meta_path.is_file():
                try:
                    meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
                    source_url = str(meta_data.get("url", "")).strip()
                except Exception:
                    pass

            # Check manifest file
            if not source_url and manifest:
                entry = manifest.get(p.stem) or manifest.get(p.name) or {}
                if isinstance(entry, dict):
                    source_url = str(entry.get("url", "")).strip()
                elif isinstance(entry, str):
                    source_url = entry.strip()

            # Check header / frontmatter (strictly 'URL:', not loose citations like 'Source:')
            if not source_url:
                first_lines = content[:500].splitlines()
                for line in first_lines[:3]:
                    m = re.match(r"^(?:<!--\s*)?URL:\s*(https?://\S+?)(?:\s*-->)?$", line.strip(), re.I)
                    if m:
                        source_url = m.group(1).strip()
                        break

            item = StoredSource(content, digest, source_url)
            out[p.stem] = item
            out[p.name] = item
        except Exception:
            continue
    return out


@dataclass
class FactAuditOutcome:
    results: List[ClaimResult]
    blockers: List[ClaimResult]
    report_path: Path

    @property
    def blocked(self) -> bool:
        return bool(self.blockers)


def audit_project_facts(
    script_path: Path,
    title: str = "",
    cut_times: Optional[Dict[int, float]] = None,
) -> FactAuditOutcome:
    """Read `claims.json` beside the script, verify quotes against sources/, write `sources.md`, return outcome.

    Raises FileNotFoundError when no ledger exists: a video with no ledger is unaudited.
    """
    project_dir = script_path.parent
    claims_path = project_dir / CLAIMS_FILENAME
    if not claims_path.is_file():
        raise FileNotFoundError(f"No claim ledger found: {claims_path}")

    claims = load_claims(claims_path)
    sources = load_project_sources(project_dir)

    results: List[ClaimResult] = []
    for c in claims:
        quote_errors: List[str] = []
        for e in c.evidence:
            if not e.source_id:
                if c.weight is ClaimWeight.CENTRAL:
                    quote_errors.append(
                        f"central claim requires verified source in sources/, got unlinked '{e.url}'"
                    )
                continue
            if e.source_id not in sources:
                quote_errors.append(f"source '{e.source_id}' not found in sources/")
                continue
            src = sources[e.source_id]
            src_text, src_sha, src_url = src.text, src.sha256, src.url

            # Central claims FAIL-CLOSED security checks:
            if c.weight is ClaimWeight.CENTRAL:
                if not src_url:
                    quote_errors.append(
                        f"central claim source '{e.source_id}' has no registered origin URL (requires manifest.json or .meta.json)"
                    )
                elif enforce_source_tier(src_url, 1) != 1:
                    quote_errors.append(
                        f"central claim source '{e.source_id}' origin '{src_url}' is not a recognized Tier 1 primary authority"
                    )
                elif canonical_institution(e.url) != canonical_institution(src_url):
                    quote_errors.append(
                        f"source '{e.source_id}' registered for '{src_url}' ({canonical_institution(src_url)}), does not match evidence url '{e.url}' ({canonical_institution(e.url)})"
                    )

                if not e.sha256:
                    quote_errors.append(
                        f"central claim evidence for source '{e.source_id}' is missing required sha256 checksum"
                    )
                elif e.sha256.lower() != src_sha.lower():
                    quote_errors.append(
                        f"tampered source '{e.source_id}' (expected sha256 {e.sha256[:8]}, got {src_sha[:8]})"
                    )
            else:
                # Non-central claims checks
                if e.sha256 and e.sha256.lower() != src_sha.lower():
                    quote_errors.append(
                        f"tampered source '{e.source_id}' (expected sha256 {e.sha256[:8]}, got {src_sha[:8]})"
                    )
                elif src_url and canonical_institution(e.url) != canonical_institution(src_url):
                    quote_errors.append(
                        f"source '{e.source_id}' registered for '{src_url}', does not match evidence url '{e.url}'"
                    )

            if not verify_quote_in_source(e.quote, src_text):
                quote_errors.append(f"quote not found in stored source '{e.source_id}'")

        res = verdict_for(c, quote_errors=quote_errors)
        results.append(res)

    report_path = project_dir / REPORT_FILENAME
    report_path.write_text(
        render_report(title or project_dir.name, results, cut_times=cut_times),
        encoding="utf-8",
    )
    return FactAuditOutcome(results, gate_failures(results), report_path)


def draft_project_claims(script_path: Path, script: List[Dict[str, Any]]) -> Tuple[Path, int]:
    """Create or extend `claims.json` with draft claims; returns (path, number added)."""
    claims_path = script_path.parent / CLAIMS_FILENAME
    existing = load_claims(claims_path) if claims_path.is_file() else []
    merged = extract_draft_claims(script, existing)
    claims_path.write_text(claims_to_json(merged), encoding="utf-8")
    return claims_path, len(merged) - len(existing)
