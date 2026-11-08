from veraxi_ymmp.epistemic.facts import Claim, Stance, Verdict, verdict_for
from veraxi_ymmp.core.ports import FactChecker
from veraxi_ymmp.epistemic.veraxi_checker import ManualChecker, parse_proof_card

VACUOUS = """### 🛡️ VERAXI FORENSIC FACT-CHECK PROOF CARD
- **Verification:** 🟢 **FACT CHECK PASSED [Factual alignment confirmed]**
- **Grounding Score:** `1.00` (Required Threshold: `0.80`)

#### 📑 Forensic Evidence Citations (0 passages retrieved)
| # | Document | Location | Verbatim Proof Quote |
|---|---|---|---|"""

REAL = """#### 📑 Forensic Evidence Citations (1 passages retrieved)
| # | Document | Location | Verbatim Proof Quote |
|---|---|---|---|
| 1 | https://www.sec.gov/x/10k.pdf | Page 42 | "Purchases of property and equipment (64,551)" |"""


def test_vacuous_pass_is_not_evidence() -> None:
    assert parse_proof_card(VACUOUS) == []
    c = Claim("c1", 1, "x", evidence=parse_proof_card(VACUOUS))
    assert verdict_for(c).verdict is Verdict.UNVERIFIED


def test_real_card_yields_quoted_evidence() -> None:
    (e,) = parse_proof_card(REAL, tier=1)
    assert e.stance is Stance.CONFIRMS and e.page == 42 and e.url.startswith("https://www.sec.gov")
    assert "64,551" in e.quote and e.tier == 1


def test_manual_checker_satisfies_port() -> None:
    assert isinstance(ManualChecker(), FactChecker)



def test_deterministic_grounding_lexical_overlap() -> None:
    from veraxi_ymmp.epistemic.facts import compute_deterministic_grounding
    from veraxi_ymmp.epistemic.veraxi_checker import evaluate_grounding_safe

    # Substantial term overlap
    claim = "PythonはGuido van Rossumによって開発されました。"
    context = "Python was created by Guido van Rossum in the late 1980s."
    score = compute_deterministic_grounding(claim, context)
    assert score >= 0.5

    # Completely disjoint
    disjoint_context = "The quick brown fox jumps over the lazy dog."
    assert compute_deterministic_grounding(claim, disjoint_context) == 0.0

    # Safe evaluation fallback without MCP
    assert evaluate_grounding_safe(claim, context) == score

    # Safe evaluation with mock MCP client
    class MockMcpClient:
        def evaluate_grounding(self, context_text: str, response_text: str) -> float:
            return 0.95

    assert evaluate_grounding_safe(claim, context, mcp_client=MockMcpClient()) == 0.95
