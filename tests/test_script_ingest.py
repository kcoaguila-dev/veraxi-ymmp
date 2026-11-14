import json
from pathlib import Path

from veraxi_ymmp.editorial.script_ingest import (
    ingest_notebooklm_markdown_to_claims,
    parse_markdown_dialogue,
    split_text_to_char_limit,
    normalize_speaker,
)


def test_normalize_speaker() -> None:
    assert normalize_speaker("Zundamon") == "ずんだもん"
    assert normalize_speaker("[ずんだもん]") == "ずんだもん"
    assert normalize_speaker("**Metan**") == "四国めたん"
    assert normalize_speaker("tsumugi") == "春日部つむぎ"
    assert normalize_speaker("Unknown") is None


def test_split_text_to_char_limit_under_ceiling() -> None:
    short_text = "こんにちはなのだ！"
    chunks = split_text_to_char_limit(short_text, max_chars=38)
    assert chunks == [short_text]


def test_split_text_to_char_limit_exceeding_ceiling() -> None:
    long_text = "ボクの持っている株が明日大暴落するなんて信じられないのだ！今すぐ全部売って現金に換えてくるのだー！"
    chunks = split_text_to_char_limit(long_text, max_chars=38)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 38


def test_parse_markdown_dialogue_valid_script() -> None:
    md_content = """
# NotebookLM Response

[Zundamon]: ボクの株、明日売っ払ってくるのだー！
**Metan**: 底値で狼狽売りする養分の鑑ですわね。
3. [Tsumugi]: でもサーバ室のログ見たら、先週からエラー出てたっすよ。
"""
    entries = parse_markdown_dialogue(md_content)
    assert len(entries) == 3

    assert entries[0]["character"] == "ずんだもん"
    assert entries[0]["character_position"] == "right"
    assert entries[0]["emotion"] == "excited"

    assert entries[1]["character"] == "四国めたん"
    assert entries[1]["character_position"] == "left"

    assert entries[2]["character"] == "春日部つむぎ"
    assert entries[2]["character_position"] == "right"

    # Invariants for cuts 0-2 (Cold Open)
    for i in range(3):
        assert entries[i]["image"] is None


def test_ingest_notebooklm_harvests_primary_urls_from_source_column(tmp_path: Path) -> None:
    sec_url = "https://www.sec.gov/Archives/edgar/data/0001018724/amzn-20260930.htm"
    fed_url = "https://www.federalreserve.gov/monetarypolicy/fomcminutes20260918.htm"
    evidence_md = (
        "| # | Point of Contention / Claim | Canonical Period / Scope | "
        "Verbatim Quote Refuting or Explaining | Source Doc & Exact Section/Page | "
        "Root Cause / Hard Metric |\n"
        "|---|---|---|---|---|---|\n"
        f"| 1 | 設備投資が850億ドルに達した | 2026-Q3 | "
        f"Amazon capex reached $85 billion in FY2026. | {sec_url} p.12 | $85B (850億ドル) |\n"
        f"| 2 | 政策金利は4.25%に維持された | 2026-Q3 | "
        f"Policy rate held steady at 4.25 percent in September 2026. | {fed_url} p.4 | 4.25% |\n"
    )
    script_entries = [
        {"character": "四国めたん", "text": "設備投資は850億ドルに達したのですわ", "emotion": "normal", "motion": "none", "image": None},
        {"character": "ずんだもん", "text": "政策金利は4.25%に維持されたのだ", "emotion": "normal", "motion": "none", "image": None},
    ]
    sources_dir = tmp_path / "sources"
    claims = ingest_notebooklm_markdown_to_claims(
        script_entries, evidence_md, sources_dir=sources_dir
    )

    manifest = json.loads((sources_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest_urls = {
        v.get("url") for v in manifest.values() if isinstance(v, dict) and v.get("url")
    }
    assert sec_url in manifest_urls
    assert fed_url in manifest_urls
    assert "https://www.sec.gov/Archives/edgar/data/0000000000/primary_anchor_doc.pdf" not in manifest_urls
    assert "https://nvd.nist.gov/vuln/detail/CVE-2026-0001" not in manifest_urls

    evidence_urls = {ev.url for c in claims for ev in c.evidence}
    assert sec_url in evidence_urls
    assert fed_url in evidence_urls
    assert "https://www.sec.gov/Archives/edgar/data/0000000000/primary_anchor_doc.pdf" not in evidence_urls
    assert "https://nvd.nist.gov/vuln/detail/CVE-2026-0001" not in evidence_urls


def test_ingest_notebooklm_table_urls_override_ideate_placeholder_manifest(tmp_path: Path) -> None:
    sec_url = "https://www.sec.gov/Archives/edgar/data/0001018724/amzn-20260930.htm"
    fed_url = "https://www.federalreserve.gov/monetarypolicy/fomcminutes20260918.htm"
    placeholder_sec = "https://www.sec.gov/Archives/edgar/data/0000000000/primary_anchor_doc.pdf"
    placeholder_cve = "https://nvd.nist.gov/vuln/detail/CVE-2026-0001"

    sources_dir = tmp_path / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    placeholder_manifest = {
        "topic": "Test Topic",
        "archetype": "post_mortem",
        "primary_anchor_doc": {
            "url": placeholder_sec,
            "title": "Primary Anchor Doc (Official Report / Whitepaper / Court Filing)",
            "primary": True,
        },
        "counter_analysis": {
            "url": placeholder_cve,
            "title": "Counter-Perspective or Dissenting Analysis",
            "primary": False,
        },
    }
    (sources_dir / "manifest.json").write_text(
        json.dumps(placeholder_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    evidence_md = (
        "| # | Point of Contention / Claim | Canonical Period / Scope | "
        "Verbatim Quote Refuting or Explaining | Source Doc & Exact Section/Page | "
        "Root Cause / Hard Metric |\n"
        "|---|---|---|---|---|---|\n"
        f"| 1 | 設備投資が850億ドルに達した | 2026-Q3 | "
        f"Amazon capex reached $85 billion in FY2026. | {sec_url} p.12 | $85B (850億ドル) |\n"
        f"| 2 | 政策金利は4.25%に維持された | 2026-Q3 | "
        f"Policy rate held steady at 4.25 percent in September 2026. | {fed_url} p.4 | 4.25% |\n"
    )
    script_entries = [
        {"character": "四国めたん", "text": "設備投資は850億ドルに達したのですわ", "emotion": "normal", "motion": "none", "image": None},
        {"character": "ずんだもん", "text": "政策金利は4.25%に維持されたのだ", "emotion": "normal", "motion": "none", "image": None},
    ]

    claims = ingest_notebooklm_markdown_to_claims(
        script_entries, evidence_md, manifest=placeholder_manifest, sources_dir=sources_dir
    )

    manifest = json.loads((sources_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest_urls = {
        v.get("url") for v in manifest.values() if isinstance(v, dict) and v.get("url")
    }
    assert sec_url in manifest_urls
    assert fed_url in manifest_urls
    assert placeholder_sec not in manifest_urls
    assert placeholder_cve not in manifest_urls

    evidence_urls = {ev.url for c in claims for ev in c.evidence}
    assert sec_url in evidence_urls
    assert fed_url in evidence_urls
    assert placeholder_sec not in evidence_urls
    assert placeholder_cve not in evidence_urls


def test_ingest_notebooklm_single_pdf_no_cve_padding(tmp_path: Path) -> None:
    from veraxi_ymmp.epistemic.fact_audit import audit_project_facts
    from veraxi_ymmp.epistemic.facts import claims_to_json

    sec_url = "https://www.sec.gov/Archives/edgar/data/0001018724/amzn-20260930.htm"
    placeholder_sec = "https://www.sec.gov/Archives/edgar/data/0000000000/primary_anchor_doc.pdf"
    placeholder_cve = "https://nvd.nist.gov/vuln/detail/CVE-2026-0001"

    sources_dir = tmp_path / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    placeholder_manifest = {
        "topic": "Amazon Capex 10-Q Only",
        "archetype": "post_mortem",
        "primary_anchor_doc": {"url": placeholder_sec, "title": "Placeholder Primary", "primary": True},
        "counter_analysis": {"url": placeholder_cve, "title": "Placeholder Counter", "primary": False},
    }
    (sources_dir / "manifest.json").write_text(
        json.dumps(placeholder_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    evidence_md = (
        "| # | Point of Contention / Claim | Canonical Period / Scope | "
        "Verbatim Quote Refuting or Explaining | Source Doc & Exact Section/Page | "
        "Root Cause / Hard Metric |\n"
        "|---|---|---|---|---|---|\n"
        "| 1 | 設備投資が850億ドルに達した | 2026-Q3 | "
        f"Amazon capex reached $85 billion in FY2026. | {sec_url} p.12 | $85B (850億ドル) |\n"
    )
    script_entries = [
        {"character": "四国めたん", "text": "設備投資は850億ドルに達したのですわ", "emotion": "normal", "motion": "none", "image": None},
    ]
    (tmp_path / "script.json").write_text(json.dumps(script_entries, ensure_ascii=False), encoding="utf-8")

    claims = ingest_notebooklm_markdown_to_claims(
        script_entries, evidence_md, manifest=placeholder_manifest, sources_dir=sources_dir
    )
    (tmp_path / "claims.json").write_text(claims_to_json(claims), encoding="utf-8")

    manifest = json.loads((sources_dir / "manifest.json").read_text(encoding="utf-8"))
    source_entries = {k: v for k, v in manifest.items() if isinstance(v, dict) and v.get("url")}
    assert len(source_entries) == 1
    assert {v["url"] for v in source_entries.values()} == {sec_url}
    assert placeholder_cve not in json.dumps(manifest)
    assert [p.name for p in sources_dir.glob("*.md")] == [f"{next(iter(source_entries))}.md"]

    outcome = audit_project_facts(tmp_path / "script.json")
    assert outcome.blockers == []
