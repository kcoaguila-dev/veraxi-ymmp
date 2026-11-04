import json
from pathlib import Path

import pytest

from veraxi_ymmp.fact_audit import audit_project_facts


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
    from veraxi_ymmp.fact_audit import draft_project_claims

    script = tmp_path / "script.json"
    data = [{"character": "a", "text": "売上は500億ドルです。"}, {"character": "b", "text": "はぁ！？"}]
    script.write_text("[]", encoding="utf-8")
    _, added = draft_project_claims(script, data)
    _, again = draft_project_claims(script, data)
    assert (added, again) == (1, 0)
