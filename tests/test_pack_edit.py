"""Tests for veraxi_ymmp.app.pack_edit (WP4 anchored edit mode)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import veraxi_ymmp.app.pack_apply as pa
import veraxi_ymmp.app.pack_edit as pe

REPO_ROOT = Path(__file__).resolve().parents[1]

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


def _make_mini_video_project(root: Path) -> Path:
    from veraxi_ymmp.epistemic.fact_audit import compute_file_sha256

    proj = root / "projects" / "10_mini"
    sources = proj / "sources"
    sources.mkdir(parents=True)
    sec_url = "https://www.sec.gov/Archives/edgar/data/0001018724/amzn-20260930.htm"
    src_file = sources / "sec_amzn_10q_q3_2026.md"
    src_file.write_text(
        "Amazon capex reached $85 billion in FY2026. Operating cash flow covered outlays.\n",
        encoding="utf-8",
    )
    digest = compute_file_sha256(src_file)
    (sources / "manifest.json").write_text(
        json.dumps(
            {
                "sec_amzn_10q_q3_2026": {
                    "url": sec_url,
                    "title": "Amazon 10-Q Q3 2026",
                    "sha256": digest,
                    "provenance": "notebooklm_evidence",
                    "primary": True,
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (proj / "evidence.md").write_text(
        "| # | Point of Contention / Claim | Canonical Period / Scope | "
        "Verbatim Quote Refuting or Explaining | Source Doc & Exact Section/Page | "
        "Root Cause / Hard Metric |\n"
        "|---|---|---|---|---|---|\n"
        f"| 1 | 設備投資が850億ドルに達した | 2026-Q3 | "
        f"Amazon capex reached $85 billion in FY2026. | {sec_url} p.12 | "
        "$85B (850億ドル) |\n",
        encoding="utf-8",
    )

    def _c(char: str, text: str, emo: str = "normal", img: str | None = None) -> dict:
        pos = "left" if char == "四国めたん" else "right"
        return {
            "character": char,
            "character_position": pos,
            "text": text,
            "emotion": emo,
            "motion": "none",
            "bgm": None,
            "sfx": None,
            "image": img,
        }

    script = [
        _c("ずんだもん", "巨額投資があれば必ず儲かるのだ！", "excited", None),
        _c("四国めたん", "甘い幻想ですわ。設備投資は850億ドルですわ。", "smug", None),
        _c("ずんだもん", "えっ！？", "surprised", None),
        _c("四国めたん", "この巨額出費が利益を圧迫する現実ですわ。", "normal", "broll/slide_01.png"),
        _c("ずんだもん", "850億ドルって一体どれほどの負担なのだ？", "confused", "broll/slide_01.png"),
        _c("四国めたん", "償却費が雪だるま式に膨らみ続けますわ。", "normal", "broll/slide_01.png"),
        _c("春日部つむぎ", "現場のインフラでも負担が増えてるっす！", "angry", None),
        _c("ずんだもん", "マジで！？", "surprised", None),
        _c("四国めたん", "しかも設備の稼働率が追いついていませんわ。", "angry", "broll/slide_02.png"),
        _c("春日部つむぎ", "運用コストが現場を直撃してるっすよ。", "sad", "broll/slide_02.png"),
        _c("四国めたん", "投資を急ぐあまり回収が遅れていますの。", "normal", "broll/slide_02.png"),
        _c("ずんだもん", "技術も予算も限界スレスレだったのだ…", "sad", None),
        _c("四国めたん", "一次資料を直視しない企業から脱落しますわ。", "smug", None),
        _c("春日部つむぎ", "現場の負荷を見落とすと取り返しがつかないっす。", "normal", None),
        _c("四国めたん", "結局は資金規律を保てるかどうかの勝負ですわ。", "normal", None),
        _c("ずんだもん", "財務の現実から目を背けちゃダメなのだ。", "normal", None),
    ]
    (proj / "script.json").write_text(
        json.dumps(script, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    broll = [
        {
            "type": "clash",
            "filename": "slide_01.png",
            "title": "投資規模の対決",
            "hero_metric": "設備投資850億ドル",
            "left": {"name": "市場予想", "metric": "楽観視", "sub": "即回収想定", "color": "amber"},
            "right": {"name": "一次資料", "metric": "850億ドル", "sub": "現金流出増", "color": "blue"},
            "impact_tag": "現実",
            "impact_text": "償却負担が利益を直撃",
            "theme_color": "amber",
        },
        {
            "type": "domino",
            "filename": "slide_02.png",
            "title": "巨額投資の連鎖",
            "stages": [
                {"num": "01", "title": "巨額投資", "sub": "850億ドル支出", "color": "amber"},
                {"num": "02", "title": "償却急増", "sub": "固定費が重荷", "color": "amber"},
                {"num": "03", "title": "利益圧縮", "sub": "粗利率が低下", "color": "red"},
                {"num": "04", "title": "回収遅延", "sub": "警戒感が拡大", "color": "red"},
            ],
            "bottom_text": "投資回収の壁が立ち塞がる",
            "theme_color": "red",
        },
    ]
    (proj / "broll_manifest.json").write_text(
        json.dumps(broll, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    ev = [
        {
            "url": sec_url,
            "quote": "Amazon capex reached $85 billion in FY2026.",
            "stance": "confirms",
            "tier": 1,
            "source_id": "sec_amzn_10q_q3_2026",
            "sha256": digest,
        }
    ]
    claims = [
        {
            "id": "c01",
            "cut_index": 1,
            "text": "甘い幻想ですわ。設備投資は850億ドルですわ。",
            "kind": "number",
            "weight": "central",
            "evidence": ev,
        },
        {
            "id": "c02",
            "cut_index": 4,
            "text": "850億ドルって一体どれほどの負担なのだ？",
            "kind": "number",
            "weight": "minor",
            "evidence": ev,
        },
    ]
    (proj / "claims.json").write_text(
        json.dumps(claims, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return proj


def test_apply_edit_in_place_skips_branch_creation(tmp_path):
    root = _make_repo(tmp_path)
    before_branches = _branches(root)
    reply = _reply(_edit_block("mod.py", "    return a - b", FIXED_LINE))
    code = pe.apply_edit_reply(
        reply, root, in_place=True, check_runner=_no_failures, output_fn=lambda _m: None
    )
    assert code == 0
    assert (root / "mod.py").read_text(encoding="utf-8") == (
        "def add(a, b):\n    return a + b\n"
    )
    assert _branches(root) == before_branches


def test_project_edit_reconciles_claims_on_cut_insert_and_reword(tmp_path):
    from veraxi_ymmp.epistemic.fact_audit import audit_project_facts

    root = _make_repo(tmp_path)
    proj = _make_mini_video_project(root)
    before_branches = _branches(root)

    script_rel = "projects/10_mini/script.json"
    broll_rel = "projects/10_mini/broll_manifest.json"
    old_c1 = '    "text": "甘い幻想ですわ。設備投資は850億ドルですわ。",'
    new_c1 = '    "text": "夢を見すぎですわ。設備投資は850億ドルですの。",'
    old_c4 = '  {\n    "character": "ずんだもん",\n    "character_position": "right",\n    "text": "850億ドルって一体どれほどの負担なのだ？",'
    new_c4 = (
        '  {\n    "character": "ずんだもん",\n    "character_position": "right",\n'
        '    "text": "な、なんだってー！？",\n    "emotion": "surprised",\n'
        '    "motion": "none",\n    "bgm": null,\n    "sfx": null,\n'
        '    "image": "broll/slide_01.png"\n  },\n'
        + old_c4
    )
    reply = _reply(
        _edit_block(script_rel, old_c1, new_c1),
        _edit_block(script_rel, old_c4, new_c4),
        _edit_block(broll_rel, '"title": "投資規模の対決"', '"title": "設備投資規模の現実"'),
    )
    outputs: list[str] = []
    code = pe.apply_edit_reply(
        reply, root, in_place=True, check_runner=_no_failures, output_fn=outputs.append
    )
    assert code == 0, "\n".join(outputs)
    assert _branches(root) == before_branches

    updated_claims = json.loads((proj / "claims.json").read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in updated_claims}
    assert by_id["c01"]["cut_index"] == 1
    assert by_id["c01"]["text"] == "夢を見すぎですわ。設備投資は850億ドルですの。"
    assert by_id["c01"]["weight"] == "central"
    assert len(by_id["c01"]["evidence"]) == 1
    assert by_id["c02"]["cut_index"] == 5
    assert len(by_id["c02"]["evidence"]) == 1

    outcome = audit_project_facts(proj / "script.json")
    assert not outcome.blocked, f"Unexpected blockers: {outcome.blockers}"


@pytest.mark.parametrize(
    "search_txt,replace_txt,expected_tag",
    [
        (
            '"text": "この巨額出費が利益を圧迫する現実ですわ。",\n'
            '    "emotion": "normal",\n    "motion": "none",\n'
            '    "bgm": null,\n    "sfx": null,\n'
            '    "image": "broll/slide_01.png"',
            '"text": "この巨額出費が利益を圧迫する現実ですわ。",\n'
            '    "emotion": "normal",\n    "motion": "none",\n'
            '    "bgm": null,\n    "sfx": null,\n'
            '    "image": "broll/nonexistent.png"',
            "[ASSET]",
        ),
        ('"text": "技術も予算も限界スレスレだったのだ…"', '"text": "XYZZQXも限界スレスレだったのだ…"', "Unmapped ASCII"),
        ('"text": "甘い幻想ですわ。設備投資は850億ドルですわ。"', '"text": "甘い幻想ですわ。設備投資は9999億ドルですわ。"', "[FACTS]"),
    ],
)
def test_project_edit_rejects_bad_asset_unmapped_ascii_and_hallucinated_number(
    tmp_path, search_txt, replace_txt, expected_tag
):
    root = _make_repo(tmp_path)
    proj = _make_mini_video_project(root)
    orig_script = (proj / "script.json").read_text(encoding="utf-8")
    orig_claims = (proj / "claims.json").read_text(encoding="utf-8")

    reply = _reply(_edit_block("projects/10_mini/script.json", search_txt, replace_txt))
    outputs: list[str] = []
    code = pe.apply_edit_reply(
        reply, root, in_place=True, check_runner=_no_failures, output_fn=outputs.append
    )
    joined = "\n".join(outputs)
    assert code == 1
    assert "LLM RE-PROMPT BLOCK" in joined
    assert expected_tag in joined
    assert (proj / "script.json").read_text(encoding="utf-8") == orig_script
    assert (proj / "claims.json").read_text(encoding="utf-8") == orig_claims


def test_pack_edit_auto_includes_project_rules_and_fits_video11_budget(
    monkeypatch, capsys
):
    monkeypatch.chdir(REPO_ROOT)
    pa.cmd_pack([
        "--mode", "edit",
        "--task", "Sharpen the cold open hook",
        "--files",
        "projects/11_anthropic_ipo_2026/script.json",
        "projects/11_anthropic_ipo_2026/broll_manifest.json",
        "projects/11_anthropic_ipo_2026/evidence.md",
    ])
    out = capsys.readouterr().out
    assert "Video Project Editing Rules" in out
    assert "`emotion`" in out
    assert "<= 40" in out
    assert "broll_manifest.json" in out
    assert "<<<<<<< SEARCH" in out


def test_video11_staged_edit_reconciles_all_80_claims_cleanly(tmp_path):
    root = _make_repo(tmp_path)
    src_proj = REPO_ROOT / "projects" / "11_anthropic_ipo_2026"
    dst_proj = root / "projects" / "11_anthropic_ipo_2026"
    dst_proj.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_proj, dst_proj)

    search_c1 = (
        '  {\n'
        '    "character": "ずんだもん",\n'
        '    "text": "時価総額２兆ドルでクロード無双なのだ！",'
    )
    replace_c1 = (
        '  {\n'
        '    "character": "ずんだもん",\n'
        '    "text": "ま、まさかなのだ！？",\n'
        '    "emotion": "surprised",\n'
        '    "motion": "none",\n'
        '    "bgm": null,\n'
        '    "sfx": null,\n'
        '    "image": null,\n'
        '    "character_position": "right",\n'
        '    "subtitle_position": "bottom_center",\n'
        '    "subtitle_style": "outlined"\n'
        '  },\n'
        '  {\n'
        '    "character": "ずんだもん",\n'
        '    "text": "時価総額２兆ドルでまさにクロード無双なのだ！",'
    )
    reply = _reply(_edit_block(
        "projects/11_anthropic_ipo_2026/script.json", search_c1, replace_c1
    ))
    outputs: list[str] = []
    code = pe.apply_edit_reply(
        reply, root, in_place=True, check_runner=_no_failures, output_fn=outputs.append
    )
    assert code == 0, "\n".join(outputs)

    updated_claims = json.loads(
        (dst_proj / "claims.json").read_text(encoding="utf-8")
    )
    assert len(updated_claims) == 80
    by_id = {c["id"]: c for c in updated_claims}
    assert by_id["c01"]["cut_index"] == 2
    assert by_id["c01"]["text"] == "時価総額２兆ドルでまさにクロード無双なのだ！"
    assert by_id["c170"]["cut_index"] == 171


def test_video11_edit_rhetorical_negation_and_hook_claim_promotion(tmp_path):
    root = _make_repo(tmp_path)
    src_proj = REPO_ROOT / "projects" / "11_anthropic_ipo_2026"
    dst_proj = root / "projects" / "11_anthropic_ipo_2026"
    dst_proj.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_proj, dst_proj)

    before_sources = sorted(p.name for p in (dst_proj / "sources").iterdir())
    search_c1 = (
        '  {\n'
        '    "character": "ずんだもん",\n'
        '    "text": "時価総額２兆ドルでクロード無双なのだ！",\n'
        '    "emotion": "normal",\n'
        '    "motion": "none",\n'
        '    "bgm": null,\n'
        '    "sfx": null,\n'
        '    "image": null,\n'
        '    "character_position": "right",\n'
        '    "subtitle_position": "bottom_center",\n'
        '    "subtitle_style": "outlined"\n'
        '  },'
    )
    replace_c1 = (
        '  {\n'
        '    "character": "ずんだもん",\n'
        '    "text": "時価総額２兆ドルなんて信じられないのだ！",\n'
        '    "emotion": "surprised",\n'
        '    "motion": "none",\n'
        '    "bgm": null,\n'
        '    "sfx": null,\n'
        '    "image": null,\n'
        '    "character_position": "right",\n'
        '    "subtitle_position": "bottom_center",\n'
        '    "subtitle_style": "outlined"\n'
        '  },\n'
        '  {\n'
        '    "character": "ずんだもん",\n'
        '    "text": "しかも純損失は９４３億ドルでありえないのだ！",\n'
        '    "emotion": "surprised",\n'
        '    "motion": "none",\n'
        '    "bgm": null,\n'
        '    "sfx": null,\n'
        '    "image": null,\n'
        '    "character_position": "right",\n'
        '    "subtitle_position": "bottom_center",\n'
        '    "subtitle_style": "outlined"\n'
        '  },'
    )
    search_c14 = (
        '  {\n'
        '    "character": "ずんだもん",\n'
        '    "text": "中央値の７４ドルでも超大型なのだ！",\n'
        '    "emotion": "normal",\n'
        '    "motion": "none",\n'
        '    "bgm": null,\n'
        '    "sfx": null,\n'
        '    "image": null,\n'
        '    "character_position": "right",\n'
        '    "subtitle_position": "bottom_center",\n'
        '    "subtitle_style": "outlined"\n'
        '  },'
    )
    replace_c14 = (
        search_c14
        + '\n  {\n'
        '    "character": "ずんだもん",\n'
        '    "text": "仮条件の上限は１株７８ドルなのだ！",\n'
        '    "emotion": "normal",\n'
        '    "motion": "none",\n'
        '    "bgm": null,\n'
        '    "sfx": null,\n'
        '    "image": null,\n'
        '    "character_position": "right",\n'
        '    "subtitle_position": "bottom_center",\n'
        '    "subtitle_style": "outlined"\n'
        '  },'
    )
    reply = _reply(
        _edit_block("projects/11_anthropic_ipo_2026/script.json", search_c1, replace_c1),
        _edit_block("projects/11_anthropic_ipo_2026/script.json", search_c14, replace_c14),
    )
    outputs: list[str] = []
    code = pe.apply_edit_reply(
        reply, root, in_place=True, check_runner=_no_failures, output_fn=outputs.append
    )
    assert code == 0, "\n".join(outputs)

    after_sources = sorted(p.name for p in (dst_proj / "sources").iterdir())
    assert after_sources == before_sources
    assert not any(name.endswith("_notebooklm.md") for name in after_sources)

    updated_claims = json.loads(
        (dst_proj / "claims.json").read_text(encoding="utf-8")
    )
    by_text = {c["text"]: c for c in updated_claims}
    hook_943 = by_text["しかも純損失は９４３億ドルでありえないのだ！"]
    assert hook_943["cut_index"] == 2
    assert hook_943["weight"] == "central"
    assert len(hook_943["evidence"]) >= 2

    cut_78 = by_text["仮条件の上限は１株７８ドルなのだ！"]
    assert any(ev.get("source_id") == "anthropic_s1_a" for ev in cut_78["evidence"])


def test_video11_edit_compound_claim_union_and_fact_loss_polarity(tmp_path):
    root = _make_repo(tmp_path)
    src_proj = REPO_ROOT / "projects" / "11_anthropic_ipo_2026"
    dst_proj = root / "projects" / "11_anthropic_ipo_2026"
    dst_proj.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_proj, dst_proj)

    before_sources = sorted(p.name for p in (dst_proj / "sources").iterdir())
    search_c15 = (
        '  {\n'
        '    "character": "四国めたん",\n'
        '    "text": "そして９ヶ月の純損失は１０４０億ドルよ。",\n'
        '    "emotion": "normal",\n'
        '    "motion": "none",\n'
        '    "bgm": null,\n'
        '    "sfx": null,\n'
        '    "image": null,\n'
        '    "character_position": "left",\n'
        '    "subtitle_position": "bottom_center",\n'
        '    "subtitle_style": "outlined"\n'
        '  },'
    )
    replace_c15 = (
        '  {\n'
        '    "character": "四国めたん",\n'
        '    "text": "事実、９ヶ月の純損失は１０４０億ドルよ。",\n'
        '    "emotion": "normal",\n'
        '    "motion": "none",\n'
        '    "bgm": null,\n'
        '    "sfx": null,\n'
        '    "image": null,\n'
        '    "character_position": "left",\n'
        '    "subtitle_position": "bottom_center",\n'
        '    "subtitle_style": "outlined"\n'
        '  },\n'
        '  {\n'
        '    "character": "ずんだもん",\n'
        '    "text": "売上３３２億ドルでも評価損は９４３億ドルなのだ！",\n'
        '    "emotion": "surprised",\n'
        '    "motion": "none",\n'
        '    "bgm": null,\n'
        '    "sfx": null,\n'
        '    "image": null,\n'
        '    "character_position": "right",\n'
        '    "subtitle_position": "bottom_center",\n'
        '    "subtitle_style": "outlined"\n'
        '  },'
    )
    reply = _reply(_edit_block(
        "projects/11_anthropic_ipo_2026/script.json", search_c15, replace_c15
    ))
    outputs: list[str] = []
    code = pe.apply_edit_reply(
        reply, root, in_place=True, check_runner=_no_failures, output_fn=outputs.append
    )
    assert code == 0, "\n".join(outputs)

    after_sources = sorted(p.name for p in (dst_proj / "sources").iterdir())
    assert after_sources == before_sources
    assert not any(name.endswith("_notebooklm.md") for name in after_sources)

    updated_claims = json.loads(
        (dst_proj / "claims.json").read_text(encoding="utf-8")
    )
    by_text = {c["text"]: c for c in updated_claims}
    assert "事実、９ヶ月の純損失は１０４０億ドルよ。" in by_text

    compound = by_text["売上３３２億ドルでも評価損は９４３億ドルなのだ！"]
    assert len(compound["evidence"]) >= 2
    merged_quotes = " ".join(ev.get("quote", "") for ev in compound["evidence"])
    assert "332億ドル" in merged_quotes
    assert "943億ドル" in merged_quotes


def test_video11_edit_synthesizes_derived_arithmetic_claim(tmp_path):
    root = _make_repo(tmp_path)
    src_proj = REPO_ROOT / "projects" / "11_anthropic_ipo_2026"
    dst_proj = root / "projects" / "11_anthropic_ipo_2026"
    dst_proj.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_proj, dst_proj)

    search_c24 = (
        '  {\n'
        '    "character": "四国めたん",\n'
        '    "text": "サブスクリプションが６９億ドルよ。",\n'
        '    "emotion": "normal",\n'
        '    "motion": "none",\n'
        '    "bgm": null,\n'
        '    "sfx": null,\n'
        '    "image": null,\n'
        '    "character_position": "left",\n'
        '    "subtitle_position": "bottom_center",\n'
        '    "subtitle_style": "outlined"\n'
        '  },'
    )
    replace_c24 = (
        search_c24
        + '\n  {\n'
        '    "character": "ずんだもん",\n'
        '    "text": "従量課金とサブスクの差は１９４億ドルなのだ！",\n'
        '    "emotion": "surprised",\n'
        '    "motion": "none",\n'
        '    "bgm": null,\n'
        '    "sfx": null,\n'
        '    "image": null,\n'
        '    "character_position": "right",\n'
        '    "subtitle_position": "bottom_center",\n'
        '    "subtitle_style": "outlined"\n'
        '  },'
    )
    reply = _reply(_edit_block(
        "projects/11_anthropic_ipo_2026/script.json", search_c24, replace_c24
    ))
    outputs: list[str] = []
    code = pe.apply_edit_reply(
        reply, root, in_place=True, check_runner=_no_failures, output_fn=outputs.append
    )
    assert code == 0, "\n".join(outputs)

    updated_claims = json.loads(
        (dst_proj / "claims.json").read_text(encoding="utf-8")
    )
    by_text = {c["text"]: c for c in updated_claims}
    derived_cl = by_text["従量課金とサブスクの差は１９４億ドルなのだ！"]
    assert derived_cl["derived"] is True
    assert derived_cl["derivation"] == "263億ドル - 69億ドル = 194億ドル"
    assert derived_cl["weight"] == "minor"
    assert any(ev.get("source_id") == "anthropic_s1_a" for ev in derived_cl["evidence"])


def test_bilingual_sec_entity_aliases_ground_raw_english_quotes():
    from veraxi_ymmp.epistemic.facts import compute_deterministic_grounding

    raw_quote = (
        "Consumption-based token revenue was $26,306 million, subscription revenue was $6,936 million. "
        "Net cash provided by operating activities was $6,569 million. "
        "Loss from change in fair value of convertible notes was $94,300 million."
    )
    assert compute_deterministic_grounding("転換社債の評価替えで評価損が出た。", raw_quote) > 0.0
    assert compute_deterministic_grounding("従量課金とサブスクリプションの差は大きい。", raw_quote) > 0.0
    assert compute_deterministic_grounding(
        "営業キャッシュフローが黒字です。",
        "Net cash provided by operating activities was $6,569 million.",
    ) > 0.0
    assert compute_deterministic_grounding("営業キャッシュフローは６５億ドルです。", raw_quote) > 0.0
    assert compute_deterministic_grounding(
        "売出規模と仮条件を確認する。",
        "An aggregate offering of 825,000,000 shares at an initial public offering price midpoint.",
    ) > 0.0


def test_single_primary_authority_hook_promotion_passes_fact_audit(tmp_path):
    import hashlib
    from veraxi_ymmp.app.project_gate import validate_and_reconcile_staged_project
    from veraxi_ymmp.epistemic.fact_audit import audit_project_facts

    proj = tmp_path / "single_sec_proj"
    sources_dir = proj / "sources"
    sources_dir.mkdir(parents=True)
    sec_text = (
        "Consumption-based token revenue was $26,306 million, subscription revenue was $6,936 million. "
        "Net cash provided by operating activities was $6,569 million. "
        "Loss from change in fair value of convertible notes was $94,300 million."
    )
    sec_path = sources_dir / "anthropic_s1_a.txt"
    sec_path.write_text(sec_text, encoding="utf-8")
    sec_sha = hashlib.sha256(sec_text.encode("utf-8")).hexdigest()
    sec_url = "https://www.sec.gov/Archives/edgar/data/0001991288/000119312526000001/anthropic-s1a.htm"
    (sources_dir / "manifest.json").write_text(
        json.dumps({"anthropic_s1_a": {"url": sec_url, "sha256": sec_sha}}),
        encoding="utf-8",
    )

    # 16 cuts meeting pacing rules (no Tsumugi in cuts 0-2, slides from cut 3+, 50/30/20-like mix)
    def _cut(char: str, text: str, img=None):
        return {
            "character": char,
            "character_position": "left" if char == "四国めたん" else "right",
            "text": text,
            "emotion": "normal",
            "motion": "none",
            "bgm": None,
            "sfx": None,
            "image": img,
        }

    script_entries = [
        _cut("ずんだもん", "大赤字の裏側を見るのだ！"),
        _cut("四国めたん", "転換社債の評価損が９４３億ドルですわ。"),
        _cut("ずんだもん", "えっ！？"),
        _cut("四国めたん", "評価替えによる会計上の損失ですわ。", "broll/slide_01.png"),
        _cut("ずんだもん", "どういうことなのだ？", "broll/slide_01.png"),
        _cut("四国めたん", "従量課金が２６３億ドルありますの。", "broll/slide_01.png"),
        _cut("春日部つむぎ", "サブスクリプションは６９億ドルっすよ。", "broll/slide_01.png"),
        _cut("ずんだもん", "しかも本業ではしっかり稼いでいるのだ！"),
        _cut("四国めたん", "営業キャッシュフローは６５億ドルですわ。"),
        _cut("ずんだもん", "ほんとなのだ！？"),
        _cut("四国めたん", "現金を生み出す本業は堅調ですの。"),
        _cut("春日部つむぎ", "数字の仕組みがわかってきたっす！"),
        _cut("ずんだもん", "従量課金とサブスクの差は１９４億ドルなのだ！"),
        _cut("四国めたん", "一次資料の数値は裏切りませんわ。"),
        _cut("春日部つむぎ", "みんなも決算書を読むっす！"),
        _cut("ずんだもん", "最後まで見てくれてありがとうなのだ。"),
    ]

    initial_claims = [
        {
            "id": "c01",
            "cut_index": 5,
            "text": "従量課金が２６３億ドルありますの。",
            "kind": "number",
            "weight": "minor",
            "evidence": [{
                "url": sec_url,
                "quote": "Consumption-based token revenue was $26,306 million, subscription revenue was $6,936 million.",
                "stance": "confirms",
                "tier": 1,
                "source_id": "anthropic_s1_a",
                "sha256": sec_sha,
            }],
        },
        {
            "id": "c02",
            "cut_index": 6,
            "text": "サブスクリプションは６９億ドルっすよ。",
            "kind": "number",
            "weight": "minor",
            "evidence": [{
                "url": sec_url,
                "quote": "Consumption-based token revenue was $26,306 million, subscription revenue was $6,936 million.",
                "stance": "confirms",
                "tier": 1,
                "source_id": "anthropic_s1_a",
                "sha256": sec_sha,
            }],
        },
        {
            "id": "c03",
            "cut_index": 1,
            "text": "転換社債の評価損が９４３億ドルですわ。",
            "kind": "number",
            "weight": "minor",
            "evidence": [{
                "url": sec_url,
                "quote": "Loss from change in fair value of convertible notes was $94,300 million.",
                "stance": "confirms",
                "tier": 1,
                "source_id": "anthropic_s1_a",
                "sha256": sec_sha,
            }],
        },
        {
            "id": "c04",
            "cut_index": 8,
            "text": "営業キャッシュフローは６５億ドルですわ。",
            "kind": "number",
            "weight": "minor",
            "evidence": [{
                "url": sec_url,
                "quote": "Net cash provided by operating activities was $6,569 million.",
                "stance": "confirms",
                "tier": 1,
                "source_id": "anthropic_s1_a",
                "sha256": sec_sha,
            }],
        },
    ]
    broll_manifest = [
        {
            "type": "metric",
            "filename": "broll/slide_01.png",
            "title": "売上内訳",
            "hero_metric": "263億ドル",
            "theme_color": "blue",
        }
    ]
    (proj / "script.json").write_text(json.dumps(script_entries, ensure_ascii=False, indent=2), encoding="utf-8")
    (proj / "broll_manifest.json").write_text(json.dumps(broll_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (proj / "claims.json").write_text(json.dumps(initial_claims, ensure_ascii=False, indent=2), encoding="utf-8")

    staged = {"script.json": json.dumps(script_entries, ensure_ascii=False, indent=2)}
    reconciled_json, errors = validate_and_reconcile_staged_project(proj, staged, strict_facts=True)
    assert errors == [], f"Unexpected errors: {errors}"
    assert reconciled_json is not None

    reconciled = json.loads(reconciled_json)
    by_text = {c["text"]: c for c in reconciled}
    assert by_text["転換社債の評価損が９４３億ドルですわ。"]["weight"] == "central"
    assert by_text["従量課金とサブスクの差は１９４億ドルなのだ！"]["derived"] is True

    (proj / "claims.json").write_text(reconciled_json, encoding="utf-8")
    outcome = audit_project_facts(proj / "script.json")
    assert not outcome.blocked, f"Unexpected blockers: {outcome.blockers}"


def test_editorial_reconcile_module_line_bounds():
    root = Path(__file__).resolve().parent.parent / "veraxi_ymmp" / "editorial"
    nb_lines = len((root / "notebooklm_verify.py").read_text(encoding="utf-8").splitlines())
    si_lines = len((root / "script_ingest.py").read_text(encoding="utf-8").splitlines())
    cr_lines = len((root / "claim_reconcile.py").read_text(encoding="utf-8").splitlines())
    assert nb_lines < 750, f"notebooklm_verify.py too long: {nb_lines}"
    assert si_lines < 750, f"script_ingest.py too long: {si_lines}"
    assert 100 <= cr_lines <= 900, f"claim_reconcile.py out of bounds: {cr_lines}"


def test_positive_cash_flow_not_poisoned_by_header_net_loss(tmp_path: Path):
    from veraxi_ymmp.epistemic.fact_audit import audit_project_facts, compute_file_sha256
    from veraxi_ymmp.epistemic.facts import compute_deterministic_grounding

    # Direct grounding check when multi-sentence context includes an unrelated loss clause
    score = compute_deterministic_grounding(
        "営業キャッシュフローは６５億ドルの黒字よ。",
        "GAAP Net Loss was $(104,039) million. Net cash provided by operating activities was $6,569 million.",
    )
    assert score > 0.0

    # End-to-end audit_project_facts check with "Net Loss" in the first 400 chars of source
    proj = tmp_path / "projects" / "pos_cash"
    sources = proj / "sources"
    sources.mkdir(parents=True)
    sec_url = "https://www.sec.gov/Archives/edgar/data/0001234567/filing.htm"
    src_file = sources / "sec_filing.md"
    src_file.write_text(
        "FORM S-1 SUMMARY\nGAAP Net Loss was $(104,039) million for the period.\n"
        + ("Filler line.\n" * 10)
        + "Net cash provided by operating activities was $6,569 million.\n",
        encoding="utf-8",
    )
    sec_sha = compute_file_sha256(src_file)
    (sources / "manifest.json").write_text(
        json.dumps({
            "sec_filing": {"url": sec_url, "title": "Filing", "sha256": sec_sha, "provenance": "notebooklm_evidence", "primary": True}
        }),
        encoding="utf-8",
    )
    script_entries = [{"cut_index": 0, "character": "四国めたん", "text": "営業キャッシュフローは６５億ドルの黒字よ。"}]
    claims = [{
        "id": "c01",
        "cut_index": 0,
        "text": "営業キャッシュフローは６５億ドルの黒字よ。",
        "kind": "number",
        "weight": "minor",
        "evidence": [{
            "url": sec_url,
            "quote": "Net cash provided by operating activities was $6,569 million.",
            "stance": "confirms",
            "tier": 1,
            "source_id": "sec_filing",
            "sha256": sec_sha,
        }],
    }]
    (proj / "script.json").write_text(json.dumps(script_entries, ensure_ascii=False), encoding="utf-8")
    (proj / "claims.json").write_text(json.dumps(claims, ensure_ascii=False), encoding="utf-8")

    outcome = audit_project_facts(proj / "script.json")
    assert not outcome.blocked, f"Unexpected blockers: {outcome.blockers}"


def test_compound_japanese_multi_unit_numbers_ground_raw_english(tmp_path: Path):
    from veraxi_ymmp.epistemic.fact_audit import audit_project_facts, compute_file_sha256
    from veraxi_ymmp.epistemic.facts import Claim, ClaimKind, ClaimWeight, Evidence, Stance, check_claim_numbers

    cases = [
        ("売出規模は８億２５００万株。", "825,000,000 shares"),
        ("本業の営業損失はわずか１２億６０００万ドル。", "$(1,260) million"),
        ("本質的価値は１兆４７５０億ドルよ。", "$1.475 trillion"),
    ]
    for idx, (jp_text, en_quote) in enumerate(cases):
        cl = Claim(
            id=f"c{idx}", cut_index=idx, text=jp_text, kind=ClaimKind.NUMBER, weight=ClaimWeight.MINOR,
            evidence=[Evidence(url="https://www.sec.gov/Archives/edgar/1.htm", quote=en_quote, stance=Stance.CONFIRMS, tier=1)],
        )
        assert check_claim_numbers(cl, [en_quote]) == [], f"Failed check_claim_numbers for {jp_text} vs {en_quote}"

    proj = tmp_path / "projects" / "compound_jp"
    sources = proj / "sources"
    sources.mkdir(parents=True)
    sec_url = "https://www.sec.gov/Archives/edgar/data/0001234567/s1.htm"
    src_file = sources / "sec_s1.md"
    src_file.write_text(
        "The offering consists of 825,000,000 shares of common stock.\n"
        "Operating loss was $(1,260) million.\n"
        "Estimated intrinsic value reached $1.475 trillion.\n",
        encoding="utf-8",
    )
    sec_sha = compute_file_sha256(src_file)
    (sources / "manifest.json").write_text(
        json.dumps({"sec_s1": {"url": sec_url, "title": "S-1", "sha256": sec_sha, "provenance": "notebooklm_evidence", "primary": True}}),
        encoding="utf-8",
    )
    script_entries = [{"cut_index": i, "character": "四国めたん", "text": jp} for i, (jp, _) in enumerate(cases)]
    claims = [
        {
            "id": f"c0{i}",
            "cut_index": i,
            "text": jp,
            "kind": "number",
            "weight": "minor",
            "evidence": [{
                "url": sec_url, "quote": en_q, "stance": "confirms", "tier": 1, "source_id": "sec_s1", "sha256": sec_sha,
            }],
        }
        for i, (jp, en_q) in enumerate(cases)
    ]
    (proj / "script.json").write_text(json.dumps(script_entries, ensure_ascii=False), encoding="utf-8")
    (proj / "claims.json").write_text(json.dumps(claims, ensure_ascii=False), encoding="utf-8")

    outcome = audit_project_facts(proj / "script.json")
    assert not outcome.blocked, f"Unexpected blockers: {outcome.blockers}"


def test_pass4_synthesizes_yoy_percentage_from_quote_operands():
    from veraxi_ymmp.editorial.claim_reconcile import _synthesize_derived_claim_from_pool
    from veraxi_ymmp.epistemic.facts import Claim, ClaimKind, ClaimWeight, Evidence, Stance, check_claim_numbers

    quote = "Revenue was $2,545 million in 2025 and $33,242 million in 2026."
    base_claim = Claim(
        id="c01",
        cut_index=5,
        text="２０２６年の売上高は３３２億ドルですわ。",
        kind=ClaimKind.NUMBER,
        weight=ClaimWeight.MINOR,
        evidence=[Evidence(url="https://www.sec.gov/Archives/edgar/1.htm", quote=quote, stance=Stance.CONFIRMS, tier=1, source_id="s1", sha256="a" * 64)],
    )
    derived = _synthesize_derived_claim_from_pool(
        15,
        "売上高は前年比１２０６％増の驚異的な成長なのだ！",
        "c_edit_015",
        [base_claim],
    )
    assert derived is not None
    assert derived.derived is True
    assert "100" in derived.derivation
    assert check_claim_numbers(derived, [quote]) == []


def test_kanjize_and_word2number_extract_token_magnitudes():
    from veraxi_ymmp.epistemic.epistemic_units import extract_token_magnitudes

    jp_mags = extract_token_magnitudes("時価総額は二兆三千億ドルに達したのだ。")
    assert any(abs(v - 2.3e12) < 1.0 for vals in jp_mags.values() for v in vals)

    en_mags = extract_token_magnitudes("Revenue reached twenty-three million dollars and two hundred fifty thousand users.")
    vals = [v for vs in en_mags.values() for v in vs]
    assert any(abs(v - 23_000_000.0) < 1.0 for v in vals)
    assert any(abs(v - 250_000.0) < 1.0 for v in vals)


def test_pass4_synthesizes_midpoint_from_quote_range():
    from veraxi_ymmp.editorial.claim_reconcile import _synthesize_derived_claim_from_pool
    from veraxi_ymmp.epistemic.facts import Claim, ClaimKind, ClaimWeight, Evidence, Stance, check_claim_numbers

    quote = "It is currently estimated that the initial public offering price per share will be between $70.00 and $78.00."
    base_claim = Claim(
        id="c01",
        cut_index=12,
        text="仮条件は７０ドルから７８ドルよ。",
        kind=ClaimKind.NUMBER,
        weight=ClaimWeight.MINOR,
        evidence=[Evidence(url="https://www.sec.gov/Archives/edgar/1.htm", quote=quote, stance=Stance.CONFIRMS, tier=1, source_id="s1", sha256="a" * 64)],
    )
    derived = _synthesize_derived_claim_from_pool(
        14,
        "中央値の７４ドルでも超大型なのだ！",
        "c_edit_014",
        [base_claim],
    )
    assert derived is not None
    assert derived.derived is True
    assert "/ 2" in derived.derivation
    assert check_claim_numbers(derived, [quote]) == []
