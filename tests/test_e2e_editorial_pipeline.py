import json
from pathlib import Path
from veraxi_ymmp.cli_ideate import cmd_ideate
from veraxi_ymmp.script_ingest import parse_markdown_dialogue
from veraxi_ymmp.pacing import audit_script_pacing
from veraxi_ymmp.facts import compute_deterministic_grounding


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
