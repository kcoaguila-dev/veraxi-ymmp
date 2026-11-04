from veraxi_ymmp.claim_extractor import classify_text, extract_draft_claims
from veraxi_ymmp.facts import Claim, ClaimKind, ClaimWeight, Verdict, audit, gate_failures


def test_banter_is_not_a_claim() -> None:
    assert classify_text("おめでたい頭ですわね") is None
    assert classify_text("嘘でしょ！？") is ClaimKind.COMMENTARY


def test_reaction_echoing_a_number_is_commentary_not_a_claim() -> None:
    assert classify_text("に、25兆円！？") is ClaimKind.COMMENTARY


def test_numeric_statement_is_a_claim() -> None:
    assert classify_text("アマゾンは約850億ドルに達します。") is ClaimKind.NUMBER


def test_commentary_never_blocks_even_if_central() -> None:
    c = Claim("c1", 1, "joke", ClaimKind.COMMENTARY, ClaimWeight.CENTRAL)
    res = audit([c])
    assert res[0].verdict is Verdict.OPINION and not gate_failures(res)


def test_extraction_skips_banter_and_preserves_existing() -> None:
    script = [
        {"type": "bgm", "path": "x"},
        {"character": "a", "text": "売上は500億ドルです。"},
        {"character": "b", "text": "はぁ！？"},
        {"character": "a", "text": "やれやれですわね。"},
    ]
    kept = Claim("c1", 1, "売上は500億ドルです。", ClaimKind.NUMBER, ClaimWeight.CENTRAL)
    out = extract_draft_claims(script, [kept])
    assert out == [kept]
    assert [c.cut_index for c in extract_draft_claims(script)] == [1]
