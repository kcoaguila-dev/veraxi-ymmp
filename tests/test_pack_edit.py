"""Tests for veraxi_ymmp.app.pack_edit (WP4 anchored edit mode)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import veraxi_ymmp.app.pack_apply as pa
import veraxi_ymmp.app.pack_edit as pe

BUGGY_MOD = "def add(a, b):\n    return a - b\n"
FIXED_LINE = "    return a + b"


def _make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@e.c"],
                 ["config", "user.name", "T"]):
        subprocess.run(["git", "-C", str(root), *args],
                       check=True, stdin=subprocess.DEVNULL, capture_output=True)
    (root / "mod.py").write_text(BUGGY_MOD, encoding="utf-8")
    (root / "other.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"],
                   check=True, stdin=subprocess.DEVNULL, capture_output=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "init"],
                   check=True, stdin=subprocess.DEVNULL, capture_output=True)
    return root


def _no_failures(changed, test_path, root):
    return []


def _edit_block(path: str, search: str, replace: str) -> str:
    return (
        f"### Edit: `{path}`\n{pe.SEARCH_MARKER}\n{search}\n"
        f"{pe.SEPARATOR}\n{replace}\n{pe.REPLACE_MARKER}\n"
    )


def _reply(*blocks: str) -> str:
    return "".join(blocks) + pa.END_MARKER + "\n"


def _branches(root: Path) -> list:
    out = subprocess.run(
        ["git", "-C", str(root), "branch", "--format=%(refname:short)"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, check=True,
    )
    return out.stdout.split()


def test_edit_exact_once_applies(tmp_path):
    root = _make_repo(tmp_path)
    reply = _reply(_edit_block("mod.py", "    return a - b", FIXED_LINE))
    code = pe.apply_edit_reply(
        reply, root, branch_name="agent-edit-test",
        check_runner=_no_failures, output_fn=lambda _m: None,
    )
    assert code == 0
    assert (root / "mod.py").read_text(encoding="utf-8") == (
        "def add(a, b):\n    return a + b\n"
    )
    assert "agent-edit-test" in _branches(root)


def test_edit_zero_match_rejected_and_untouched(tmp_path):
    root = _make_repo(tmp_path)
    reply = _reply(_edit_block("mod.py", "    return a * b", FIXED_LINE))
    outputs: list = []
    code = pe.apply_edit_reply(
        reply, root, branch_name="agent-edit-zero",
        check_runner=_no_failures, output_fn=outputs.append,
    )
    assert code == 1
    assert "0 matches" in "\n".join(outputs)
    assert (root / "mod.py").read_text(encoding="utf-8") == BUGGY_MOD
    assert "agent-edit-zero" not in _branches(root)


def test_edit_duplicate_match_rejected_and_untouched(tmp_path):
    root = _make_repo(tmp_path)
    (root / "mod.py").write_text("x = 1\nx = 1\n", encoding="utf-8")
    reply = _reply(_edit_block("mod.py", "x = 1", "x = 2"))
    outputs: list = []
    code = pe.apply_edit_reply(
        reply, root, branch_name="agent-edit-dup",
        check_runner=_no_failures, output_fn=outputs.append,
    )
    assert code == 1
    assert "matches 2 places" in "\n".join(outputs)
    assert (root / "mod.py").read_text(encoding="utf-8") == "x = 1\nx = 1\n"
    assert "agent-edit-dup" not in _branches(root)


def test_edit_multi_block_multi_file_and_sequential(tmp_path):
    root = _make_repo(tmp_path)
    reply = _reply(
        _edit_block("mod.py", "    return a - b", FIXED_LINE),
        _edit_block("mod.py", "def add(a, b):", "def add(a, b):  # fixed"),
        _edit_block("other.py", "x = 1", "x = 2"),
    )
    code = pe.apply_edit_reply(
        reply, root, branch_name="agent-edit-multi",
        check_runner=_no_failures, output_fn=lambda _m: None,
    )
    assert code == 0
    assert (root / "mod.py").read_text(encoding="utf-8") == (
        "def add(a, b):  # fixed\n    return a + b\n"
    )
    assert (root / "other.py").read_text(encoding="utf-8") == "x = 2\n"


def test_edit_failure_leaves_all_files_untouched(tmp_path):
    root = _make_repo(tmp_path)
    reply = _reply(
        _edit_block("mod.py", "    return a - b", FIXED_LINE),
        _edit_block("other.py", "x = 99", "x = 2"),  # zero matches
    )
    code = pe.apply_edit_reply(
        reply, root, branch_name="agent-edit-atomic",
        check_runner=_no_failures, output_fn=lambda _m: None,
    )
    assert code == 1
    assert (root / "mod.py").read_text(encoding="utf-8") == BUGGY_MOD
    assert (root / "other.py").read_text(encoding="utf-8") == "x = 1\n"
    assert "agent-edit-atomic" not in _branches(root)


def test_edit_japanese_lf_byte_exact(tmp_path):
    root = _make_repo(tmp_path)
    original = "タイトル = '挨拶'\n本文 = 'こんにちは、世界'\n"
    (root / "mod.py").write_bytes(original.encode("utf-8"))
    reply = _reply(_edit_block(
        "mod.py", "本文 = 'こんにちは、世界'", "本文 = 'さようなら、世界'"
    ))
    code = pe.apply_edit_reply(
        reply, root, branch_name="agent-edit-jp",
        check_runner=_no_failures, output_fn=lambda _m: None,
    )
    assert code == 0
    expected = "タイトル = '挨拶'\n本文 = 'さようなら、世界'\n"
    assert (root / "mod.py").read_bytes() == expected.encode("utf-8")


def test_edit_japanese_crlf_preserved_byte_exact(tmp_path):
    root = _make_repo(tmp_path)
    original = "タイトル = '挨拶'\r\n本文 = 'こんにちは、世界'\r\n"
    (root / "mod.py").write_bytes(original.encode("utf-8"))
    # The reply arrives LF-normalized (copied from an LF bundle).
    reply = _reply(_edit_block(
        "mod.py", "本文 = 'こんにちは、世界'", "本文 = 'さようなら、世界'"
    ))
    code = pe.apply_edit_reply(
        reply, root, branch_name="agent-edit-crlf",
        check_runner=_no_failures, output_fn=lambda _m: None,
    )
    assert code == 0
    expected = "タイトル = '挨拶'\r\n本文 = 'さようなら、世界'\r\n"
    data = (root / "mod.py").read_bytes()
    assert data == expected.encode("utf-8")
    assert data.count(b"\n") == data.count(b"\r\n")  # no bare LF


def test_edit_missing_end_marker_rejected(tmp_path):
    root = _make_repo(tmp_path)
    reply = _edit_block("mod.py", "    return a - b", FIXED_LINE)
    code = pe.apply_edit_reply(
        reply, root, branch_name="agent-edit-trunc",
        check_runner=_no_failures, output_fn=lambda _m: None,
    )
    assert code == 1
    assert (root / "mod.py").read_text(encoding="utf-8") == BUGGY_MOD
    assert "agent-edit-trunc" not in _branches(root)


def test_edit_tests_dir_rejected_without_flag(tmp_path):
    root = _make_repo(tmp_path)
    (root / "tests").mkdir()
    (root / "tests" / "t.py").write_text("y = 1\n", encoding="utf-8")
    reply = _reply(_edit_block("tests/t.py", "y = 1", "y = 2"))
    code = pe.apply_edit_reply(
        reply, root, branch_name="agent-edit-guard",
        check_runner=_no_failures, output_fn=lambda _m: None,
    )
    assert code == 1
    assert (root / "tests" / "t.py").read_text(encoding="utf-8") == "y = 1\n"


def test_edit_elision_in_replace_rejected(tmp_path):
    root = _make_repo(tmp_path)
    reply = _reply(_edit_block(
        "mod.py", "    return a - b",
        "    return a + b  # rest of the file unchanged",
    ))
    outputs: list = []
    code = pe.apply_edit_reply(
        reply, root, branch_name="agent-edit-elision",
        check_runner=_no_failures, output_fn=outputs.append,
    )
    assert code == 1
    assert "elision" in "\n".join(outputs)
    assert (root / "mod.py").read_text(encoding="utf-8") == BUGGY_MOD


def test_edit_empty_search_and_missing_file_rejected(tmp_path):
    root = _make_repo(tmp_path)
    empty = _reply(_edit_block("mod.py", "", "x = 1"))
    assert pe.apply_edit_reply(
        empty, root, branch_name="b1", check_runner=_no_failures,
        output_fn=lambda _m: None,
    ) == 1
    missing = _reply(_edit_block("nope.py", "x = 1", "x = 2"))
    assert pe.apply_edit_reply(
        missing, root, branch_name="b2", check_runner=_no_failures,
        output_fn=lambda _m: None,
    ) == 1
    assert "b1" not in _branches(root)
    assert "b2" not in _branches(root)


def test_pack_bundle_edit_mode_format():
    files = [("mod.py", BUGGY_MOD)]
    bundle_edit = pa.build_pack_bundle("t", files, "rules", mode="edit")
    assert "<<<<<<< SEARCH" in bundle_edit
    assert ">>>>>>> REPLACE" in bundle_edit
    assert "COMPLETE new content" not in bundle_edit
    bundle_full = pa.build_pack_bundle("t", files, "rules")
    assert "<<<<<<< SEARCH" not in bundle_full
    assert "COMPLETE new content" in bundle_full
    with pytest.raises(ValueError):
        pa.build_pack_bundle("t", files, "rules", mode="bogus")


def test_cmd_pack_hint_for_large_files(tmp_path, monkeypatch, capsys):
    root = _make_repo(tmp_path)
    (root / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
    (root / "big.py").write_text(
        "".join(f"line {i}\n" for i in range(401)), encoding="utf-8"
    )
    monkeypatch.chdir(root)
    pa.cmd_pack(["--task", "t", "--files", "big.py"])
    captured = capsys.readouterr()
    assert "--mode edit" in captured.err
    pa.cmd_pack(["--task", "t", "--files", "big.py", "--mode", "edit"])
    captured = capsys.readouterr()
    assert "<<<<<<< SEARCH" in captured.out
    assert "--mode edit" not in captured.err


# --- WP4 follow-ups: CodeRabbit data-integrity threads ----------------------


def test_edit_overlapping_matches_rejected(tmp_path):
    root = _make_repo(tmp_path)
    (root / "mod.py").write_text("pass\npass\npass\n", encoding="utf-8")
    # "pass\npass" occurs at two overlapping offsets; str.count says 1.
    reply = _reply(_edit_block("mod.py", "pass\npass", "done"))
    outputs: list = []
    code = pe.apply_edit_reply(
        reply, root, branch_name="agent-edit-overlap",
        check_runner=_no_failures, output_fn=outputs.append,
    )
    assert code == 1
    assert "matches 2 places" in "\n".join(outputs)
    assert (root / "mod.py").read_text(encoding="utf-8") == (
        "pass\npass\npass\n"
    )
    assert "agent-edit-overlap" not in _branches(root)


def test_edit_same_file_via_different_path_spellings(tmp_path):
    root = _make_repo(tmp_path)
    reply = _reply(
        _edit_block("mod.py", "    return a - b", FIXED_LINE),
        _edit_block("./mod.py", "def add(a, b):", "def add(a, b):  # fixed"),
    )
    code = pe.apply_edit_reply(
        reply, root, branch_name="agent-edit-canon",
        check_runner=_no_failures, output_fn=lambda _m: None,
    )
    assert code == 0
    # Both edits are present; neither was silently overwritten.
    assert (root / "mod.py").read_text(encoding="utf-8") == (
        "def add(a, b):  # fixed\n    return a + b\n"
    )


def test_edit_mixed_eol_untouched_lines_preserved(tmp_path):
    root = _make_repo(tmp_path)
    (root / "mod.py").write_bytes(b"x = 1\r\ny = 2\n")
    reply = _reply(_edit_block("mod.py", "x = 1", "x = 9"))
    code = pe.apply_edit_reply(
        reply, root, branch_name="agent-edit-mixed",
        check_runner=_no_failures, output_fn=lambda _m: None,
    )
    assert code == 0
    # The edited line takes the local CRLF; the untouched LF line
    # keeps its LF — no whole-file ending conversion.
    assert (root / "mod.py").read_bytes() == b"x = 9\r\ny = 2\n"


def test_edit_unicode_line_separator_preserved(tmp_path):
    root = _make_repo(tmp_path)
    # Byte-exact fixture: write_text would translate \n to \r\n on
    # Windows and change what the byte assertion below can expect.
    (root / "mod.py").write_bytes(b's = "a"\n')
    reply = _reply(_edit_block("mod.py", 's = "a"', 's = "a\u2028b"'))
    code = pe.apply_edit_reply(
        reply, root, branch_name="agent-edit-u2028",
        check_runner=_no_failures, output_fn=lambda _m: None,
    )
    assert code == 0
    assert (root / "mod.py").read_bytes() == 's = "a\u2028b"\n'.encode(
        "utf-8"
    )
