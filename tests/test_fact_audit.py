import json
from pathlib import Path

import pytest

from veraxi_ymmp.epistemic.fact_audit import audit_project_facts


def _write(tmp_path: Path, claims: list) -> Path:
    script = tmp_path / "script.json"
    script.write_text("[]", encoding="utf-8")
    (tmp_path / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
    return script


def test_missing_ledger_raises(tmp_path: Path) -> None:
    script = tmp_path / "script.json"
    script.write_text("[]", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        audit_project_facts(script)


def test_unverified_central_blocks_and_writes_report(tmp_path: Path) -> None:
    script = _write(tmp_path, [{"id": "c1", "cut_index": 1, "text": "x", "weight": "central"}])
    out = audit_project_facts(script)
    assert out.blocked and out.report_path.read_text(encoding="utf-8").startswith("# Source Dossier")


def test_supported_ledger_is_clear(tmp_path: Path) -> None:
    ev = [{"url": "u", "quote": "q", "stance": "confirms", "tier": 1}]
    script = _write(tmp_path, [{"id": "c1", "cut_index": 1, "text": "x", "evidence": ev}])
    assert not audit_project_facts(script).blocked


def test_draft_claims_skips_banter_and_is_idempotent(tmp_path: Path) -> None:
    from veraxi_ymmp.epistemic.fact_audit import draft_project_claims

    script = tmp_path / "script.json"
    data = [{"character": "a", "text": "売上は500億ドルです。"}, {"character": "b", "text": "はぁ！？"}]
    script.write_text("[]", encoding="utf-8")
    _, added = draft_project_claims(script, data)
    _, again = draft_project_claims(script, data)
    assert (added, again) == (1, 0)


def test_quote_verification_passes_when_quote_present(tmp_path: Path) -> None:
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    doc = sources_dir / "sec_filing.txt"
    doc.write_text("Amazon's capex reached $85B in fiscal year 2026.", encoding="utf-8")

    ev = [{"url": "https://sec.gov/amzn", "quote": "capex reached $85B", "stance": "confirms", "tier": 1, "source_id": "sec_filing"}]
    script = _write(tmp_path, [{"id": "c1", "cut_index": 1, "text": "capex", "evidence": ev}])
    out = audit_project_facts(script)
    assert not out.blocked
    assert out.results[0].verdict.value == "supported"


def test_quote_verification_fails_when_quote_hallucinated(tmp_path: Path) -> None:
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    doc = sources_dir / "sec_filing.txt"
    doc.write_text("Amazon's capex reached $85B in fiscal year 2026.", encoding="utf-8")

    # Hallucinated $95B
    ev = [{"url": "https://sec.gov/amzn", "quote": "capex reached $95B", "stance": "confirms", "tier": 1, "source_id": "sec_filing"}]
    script = _write(tmp_path, [{"id": "c1", "cut_index": 1, "text": "capex", "evidence": ev}])
    out = audit_project_facts(script)
    assert out.blocked
    assert any("quote not found in stored source 'sec_filing'" in b.reason for b in out.blockers)


def test_quote_verification_fails_when_source_file_missing(tmp_path: Path) -> None:
    ev = [{"url": "https://sec.gov/amzn", "quote": "capex reached $85B", "stance": "confirms", "tier": 1, "source_id": "missing_doc"}]
    script = _write(tmp_path, [{"id": "c1", "cut_index": 1, "text": "capex", "evidence": ev}])
    out = audit_project_facts(script)
    assert out.blocked
    assert any("source 'missing_doc' not found in sources/" in b.reason for b in out.blockers)


def test_quote_verification_fails_when_sha256_tampered(tmp_path: Path) -> None:
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    doc = sources_dir / "sec_filing.txt"
    doc.write_text("Amazon's capex reached $85B in fiscal year 2026.", encoding="utf-8")

    ev = [{
        "url": "https://sec.gov/amzn",
        "quote": "capex reached $85B",
        "stance": "confirms",
        "tier": 1,
        "source_id": "sec_filing",
        "sha256": "badbeef000000000000000000000000000000000000000000000000000000000",
    }]
    script = _write(tmp_path, [{"id": "c1", "cut_index": 1, "text": "capex", "evidence": ev}])
    out = audit_project_facts(script)
    assert out.blocked
    assert any("tampered source 'sec_filing'" in b.reason for b in out.blockers)


def test_unlinked_quote_on_central_claim_blocks_gate(tmp_path: Path) -> None:
    # Central claim with unlinked evidence (no source_id) must be blocked
    ev = [{"url": "https://sec.gov/amzn", "quote": "capex reached $85B", "stance": "confirms", "tier": 1}]
    script = _write(tmp_path, [{"id": "c1", "cut_index": 1, "text": "capex", "weight": "central", "evidence": ev}])
    out = audit_project_facts(script)
    assert out.blocked
    assert any("central claim requires verified source in sources/" in b.reason for b in out.blockers)


def test_manual_override_on_central_claim_is_blocked(tmp_path: Path) -> None:
    # Central claims strictly forbid manual overrides: they require disk-verified source_id
    ev = [
        {"url": "https://sec.gov/amzn", "quote": "capex reached $85B", "stance": "confirms", "tier": 1, "manual": True},
        {"url": "https://fred.stlouisfed.org/series/GDP", "quote": "GDP was X", "stance": "confirms", "tier": 1, "manual": True},
    ]
    script = _write(tmp_path, [{"id": "c1", "cut_index": 1, "text": "capex", "weight": "central", "evidence": ev}])
    out = audit_project_facts(script)
    assert out.blocked
    assert any("central claim requires verified source in sources/" in b.reason for b in out.blockers)


def test_manual_override_on_minor_claim_allowed(tmp_path: Path) -> None:
    # Minor claims allow manual verification without on-disk source_id
    ev = [{"url": "https://sec.gov/amzn", "quote": "capex reached $85B", "stance": "confirms", "tier": 1, "manual": True}]
    script = _write(tmp_path, [{"id": "c1", "cut_index": 1, "text": "capex", "weight": "minor", "evidence": ev}])
    out = audit_project_facts(script)
    assert not out.blocked
    assert out.results[0].verdict.value == "supported"


def test_url_mismatch_with_source_metadata_blocks(tmp_path: Path) -> None:
    # Claim cites sec.gov as URL to get Tier 1, but source_id points to blog with different registered URL
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    doc = sources_dir / "blog_doc.txt"
    doc.write_text("Amazon capex reached $85B in 2026.", encoding="utf-8")
    meta = sources_dir / "blog_doc.meta.json"
    meta.write_text(json.dumps({"url": "https://tech-rumor-blog.com/post"}), encoding="utf-8")

    ev = [{
        "url": "https://sec.gov/edgar/data/amzn",
        "quote": "capex reached $85B",
        "stance": "confirms",
        "tier": 1,
        "source_id": "blog_doc",
    }]
    script = _write(tmp_path, [{"id": "c1", "cut_index": 1, "text": "capex", "evidence": ev}])
    out = audit_project_facts(script)
    assert out.blocked
    assert any(
        "source 'blog_doc' registered for 'https://tech-rumor-blog.com/post', does not match evidence url"
        in b.reason
        for b in out.blockers
    )


def test_url_match_with_source_metadata_passes(tmp_path: Path) -> None:
    # URL in metadata matches canonical institution of evidence URL
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    doc = sources_dir / "sec_filing.txt"
    doc.write_text("Amazon capex reached $85B in 2026.", encoding="utf-8")
    meta = sources_dir / "sec_filing.meta.json"
    meta.write_text(json.dumps({"url": "https://www.sec.gov/edgar/data/1018724/amzn"}), encoding="utf-8")

    ev = [{
        "url": "https://sec.gov/edgar/data/1018724/amzn",
        "quote": "capex reached $85B",
        "stance": "confirms",
        "tier": 1,
        "source_id": "sec_filing",
    }]
    script = _write(tmp_path, [{"id": "c1", "cut_index": 1, "text": "capex", "evidence": ev}])
    out = audit_project_facts(script)
    assert not out.blocked
    assert out.results[0].verdict.value == "supported"



def test_central_claim_fails_closed_without_registered_origin(tmp_path: Path) -> None:
    # A source file exists in sources/ but has no origin URL (no meta.json, manifest, or header)
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    doc = sources_dir / "unregistered_doc.txt"
    doc.write_text("Amazon capex reached $85B in 2026.", encoding="utf-8")

    from veraxi_ymmp.epistemic.fact_audit import compute_file_sha256
    digest = compute_file_sha256(doc)

    ev = [{
        "url": "https://sec.gov/edgar/data/1018724/amzn",
        "quote": "capex reached $85B",
        "stance": "confirms",
        "tier": 1,
        "source_id": "unregistered_doc",
        "sha256": digest,
    }]
    script = _write(tmp_path, [{"id": "c1", "cut_index": 1, "text": "capex", "weight": "central", "evidence": ev}])
    out = audit_project_facts(script)
    assert out.blocked
    assert any("has no registered origin URL" in b.reason for b in out.blockers)


def test_central_claim_fails_closed_without_sha256(tmp_path: Path) -> None:
    # Central claim evidence missing sha256 checksum must be blocked fail-closed
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    doc = sources_dir / "sec_filing.txt"
    doc.write_text("Amazon capex reached $85B in 2026.", encoding="utf-8")
    meta = sources_dir / "sec_filing.meta.json"
    meta.write_text(json.dumps({"url": "https://www.sec.gov/edgar/data/1018724/amzn"}), encoding="utf-8")

    ev = [{
        "url": "https://sec.gov/edgar/data/1018724/amzn",
        "quote": "capex reached $85B",
        "stance": "confirms",
        "tier": 1,
        "source_id": "sec_filing",
        # sha256 omitted
    }]
    script = _write(tmp_path, [{"id": "c1", "cut_index": 1, "text": "capex", "weight": "central", "evidence": ev}])
    out = audit_project_facts(script)
    assert out.blocked
    assert any("missing required sha256 checksum" in b.reason for b in out.blockers)


def test_central_claim_fails_closed_when_source_origin_not_tier1(tmp_path: Path) -> None:
    # Source registered for a blog domain is not Tier 1, so it cannot back a central claim
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    doc = sources_dir / "blog_doc.txt"
    doc.write_text("Amazon capex reached $85B in 2026.", encoding="utf-8")
    meta = sources_dir / "blog_doc.meta.json"
    meta.write_text(json.dumps({"url": "https://tech-rumor-blog.com/post"}), encoding="utf-8")

    from veraxi_ymmp.epistemic.fact_audit import compute_file_sha256
    digest = compute_file_sha256(doc)

    ev = [{
        "url": "https://tech-rumor-blog.com/post",
        "quote": "capex reached $85B",
        "stance": "confirms",
        "tier": 1,
        "source_id": "blog_doc",
        "sha256": digest,
    }]
    script = _write(tmp_path, [{"id": "c1", "cut_index": 1, "text": "capex", "weight": "central", "evidence": ev}])
    out = audit_project_facts(script)
    assert out.blocked
    assert any("is not a recognized Tier 1 primary authority" in b.reason for b in out.blockers)




def test_project_audit_with_general_profile(tmp_path: Path) -> None:
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    doc = sources_dir / "wiki_doc.txt"
    doc.write_text("Python was created by Guido van Rossum and released in 1991.", encoding="utf-8")
    meta = sources_dir / "wiki_doc.meta.json"
    meta.write_text(json.dumps({"url": "https://en.wikipedia.org/wiki/Python_(programming_language)"}), encoding="utf-8")

    from veraxi_ymmp.epistemic.fact_audit import compute_file_sha256
    digest = compute_file_sha256(doc)

    ev = [{
        "url": "https://en.wikipedia.org/wiki/Python_(programming_language)",
        "quote": "Python was created by Guido van Rossum",
        "stance": "confirms",
        "tier": 1,
        "source_id": "wiki_doc",
        "sha256": digest,
    }]
    # Minor claim with Wikipedia source
    script = _write(tmp_path, [{"id": "c1", "cut_index": 1, "text": "Python created by Guido", "kind": "fact", "weight": "minor", "evidence": ev}])

    # Under finance profile, audit passes for minor claim (Tier 2 allowed)
    out_fin = audit_project_facts(script, profile="finance")
    assert not out_fin.blocked
    assert out_fin.results[0].grounding_score is not None

    # For central claim, under finance profile it fails closed
    script_central = _write(tmp_path, [{"id": "c1", "cut_index": 1, "text": "Python created by Guido", "kind": "fact", "weight": "central", "evidence": ev}])
    out_central_fin = audit_project_facts(script_central, profile="finance")
    assert out_central_fin.blocked
    assert any("is not a recognized Tier 1 primary authority" in b.reason for b in out_central_fin.blockers)

    # Now add second general source (Reuters) and audit with profile="general"
    doc2 = sources_dir / "reuters_doc.txt"
    doc2.write_text("Python created by Guido van Rossum gained popularity worldwide.", encoding="utf-8")
    meta2 = sources_dir / "reuters_doc.meta.json"
    meta2.write_text(json.dumps({"url": "https://www.reuters.com/technology/python-creator"}), encoding="utf-8")
    digest2 = compute_file_sha256(doc2)
    ev2 = {
        "url": "https://www.reuters.com/technology/python-creator",
        "quote": "Python created by Guido van Rossum",
        "stance": "confirms",
        "tier": 1,
        "source_id": "reuters_doc",
        "sha256": digest2,
    }
    script_central2 = _write(tmp_path, [{
        "id": "c1",
        "cut_index": 1,
        "text": "Python created by Guido",
        "kind": "fact",
        "weight": "central",
        "evidence": [ev[0], ev2],
    }])
    out_gen = audit_project_facts(script_central2, profile="general")
    assert not out_gen.blocked
    assert out_gen.results[0].verdict.value == "supported"
