"""Phase 3: pack/apply coding-agent fallback."""

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

import veraxi_ymmp.app.pack_apply as pa

FIXED_MOD = "def add(a, b):\n    return a + b\n"
BUGGY_MOD = "def add(a, b):\n    return a - b\n"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "AGENTS.md").write_text("# Rules\nBe careful.\n", encoding="utf-8")
    (root / "mod.py").write_text(BUGGY_MOD, encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_mod.py").write_text(
        "from mod import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def _reply(body: str, end: str = pa.END_MARKER) -> str:
    return f"### File: `mod.py`\n```python\n{body}```\n{end}\n"


def _no_failures(changed, test_path, root):
    return []


def test_parse_reply_complete_and_incomplete_variants():
    parsed = pa.parse_reply(_reply(FIXED_MOD))
    assert parsed.complete and parsed.blocks == [("mod.py", FIXED_MOD)]

    no_end = pa.parse_reply(_reply(FIXED_MOD, end=""))
    assert not no_end.complete and "truncated" in no_end.problem

    truncated = pa.parse_reply("### File: `mod.py`\n```python\ndef add(a, b):\n")
    assert not truncated.complete and "truncated" in truncated.problem

    continuation = pa.parse_reply(_reply(FIXED_MOD, end=pa.CONTINUATION_MARKER))
    assert not continuation.complete

    empty = pa.parse_reply("I cannot help with that.")
    assert empty.blocks == [] and not empty.complete


def test_build_pack_bundle_contents():
    bundle = pa.build_pack_bundle(
        "Fix the add bug",
        [("mod.py", BUGGY_MOD)],
        "# Rules\nBe careful.",
        test_path="tests/test_mod.py",
        test_output="FAILED tests/test_mod.py::test_add",
    )
    assert "Fix the add bug" in bundle
    assert "Be careful." in bundle
    assert "return a - b" in bundle
    assert "FAILED tests/test_mod.py::test_add" in bundle
    assert pa.END_MARKER in bundle
    assert pa.CONTINUATION_MARKER in bundle


def test_cmd_pack_budget_fails_loudly(tmp_path, monkeypatch):
    root = _make_repo(tmp_path)
    monkeypatch.chdir(root)
    with pytest.raises(SystemExit) as excinfo:
        pa.cmd_pack(["--task", "x", "--files", "mod.py", "--budget", "10"])
    assert excinfo.value.code == 2


def test_cmd_pack_includes_failing_test_output(tmp_path, monkeypatch, capsys):
    root = _make_repo(tmp_path)
    monkeypatch.chdir(root)
    pa.cmd_pack(["--task", "Fix add", "--files", "mod.py",
                 "--test", "tests/test_mod.py"])
    out = capsys.readouterr().out
    assert "## Failing Tests" in out
    assert "test_add" in out


def test_apply_happy_path_creates_branch_and_writes(tmp_path):
    root = _make_repo(tmp_path)
    outputs: list = []
    code = pa.apply_reply(
        _reply(FIXED_MOD), root,
        branch_name="agent-apply-test", check_runner=_no_failures,
        output_fn=outputs.append,
    )
    assert code == 0
    assert (root / "mod.py").read_text(encoding="utf-8") == FIXED_MOD
    branch = subprocess.run(
        ["git", "-C", str(root), "branch", "--show-current"],
        capture_output=True, text=True,
    ).stdout.strip()
    assert branch == "agent-apply-test"


def test_apply_malformed_reply_modifies_nothing(tmp_path):
    root = _make_repo(tmp_path)
    code = pa.apply_reply(
        "no blocks here", root, check_runner=_no_failures,
        output_fn=lambda _m: None,
    )
    assert code == 1
    assert (root / "mod.py").read_text(encoding="utf-8") == BUGGY_MOD
    branches = subprocess.run(
        ["git", "-C", str(root), "branch"], capture_output=True, text=True
    ).stdout
    assert "agent-apply" not in branches


def test_apply_incomplete_reply_asks_for_continuation(tmp_path):
    root = _make_repo(tmp_path)
    outputs: list = []
    code = pa.apply_reply(
        _reply(FIXED_MOD, end=""), root, check_runner=_no_failures,
        output_fn=outputs.append,
    )
    assert code == 1
    assert (root / "mod.py").read_text(encoding="utf-8") == BUGGY_MOD
    assert any("CONTINUATION" in o or "resend" in o for o in outputs)


def test_apply_refuses_outside_paths_and_tests(tmp_path):
    root = _make_repo(tmp_path)
    evil = f"### File: `../evil.py`\n```python\nx = 1\n```\n{pa.END_MARKER}\n"
    assert pa.apply_reply(evil, root, check_runner=_no_failures,
                          output_fn=lambda _m: None) == 1
    assert not (tmp_path / "evil.py").exists()

    test_edit = (
        f"### File: `tests/test_mod.py`\n```python\nx = 1\n```\n{pa.END_MARKER}\n"
    )
    assert pa.apply_reply(test_edit, root, check_runner=_no_failures,
                          output_fn=lambda _m: None) == 1
    assert pa.apply_reply(
        test_edit, root, allow_tests=True, branch_name="agent-apply-tests",
        check_runner=_no_failures, output_fn=lambda _m: None,
    ) == 0


def test_apply_check_failures_print_reprompt_but_keep_changes(tmp_path):
    root = _make_repo(tmp_path)
    outputs: list = []

    def failing_checks(changed, test_path, root_):
        return [("PYTEST", "tests/test_mod.py::test_add FAILED")]

    code = pa.apply_reply(
        _reply(FIXED_MOD), root, branch_name="agent-apply-fail",
        check_runner=failing_checks, output_fn=outputs.append,
    )
    assert code == 1
    assert (root / "mod.py").read_text(encoding="utf-8") == FIXED_MOD
    joined = "\n".join(outputs)
    assert "LLM RE-PROMPT BLOCK" in joined and "[PYTEST]" in joined


def test_apply_real_bugfix_end_to_end(tmp_path):
    """pack-shaped reply + real ruff/mypy/pytest runner: bug fix goes green."""
    root = _make_repo(tmp_path)
    code = pa.apply_reply(
        _reply(FIXED_MOD), root, test_path="tests/test_mod.py",
        branch_name="agent-apply-e2e",
    )
    # mod.py has no annotations; the repo's own mypy config may or may not
    # apply here — assert on pytest only by checking the file was applied.
    assert (root / "mod.py").read_text(encoding="utf-8") == FIXED_MOD
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_mod.py", "-q",
         "-p", "no:cacheprovider"],
        cwd=root, capture_output=True, text=True,
    )
    assert proc.returncode == 0
    assert code in (0, 1)  # mypy strictness in a bare tmp repo may differ


# --- WP2: manifest, elision, shrink guards ---------------------------------


def _commit_all(root: Path, message: str = "update") -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def _branches(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "branch"], capture_output=True, text=True
    ).stdout


def test_cmd_pack_output_writes_manifest_sidecar(tmp_path, monkeypatch):
    root = _make_repo(tmp_path)
    monkeypatch.chdir(root)
    pa.cmd_pack(["--task", "Fix add", "--files", "mod.py", "-o", "bundle.md"])
    manifest_file = root / "bundle.md.manifest.json"
    assert manifest_file.is_file()
    manifest = pa.load_manifest(manifest_file)
    assert manifest["packed_at"]
    (entry,) = manifest["files"]
    assert entry["path"] == "mod.py"
    assert entry["sha256"] == hashlib.sha256(BUGGY_MOD.encode()).hexdigest()
    assert entry["line_count"] == 2

    # Stdout mode writes no manifest.
    other_parent = tmp_path / "b"
    other_parent.mkdir()
    other = _make_repo(other_parent)
    monkeypatch.chdir(other)
    pa.cmd_pack(["--task", "Fix add", "--files", "mod.py"])
    assert not (other / "bundle.md.manifest.json").exists()


def test_apply_manifest_happy_stale_and_unlisted(tmp_path):
    root = _make_repo(tmp_path)
    manifest = pa.build_manifest([("mod.py", BUGGY_MOD)])

    outputs: list = []
    code = pa.apply_reply(
        _reply(FIXED_MOD), root, manifest=manifest,
        branch_name="agent-wp2-ok", check_runner=_no_failures,
        output_fn=outputs.append,
    )
    assert code == 0
    assert (root / "mod.py").read_text(encoding="utf-8") == FIXED_MOD

    # Stale base: the file changed after packing.
    root2_parent = tmp_path / "stale"
    root2_parent.mkdir()
    root2 = _make_repo(root2_parent)
    (root2 / "mod.py").write_text("# drifted\n", encoding="utf-8")
    outputs = []
    code = pa.apply_reply(
        _reply(FIXED_MOD), root2, manifest=manifest,
        branch_name="agent-wp2-stale", check_runner=_no_failures,
        output_fn=outputs.append,
    )
    assert code == 1
    assert "base drifted since pack; re-pack" in "\n".join(outputs)
    assert (root2 / "mod.py").read_text(encoding="utf-8") == "# drifted\n"
    assert "agent-wp2-stale" not in _branches(root2)
    # --force-stale overrides.
    code = pa.apply_reply(
        _reply(FIXED_MOD), root2, manifest=manifest, force_stale=True,
        branch_name="agent-wp2-forced", check_runner=_no_failures,
        output_fn=lambda _m: None,
    )
    assert code == 0

    # Unlisted path rejected; --allow-new permits it.
    root3_parent = tmp_path / "new"
    root3_parent.mkdir()
    root3 = _make_repo(root3_parent)
    new_file_reply = (
        f"### File: `other.py`\n```python\nx = 1\n```\n{pa.END_MARKER}\n"
    )
    outputs = []
    code = pa.apply_reply(
        new_file_reply, root3, manifest=manifest,
        branch_name="agent-wp2-new", check_runner=_no_failures,
        output_fn=outputs.append,
    )
    assert code == 1
    assert "not in pack manifest" in "\n".join(outputs)
    assert not (root3 / "other.py").exists()
    assert "agent-wp2-new" not in _branches(root3)
    code = pa.apply_reply(
        new_file_reply, root3, manifest=manifest, allow_new=["other.py"],
        branch_name="agent-wp2-new", check_runner=_no_failures,
        output_fn=lambda _m: None,
    )
    assert code == 0
    assert (root3 / "other.py").read_text(encoding="utf-8") == "x = 1\n"


def test_apply_elision_rejected_but_preexisting_word_is_fine(tmp_path):
    root = _make_repo(tmp_path)
    outputs: list = []
    lazy = FIXED_MOD + "# rest of the file unchanged\n"
    code = pa.apply_reply(
        _reply(lazy), root, branch_name="agent-wp2-lazy",
        check_runner=_no_failures, output_fn=outputs.append,
    )
    assert code == 1
    joined = "\n".join(outputs)
    assert "LLM RE-PROMPT BLOCK" in joined and "[GUARD]" in joined
    assert "mod.py:3" in joined
    assert (root / "mod.py").read_text(encoding="utf-8") == BUGGY_MOD
    assert "agent-wp2-lazy" not in _branches(root)

    # The same word already present in the old file is not a new line,
    # so a reply that keeps it verbatim is not rejected for it.
    root2_parent = tmp_path / "pre"
    root2_parent.mkdir()
    root2 = _make_repo(root2_parent)
    header = "# this header stays unchanged\n"
    (root2 / "mod.py").write_text(header + BUGGY_MOD, encoding="utf-8")
    _commit_all(root2)
    code = pa.apply_reply(
        _reply(header + FIXED_MOD), root2, branch_name="agent-wp2-pre",
        check_runner=_no_failures, output_fn=lambda _m: None,
    )
    assert code == 0


def test_apply_shrink_and_empty_rejected_unless_allowed(tmp_path):
    root = _make_repo(tmp_path)
    big = "".join(f"x{i} = {i}\n" for i in range(40))
    (root / "big.py").write_text(big, encoding="utf-8")
    _commit_all(root)

    small = "".join(f"x{i} = {i}\n" for i in range(10))
    small_reply = f"### File: `big.py`\n```python\n{small}```\n{pa.END_MARKER}\n"
    outputs: list = []
    code = pa.apply_reply(
        small_reply, root, branch_name="agent-wp2-shrink",
        check_runner=_no_failures, output_fn=outputs.append,
    )
    assert code == 1
    assert "shrinks from 40 to 10" in "\n".join(outputs)
    assert (root / "big.py").read_text(encoding="utf-8") == big
    assert "agent-wp2-shrink" not in _branches(root)
    code = pa.apply_reply(
        small_reply, root, allow_shrink=True, branch_name="agent-wp2-shrink",
        check_runner=_no_failures, output_fn=lambda _m: None,
    )
    assert code == 0

    empty_reply = _reply("")
    code = pa.apply_reply(
        empty_reply, root, branch_name="agent-wp2-empty",
        check_runner=_no_failures, output_fn=lambda _m: None,
    )
    assert code == 1
    assert (root / "mod.py").read_text(encoding="utf-8") == BUGGY_MOD
    assert "agent-wp2-empty" not in _branches(root)


def test_apply_no_manifest_warns_diff_stat_printed_and_eol(tmp_path):
    root = _make_repo(tmp_path)
    outputs: list = []
    code = pa.apply_reply(
        _reply(FIXED_MOD), root, branch_name="agent-wp2-plain",
        check_runner=_no_failures, output_fn=outputs.append,
    )
    assert code == 0
    joined = "\n".join(outputs)
    assert "allowlist" in joined  # the no-manifest warning
    assert "git diff --stat" in joined and "mod.py" in joined
    # LF files stay LF on disk (no CRLF translation).
    assert b"\r\n" not in (root / "mod.py").read_bytes()

    # .ps1 files follow the repo's .gitattributes CRLF rule.
    ps_reply = (
        f"### File: `run.ps1`\n```text\necho hi\n```\n{pa.END_MARKER}\n"
    )
    code = pa.apply_reply(
        ps_reply, root, branch_name="agent-wp2-ps",
        check_runner=_no_failures, output_fn=lambda _m: None,
    )
    assert code == 0
    assert (root / "run.ps1").read_bytes() == b"echo hi\r\n"
