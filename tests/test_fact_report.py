from veraxi_ymmp.fact_report import render_report
from veraxi_ymmp.facts import Claim, ClaimWeight, Evidence, Stance, audit


def _claims() -> list[Claim]:
    ok = Claim("c1", 2, "Revenue was X | Y", evidence=[Evidence("https://sec.gov/a", "rev X", Stance.CONFIRMS, 1, 12)])
    bad = Claim("c2", 4, "Central claim", weight=ClaimWeight.CENTRAL)
    return [ok, bad]


def test_report_has_sections_and_blocks() -> None:
    md = render_report("Demo", audit(_claims()), {2: 65.0})
    assert "BLOCKED" in md and "## Claim ledger" in md and "## Bibliography" in md
    assert "1:05" in md and "(p.12)" in md and "Revenue was X \\| Y" in md
    assert "https://sec.gov/a" in md.split("## Description source list")[1]


def test_report_clear_when_all_supported() -> None:
    c = Claim("c1", 1, "x", evidence=[Evidence("u", "q", Stance.CONFIRMS)])
    assert "CLEAR" in render_report("Demo", audit([c]))
