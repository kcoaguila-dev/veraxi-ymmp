"""HTTP-level tests for the Studio Golden Path workflow routes (Steps 1/2/3/5).

Covers POST /api/ideate, GET|POST /api/projects/<name>/sources,
POST /api/projects/<name>/ingest, POST /api/projects/<name>/validate and
POST /api/projects/<name>/qa against a temporary workspace.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import threading
import time
from http.server import HTTPServer
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest
import requests

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


def _ideate(api_server: str, **overrides: Any) -> requests.Response:
    body: Dict[str, Any] = {"topic": "Server Outage Post Mortem", "archetype": "post_mortem"}
    body.update(overrides)
    return requests.post(f"{api_server}/api/ideate", json=body)


DIALOGUE_MD = """
[Zundamon]: ボクの株、明日売っ払ってくるのだー！
**Metan**: 底値で狼狽売りする養分の鑑ですわね。
3. [Tsumugi]: でもサーバ室のログ見たら、先週からエラー出てたっすよ。
"""

EVIDENCE_MD = (
    "| # | Point of Contention / Claim | Canonical Period / Scope | "
    "Verbatim Quote Refuting or Explaining | Source Doc & Exact Section/Page | "
    "Root Cause / Hard Metric |\n"
    "|---|---|---|---|---|---|\n"
    "| 1 | 設備投資が850億ドルに達した | 2026-Q3 | "
    "Amazon capex reached $85 billion in FY2026. | "
    "https://www.sec.gov/Archives/edgar/data/0001018724/amzn-20260930.htm p.12 | "
    "$85B (850億ドル) |\n"
)

EVIDENCE_DIALOGUE_MD = "[Metan]: 設備投資は850億ドルに達したのですわ\n"


# ---------------------------------------------------------------- Step 1 ---

def test_ideate_creates_project_dossier_and_manifest(
    api_server: str, workspace: Path
) -> None:
    res = _ideate(api_server)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    slug = data["project_name"]
    assert slug
    assert "NotebookLM" in data["dossier_markdown"]
    assert data["sources_manifest"]["topic"] == "Server Outage Post Mortem"

    proj = workspace / "projects" / slug
    assert (proj / "notebooklm_dossier.md").is_file()
    assert (proj / "script_seed.json").is_file()
    assert (proj / "sources" / "manifest.json").is_file()
    assert (proj / "script.json").is_file()


def test_ideate_rejects_missing_topic_and_bad_archetype(api_server: str) -> None:
    res = requests.post(f"{api_server}/api/ideate", json={"archetype": "post_mortem"})
    assert res.status_code == 400
    res = _ideate(api_server, archetype="not_a_real_archetype")
    assert res.status_code == 400
    assert "archetype" in res.json()["error"].lower()


def test_sources_file_upload_lists_sha256(api_server: str, workspace: Path) -> None:
    slug = _ideate(api_server).json()["project_name"]
    content = "Primary source body text."
    res = requests.post(
        f"{api_server}/api/projects/{slug}/sources",
        json={"filename": "filing.txt", "content": content},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    entry = next(s for s in payload["sources"] if s["name"] == "filing.txt")
    assert entry["sha256"] == hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert payload["sources_manifest"]["filing"]["filename"] == "filing.txt"

    res = requests.get(f"{api_server}/api/projects/{slug}/sources")
    assert res.status_code == 200
    assert any(s["name"] == "filing.txt" for s in res.json()["sources"])


def test_sources_url_registration_and_rejections(api_server: str) -> None:
    slug = _ideate(api_server).json()["project_name"]
    res = requests.post(
        f"{api_server}/api/projects/{slug}/sources",
        json={"url": "https://www.sec.gov/example.htm", "title": "SEC Filing"},
    )
    assert res.status_code == 200
    manifest = res.json()["sources_manifest"]
    assert any(
        isinstance(v, dict) and v.get("url") == "https://www.sec.gov/example.htm"
        for v in manifest.values()
    )

    res = requests.post(
        f"{api_server}/api/projects/{slug}/sources",
        json={"filename": "evil.exe", "content": "x"},
    )
    assert res.status_code == 400
    res = requests.post(
        f"{api_server}/api/projects/{slug}/sources", json={"url": "ftp://bad"}
    )
    assert res.status_code == 400
    res = requests.get(f"{api_server}/api/projects/nope/sources")
    assert res.status_code == 404


# ---------------------------------------------------------------- Step 2 ---

def test_ingest_dialogue_builds_script(api_server: str, workspace: Path) -> None:
    slug = _ideate(api_server).json()["project_name"]
    res = requests.post(
        f"{api_server}/api/projects/{slug}/ingest",
        json={"dialogue_markdown": DIALOGUE_MD},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["cut_count"] == 3
    assert data["script"][0]["character"] == "ずんだもん"
    on_disk = json.loads(
        (workspace / "projects" / slug / "script.json").read_text(encoding="utf-8")
    )
    assert len(on_disk) == 3
    assert (workspace / "projects" / slug / "dialogue_raw.md").is_file()


def test_ingest_evidence_builds_claims(api_server: str, workspace: Path) -> None:
    slug = _ideate(api_server).json()["project_name"]
    res = requests.post(
        f"{api_server}/api/projects/{slug}/ingest",
        json={"dialogue_markdown": EVIDENCE_DIALOGUE_MD, "evidence_markdown": EVIDENCE_MD},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["cut_count"] == 1
    assert data["claim_count"] >= 1
    claims = json.loads(
        (workspace / "projects" / slug / "claims.json").read_text(encoding="utf-8")
    )
    assert isinstance(claims, list) and len(claims) >= 1
    assert (workspace / "projects" / slug / "evidence.md").is_file()


def test_ingest_rejects_empty_payload_and_traversal(api_server: str) -> None:
    slug = _ideate(api_server).json()["project_name"]
    res = requests.post(f"{api_server}/api/projects/{slug}/ingest", json={})
    assert res.status_code == 400
    res = requests.post(f"{api_server}/api/projects/../ingest", json={"dialogue_markdown": "x"})
    # '..' reaches the handler only as a single path segment in some clients;
    # either a 400 from the handler or a 404 from routing is a safe rejection.
    assert res.status_code in (400, 404)
    res = requests.post(
        f"{api_server}/api/projects/ghost/ingest", json={"dialogue_markdown": "x"}
    )
    assert res.status_code == 404


# ---------------------------------------------------------------- Step 3 ---

def test_validate_returns_pacing_and_fact_summary(
    api_server: str, workspace: Path
) -> None:
    slug = _ideate(api_server).json()["project_name"]
    requests.post(
        f"{api_server}/api/projects/{slug}/ingest",
        json={"dialogue_markdown": EVIDENCE_DIALOGUE_MD},
    )
    res = requests.post(f"{api_server}/api/projects/{slug}/validate", json={})
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data["retention_score"], int)
    assert isinstance(data["pacing_violations"], list)
    assert isinstance(data["cast_balance"], dict)
    summary = data["fact_summary"]
    assert summary["total"] == len(summary["claims"])
    assert summary["supported"] + summary["unsupported"] + summary["insufficient"] == (
        summary["total"]
    )
    for claim in summary["claims"]:
        assert claim["verdict"] in ("SUPPORTED", "UNSUPPORTED", "INSUFFICIENT")
    assert isinstance(data["passed"], bool)
    assert (workspace / "projects" / slug / "sources.md").is_file()


def test_validate_missing_project_is_404(api_server: str) -> None:
    res = requests.post(f"{api_server}/api/projects/ghost/validate", json={})
    assert res.status_code == 404


# ---------------------------------------------------------------- Step 5 ---

def test_qa_without_video_fails_closed(api_server: str) -> None:
    slug = _ideate(api_server).json()["project_name"]
    requests.post(
        f"{api_server}/api/projects/{slug}/ingest",
        json={"dialogue_markdown": DIALOGUE_MD},
    )
    res = requests.post(f"{api_server}/api/projects/{slug}/qa", json={})
    assert res.status_code == 200
    data = res.json()
    assert data["passed"] is False
    assert data["frames"] == []
    assert data["checks"][0]["name"] == "prerequisites"
    assert data["checks"][0]["passed"] is False


def test_qa_maps_frames_to_media_urls(api_server: str, workspace: Path) -> None:
    slug = _ideate(api_server).json()["project_name"]
    proj = workspace / "projects" / slug
    frame_path = proj / "qa_frames" / "01_cold_open.png"
    fake_report = {
        "success": True,
        "video_path": str(proj / "qa_test.mp4"),
        "video_duration_sec": 12.5,
        "total_cuts": 3,
        "missing_audio": [],
        "coverage_issues": [],
        "thumbnail_issues": [],
        "thumbnail_path": None,
        "frames": {
            "01_cold_open": {
                "cut_index": 0,
                "timestamp_sec": 0.5,
                "speaker": "ずんだもん",
                "text": "ボクの株",
                "frame_path": str(frame_path),
            }
        },
    }
    with patch(
        "veraxi_ymmp.app.studio_workflow_routes.run_project_qa",
        return_value=fake_report,
    ):
        res = requests.post(f"{api_server}/api/projects/{slug}/qa", json={})
    assert res.status_code == 200
    data = res.json()
    assert data["passed"] is True
    assert data["frames"][0]["label"] == "Cold Open"
    assert data["frames"][0]["url"] == (
        f"/api/projects/{slug}/media/qa_frames/01_cold_open.png"
    )
    check_names = {c["name"] for c in data["checks"]}
    assert check_names == {"tts_coverage", "speaker_coverage", "thumbnail", "keyframes"}
