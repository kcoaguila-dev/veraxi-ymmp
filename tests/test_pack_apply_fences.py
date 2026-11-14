"""WP1: fence-robust reply parsing for pack/apply.

Fences are built from FENCE/FENCE4 variables so this test file itself
contains no literal fence lines and can round-trip like any other file.
"""

import subprocess
from pathlib import Path

import veraxi_ymmp.app.pack_apply as pa

FENCE = "`" * 3
FENCE4 = "`" * 4

REPO_ROOT = Path(__file__).resolve().parents[1]

DOC_WITH_JSON_FENCE = (
    "# Doc\n\n"
    + FENCE + "json\n"
    + '{"a": 1}\n'
    + FENCE + "\n\n"
    + "trailing text after the inner fence\n"
)


def _reply(path: str, fence: str, lang: str, content: str) -> str:
    return (
        f"### File: `{path}`\n"
        f"{fence}{lang}\n"
        f"{content}"
        f"{fence}\n"
        f"{pa.END_MARKER}\n"
    )


def test_four_backtick_block_with_inner_json_fence_round_trips():
    parsed = pa.parse_reply(
        _reply("doc.md", FENCE4, "markdown", DOC_WITH_JSON_FENCE)
    )
    assert parsed.complete, parsed.problem
    assert parsed.blocks == [("doc.md", DOC_WITH_JSON_FENCE)]


def test_three_backtick_outer_with_tagged_inner_fence_uses_depth_tracking():
    parsed = pa.parse_reply(
        _reply("doc.md", FENCE, "markdown", DOC_WITH_JSON_FENCE)
    )
    assert parsed.complete, parsed.problem
    assert parsed.blocks == [("doc.md", DOC_WITH_JSON_FENCE)]


def test_premature_close_from_bare_inner_fence_is_rejected_as_stray():
    content = (
        "line one\n"
        + FENCE + "\n"
        + "inner code\n"
        + FENCE + "\n"
        + "line after the inner fence\n"
    )
    parsed = pa.parse_reply(_reply("doc.md", FENCE, "markdown", content))
    assert not parsed.complete
    assert parsed.problem == (
        "stray code fence after block for doc.md; "
        "nested fences likely broke the block"
    )


def test_premature_close_reply_applies_nothing(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    for args in (
        ["init", "-q"],
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "Test"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True,
                       stdin=subprocess.DEVNULL, capture_output=True)
    (root / "doc.md").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True,
                   stdin=subprocess.DEVNULL, capture_output=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "init"],
                   check=True, stdin=subprocess.DEVNULL, capture_output=True)

    content = "line one\n" + FENCE + "\ninner\n" + FENCE + "\nafter\n"
    code = pa.apply_reply(
        _reply("doc.md", FENCE, "markdown", content), root,
        branch_name="agent-apply-fence-test",
        check_runner=lambda changed, test_path, root_: [],
        output_fn=lambda _m: None,
    )
    assert code == 1
    assert (root / "doc.md").read_text(encoding="utf-8") == "original\n"
    branches = subprocess.run(
        ["git", "-C", str(root), "branch"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
    ).stdout
    assert "agent-apply-fence-test" not in branches


def test_reply_wrapped_in_one_outer_fence_parses():
    inner = _reply("mod.py", FENCE, "python", "x = 1\n")
    wrapped = f"{FENCE4}markdown\n{inner}{FENCE4}\n"
    parsed = pa.parse_reply(wrapped)
    assert parsed.complete, parsed.problem
    assert parsed.blocks == [("mod.py", "x = 1\n")]

    # A shorter fence after the wrapper content is not a valid
    # wrapper closer: the reply now fails closed as an unclosed
    # wrapper instead of parsing as if it were never wrapped.
    parsed = pa.parse_reply(wrapped + FENCE + "\n")
    assert not parsed.complete
    assert "wrapper" in parsed.problem

    # Without a wrapper opening fence, a fence after the end marker
    # is still rejected (the original safety net is unchanged).
    parsed = pa.parse_reply(inner + FENCE4 + "\n")
    assert not parsed.complete
    assert "stray code fence" in parsed.problem


def _make_git_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for args in (
        ["init", "-q"],
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "Test"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True,
                       stdin=subprocess.DEVNULL, capture_output=True)
    (root / "doc.md").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True,
                   stdin=subprocess.DEVNULL, capture_output=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "init"],
                   check=True, stdin=subprocess.DEVNULL, capture_output=True)
    return root


def _assert_apply_writes_nothing(tmp_path: Path, reply: str) -> None:
    parsed = pa.parse_reply(reply)
    assert not parsed.complete
    assert "wrapper" in parsed.problem
    root = _make_git_repo(tmp_path)
    code = pa.apply_reply(
        reply, root, branch_name="agent-apply-wrapper-fail",
        check_runner=lambda changed, test_path, root_: [],
        output_fn=lambda _m: None,
    )
    assert code == 1
    assert (root / "doc.md").read_text(encoding="utf-8") == "original\n"
    branches = subprocess.run(
        ["git", "-C", str(root), "branch"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
    ).stdout
    assert "agent-apply-wrapper-fail" not in branches


def test_apply_reply_unclosed_wrapper_rejected(tmp_path):
    # Opens with a wrapper fence, contains a valid block and the end
    # marker, but never closes the wrapper: fail closed.
    reply = f"{FENCE4}markdown\n" + _reply(
        "doc.md", FENCE, "markdown", "new content\n"
    )
    parsed = pa.parse_reply(reply)
    assert not parsed.complete
    assert parsed.problem == "unclosed wrapper code fence"
    _assert_apply_writes_nothing(tmp_path, reply)


def test_apply_reply_unmatched_wrapper_closer_rejected(tmp_path):
    # The closing fence is shorter than the wrapper opening fence.
    reply = (
        f"{FENCE4}markdown\n"
        + _reply("doc.md", FENCE, "markdown", "new content\n")
        + f"{FENCE}\n"
    )
    _assert_apply_writes_nothing(tmp_path, reply)


def test_apply_reply_tagged_wrapper_closer_rejected(tmp_path):
    # A tagged line is not a bare closing fence for the wrapper.
    reply = (
        f"{FENCE4}markdown\n"
        + _reply("doc.md", FENCE, "markdown", "new content\n")
        + f"{FENCE4}markdown\n"
    )
    _assert_apply_writes_nothing(tmp_path, reply)


def test_failing_tests_section_uses_fence_longer_than_its_output():
    test_output = "FAILED x\n" + FENCE + "\nconfusing fence line in output\n"
    bundle = pa.build_pack_bundle(
        "task", [("mod.py", "x = 1\n")], "# rules",
        test_path="tests/test_mod.py", test_output=test_output,
    )
    assert f"{FENCE4}text" in bundle


def test_unmatched_shorter_tagged_fence_is_plain_content():
    # A lone ```python line inside a 4-backtick block can never close
    # the block; it must not pollute the fence stack either, or the
    # real 4-backtick closer pops the wrong level and the block is
    # falsely reported unclosed.
    content = "doc line\n" + FENCE + "python\ncode line\n"
    parsed = pa.parse_reply(_reply("doc.md", FENCE4, "markdown", content))
    assert parsed.complete, parsed.problem
    assert parsed.blocks == [("doc.md", content)]


def test_wrapper_with_premature_close_and_inner_end_marker_is_rejected(tmp_path):
    # The file body itself contains a bare 4-backtick line and an
    # END_MARKER line, with more body after them. Envelope unwrapping
    # must not let the inner end marker + real closer pass as a
    # complete reply with a truncated file.
    body = (
        "keep line\n" + FENCE4 + "\n" + pa.END_MARKER + "\nlost line\n"
    )
    wrapped = (
        f"{FENCE4}markdown\n"
        + _reply("doc.md", FENCE4, "markdown", body)
        + f"{FENCE4}\n"
    )
    parsed = pa.parse_reply(wrapped)
    assert not parsed.complete
    assert "stray code fence" in parsed.problem

    root = tmp_path / "repo"
    root.mkdir()
    for args in (
        ["init", "-q"],
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "Test"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True,
                       stdin=subprocess.DEVNULL, capture_output=True)
    (root / "doc.md").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True,
                   stdin=subprocess.DEVNULL, capture_output=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "init"],
                   check=True, stdin=subprocess.DEVNULL, capture_output=True)
    code = pa.apply_reply(
        wrapped, root, branch_name="agent-apply-wrapper-test",
        check_runner=lambda changed, test_path, root_: [],
        output_fn=lambda _m: None,
    )
    assert code == 1
    assert (root / "doc.md").read_text(encoding="utf-8") == "original\n"
    branches = subprocess.run(
        ["git", "-C", str(root), "branch"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
    ).stdout
    assert "agent-apply-wrapper-test" not in branches


def test_file_header_line_inside_content_round_trips_via_bundle():
    # Content with a bare 4-backtick line followed by a File header
    # line: build_pack_bundle escalates to a 5-backtick fence, so the
    # header line stays content and the round-trip yields one block.
    fence5 = "`" * 5
    content = "text\n" + FENCE4 + "\n### File: `other.md`\nmore\n"
    bundle = pa.build_pack_bundle("task", [("a.md", content)], "# rules")
    assert f"{fence5}text" in bundle
    start = bundle.index("## Files\n") + len("## Files\n")
    end = bundle.rindex("## Reply Format")
    reply = bundle[start:end].strip("\n") + f"\n{pa.END_MARKER}\n"
    parsed = pa.parse_reply(reply)
    assert parsed.complete, parsed.problem
    assert parsed.blocks == [("a.md", content)]


def test_bundle_round_trip_preserves_multiple_trailing_newlines():
    content = "body\n\n"
    bundle = pa.build_pack_bundle("task", [("note.md", content)], "# rules")
    start = bundle.index("## Files\n") + len("## Files\n")
    end = bundle.rindex("## Reply Format")
    reply = bundle[start:end].strip("\n") + f"\n{pa.END_MARKER}\n"
    parsed = pa.parse_reply(reply)
    assert parsed.complete, parsed.problem
    # Exact equality: no rstrip masking a collapsed trailing newline.
    assert parsed.blocks == [("note.md", content)]
    # Plain files with no backticks are also wrapped in >= 4 backticks.
    plain = pa.build_pack_bundle("task", [("m.py", "x = 1\n")], "# rules")
    assert f"{FENCE4}python" in plain


def test_build_pack_bundle_uses_longer_fence_for_fenced_content():
    bundle = pa.build_pack_bundle(
        "task", [("doc.md", DOC_WITH_JSON_FENCE)], "# rules"
    )
    assert f"{FENCE4}text" in bundle
    # The Reply Format section must require 4-backtick fences.
    reply_format = bundle[bundle.rindex("## Reply Format"):]
    assert "FOUR backticks" in reply_format


def test_pack_bundle_round_trip_over_every_tracked_py_and_md_file():
    proc = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
    )
    tracked = [
        line for line in proc.stdout.splitlines()
        if line.endswith((".py", ".md"))
    ]
    assert tracked, "expected tracked .py/.md files from git ls-files"
    # The templates and README named in the WP are part of this set.
    assert "README.md" in tracked
    assert any(name.endswith(".md") and "templates" in name for name in tracked)

    for rel_path in tracked:
        content = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        bundle = pa.build_pack_bundle(
            "round-trip", [(rel_path, content)], "# rules"
        )
        # Take the Files section as the model's reply would carry it.
        # rindex for the trailing section: a packed file's own content
        # (pack_apply.py) contains the same heading string.
        start = bundle.index("## Files\n") + len("## Files\n")
        end = bundle.rindex("## Reply Format")
        reply = bundle[start:end].strip("\n") + f"\n{pa.END_MARKER}\n"
        parsed = pa.parse_reply(reply)
        assert parsed.complete, f"{rel_path}: {parsed.problem}"
        assert len(parsed.blocks) == 1, rel_path
        got_path, got_content = parsed.blocks[0]
        assert got_path == rel_path
        # Identical modulo one trailing newline (build_pack_bundle
        # rstrips the content's final newline before fencing it).
        assert got_content.rstrip("\n") == content.rstrip("\n"), rel_path
