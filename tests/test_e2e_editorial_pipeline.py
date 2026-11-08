import hashlib
import json
from pathlib import Path
from veraxi_ymmp.app.cli_ideate import cmd_ideate
from veraxi_ymmp.editorial.script_ingest import parse_markdown_dialogue
from veraxi_ymmp.editorial.pacing import audit_script_pacing
from veraxi_ymmp.epistemic.facts import compute_deterministic_grounding


def test_e2e_editorial_to_grounded_script(tmp_path: Path) -> None:
    project_dir = tmp_path / "crowdstrike_outage"

    # Step 1: Upstream Ideation
    cmd_ideate([
        "CrowdStrike Kernel Sensor Outage",
        "--archetype", "post_mortem",
        "--output", str(project_dir)
    ])

    assert (project_dir / "notebooklm_dossier.md").exists()
    assert (project_dir / "sources" / "manifest.json").exists()
    assert (project_dir / "script_seed.json").exists()

    # Step 2: Simulate saving a downloaded source document on disk
    source_file = project_dir / "sources" / "pir_report.txt"
    source_text = "Channel 291 configuration file caused a logical null pointer exception in CSagent.sys resulting in 8.5 million blue screen crashes."
    source_file.write_text(source_text, encoding="utf-8")

    # Step 3: Simulate NotebookLM dialectic response saved to dialogue_raw.md
    raw_md_file = project_dir / "dialogue_raw.md"
    raw_md_content = """
[Zundamon]: Windowsが突然世界中で青い画面になったのだ！
[Metan]: マイクロソフトではなく、Channel 291のNull Pointerが原因ですわ。
[Zundamon]: ええっ、たったひとつの設定ファイルで壊れたのだ！？
[Metan]: CSagent.sysの不具合で850万台が停止したのが現実ですわ。
[Tsumugi]: うちのサーバ室も夜通し復旧作業で地獄だったっす！
"""
    raw_md_file.write_text(raw_md_content, encoding="utf-8")

    # Step 4: Ingest Markdown Dialogue into script.json
    script_entries = parse_markdown_dialogue(raw_md_content)
    # Metan's line (40 chars) was split automatically to respect the <= 38 char limit
    assert len(script_entries) == 6
    for entry in script_entries:
        assert len(entry["text"]) <= 38

    script_json_file = project_dir / "script.json"
    script_json_file.write_text(
        json.dumps(script_entries, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    # Step 5: Audit Pacing & Retention Readiness
    report = audit_script_pacing(script_entries)
    # Ensure there are no fatal schema/pacing errors
    fatal_errors = [v for v in report.violations if v.severity == "ERROR"]
    assert len(fatal_errors) == 0

    # Step 6: Verify L1 Deterministic Grounding against local source file
    metan_claim = script_entries[1]["text"]
    grounding_score = compute_deterministic_grounding(metan_claim, source_text)
    # "Channel 291" and "Null Pointer" should match with high grounding
    assert grounding_score > 0.0


def test_e2e_tech_topic_agnostic_audit_and_metadata(tmp_path: Path) -> None:
    from veraxi_ymmp.epistemic.fact_audit import audit_project_facts
    from veraxi_ymmp.graphics.thumbnail import auto_extract_thumbnail_config
    from veraxi_ymmp.exporters.youtube_metadata import generate_project_youtube_metadata
    from veraxi_ymmp.epistemic.facts import Claim, ClaimWeight, ClaimKind, Evidence, Verdict, claims_to_json

    project_dir = tmp_path / "xz_backdoor_forensic"
    project_dir.mkdir(parents=True)
    sources_dir = project_dir / "sources"
    sources_dir.mkdir(parents=True)

    # 1. Source Document & Manifest
    source_file = sources_dir / "nvd_cve_2024_3094.txt"
    source_text = "CVE-2024-3094 has a CVSS severity score of 10.0 critical. Upstream tarballs for XZ Utils versions 5.6.0 and 5.6.1 contained malicious code injected via m4 macros."
    source_file.write_text(source_text, encoding="utf-8")
    source_sha = hashlib.sha256(source_text.encode("utf-8")).hexdigest()

    manifest_data = {
        "nvd_cve_2024_3094": {
            "source_id": "nvd_cve_2024_3094",
            "title": "NVD CVE-2024-3094 Advisory",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2024-3094",
            "file": "sources/nvd_cve_2024_3094.txt",
            "sha256": source_sha,
            "verified": True,
        }
    }
    (sources_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    # 2. Dialogue Script (Tech Post-Mortem)
    script_data = [
        {"character": "zundamon", "text": "Linux界隈が前代未聞のバックドアで大騒ぎなのだ！"},
        {"character": "metan", "text": "XZ Utilsに仕込まれた脆弱性CVE-2024-3094の危険度は10.0ですわ。"},
        {"character": "zundamon", "text": "最高スコアの10.0！？国家レベルの攻撃なのだ…"},
        {"character": "tsumugi", "text": "バージョン5.6.0と5.6.1が汚染されてたっす！"},
    ]
    (project_dir / "script.json").write_text(json.dumps(script_data, ensure_ascii=False), encoding="utf-8")

    # 3. Claims Ledger
    claims = [
        Claim(
            id="C01",
            text="脆弱性CVE-2024-3094の危険度は10.0",
            kind=ClaimKind.NUMBER,
            weight=ClaimWeight.MINOR,
            cut_index=1,
            evidence=[
                Evidence(
                    source_id="nvd_cve_2024_3094",
                    url="https://nvd.nist.gov/vuln/detail/CVE-2024-3094",
                    quote="CVE-2024-3094 has a CVSS severity score of 10.0 critical.",
                    sha256=source_sha,
                )
            ],
        ),
        Claim(
            id="C02",
            text="バージョン5.6.0と5.6.1が汚染",
            kind=ClaimKind.FACT,
            weight=ClaimWeight.MINOR,
            cut_index=3,
            evidence=[
                Evidence(
                    source_id="nvd_cve_2024_3094",
                    url="https://nvd.nist.gov/vuln/detail/CVE-2024-3094",
                    quote="Upstream tarballs for XZ Utils versions 5.6.0 and 5.6.1 contained malicious code",
                    sha256=source_sha,
                )
            ],
        ),
    ]
    (project_dir / "claims.json").write_text(claims_to_json(claims), encoding="utf-8")

    # 4. Audit Facts with tech profile
    outcome = audit_project_facts(
        project_dir / "script.json",
        profile="tech",
    )
    assert not outcome.blocked, f"Expected not blocked, got blockers: {outcome.blockers}"
    unverified = [r for r in outcome.results if r.verdict != Verdict.SUPPORTED]
    assert len(unverified) == 0, f"Expected 0 unverified, got: {unverified}"

    # 5. Thumbnail Generation: Must NOT match finance presets
    thumb_cfg = auto_extract_thumbnail_config(project_dir)
    assert "半導体" not in thumb_cfg.title_line1
    assert "株式" not in thumb_cfg.title_line1
    assert "大損" not in thumb_cfg.title_line2

    # 6. YouTube Metadata: is_finance must be False, no finance hashtags
    meta = generate_project_youtube_metadata(project_dir)
    assert not any("投資" in tag or "株" in tag for tag in meta.tags)
    assert not any("#AI半導体" in tag or "#株式投資" in tag for tag in meta.tags)
