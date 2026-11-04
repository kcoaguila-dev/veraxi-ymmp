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


def ev(url: str, stance: Stance = Stance.CONFIRMS, tier: int = 1, quote: str = "q") -> Evidence:
    return Evidence(url=url, quote=quote, stance=stance, tier=tier)


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
    c = Claim("c1", 3, "x", weight=ClaimWeight.CENTRAL, evidence=[ev("u1"), ev("u1")])
    assert verdict_for(c).verdict is Verdict.UNVERIFIED
    c.evidence.append(ev("u2"))
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
