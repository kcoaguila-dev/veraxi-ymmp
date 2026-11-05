from veraxi_ymmp.facts import (
    Claim,
    ClaimKind,
    ClaimWeight,
    Evidence,
    Stance,
    Verdict,
    audit,
    claims_from_json,
    claims_to_json,
    gate_failures,
    verdict_for,
)


def ev(
    url: str,
    stance: Stance = Stance.CONFIRMS,
    tier: int = 1,
    quote: str = "q",
    source_id: str = "",
    manual: bool = False,
) -> Evidence:
    if tier == 1 and not (url.startswith("http") or "." in url):
        url = f"https://sec.gov/{url}"
    # Default to manual=True in unit tests if no source_id provided, so test mocks qualify
    if not source_id and not manual:
        manual = True
    return Evidence(url=url, quote=quote, stance=stance, tier=tier, source_id=source_id, manual=manual)


def test_opinion_is_not_checked() -> None:
    c = Claim("c1", 0, "x", kind=ClaimKind.OPINION)
    assert verdict_for(c).verdict is Verdict.OPINION


def test_no_evidence_is_unverified_not_false() -> None:
    assert verdict_for(Claim("c1", 1, "x")).verdict is Verdict.UNVERIFIED


def test_minor_claim_supported_with_one_quoted_source() -> None:
    c = Claim("c1", 1, "x", evidence=[ev("u1", tier=2)])
    assert verdict_for(c).verdict is Verdict.SUPPORTED


def test_confirm_without_quote_does_not_count() -> None:
    c = Claim("c1", 1, "x", evidence=[ev("u1", quote="  ")])
    assert verdict_for(c).verdict is Verdict.UNVERIFIED


def test_central_needs_two_distinct_primary_sources() -> None:
    c = Claim(
        "c1",
        3,
        "x",
        weight=ClaimWeight.CENTRAL,
        evidence=[
            ev("https://sec.gov/u1", source_id="s1"),
            ev("https://sec.gov/u2", source_id="s2"),
        ],
    )
    # Both are SEC, which maps to same canonical institution (sec); central needs 2 distinct institutions
    assert verdict_for(c).verdict is Verdict.UNVERIFIED
    c.evidence.append(ev("https://fred.stlouisfed.org/series/GDP", source_id="s3"))
    assert verdict_for(c).verdict is Verdict.SUPPORTED


def test_contradiction_refutes_even_with_confirmations() -> None:
    c = Claim("c1", 1, "x", evidence=[ev("u1"), ev("u2", Stance.CONTRADICTS, tier=2)])
    assert verdict_for(c).verdict is Verdict.REFUTED


def test_gate_blocks_refuted_and_unverified_central_only() -> None:
    claims = [
        Claim("a", 1, "x", weight=ClaimWeight.CENTRAL),
        Claim("b", 2, "x"),
        Claim("c", 3, "x", evidence=[ev("u", Stance.CONTRADICTS)]),
    ]
    assert {r.claim.id for r in gate_failures(audit(claims))} == {"a", "c"}


def test_json_roundtrip() -> None:
    c = Claim("c1", 2, "x", ClaimKind.DATE, ClaimWeight.CENTRAL, [ev("u1")])
    back = claims_from_json(claims_to_json([c]))
    assert back == [c]


def test_enforce_source_tier_downgrades_non_primary() -> None:
    from veraxi_ymmp.facts import enforce_source_tier

    assert enforce_source_tier("https://sec.gov/edgar/data", 1) == 1
    assert enforce_source_tier("https://fred.stlouisfed.org/series/GDP", 1) == 1
    assert enforce_source_tier("https://e-stat.go.jp/stat", 1) == 1
    assert enforce_source_tier("https://www.federalreserve.gov/releases", 1) == 1
    assert enforce_source_tier("https://techcrunch.com/ai-capex", 1) == 2
    assert enforce_source_tier("https://unknown-blog.com/post", 1) == 2


def test_quote_normalization_and_strict_verification() -> None:
    from veraxi_ymmp.facts import verify_quote_in_source

    source = "2026年第1四半期の売上高は500億ドルに達した。営業利益率は42%であった。"
    assert verify_quote_in_source("売上高は500億ドル", source) is True
    # Quote with Japanese bracket quotes matches source
    assert verify_quote_in_source("「売上高は500億ドル」", source) is True
    # Zenkaku spaces and newlines normalized
    assert verify_quote_in_source("売上高は　500億ドル", source) is True
    # Hallucinated or modified text fails strictly
    assert verify_quote_in_source("売上高は600億ドル", source) is False
    assert verify_quote_in_source("営業利益率は45%", source) is False


def test_quote_error_blocks_gate() -> None:
    from veraxi_ymmp.facts import gate_failures, verdict_for

    claim = Claim("c1", 1, "test", weight=ClaimWeight.MINOR)
    res = verdict_for(claim, quote_errors=["quote not found in source 'doc1'"])
    assert res.verdict is Verdict.UNVERIFIED
    assert len(res.quote_errors) == 1
    assert gate_failures([res]) == [res]


def test_quote_matching_preserves_english_word_boundaries() -> None:
    from veraxi_ymmp.facts import verify_quote_in_source

    source = "The quick brown fox jumps over the lazy dog."
    assert verify_quote_in_source("brown fox", source) is True
    # English word boundary: "a bc" should NOT match "ab c" or "a b c"
    assert verify_quote_in_source("bro wn", source) is False
    assert verify_quote_in_source("brownfox", source) is False


def test_central_claim_rejects_unlinked_unreviewed_evidence() -> None:
    # Evidence without source_id and manual=False cannot satisfy central claim
    unlinked_ev = Evidence(
        url="https://sec.gov/filing",
        quote="Revenue was $50B",
        stance=Stance.CONFIRMS,
        tier=1,
        source_id="",
        manual=False,
    )
    c = Claim("c1", 1, "test", weight=ClaimWeight.CENTRAL, evidence=[unlinked_ev])
    assert verdict_for(c).verdict is Verdict.UNVERIFIED


def test_primary_authority_key_deduplicates_same_institution() -> None:
    e1 = Evidence(url="https://sec.gov/10k#page1", quote="q", stance=Stance.CONFIRMS, tier=1, source_id="s1")
    e2 = Evidence(url="https://www.sec.gov/press-release", quote="q", stance=Stance.CONFIRMS, tier=1, source_id="s2")
    c = Claim("c1", 1, "test", weight=ClaimWeight.CENTRAL, evidence=[e1, e2])
    # Both sec.gov and www.sec.gov map to same canonical institution (sec); central requires 2 distinct institutions
    assert verdict_for(c).verdict is Verdict.UNVERIFIED
    # Adding distinct authority (FRED) satisfies requirement
    e3 = Evidence(url="https://fred.stlouisfed.org/series/GDP", quote="q", stance=Stance.CONFIRMS, tier=1, source_id="s3")
    c.evidence.append(e3)
    assert verdict_for(c).verdict is Verdict.SUPPORTED


def test_central_claim_rejects_manual_override_without_source_id() -> None:
    manual_ev = Evidence(
        url="https://sec.gov/filing",
        quote="Revenue was $50B",
        stance=Stance.CONFIRMS,
        tier=1,
        source_id="",
        manual=True,
    )
    c = Claim("c1", 1, "test", weight=ClaimWeight.CENTRAL, evidence=[manual_ev])
    assert verdict_for(c).verdict is Verdict.UNVERIFIED


def test_number_check_passes_when_number_in_quote() -> None:
    e = Evidence(url="u", quote="Revenue reached $85B", stance=Stance.CONFIRMS, tier=2)
    c = Claim("c1", 1, "Amazon capex reached $85B", kind=ClaimKind.NUMBER, evidence=[e])
    assert verdict_for(c).verdict is Verdict.SUPPORTED


def test_number_check_fails_when_number_missing_from_quote() -> None:
    e = Evidence(url="u", quote="Revenue reached $85B", stance=Stance.CONFIRMS, tier=2)
    c = Claim("c1", 1, "Amazon capex reached $95B", kind=ClaimKind.NUMBER, evidence=[e])
    res = verdict_for(c)
    assert res.verdict is Verdict.UNVERIFIED
    assert any("number '95' in claim text not found" in err for err in res.quote_errors)


def test_number_check_passes_when_derived_flag_set() -> None:
    e = Evidence(url="u", quote="Revenue reached $85B from $60B", stance=Stance.CONFIRMS, tier=2)
    c = Claim(
        "c1",
        1,
        "Capex increased by 42%",
        kind=ClaimKind.NUMBER,
        derived=True,
        derivation="($85B - $60B) / $60B = 41.6% ~ 42%",
        evidence=[e],
    )
    assert verdict_for(c).verdict is Verdict.SUPPORTED



def test_canonical_institution_subdomain_deduplication() -> None:
    from veraxi_ymmp.facts import canonical_institution

    assert canonical_institution("https://data.sec.gov/api/xbrl") == "sec"
    assert canonical_institution("https://efts.sec.gov/LATEST/search") == "sec"
    assert canonical_institution("https://www.sec.gov/edgar") == "sec"
    assert canonical_institution("https://sec.gov") == "sec"

    assert canonical_institution("https://fred.stlouisfed.org/series/GDP") == "federalreserve"
    assert canonical_institution("https://federalreserve.gov/releases") == "federalreserve"
    assert canonical_institution("https://home.treasury.gov/policy") == "treasury"
    assert canonical_institution("https://apps.bea.gov/iTable") == "bea"

    # Central claim citing data.sec.gov and sec.gov must count as only 1 institution and remain UNVERIFIED
    c = Claim(
        "c1",
        1,
        "Capex was high",
        weight=ClaimWeight.CENTRAL,
        evidence=[
            Evidence(url="https://data.sec.gov/api", quote="Capex was high", stance=Stance.CONFIRMS, tier=1, source_id="s1"),
            Evidence(url="https://sec.gov/doc", quote="Capex was high", stance=Stance.CONFIRMS, tier=1, source_id="s2"),
        ],
    )
    assert verdict_for(c).verdict is Verdict.UNVERIFIED

    # Adding distinct institution (e.g. BEA) satisfies 2 institutions requirement
    c.evidence.append(
        Evidence(url="https://apps.bea.gov/data", quote="Capex was high", stance=Stance.CONFIRMS, tier=1, source_id="s3")
    )
    assert verdict_for(c).verdict is Verdict.SUPPORTED


def test_number_boundary_check() -> None:
    # 5 should NOT match 2500 or 5.8
    e_bad = Evidence(url="u", quote="Revenue was 2500 dollars", stance=Stance.CONFIRMS, tier=2)
    c1 = Claim("c1", 1, "Revenue was 5 dollars", kind=ClaimKind.NUMBER, evidence=[e_bad])
    res1 = verdict_for(c1)
    assert res1.verdict is Verdict.UNVERIFIED
    assert any("number '5' in claim text not found" in err for err in res1.quote_errors)

    e_bad2 = Evidence(url="u", quote="Revenue was 5.8 dollars", stance=Stance.CONFIRMS, tier=2)
    c2 = Claim("c2", 1, "Revenue was 5 dollars", kind=ClaimKind.NUMBER, evidence=[e_bad2])
    res2 = verdict_for(c2)
    assert res2.verdict is Verdict.UNVERIFIED

    # 85 should NOT match 1850
    e_bad3 = Evidence(url="u", quote="Population was 1850 people", stance=Stance.CONFIRMS, tier=2)
    c3 = Claim("c3", 1, "Population was 85 people", kind=ClaimKind.NUMBER, evidence=[e_bad3])
    res3 = verdict_for(c3)
    assert res3.verdict is Verdict.UNVERIFIED

    # Exact token 5 matches in "$5M" or "5 percent"
    e_good = Evidence(url="u", quote="Paid $5M in cash", stance=Stance.CONFIRMS, tier=2)
    c4 = Claim("c4", 1, "Paid 5 dollars", kind=ClaimKind.NUMBER, evidence=[e_good])
    assert verdict_for(c4).verdict is Verdict.SUPPORTED


def test_derived_claim_requires_non_empty_derivation() -> None:
    e = Evidence(url="u", quote="Revenue reached $85B from $60B", stance=Stance.CONFIRMS, tier=2)
    # derived=True with empty derivation fails
    c_empty = Claim("c1", 1, "Capex rose 42%", kind=ClaimKind.NUMBER, derived=True, derivation="", evidence=[e])
    res = verdict_for(c_empty)
    assert res.verdict is Verdict.UNVERIFIED
    assert any("requires non-empty derivation formula" in err for err in res.quote_errors)

    # derived=True with whitespace derivation fails
    c_spaces = Claim("c2", 1, "Capex rose 42%", kind=ClaimKind.NUMBER, derived=True, derivation="   ", evidence=[e])
    assert verdict_for(c_spaces).verdict is Verdict.UNVERIFIED

    # derived=True with valid derivation passes
    c_valid = Claim(
        "c3", 1, "Capex rose 42%", kind=ClaimKind.NUMBER, derived=True, derivation="85 - 60 = 25", evidence=[e]
    )
    assert verdict_for(c_valid).verdict is Verdict.SUPPORTED


def test_year_not_dropped_when_other_numbers_exist() -> None:
    from veraxi_ymmp.facts import extract_claim_numbers

    # "2000 jobs" is a quantity, not a calendar year, so it must not be dropped when "5" is present
    nums = extract_claim_numbers("In 2024, the company cut 2000 jobs and paid $5M")
    assert "2000" in nums
    assert "5" in nums
    assert "2024" not in nums  # 2024 is preceded by "In " and is temporal



def test_sentence_ending_number_matches_quote() -> None:
    # 5 followed by period at end of sentence must match, not be rejected by lookahead
    e_period = Evidence(url="u", quote="Revenue grew 5. Next quarter will tell.", stance=Stance.CONFIRMS, tier=2)
    c_period = Claim("c1", 1, "Revenue grew 5", kind=ClaimKind.NUMBER, evidence=[e_period])
    assert verdict_for(c_period).verdict is Verdict.SUPPORTED

    # Decimal 5.2 at end of sentence must also match
    e_dec_period = Evidence(url="u", quote="Revenue grew 5.2. Next quarter will tell.", stance=Stance.CONFIRMS, tier=2)
    c_dec_period = Claim("c2", 1, "Revenue grew 5.2", kind=ClaimKind.NUMBER, evidence=[e_dec_period])
    assert verdict_for(c_dec_period).verdict is Verdict.SUPPORTED

    # 5 must NOT match .5 (preceded by period decimal point)
    e_point_five = Evidence(url="u", quote="Revenue grew .5 percent", stance=Stance.CONFIRMS, tier=2)
    c_five = Claim("c3", 1, "Revenue grew 5 percent", kind=ClaimKind.NUMBER, evidence=[e_point_five])
    res_five = verdict_for(c_five)
    assert res_five.verdict is Verdict.UNVERIFIED
    assert any("number '5' in claim text not found" in err for err in res_five.quote_errors)


def test_derived_claim_security_and_grounding() -> None:
    e = Evidence(url="https://sec.gov/doc", quote="Revenue reached $85B", stance=Stance.CONFIRMS, tier=1, source_id="s1")

    # Central claims cannot be derived (prevents primary source bypass)
    c_central_derived = Claim(
        "c_cent",
        1,
        "Capex rose 42%",
        kind=ClaimKind.NUMBER,
        weight=ClaimWeight.CENTRAL,
        derived=True,
        derivation="85 - 60 = 25",
        evidence=[e],
    )
    res_cent = verdict_for(c_central_derived)
    assert res_cent.verdict is Verdict.UNVERIFIED
    assert any("central claims cannot be derived" in err for err in res_cent.quote_errors)

    # Derivation without numbers (dummy text like 'x' or 'calculated') fails
    c_no_num_der = Claim(
        "c_nonum",
        1,
        "Capex rose 42%",
        kind=ClaimKind.NUMBER,
        derived=True,
        derivation="calculated from annual filings",
        evidence=[e],
    )
    res_no_num = verdict_for(c_no_num_der)
    assert res_no_num.verdict is Verdict.UNVERIFIED
    assert any("must contain numeric inputs" in err for err in res_no_num.quote_errors)

    # Derivation with ungrounded numbers (none in quotes) fails
    c_ungrounded = Claim(
        "c_unground",
        1,
        "Capex rose 42%",
        kind=ClaimKind.NUMBER,
        derived=True,
        derivation="999 - 111 = 888",
        evidence=[e],
    )
    res_unground = verdict_for(c_ungrounded)
    assert res_unground.verdict is Verdict.UNVERIFIED
    assert any("derivation input number" in err for err in res_unground.quote_errors)


def test_year_fallback_when_only_year_present() -> None:
    from veraxi_ymmp.facts import extract_claim_numbers

    # A claim asserting only a year falls back to auditing the year
    nums = extract_claim_numbers("The financial crisis began in 2008")
    assert nums == ["2008"]

    e_match = Evidence(url="u", quote="The financial crisis began in 2008", stance=Stance.CONFIRMS, tier=2)
    c_year_match = Claim("c1", 1, "The financial crisis began in 2008", kind=ClaimKind.NUMBER, evidence=[e_match])
    assert verdict_for(c_year_match).verdict is Verdict.SUPPORTED

    e_mismatch = Evidence(url="u", quote="The financial crisis began in 2007", stance=Stance.CONFIRMS, tier=2)
    c_year_mismatch = Claim("c2", 1, "The financial crisis began in 2008", kind=ClaimKind.NUMBER, evidence=[e_mismatch])
    res_mismatch = verdict_for(c_year_mismatch)
    assert res_mismatch.verdict is Verdict.UNVERIFIED
    assert any("number '2008' in claim text not found" in err for err in res_mismatch.quote_errors)



def test_derived_claim_rejects_hallucinated_lhs_operand() -> None:
    # Quote only has 85; 60 is missing from evidence quotes
    e = Evidence(url="u", quote="Revenue reached $85B", stance=Stance.CONFIRMS, tier=2)
    c = Claim(
        "c1",
        1,
        "Capex rose 25%",
        kind=ClaimKind.NUMBER,
        derived=True,
        derivation="85 - 60 = 25",
        evidence=[e],
    )
    res = verdict_for(c)
    assert res.verdict is Verdict.UNVERIFIED
    assert any("derivation input number '60' not found in confirmed quotes" in err for err in res.quote_errors)

    # Fake formula with Q1 matching 1 but hallucinating 99999 fails
    e_q1 = Evidence(url="u", quote="Q1 results showed growth", stance=Stance.CONFIRMS, tier=2)
    c_fake = Claim(
        "c2",
        1,
        "Loss of 100000",
        kind=ClaimKind.NUMBER,
        derived=True,
        derivation="1 + 99999 = 100000",
        evidence=[e_q1],
    )
    res_fake = verdict_for(c_fake)
    assert res_fake.verdict is Verdict.UNVERIFIED
    assert any("derivation input number '99999' not found in confirmed quotes" in err for err in res_fake.quote_errors)


def test_derived_claim_allows_standard_scaling_constants() -> None:
    e = Evidence(url="u", quote="Revenue reached $85B from prior $60B", stance=Stance.CONFIRMS, tier=2)
    # Scaling constant 100 on LHS does not need to be in quote
    c = Claim(
        "c1",
        1,
        "Growth was 41.7%",
        kind=ClaimKind.NUMBER,
        derived=True,
        derivation="($85 - $60) / $60 * 100 = 41.7%",
        evidence=[e],
    )
    assert verdict_for(c).verdict is Verdict.SUPPORTED

    # Divisor 12 (months) does not need to be in quote
    e_ann = Evidence(url="u", quote="Annual run rate was 84 billion", stance=Stance.CONFIRMS, tier=2)
    c_monthly = Claim(
        "c2",
        1,
        "Monthly run rate was 7 billion",
        kind=ClaimKind.NUMBER,
        derived=True,
        derivation="84 / 12 = 7",
        evidence=[e_ann],
    )
    assert verdict_for(c_monthly).verdict is Verdict.SUPPORTED


def test_bare_numbers_in_year_range_not_dropped() -> None:
    from veraxi_ymmp.facts import extract_claim_numbers

    # Index points and stock prices in 1900-2099 must NOT be dropped when other numbers exist
    nums1 = extract_claim_numbers("S&P 500 fell to 1980, down 12%")
    assert "1980" in nums1
    assert "12" in nums1
    assert "500" in nums1

    nums2 = extract_claim_numbers("Stock hit 1950, up 20%")
    assert "1950" in nums2
    assert "20" in nums2


def test_duplicate_year_and_quantity_preserved() -> None:
    from veraxi_ymmp.facts import extract_claim_numbers

    # "In 2024" is a temporal year, but "2024 jobs" is a real quantity:
    # 2024 jobs must NOT be dropped by value-set poisoning
    nums = extract_claim_numbers("In 2024, the company cut 2024 jobs and paid 5M")
    assert "2024" in nums
    assert "5" in nums
