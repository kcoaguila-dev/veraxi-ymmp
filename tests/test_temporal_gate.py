"""Tests for epistemic temporal recency gate."""

import pytest
from veraxi_ymmp.epistemic.facts import Claim, Evidence, Stance
from veraxi_ymmp.epistemic.temporal_gate import (
    StaleTemporalSourceError,
    audit_temporal_recency,
    enforce_temporal_recency,
    extract_referenced_years,
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
