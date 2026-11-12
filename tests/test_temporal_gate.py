"""Tests for epistemic temporal recency gate."""

import pytest
from veraxi_ymmp.epistemic.facts import Claim, Evidence, Stance
from veraxi_ymmp.epistemic.temporal_gate import (
    StaleTemporalSourceError,
    TemporalParityMismatchError,
    assert_temporal_parity,
    audit_temporal_recency,
    enforce_temporal_recency,
    extract_referenced_years,
    normalize_to_canonical_period,
)


def test_extract_referenced_years() -> None:
    text_en = "In FY24 Amazon spent billions, and by 2026 Azure caught up."
    years_en = extract_referenced_years(text_en)
    assert 2024 in years_en
    assert 2026 in years_en

    text_jp = "2024年度の決算と2026年の動向"
    years_jp = extract_referenced_years(text_jp)
    assert 2024 in years_jp
    assert 2026 in years_jp


def test_extract_referenced_years_ignores_cve_identifiers() -> None:
    # The 2024 in CVE-2024-3094 is an identifier segment, not a calendar year.
    assert extract_referenced_years("CVE-2024-3094") == []
    assert extract_referenced_years("脆弱性CVE-2024-3094の危険度は10.0") == []
    assert extract_referenced_years("https://nvd.nist.gov/vuln/detail/CVE-2024-3094") == []
    assert extract_referenced_years("nvd_cve_2024_3094") == []
    # A standalone year next to an identifier is still a real year.
    years = extract_referenced_years("Disclosed in 2024 as CVE-2024-3094, patched by 2026.")
    assert years == [2024, 2026]


def test_audit_ignores_cve_identifier_years() -> None:
    cve_claim = Claim(
        id="cve01",
        cut_index=1,
        text="脆弱性CVE-2024-3094の危険度は10.0です。",
        evidence=[
            Evidence(
                url="https://nvd.nist.gov/vuln/detail/CVE-2024-3094",
                quote="CVE-2024-3094 has a CVSS severity score of 10.0 critical.",
                source_id="nvd_cve_2024_3094",
                stance=Stance.CONFIRMS,
            )
        ],
    )
    violations = audit_temporal_recency([cve_claim], operational_year=2026)
    assert violations == []


def test_audit_flags_stale_present_tense_claims() -> None:
    stale_claim = Claim(
        id="c01",
        cut_index=0,
        text="現在の年間設備投資額は、FY2024の決算書によると830億ドルです。",
        evidence=[
            Evidence(
                url="https://www.sec.gov/amzn-20241231.htm",
                quote="82,999",
                source_id="sec_amzn_10k_fy24",
                stance=Stance.CONFIRMS,
            )
        ],
    )

    violations = audit_temporal_recency([stale_claim], operational_year=2026)
    assert len(violations) > 0
    assert any(v.severity == "ERROR" for v in violations)
    assert any(v.detected_year == 2024 for v in violations)


def test_historical_framing_allowed_as_warning_not_breaking_error() -> None:
    historical_claim = Claim(
        id="c02",
        cut_index=1,
        text="2024年当時はアマゾンの設備投資が先行していました。",
        evidence=[],
    )

    violations = audit_temporal_recency([historical_claim], operational_year=2026)
    # Historical statement should not trigger an ERROR severity
    assert all(v.severity != "ERROR" for v in violations)


def test_compliant_2026_claims_pass_cleanly() -> None:
    fresh_claim = Claim(
        id="c03",
        cut_index=2,
        text="2026年のマイクロソフトの最新決算では増収が続いています。",
        evidence=[
            Evidence(
                url="https://www.sec.gov/msft-20260630.htm",
                quote="revenue increased",
                source_id="sec_msft_10k_fy26",
                stance=Stance.CONFIRMS,
            )
        ],
    )

    violations = audit_temporal_recency([fresh_claim], operational_year=2026)
    assert len(violations) == 0


def test_enforce_temporal_recency_raises_error() -> None:
    stale_claim = Claim(
        id="c01",
        cut_index=0,
        text="現在の年間設備投資額はFY24決算で830億ドルです。",
        evidence=[],
    )

    with pytest.raises(StaleTemporalSourceError, match="STALE_TEMPORAL_SOURCE_ERROR"):
        enforce_temporal_recency([stale_claim], operational_year=2026)


def test_canonical_period_normalization_msft_q1_fy27_vs_amzn_q3_2026() -> None:
    msft = normalize_to_canonical_period("MSFT", "Q1 FY2027")
    amzn = normalize_to_canonical_period("AMZN", "Q3 2026")

    assert msft.calendar_quarter == "2026-Q3"
    assert amzn.calendar_quarter == "2026-Q3"
    assert msft.period_end.isoformat() == "2026-09-30"
    assert amzn.period_end.isoformat() == "2026-09-30"

    # Parity assertion must succeed without error
    assert_temporal_parity([msft, amzn])


def test_temporal_parity_fails_on_annual_vs_quarterly() -> None:
    msft_annual = normalize_to_canonical_period("MSFT", "FY2026")
    amzn_quarter = normalize_to_canonical_period("AMZN", "Q3 2026")

    with pytest.raises(TemporalParityMismatchError, match="Comparing annual filing"):
        assert_temporal_parity([msft_annual, amzn_quarter])


def test_temporal_parity_fails_on_divergent_quarters() -> None:
    msft_old_q = normalize_to_canonical_period("MSFT", "Q3 FY2026")  # Ended 2026-03-31
    amzn_new_q = normalize_to_canonical_period("AMZN", "Q3 2026")   # Ended 2026-09-30

    with pytest.raises(TemporalParityMismatchError, match="diverge by"):
        assert_temporal_parity([msft_old_q, amzn_new_q])
