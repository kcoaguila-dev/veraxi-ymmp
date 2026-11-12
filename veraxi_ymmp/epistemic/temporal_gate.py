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


class TemporalParityMismatchError(RuntimeError):
    """Raised when compared entities in a multi-entity script have asymmetric temporal windows."""


@dataclass(frozen=True)
class CanonicalPeriod:
    """Represents a normalized canonical calendar reporting period for an entity."""

    entity: str
    fiscal_label: str
    period_start: datetime.date
    period_end: datetime.date
    calendar_quarter: str
    is_annual: bool = False

    @property
    def duration_days(self) -> int:
        return (self.period_end - self.period_start).days + 1


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
# Identifier schemes whose embedded 4-digit segment is an identifier component,
# not a calendar year (e.g. CVE-2024-3094, CWE-2023-1234, GHSA-2024-...).
# Both hyphenated (CVE-2024-3094, as in URLs / claim text) and underscored
# (cve_2024_3094, as in source IDs / file names) forms are stripped before
# year extraction so the stale-source gate never flags an identifier as a
# stale temporal anchor.
_IDENTIFIER_PATTERN = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:cve|cwe|ghsa|osv|pysec|rustsec|go)[_-]\d{4}[_-]\d{3,7}(?![0-9])"
)


def _strip_identifiers(text: str) -> str:
    """Remove structured identifiers (CVE/CWE/GHSA/...) from *text*.

    The year-like segment of an identifier such as ``CVE-2024-3094`` is part
    of the identifier, not a temporal claim, so it must not be treated as a
    referenced calendar year by the stale-source gate.
    """
    return _IDENTIFIER_PATTERN.sub(" ", text)
_JP_YEAR_PATTERN = re.compile(r"(20[12]\d)年(?:度)?")
_PRESENT_INDICATORS_JP = ("現在", "今年", "直近", "最新", "今や", "足元では", "足もとでは", "現時点で")
_PRESENT_INDICATORS_EN = ("currently", "this year", "latest", "as of now", "recent", "presently", "today")
_HISTORICAL_INDICATORS_JP = ("当時", "過去", "だった", "であった", "以前", "さかのぼる", "振り返ると")
_HISTORICAL_INDICATORS_EN = ("back in", "formerly", "historically", "in the past", "was", "were", "previously")


def get_default_operational_year() -> int:
    """Return the current operational year based on system date."""
    return datetime.date.today().year


def extract_referenced_years(text: str) -> List[int]:
    """Extract all calendar or fiscal years from text.

    Structured identifiers (e.g. ``CVE-2024-3094``) are ignored: their
    year-like segment names the identifier, not a point in time.
    """
    text = _strip_identifiers(text)
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


def _calendar_quarter_for_date(d: datetime.date) -> str:
    q = (d.month - 1) // 3 + 1
    return f"{d.year}-Q{q}"


def normalize_to_canonical_period(
    entity: str,
    fiscal_label: str,
    period_end: Optional[datetime.date | str] = None,
) -> CanonicalPeriod:
    """Normalize an entity's reporting period into a canonical calendar window.

    Handles non-standard fiscal years (such as Microsoft's June year-end and
    NVIDIA's January year-end) so cross-company comparisons operate on identical
    calendar windows.
    """
    clean_ticker = entity.strip().upper()
    label_upper = fiscal_label.strip().upper()

    # Parse period_end if provided
    end_date: Optional[datetime.date] = None
    if isinstance(period_end, str):
        end_date = datetime.date.fromisoformat(period_end)
    elif isinstance(period_end, datetime.date):
        end_date = period_end

    is_annual = "10-K" in label_upper or (
        ("FY" in label_upper or "ANNUAL" in label_upper) and not any(f"Q{i}" in label_upper for i in range(1, 5))
    )

    # Extract year and quarter tokens
    q_match = re.search(r"Q([1-4])", label_upper)
    quarter_num = int(q_match.group(1)) if q_match else None

    yr_match = re.search(r"(?:FY)?\s*([12]\d{3}|[12]\d)", label_upper)
    yr_token = None
    if yr_match:
        val = int(yr_match.group(1))
        yr_token = val if val > 2000 else val + 2000

    if end_date is None:
        if yr_token is None:
            raise ValueError(f"Cannot deduce canonical period without year or period_end for {entity} '{fiscal_label}'")

        if clean_ticker == "MSFT":
            # Microsoft fiscal year ends June 30 of yr_token
            # Q1 FY[Y]: Jul 1 - Sep 30 of (Y - 1)
            # Q2 FY[Y]: Oct 1 - Dec 31 of (Y - 1)
            # Q3 FY[Y]: Jan 1 - Mar 31 of Y
            # Q4 FY[Y]: Apr 1 - Jun 30 of Y
            if quarter_num == 1:
                start_date = datetime.date(yr_token - 1, 7, 1)
                end_date = datetime.date(yr_token - 1, 9, 30)
            elif quarter_num == 2:
                start_date = datetime.date(yr_token - 1, 10, 1)
                end_date = datetime.date(yr_token - 1, 12, 31)
            elif quarter_num == 3:
                start_date = datetime.date(yr_token, 1, 1)
                end_date = datetime.date(yr_token, 3, 31)
            elif quarter_num == 4:
                start_date = datetime.date(yr_token, 4, 1)
                end_date = datetime.date(yr_token, 6, 30)
            else:
                # Annual FY[Y]: Jul 1 (Y - 1) to Jun 30 (Y)
                start_date = datetime.date(yr_token - 1, 7, 1)
                end_date = datetime.date(yr_token, 6, 30)
                is_annual = True
        elif clean_ticker == "NVDA":
            # NVIDIA fiscal year ends Jan 31 of yr_token
            if quarter_num == 1:
                start_date = datetime.date(yr_token - 1, 2, 1)
                end_date = datetime.date(yr_token - 1, 4, 30)
            elif quarter_num == 2:
                start_date = datetime.date(yr_token - 1, 5, 1)
                end_date = datetime.date(yr_token - 1, 7, 31)
            elif quarter_num == 3:
                start_date = datetime.date(yr_token - 1, 8, 1)
                end_date = datetime.date(yr_token - 1, 10, 31)
            elif quarter_num == 4:
                start_date = datetime.date(yr_token - 1, 11, 1)
                end_date = datetime.date(yr_token, 1, 31)
            else:
                start_date = datetime.date(yr_token - 1, 2, 1)
                end_date = datetime.date(yr_token, 1, 31)
                is_annual = True
        elif clean_ticker == "AAPL":
            # Apple fiscal year ends Sep 30 of yr_token
            if quarter_num == 1:
                start_date = datetime.date(yr_token - 1, 10, 1)
                end_date = datetime.date(yr_token - 1, 12, 31)
            elif quarter_num == 2:
                start_date = datetime.date(yr_token, 1, 1)
                end_date = datetime.date(yr_token, 3, 31)
            elif quarter_num == 3:
                start_date = datetime.date(yr_token, 4, 1)
                end_date = datetime.date(yr_token, 6, 30)
            elif quarter_num == 4:
                start_date = datetime.date(yr_token, 7, 1)
                end_date = datetime.date(yr_token, 9, 30)
            else:
                start_date = datetime.date(yr_token - 1, 10, 1)
                end_date = datetime.date(yr_token, 9, 30)
                is_annual = True
        else:
            # Standard calendar year (AMZN, GOOGL, META, etc.)
            if quarter_num == 1:
                start_date = datetime.date(yr_token, 1, 1)
                end_date = datetime.date(yr_token, 3, 31)
            elif quarter_num == 2:
                start_date = datetime.date(yr_token, 4, 1)
                end_date = datetime.date(yr_token, 6, 30)
            elif quarter_num == 3:
                start_date = datetime.date(yr_token, 7, 1)
                end_date = datetime.date(yr_token, 9, 30)
            elif quarter_num == 4:
                start_date = datetime.date(yr_token, 10, 1)
                end_date = datetime.date(yr_token, 12, 31)
            else:
                start_date = datetime.date(yr_token, 1, 1)
                end_date = datetime.date(yr_token, 12, 31)
                is_annual = True
    else:
        # Deduce start_date from end_date
        if is_annual:
            start_date = end_date - datetime.timedelta(days=364)
        else:
            # Standard quarter ~ 90-92 days
            start_date = end_date - datetime.timedelta(days=91)

    cal_q = _calendar_quarter_for_date(end_date)

    return CanonicalPeriod(
        entity=clean_ticker,
        fiscal_label=fiscal_label,
        period_start=start_date,
        period_end=end_date,
        calendar_quarter=cal_q,
        is_annual=is_annual,
    )


def assert_temporal_parity(
    periods: Sequence[CanonicalPeriod],
    max_discrepancy_days: int = 14,
) -> None:
    """Assert that compared entity periods maintain temporal symmetry.

    Raises:
        TemporalParityMismatchError: If the end dates diverge by more than
        max_discrepancy_days, or if an annual filing is asymmetrically compared
        against a single quarter.
    """
    if len(periods) < 2:
        return

    first = periods[0]
    for other in periods[1:]:
        if first.is_annual != other.is_annual:
            raise TemporalParityMismatchError(
                f"TEMPORAL_PARITY_MISMATCH: Comparing annual filing {first.entity} ({first.fiscal_label}) "
                f"against quarterly filing {other.entity} ({other.fiscal_label}) violates parity."
            )

        diff_days = abs((first.period_end - other.period_end).days)
        if diff_days > max_discrepancy_days:
            raise TemporalParityMismatchError(
                f"TEMPORAL_PARITY_MISMATCH: {first.entity} ({first.fiscal_label}, ended {first.period_end}) "
                f"and {other.entity} ({other.fiscal_label}, ended {other.period_end}) "
                f"diverge by {diff_days} days (maximum permitted: {max_discrepancy_days}d)."
            )
