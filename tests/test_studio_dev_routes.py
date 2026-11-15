"""HTTP-level tests for the Studio NotebookLM bridge + Dev fallback routes.

Covers POST /api/projects/<name>/notebooklm/prompt|verify (the
verify-notebooklm round-trip) and POST /api/dev/session-start|pack|apply|
apply/status (the WP1-WP8 code-editing fallback) against a temporary
workspace and a temporary git repo.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from http.server import HTTPServer
from pathlib import Path
from typing import Any, Dict

import pytest
import requests

from veraxi_ymmp.app import studio_dev_routes
from veraxi_ymmp.app.api_server import APIHandler
from veraxi_ymmp.core.utils import set_workspace_root


def get_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    s.listen(1)
    port = int(s.getsockname()[1])
    s.close()
    return port


@pytest.fixture(scope="module")
def api_server() -> Any:
    port = get_free_port()
    server = HTTPServer(("127.0.0.1", port), APIHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture(autouse=True)
def workspace(tmp_path: Path) -> Any:
    previous = os.environ.get("VERAXI_WORKSPACE_DIR")
    set_workspace_root(tmp_path)
    yield tmp_path
    if previous is None:
        os.environ.pop("VERAXI_WORKSPACE_DIR", None)
    else:
        os.environ["VERAXI_WORKSPACE_DIR"] = previous


def _write_sample_project(proj_dir: Path) -> None:
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "script_seed.json").write_text(
        json.dumps({"topic": "Amazon Capex vs Profit Scope"}, ensure_ascii=False),
        encoding="utf-8",
    )
    script = [
        {"character": "ずんだもん", "text": "えっ、本当なの！？",
         "emotion": "surprised", "motion": "nod", "image": None},
        {"character": "四国めたん",
         "text": "{設備投資|せつびとうし}は850億ドルに達したのですわ",
         "emotion": "normal", "motion": "none", "image": None},
        {"character": "ずんだもん", "text": "AWSの営業利益が34%増えたのだ",
         "emotion": "excited", "motion": "nod", "image": "broll/slide_01.png"},
    ]
    (proj_dir / "script.json").write_text(
        json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    broll = [{
        "type": "vs", "filename": "slide_01.png", "title": "AWS利益と投資規模",
        "left_title": "設備投資", "left_items": ["年間投資850億ドル"],
        "right_title": "AWS部門", "right_items": ["営業利益34%増"],
        "theme_color": "blue",
    }]
    (proj_dir / "broll_manifest.json").write_text(
        json.dumps(broll, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    thumb = {
        "badge": "【一次資料検証】", "title_line1": "850億ドルの重圧",
        "title_line2": "AWS利益34%増の真実", "theme": "gold",
        "character": "ずんだもん",
    }
    (proj_dir / "thumbnail_config.json").write_text(
        json.dumps(thumb, indent=2, ensure_ascii=False), encoding="utf-8"
    )


_SUPPORTED_TABLE = (
    "| Item ID | Assertion | Verdict | Verbatim Quote | Source & Page/URL | Discrepancy | Suggested Fix (<=38 chars) |\n"
    "|---|---|---|---|---|---|---|\n"
    "| cut_01 | 設備投資は850億ドルに達したのですわ | SUPPORTED | \"Capital expenditures reached $85 billion in FY2026.\" | https://www.sec.gov/Archives/edgar/data/0001018724/amzn-20260930.htm p.12 | - | - |\n"
    "| cut_02 | AWSの営業利益が34%増えたのだ | SUPPORTED | \"AWS segment operating income increased 34% year over year.\" | https://www.federalreserve.gov/monetarypolicy/fomcminutes20260918.htm p.24 | - | - |\n"
    "| slide_00 | AWS利益と投資規模 | SUPPORTED | \"Capital expenditures reached $85 billion and AWS income rose 34%.\" | https://www.sec.gov/Archives/edgar/data/0001018724/amzn-20260930.htm p.12 | - | - |\n"
    "| thumb_00 | 850億ドルの重圧 | SUPPORTED | \"Capital expenditures reached $85 billion in FY2026.\" | https://www.sec.gov/Archives/edgar/data/0001018724/amzn-20260930.htm p.12 | - | - |\n"
)


# --- NotebookLM bridge -------------------------------------------------


def test_notebooklm_prompt_404_for_missing_project(
    api_server: str, workspace: Path
) -> None:
    res = requests.post(f"{api_server}/api/projects/nope/notebooklm/prompt", json={})
    assert res.status_code == 404


def test_notebooklm_prompt_requires_script(
    api_server: str, workspace: Path
) -> None:
    (workspace / "projects" / "empty").mkdir(parents=True)
    res = requests.post(f"{api_server}/api/projects/empty/notebooklm/prompt", json={})
    assert res.status_code == 400
    assert "script.json" in res.json()["error"]


def test_notebooklm_prompt_and_verify_round_trip(
    api_server: str, workspace: Path
) -> None:
    proj = workspace / "projects" / "audit_proj"
    _write_sample_project(proj)

    res = requests.post(f"{api_server}/api/projects/audit_proj/notebooklm/prompt", json={})
    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    assert "cut_01" in payload["prompt"]
    assert (proj / "notebooklm_audit_prompt.md").is_file()

    res = requests.post(
        f"{api_server}/api/projects/audit_proj/notebooklm/verify",
        json={"audit_md": _SUPPORTED_TABLE},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    assert payload["passed"] is True
    assert payload["supported_count"] == 4
    assert payload["flagged_rows"] == []
    assert payload["gate_blockers"] == []
    assert (proj / "claims.json").is_file()


def test_notebooklm_verify_flagged_rows_fail_with_reprompt(
    api_server: str, workspace: Path
) -> None:
    proj = workspace / "projects" / "drift_proj"
    _write_sample_project(proj)
    drifted = _SUPPORTED_TABLE.replace(
        "| cut_02 | AWSの営業利益が34%増えたのだ | SUPPORTED |",
        "| cut_02 | Amazon全体が34%増益 | DRIFTED |",
    )
    res = requests.post(
        f"{api_server}/api/projects/drift_proj/notebooklm/verify",
        json={"audit_md": drifted},
    )
    payload = res.json()
    assert payload["success"] is True
    assert payload["passed"] is False
    assert len(payload["flagged_rows"]) == 1
    assert "LLM RE-PROMPT BLOCK" in payload["reprompt_block"]


def test_notebooklm_verify_rejects_garbage_without_writing(
    api_server: str, workspace: Path
) -> None:
    proj = workspace / "projects" / "garbage_proj"
    _write_sample_project(proj)
    res = requests.post(
        f"{api_server}/api/projects/garbage_proj/notebooklm/verify",
        json={"audit_md": "no table here at all"},
    )
    payload = res.json()
    assert payload["success"] is False
    assert payload["passed"] is False
    assert not (proj / "claims.json").exists()


# --- Dev fallback ------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


@pytest.fixture()
def dev_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev Test")
    (repo / "AGENTS.md").write_text("# Rules\nBe careful.\n", encoding="utf-8")
    (repo / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    monkeypatch.setattr(studio_dev_routes, "_dev_root", lambda: repo)
    return repo


def test_dev_session_start_returns_rules_and_git_state(
    api_server: str, dev_repo: Path
) -> None:
    res = requests.post(f"{api_server}/api/dev/session-start", json={})
    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    assert "Be careful." in payload["text"]


def test_dev_pack_builds_bundle_and_rejects_missing_file(
    api_server: str, dev_repo: Path
) -> None:
    res = requests.post(
        f"{api_server}/api/dev/pack",
        json={"task": "Change VALUE", "files": ["a.py"], "mode": "full"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    assert "### File: `a.py`" in payload["bundle"]
    assert payload["pack_id"]

    res = requests.post(
        f"{api_server}/api/dev/pack",
        json={"task": "x", "files": ["missing.py"]},
    )
    assert res.status_code == 400
    assert "missing.py" in res.json()["error"]

    res = requests.post(
        f"{api_server}/api/dev/pack",
        json={"task": "x", "files": ["../outside.py"]},
    )
    assert res.status_code == 400


def _poll_apply(api_server: str, job_id: str) -> Dict[str, Any]:
    for _ in range(100):
        res = requests.post(
            f"{api_server}/api/dev/apply/status", json={"job_id": job_id}
        )
        payload = res.json()
        if payload.get("status") == "done":
            return payload
        time.sleep(0.1)
    raise AssertionError("apply job did not finish")


def test_dev_apply_rejects_garbage_reply_fail_closed(
    api_server: str, dev_repo: Path
) -> None:
    branches_before = _git(dev_repo, "branch", "--format=%(refname:short)")
    res = requests.post(
        f"{api_server}/api/dev/apply",
        json={"reply": "here is your change, trust me", "mode": "full"},
    )
    assert res.status_code == 200
    job_id = res.json()["job_id"]
    payload = _poll_apply(api_server, job_id)
    assert payload["exit_code"] == 1
    assert _git(dev_repo, "branch", "--format=%(refname:short)") == branches_before
    assert (dev_repo / "a.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_dev_apply_status_unknown_job_404(api_server: str, dev_repo: Path) -> None:
    res = requests.post(
        f"{api_server}/api/dev/apply/status", json={"job_id": "deadbeef0000"}
    )
    assert res.status_code == 404
