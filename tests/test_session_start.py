"""Tests for veraxi_ymmp.app.session_start (WP7)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import veraxi_ymmp.app.session_start as ss


def _make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@e.c"],
                 ["config", "user.name", "T"]):
        subprocess.run(["git", "-C", str(root), *args],
                       check=True, stdin=subprocess.DEVNULL, capture_output=True)
    (root / "AGENTS_WEB.md").write_bytes(b"# Slim rules\nBe exact.\n")
    (root / "mod.py").write_bytes(b"# TODO: tighten the retry loop\nx = 1\n")
    subprocess.run(["git", "-C", str(root), "add", "-A"],
                   check=True, stdin=subprocess.DEVNULL, capture_output=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "init"],
                   check=True, stdin=subprocess.DEVNULL, capture_output=True)
    return root


def test_session_start_contains_rules_state_and_todos(tmp_path):
    root = _make_repo(tmp_path)
    text = ss.build_session_start(root)
    assert "# Slim rules" in text  # AGENTS_WEB.md preferred
    assert "Be exact." in text
    assert "## Repository state" in text
    assert "init" in text  # recent commit subject
    assert "clean" in text  # working tree clean right after commit
    assert "TODO: tighten the retry loop" in text
    assert "mod.py:1" in text  # git grep path:line prefix


def test_session_start_reports_dirty_tree(tmp_path):
    root = _make_repo(tmp_path)
    (root / "mod.py").write_bytes(b"x = 2\n")
    text = ss.build_session_start(root)
    assert "1 uncommitted change(s)" in text
    assert "mod.py" in text


def test_session_start_falls_back_to_agents_md(tmp_path):
    root = _make_repo(tmp_path)
    (root / "AGENTS_WEB.md").unlink()
    (root / "AGENTS.md").write_bytes(b"# Full rules\n")
    text = ss.build_session_start(root)
    assert "# Full rules" in text


def test_session_start_commands_and_reply_rules(tmp_path):
    root = _make_repo(tmp_path)
    text = ss.build_session_start(root)
    assert "veraxi-ymmp pack" in text
    assert "veraxi-ymmp apply reply.md" in text
    assert "veraxi-ymmp apply-edit reply.md" in text
    assert "--from-manifest" in text
    assert "WEB_CHAT_RUNBOOK.md" in text
    assert "COMPLETE file contents" in text
    assert '"broll_manifest"' in text


def test_cmd_session_start_output_file(tmp_path, monkeypatch):
    root = _make_repo(tmp_path)
    monkeypatch.setattr(ss.pa, "_repo_root", lambda: root)
    out = tmp_path / "start.md"
    assert ss.cmd_session_start(["-o", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# veraxi-ymmp — web-chat session start")
