from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from veraxi_ymmp.app.cli import _dispatch_subcommand
from veraxi_ymmp.editorial.notebooklm_verify import (
    build_post_script_audit_prompt,
    parse_notebooklm_audit_table,
    reconcile_notebooklm_audit,
)
from veraxi_ymmp.epistemic.fact_audit import audit_project_facts
from veraxi_ymmp.epistemic.facts import Verdict


def _write_sample_project(proj_dir: Path) -> None:
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "script_seed.json").write_text(
        json.dumps({"topic": "Amazon Capex vs Profit Scope"}, ensure_ascii=False),
        encoding="utf-8",
    )
    script = [
        {
            "character": "ずんだもん",
            "text": "えっ、本当なの！？",
            "emotion": "surprised",
            "motion": "nod",
            "image": None,
        },
        {
            "character": "四国めたん",
            "text": "{設備投資|せつびとうし}は850億ドルに達したのですわ",
            "emotion": "normal",
            "motion": "none",
            "image": None,
        },
        {
            "character": "ずんだもん",
            "text": "AWSの営業利益が34%増えたのだ",
            "emotion": "excited",
            "motion": "nod",
            "image": "broll/slide_01.png",
        },
    ]
    (proj_dir / "script.json").write_text(
        json.dumps(script, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    broll = [
        {
            "type": "vs",
            "filename": "slide_01.png",
            "title": "AWS利益と投資規模",
            "left_title": "設備投資",
            "left_items": ["年間投資850億ドル"],
            "right_title": "AWS部門",
            "right_items": ["営業利益34%増"],
            "theme_color": "blue",
        }
    ]
    (proj_dir / "broll_manifest.json").write_text(
        json.dumps(broll, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    thumb = {
        "badge": "【一次資料検証】",
        "title_line1": "850億ドルの重圧",
        "title_line2": "AWS利益34%増の真実",
        "theme": "gold",
        "character": "ずんだもん",
    }
    (proj_dir / "thumbnail_config.json").write_text(
        json.dumps(thumb, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def test_build_post_script_audit_prompt_includes_cuts_slides_and_thumbnail(tmp_path: Path) -> None:
    _write_sample_project(tmp_path)
    prompt = build_post_script_audit_prompt(tmp_path)

    assert "Amazon Capex vs Profit Scope" in prompt
    assert "cut_01" in prompt
    assert "設備投資は850億ドルに達したのですわ" in prompt
    assert "{設備投資|せつびとうし}" not in prompt  # ruby stripped for readability
    assert "cut_02" in prompt
    assert "cut_00" not in prompt  # short reaction skipped when checkable cuts exist
    assert "slide_00" in prompt
    assert "slide_01.png (vs)" in prompt
    assert "thumb_00" in prompt
    assert "850億ドルの重圧" in prompt
    assert "| Item ID | Assertion | Verdict | Verbatim Quote | Source & Page/URL | Discrepancy | Suggested Fix (<=38 chars) |" in prompt


def test_parse_notebooklm_audit_table_normalizes_verdicts_and_ids() -> None:
    reply = """
Here is the audit of all items against your uploaded 10-Q PDFs:

| Item ID | Assertion | Verdict | Verbatim Quote | Source & Page/URL | Discrepancy | Suggested Fix (<=38 chars) |
|---|---|---|---|---|---|---|
| `[cut_01 - Cut #1]` | 設備投資は850億ドル | **SUPPORTED** | "Amazon capex reached $85 billion in FY2026." | https://www.sec.gov/Archives/edgar/data/0001018724/amzn-20260930.htm p.12 | - | - |
| cut_02 | Amazon全体の利益が34%増 | DRIFTED | "AWS segment operating income increased 34%." | https://www.sec.gov/Archives/edgar/data/0001018724/amzn-20260930.htm p.24 | Segment profit swapped with parent total | AWS部門の営業利益が34%増ですわ |
"""
    rows = parse_notebooklm_audit_table(reply)
    assert len(rows) == 2
    assert rows[0]["item_id"] == "cut_01"
    assert rows[0]["verdict"] == "SUPPORTED"
    assert rows[0]["quote"] == "Amazon capex reached $85 billion in FY2026."
    assert rows[1]["item_id"] == "cut_02"
    assert rows[1]["verdict"] == "DRIFTED"
    assert rows[1]["suggested_fix"] == "AWS部門の営業利益が34%増ですわ"


def test_reconcile_notebooklm_audit_supported_passes_fact_gate(tmp_path: Path) -> None:
    _write_sample_project(tmp_path)
    sec_url = "https://www.sec.gov/Archives/edgar/data/0001018724/amzn-20260930.htm"
    fed_url = "https://www.federalreserve.gov/monetarypolicy/fomcminutes20260918.htm"

    audit_md = (
        "| Item ID | Assertion | Verdict | Verbatim Quote | Source & Page/URL | Discrepancy | Suggested Fix (<=38 chars) |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| cut_01 | 設備投資は850億ドルに達したのですわ | SUPPORTED | \"Capital expenditures reached $85 billion in FY2026.\" | {sec_url} p.12 | - | - |\n"
        f"| cut_02 | AWSの営業利益が34%増えたのだ | SUPPORTED | \"AWS segment operating income increased 34% year over year.\" | {fed_url} p.24 | - | - |\n"
        f"| slide_00 | AWS利益と投資規模 | SUPPORTED | \"Capital expenditures reached $85 billion and AWS income rose 34%.\" | {sec_url} p.12 | - | - |\n"
        f"| thumb_00 | 850億ドルの重圧 | SUPPORTED | \"Capital expenditures reached $85 billion in FY2026.\" | {sec_url} p.12 | - | - |\n"
    )
    res = reconcile_notebooklm_audit(tmp_path, audit_md)

    assert res.passed is True
    assert res.supported_count == 4
    assert res.flagged_rows == []
    assert res.reprompt_block == ""
    assert (tmp_path / "claims.json").is_file()

    manifest = json.loads((tmp_path / "sources" / "manifest.json").read_text(encoding="utf-8"))
    urls = {v.get("url") for v in manifest.values() if isinstance(v, dict) and v.get("url")}
    assert sec_url in urls
    assert fed_url in urls
    for sid, meta in manifest.items():
        if isinstance(meta, dict) and meta.get("sha256"):
            assert (tmp_path / "sources" / f"{sid}.md").is_file()

    outcome = audit_project_facts(tmp_path / "script.json")
    assert outcome.blockers == []


def test_reconcile_notebooklm_audit_drifted_and_refuted_fails_closed(tmp_path: Path) -> None:
    _write_sample_project(tmp_path)
    sec_url = "https://www.sec.gov/Archives/edgar/data/0001018724/amzn-20260930.htm"

    audit_md = (
        "| Item ID | Assertion | Verdict | Verbatim Quote | Source & Page/URL | Discrepancy | Suggested Fix (<=38 chars) |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| cut_01 | 設備投資は850億ドルに達したのですわ | SUPPORTED | \"Capital expenditures reached $85 billion in FY2026.\" | {sec_url} p.12 | - | - |\n"
        f"| cut_02 | Amazon全体が34%増益 | DRIFTED | \"AWS operating income increased 34%, whereas consolidated margin narrowed.\" | {sec_url} p.24 | Segment operating income swapped with parent total | AWS部門の営業利益が34%増ですわ |\n"
        f"| slide_00 | 投資850億ドルで破綻確定 | REFUTED | \"Operating cash flow covered capital outlays without liquidity distress.\" | {sec_url} p.31 | Conditional risk flipped to guaranteed failure | 投資850億ドルで資金負担が急増 |\n"
    )
    res = reconcile_notebooklm_audit(tmp_path, audit_md)

    assert res.passed is False
    assert res.supported_count == 1
    assert len(res.flagged_rows) == 2
    assert "LLM RE-PROMPT BLOCK" in res.reprompt_block
    assert "[DRIFTED] cut_02" in res.reprompt_block
    assert "Segment operating income swapped with parent total" in res.reprompt_block
    assert "AWS部門の営業利益が34%増ですわ" in res.reprompt_block
    assert "[REFUTED] slide_00" in res.reprompt_block

    outcome = audit_project_facts(tmp_path / "script.json")
    assert len(outcome.blockers) >= 2
    assert any(f.verdict is Verdict.REFUTED for f in outcome.blockers)


def test_cli_verify_notebooklm_reply_and_interactive_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_sample_project(tmp_path)
    sec_url = "https://www.sec.gov/Archives/edgar/data/0001018724/amzn-20260930.htm"
    fed_url = "https://www.federalreserve.gov/monetarypolicy/fomcminutes20260918.htm"

    ok_reply = tmp_path / "reply_ok.md"
    ok_reply.write_text(
        "| Item ID | Assertion | Verdict | Verbatim Quote | Source & Page/URL | Discrepancy | Suggested Fix (<=38 chars) |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| cut_01 | 設備投資は850億ドルに達したのですわ | SUPPORTED | \"Capital expenditures reached $85 billion in FY2026.\" | {sec_url} p.12 | - | - |\n"
        f"| cut_02 | AWSの営業利益が34%増えたのだ | SUPPORTED | \"AWS segment operating income increased 34%.\" | {fed_url} p.24 | - | - |\n",
        encoding="utf-8",
    )
    handled = _dispatch_subcommand("verify-notebooklm", [str(tmp_path), "--reply", str(ok_reply)])
    assert handled is True
    out = capsys.readouterr().out
    assert "PASS:" in out
    assert (tmp_path / "notebooklm_audit_prompt.md").is_file()

    bad_paste = (
        "| Item ID | Assertion | Verdict | Verbatim Quote | Source & Page/URL | Discrepancy | Suggested Fix (<=38 chars) |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| cut_01 | 設備投資は850億ドル | UNVERIFIED | - | {sec_url} | Missing in filing | 投資額を一次資料に合わせて修正 |\n"
        "---END---\n"
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(bad_paste))
    with pytest.raises(SystemExit) as exc_info:
        _dispatch_subcommand("verify-notebooklm", [str(tmp_path), "--interactive"])
    assert exc_info.value.code == 1
    out_fail = capsys.readouterr().out
    assert "LLM RE-PROMPT BLOCK" in out_fail
    assert "[UNVERIFIED] cut_01" in out_fail
