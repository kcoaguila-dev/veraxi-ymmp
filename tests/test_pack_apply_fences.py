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
                       capture_output=True)
    (root / "doc.md").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "init"],
                   check=True, capture_output=True)

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
        ["git", "-C", str(root), "branch"], capture_output=True, text=True
    ).stdout
    assert "agent-apply-fence-test" not in branches


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
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True
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
