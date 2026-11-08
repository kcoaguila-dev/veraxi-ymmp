"""Unit and integration tests for epistemic dialectical balance, scope inflation, and adversarial audit."""

import json
from pathlib import Path

from veraxi_ymmp.epistemic.dialectical import (
    check_contextual_baseline,
    detect_scope_inflation,
)
from veraxi_ymmp.epistemic.fact_audit import audit_project_facts
from veraxi_ymmp.epistemic.facts import (
    Claim,
    ClaimKind,
    ClaimWeight,
    Evidence,
    Stance,
    claims_to_json,
)


def test_detect_scope_inflation_catches_universal_assertion() -> None:
    # 1. Scope inflation: claim asserts "すべての環境" but quote specifies "Only under isolated benchmark"
    claim_inflated = Claim(
        id="C01",
        cut_index=1,
        text="すべての環境でクラッシュするのだ！",
        kind=ClaimKind.FACT,
        weight=ClaimWeight.CENTRAL,
        evidence=[
            Evidence(
                url="https://example.com/report",
                quote="Only under isolated benchmark conditions with debug flags enabled, 95% crashed.",
                stance=Stance.CONFIRMS,
            )
        ],
    )
    findings = detect_scope_inflation(claim_inflated)
    assert len(findings) == 1
    assert findings[0].claim_quantifier == "すべて"
    assert "benchmark" in findings[0].quote_limiter or "isolated" in findings[0].quote_limiter


def test_detect_scope_inflation_permits_properly_qualified_claim() -> None:
    # Properly qualified claim should not trigger finding
    claim_qualified = Claim(
        id="C02",
        cut_index=2,
        text="特定の検証環境では95%がクラッシュしたのだ。",
        kind=ClaimKind.FACT,
        weight=ClaimWeight.CENTRAL,
        evidence=[
            Evidence(
                url="https://example.com/report",
                quote="Only under isolated benchmark conditions with debug flags enabled, 95% crashed.",
                stance=Stance.CONFIRMS,
            )
        ],
    )
    findings = detect_scope_inflation(claim_qualified)
    assert len(findings) == 0


def test_contextual_baseline_flags_uncontextualized_extreme_metric() -> None:
    # Central claim asserts massive number without baseline denominator
    claim_no_baseline = Claim(
        id="C03",
        cut_index=3,
        text="850万台のPCが停止したのだ！",
        kind=ClaimKind.NUMBER,
        weight=ClaimWeight.CENTRAL,
        evidence=[
            Evidence(
                url="https://example.com/report",
                quote="Approximately 8.5 million machines were impacted by the configuration issue.",
                stance=Stance.CONFIRMS,
            )
        ],
    )
    finding = check_contextual_baseline(claim_no_baseline)
    assert finding is not None
    assert "baseline or denominator context" in finding.message


def test_contextual_baseline_passes_with_derivation_or_evidence_scale() -> None:
    # 1. Passes with explicit derivation denominator
    claim_with_derivation = Claim(
        id="C04",
        cut_index=4,
        text="850万台のPCが停止したのだ！",
        kind=ClaimKind.NUMBER,
        weight=ClaimWeight.CENTRAL,
        derived=True,
        derivation="8.5 million / 850 million global machines = 1%",
        evidence=[
            Evidence(
                url="https://example.com/report",
                quote="Approximately 8.5 million machines were impacted.",
                stance=Stance.CONFIRMS,
            )
        ],
    )
    assert check_contextual_baseline(claim_with_derivation) is None

    # 2. Passes when quote itself includes population denominator
    claim_with_quote_scale = Claim(
        id="C05",
        cut_index=5,
        text="850万台のPCが停止したのだ！",
        kind=ClaimKind.NUMBER,
        weight=ClaimWeight.CENTRAL,
        evidence=[
            Evidence(
                url="https://example.com/report",
                quote="8.5 million devices were impacted, representing less than 1% of all Windows machines globally.",
                stance=Stance.CONFIRMS,
            )
        ],
    )
    assert check_contextual_baseline(claim_with_quote_scale) is None


def test_adversarial_balance_audit_integration(tmp_path: Path) -> None:
    project_dir = tmp_path / "adversarial_test_proj"
    project_dir.mkdir(parents=True)
    sources_dir = project_dir / "sources"
    sources_dir.mkdir(parents=True)

    source_file = sources_dir / "study.txt"
    source_text = "Tested on a sample subset of 50 servers, 98% experienced timeout errors."
    source_file.write_text(source_text, encoding="utf-8")

    manifest_data = {
        "study": {
            "source_id": "study",
            "title": "Lab Server Timeout Study",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-9999",
            "file": "sources/study.txt",
            "verified": True,
        }
    }
    (sources_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    # Script containing universal over-generalization
    script_data = [
        {"character": "zundamon", "text": "あらゆるサーバが完全にダウンするのだ！"},
    ]
    (project_dir / "script.json").write_text(json.dumps(script_data, ensure_ascii=False), encoding="utf-8")

    claims = [
        Claim(
            id="C01",
            text="あらゆるサーバが完全にダウンする",
            kind=ClaimKind.FACT,
            weight=ClaimWeight.CENTRAL,
            cut_index=0,
            evidence=[
                Evidence(
                    source_id="study",
                    url="https://nvd.nist.gov/vuln/detail/CVE-2026-9999",
                    quote="Tested on a sample subset of 50 servers, 98% experienced timeout errors.",
                    stance=Stance.CONFIRMS,
                )
            ],
        )
    ]
    (project_dir / "claims.json").write_text(claims_to_json(claims), encoding="utf-8")

    # Run audit in adversarial mode
    outcome = audit_project_facts(project_dir / "script.json", profile="tech", adversarial=True)

    # Scope inflation should be caught and added as a blocker
    assert outcome.blocked
    assert any("Scope inflation" in b.reason for b in outcome.blockers)

    # sources.md should render the adversarial section
    sources_md = (project_dir / "sources.md").read_text(encoding="utf-8")
    assert "## Adversarial & Dialectical Balance Audit" in sources_md
    assert "Scope Inflation Violations" in sources_md
