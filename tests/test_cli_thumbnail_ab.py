"""CLI tests for `veraxi-ymmp youtube ab` (A/B thumbnail variant switching), fully offline."""

import json
import sys
from pathlib import Path

import pytest

from veraxi_ymmp import cli


def _run(monkeypatch, capsys, *args):
    monkeypatch.setattr(sys, "argv", ["veraxi-ymmp", "youtube", "ab", *args])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return exc.value.code, capsys.readouterr().out


@pytest.fixture
def project(tmp_path: Path) -> Path:
    p = tmp_path / "costco_project"
    p.mkdir()
    (p / "script.json").write_text(
        json.dumps([{"character": "ずんだもん", "text": "コストコの秘密なのだ", "emotion": "surprised"}]),
        encoding="utf-8",
    )
    return p


def test_full_ab_lifecycle_mock(monkeypatch, capsys, project):
    code, out = _run(monkeypatch, capsys, "start", "--project", str(project), "--video-id", "vid1", "--mock")
    assert code == 0, out
    code, out = _run(monkeypatch, capsys, "rotate", "--project", str(project), "--video-id", "vid1", "--mock")
    assert code == 0 and "Rotated thumbnail" in out
    code, out = _run(monkeypatch, capsys, "evaluate", "--project", str(project), "--video-id", "vid1", "--mock")
    assert code == 0 and "Leader:" in out
    code, _ = _run(monkeypatch, capsys, "commit", "--project", str(project), "--video-id", "vid1", "--mock")
    assert code == 0
    code, out = _run(monkeypatch, capsys, "status", "--project", str(project))
    assert code == 0 and out.strip()


def test_video_id_required(monkeypatch, capsys, project):
    code, _ = _run(monkeypatch, capsys, "rotate", "--project", str(project), "--mock")
    assert code == 2


def test_missing_project_fails(monkeypatch, capsys, tmp_path):
    code, _ = _run(monkeypatch, capsys, "status", "--project", str(tmp_path / "nope"))
    assert code == 1
