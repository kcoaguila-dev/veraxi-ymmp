"""Deterministic temporal recency gate and audit for claims and sources.

Eliminates LLM 'temporal muscle memory' (such as defaulting to 2023/2024 when
operating in 2026) by deterministically inspecting claims, primary source keys,
and URLs for stale temporal anchors.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from veraxi_ymmp.epistemic.facts import Claim


class StaleTemporalSourceError(RuntimeError):
    """Raised when a claim cites a stale temporal source as current."""


@dataclass(frozen=True)
class TemporalViolation:
    """Represents a detected temporal recency violation in a claim."""

    claim_id: str
    text: str
    detected_year: int
    operational_year: int
    severity: str  # 'ERROR' or 'WARNING'
    message: str


# Regex patterns for year detection and present/historical markers
_YEAR_PATTERN = re.compile(r"\b(20[12]\d)\b|(?:FY|fy)[\s_-]?([12]\d(?:\d{2})?)")
_JP_YEAR_PATTERN = re.compile(r"(20[12]\d)年(?:度)?")
_PRESENT_INDICATORS_JP = ("現在", "今年", "直近", "最新", "今や", "足元では", "足もとでは", "現時点で")
_PRESENT_INDICATORS_EN = ("currently", "this year", "latest", "as of now", "recent", "presently", "today")
_HISTORICAL_INDICATORS_JP = ("当時", "過去", "だった", "であった", "以前", "さかのぼる", "振り返ると")
_HISTORICAL_INDICATORS_EN = ("back in", "formerly", "historically", "in the past", "was", "were", "previously")


def get_default_operational_year() -> int:
    """Return the current operational year based on system date."""
    return datetime.date.today().year


def extract_referenced_years(text: str) -> List[int]:
    """Extract all calendar or fiscal years from text."""
    years: List[int] = []

    # Check western years and FY notation
    for match in _YEAR_PATTERN.finditer(text):
        standard_yr, fy_yr = match.groups()
        if standard_yr:
            years.append(int(standard_yr))
        elif fy_yr:
            yr_int = int(fy_yr)
            if yr_int < 100:
                yr_int += 2000
            years.append(yr_int)

    # Check Japanese year pattern
    for match in _JP_YEAR_PATTERN.finditer(text):
        years.append(int(match.group(1)))

    return sorted(list(set(years)))


def is_explicitly_historical(text: str) -> bool:
    """Determine whether the text explicitly frames the event in the past."""
    lower = text.lower()
    for marker in _HISTORICAL_INDICATORS_JP:
        if marker in text:
            return True
    for marker in _HISTORICAL_INDICATORS_EN:
        if marker in lower:
            return True
    return False


def has_present_tense_indicator(text: str) -> bool:
    """Determine whether the text asserts current state or present reality."""
    lower = text.lower()
    for marker in _PRESENT_INDICATORS_JP:
        if marker in text:
            return True
    for marker in _PRESENT_INDICATORS_EN:
        if marker in lower:
            return True
    return False


def audit_temporal_recency(
    claims: Sequence[Claim],
    operational_year: Optional[int] = None,
    max_stale_years_allowed: int = 1,
) -> List[TemporalViolation]:
    """Audit a sequence of claims against the operational year.

    Flags claims where:
    1. The assertion or primary source references a fiscal or calendar year older
       than (operational_year - max_stale_years_allowed), AND
    2. The claim asserts present-tense factuality without explicit historical framing.
    """
    if operational_year is None:
        operational_year = get_default_operational_year()

    stale_threshold = operational_year - max_stale_years_allowed
    violations: List[TemporalViolation] = []

    for claim in claims:
        # Check years in claim text (support both .text and legacy .assertion)
        claim_text = getattr(claim, "text", "") or getattr(claim, "assertion", "") or ""
        claim_years = extract_referenced_years(claim_text)

        # Check years embedded in evidence source IDs or URLs
        source_years: List[int] = []
        if hasattr(claim, "evidence") and claim.evidence:
            for ev in claim.evidence:
                source_id = getattr(ev, "source_id", "") or getattr(ev, "source_key", "") or ""
                url = getattr(ev, "url", "") or ""
                combined_source_text = f"{source_id} {url}"
                source_years.extend(extract_referenced_years(combined_source_text))

        all_years = sorted(list(set(claim_years + source_years)))

        # Evaluate recency for each detected year
        for yr in all_years:
            if yr < stale_threshold:
                historical = is_explicitly_historical(claim_text)
                present = has_present_tense_indicator(claim_text)

                if present or not historical:
                    msg = (
                        f"STALE_TEMPORAL_SOURCE_ERROR: Claim {claim.id} cites year/FY{yr} "
                        f"as current when FY{operational_year} is the operational anchor."
                    )
                    violations.append(
                        TemporalViolation(
                            claim_id=claim.id,
                            text=claim_text,
                            detected_year=yr,
                            operational_year=operational_year,
                            severity="ERROR" if present else "WARNING",
                            message=msg,
                        )
                    )

    return violations


def enforce_temporal_recency(
    claims: Sequence[Claim],
    operational_year: Optional[int] = None,
    max_stale_years_allowed: int = 1,
) -> None:
    """Raise StaleTemporalSourceError if any ERROR-level temporal violations exist."""
    violations = audit_temporal_recency(
        claims,
        operational_year=operational_year,
        max_stale_years_allowed=max_stale_years_allowed,
    )
    errors = [v for v in violations if v.severity == "ERROR"]
    if errors:
        error_msgs = "\n".join(f"- {e.message}" for e in errors)
        raise StaleTemporalSourceError(
            f"Epistemic temporal gate failed with {len(errors)} error(s):\n{error_msgs}"
        )
