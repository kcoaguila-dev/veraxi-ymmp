"""Phase 2: ScriptProvider port + ManualHandoffProvider + CLI --provider flag."""

import json
from pathlib import Path

import pytest

import veraxi_ymmp.app.script_provider as sp
from veraxi_ymmp.app.cli import _cmd_ingest_script
from veraxi_ymmp.app.cli_ideate import cmd_ideate
from veraxi_ymmp.core.ports import ScriptProvider

GOOD_ENTRIES = [
    {
        "character": "zundamon",
        "text": "障害の原因が判明したのだ",
        "emotion": "happy",
        "motion": "none",
        "bgm": None,
        "sfx": None,
        "image": None,
    },
    {
        "character": "metan",
        "text": "根本原因は検証不足です",
        "emotion": "normal",
        "motion": "none",
        "bgm": None,
        "sfx": None,
        "image": None,
    },
]
GOOD_JSON = json.dumps(GOOD_ENTRIES, ensure_ascii=False)

BAD_EMOTION_JSON = json.dumps(
    [dict(GOOD_ENTRIES[0], emotion="super_happy"), GOOD_ENTRIES[1]],
    ensure_ascii=False,
)


def _paste_queue(*replies: str):
    queue = list(replies)
    return lambda: queue.pop(0)


def test_manual_provider_converges_after_bad_json():
    outputs: list = []
    provider = sp.ManualHandoffProvider(
        paste_fn=_paste_queue("this is not json", BAD_EMOTION_JSON, GOOD_JSON),
        output_fn=outputs.append,
    )
    entries = provider.generate_script("Test Topic", "dossier body")
    assert entries == sp.validate_pasted_script(GOOD_JSON)
    joined = "\n".join(outputs)
    assert joined.count("LLM RE-PROMPT BLOCK") == 2
    assert "Test Topic" in joined  # the prompt itself was printed


def test_manual_provider_accepts_fenced_json():
    provider = sp.ManualHandoffProvider(
        paste_fn=_paste_queue(f"Sure! Here you go:\n```json\n{GOOD_JSON}\n```"),
        output_fn=lambda _msg: None,
    )
    assert provider.generate_script("T", "D") == sp.validate_pasted_script(GOOD_JSON)


def test_manual_provider_is_idempotent_for_same_json():
    provider = sp.ManualHandoffProvider(
        paste_fn=lambda: GOOD_JSON, output_fn=lambda _msg: None
    )
    first = provider.generate_script("T", "D")
    second = provider.generate_script("T", "D")
    assert first == second
    assert json.dumps(first, ensure_ascii=False) == json.dumps(second, ensure_ascii=False)


def test_manual_provider_aborts_on_eof_and_empty():
    def eof():
        raise EOFError

    with pytest.raises(ValueError, match="aborted"):
        sp.ManualHandoffProvider(paste_fn=eof, output_fn=lambda _m: None).generate_script(
            "T", "D"
        )
    with pytest.raises(ValueError, match="empty"):
        sp.ManualHandoffProvider(
            paste_fn=lambda: "   ", output_fn=lambda _m: None
        ).generate_script("T", "D")


def test_manual_provider_max_attempts():
    provider = sp.ManualHandoffProvider(
        paste_fn=lambda: BAD_EMOTION_JSON,
        output_fn=lambda _m: None,
        max_attempts=2,
    )
    with pytest.raises(ValueError, match="did not converge after 2"):
        provider.generate_script("T", "D")


def test_manual_provider_satisfies_script_provider_protocol():
    provider = sp.ManualHandoffProvider(paste_fn=lambda: GOOD_JSON)
    assert isinstance(provider, ScriptProvider)


def test_generate_with_provider_dispatch():
    entries = sp.generate_with_provider(
        None, "T", "D", paste_fn=lambda: GOOD_JSON, output_fn=lambda _m: None
    )
    assert entries == sp.validate_pasted_script(GOOD_JSON)
    with pytest.raises(RuntimeError, match="no LLM API key"):
        sp.generate_with_provider("api", "T", "D")
    with pytest.raises(ValueError, match="Unknown script provider"):
        sp.generate_with_provider("bogus", "T", "D")


def test_build_script_prompt_reuses_export_spec_and_embeds_inputs():
    prompt = sp.build_script_prompt("My Topic", "DOSSIER-BODY")
    assert "Available Characters" in prompt
    assert "My Topic" in prompt
    assert "DOSSIER-BODY" in prompt
    assert "Output Contract" in prompt
    assert '"character"' in prompt  # JSON schema is embedded


def test_ideate_provider_manual_writes_validated_script(tmp_path, monkeypatch):
    captured = {}

    def fake_generate(name, topic, dossier, prompt_path=None):
        captured["name"] = name
        captured["prompt_path"] = prompt_path
        return sp.validate_pasted_script(GOOD_JSON)

    monkeypatch.setattr(sp, "generate_with_provider", fake_generate)
    target = tmp_path / "proj"
    cmd_ideate(["Some Topic", "--output", str(target), "--provider", "manual"])
    assert captured["name"] == "manual"
    script = json.loads((target / "script.json").read_text(encoding="utf-8"))
    assert script == sp.validate_pasted_script(GOOD_JSON)


def test_ideate_provider_flag_alone_defaults_to_manual(tmp_path, monkeypatch):
    seen = {}

    def fake_generate(name, topic, dossier, prompt_path=None):
        seen["name"] = name
        return sp.validate_pasted_script(GOOD_JSON)

    monkeypatch.setattr(sp, "generate_with_provider", fake_generate)
    cmd_ideate(["Topic", "--output", str(tmp_path / "p"), "--provider"])
    assert seen["name"] == "manual"


def test_ideate_provider_api_exits_with_clear_error(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        cmd_ideate(["Topic", "--output", str(tmp_path / "p"), "--provider", "api"])
    assert excinfo.value.code == 2
    assert not (tmp_path / "p" / "script.json").exists()


def test_ingest_script_provider_manual(tmp_path, monkeypatch):
    md = tmp_path / "dialogue_raw.md"
    md.write_text("ずんだもん: こんにちは\n四国めたん: 始めましょう\n", encoding="utf-8")

    def fake_generate(name, topic, dossier, prompt_path=None):
        assert "こんにちは" in dossier
        return sp.validate_pasted_script(GOOD_JSON)

    monkeypatch.setattr(sp, "generate_with_provider", fake_generate)
    _cmd_ingest_script([str(md), "--provider", "manual"])
    script = json.loads((tmp_path / "script.json").read_text(encoding="utf-8"))
    assert script == sp.validate_pasted_script(GOOD_JSON)


# --- WP5: single object contract + lenient ingest ---------------------------

BROLL_CANONICAL = [
    {
        "type": "vs",
        "filename": "broll/slide_01.png",
        "title": "世間の誤解 vs 技術の実態",
        "hero_title": "表面的な楽観 vs 物理的な制約",
        "left_box": ["一般的なイメージ", "設定変更だけで完全回避", "amber"],
        "right_box": ["一次資料の現実", "メモリ境界破壊により遠隔掌握", "rose"],
        "bottom_text": "根本的なプロセス再起動のみが有効打",
        "theme_color": "blue",
    }
]

# The same slide in the legacy appended-entry shape.
BROLL_LEGACY_ENTRY = {
    "type": "broll_manifest",
    "slide_type": "vs",
    "filename": "broll/slide_01.png",
    "title": "世間の誤解 vs 技術の実態",
    "hero_title": "表面的な楽観 vs 物理的な制約",
    "left_box": ["一般的なイメージ", "設定変更だけで完全回避", "amber"],
    "right_box": ["一次資料の現実", "メモリ境界破壊により遠隔掌握", "rose"],
    "bottom_text": "根本的なプロセス再起動のみが有効打",
    "theme_color": "blue",
}

SHAPE_OBJECT = json.dumps(
    {"script": GOOD_ENTRIES, "broll_manifest": BROLL_CANONICAL},
    ensure_ascii=False,
)
SHAPE_ARRAY_EMBEDDED = json.dumps(
    GOOD_ENTRIES + [BROLL_LEGACY_ENTRY], ensure_ascii=False
)
SHAPE_BARE_ARRAY = GOOD_JSON


def test_wp5_three_shapes_normalize_identically():
    payload_object = sp.validate_pasted_payload(SHAPE_OBJECT)
    payload_embedded = sp.validate_pasted_payload(SHAPE_ARRAY_EMBEDDED)
    assert payload_object == payload_embedded
    assert payload_object["broll_manifest"] == BROLL_CANONICAL
    assert payload_object["script"] == sp.validate_pasted_script(GOOD_JSON)

    payload_bare = sp.validate_pasted_payload(SHAPE_BARE_ARRAY)
    assert payload_bare["script"] == payload_object["script"]
    assert payload_bare["broll_manifest"] == []


def test_wp5_fenced_and_prose_wrapped_object_keep_broll():
    fenced = f"Here is the script:\n```json\n{SHAPE_OBJECT}\n```"
    assert sp.validate_pasted_payload(fenced) == sp.validate_pasted_payload(
        SHAPE_OBJECT
    )
    prose = f"Sure, here you go: {SHAPE_OBJECT} — hope that helps!"
    assert sp.validate_pasted_payload(prose) == sp.validate_pasted_payload(
        SHAPE_OBJECT
    )


def test_wp5_normalize_rejects_bad_shapes():
    with pytest.raises(ValueError, match="must contain a \"script\" array"):
        sp.normalize_script_payload({"broll_manifest": []})
    with pytest.raises(ValueError, match="must be an array"):
        sp.normalize_script_payload(
            {"script": [], "broll_manifest": {"type": "vs"}}
        )
    with pytest.raises(ValueError, match="must be a JSON object or array"):
        sp.normalize_script_payload("just a string")


def test_wp5_provider_surfaces_broll_manifest():
    provider = sp.ManualHandoffProvider(
        paste_fn=lambda: SHAPE_ARRAY_EMBEDDED, output_fn=lambda _m: None
    )
    entries = provider.generate_script("T", "D")
    assert entries == sp.validate_pasted_script(GOOD_JSON)
    assert provider.last_broll_manifest == BROLL_CANONICAL


def test_wp5_extract_prose_wrapped_single_entry_array():
    # Regression (PR #20 review): the object span used to win over the
    # enclosing array, returning the single entry instead of the list.
    entry = GOOD_ENTRIES[0]
    reply = "Here is the script: " + json.dumps([entry], ensure_ascii=False)
    data = sp.extract_script_json(reply)
    assert isinstance(data, list) and len(data) == 1
    assert sp.normalize_script_payload(data) == {
        "script": [entry], "broll_manifest": [],
    }


@pytest.mark.parametrize("bad", [{}, "", False, 0, "x", 5])
def test_wp5_normalize_rejects_non_list_broll_manifest(bad):
    with pytest.raises(ValueError, match="broll_manifest"):
        sp.normalize_script_payload(
            {"script": [], "broll_manifest": bad}
        )


def test_wp5_normalize_broll_omitted_and_null_default_empty():
    assert sp.normalize_script_payload({"script": []}) == {
        "script": [], "broll_manifest": [],
    }
    assert sp.normalize_script_payload(
        {"script": [], "broll_manifest": None}
    ) == {"script": [], "broll_manifest": []}


def test_wp5_low_tier_example_is_valid_director_input():
    # The few-shot example must itself pass the pipeline's validation,
    # or a model that follows it produces a rejected reply.
    templates = Path(sp.__file__).resolve().parent.parent / "templates"
    low_tier = (templates / "LOW_TIER_SYSTEM_PROMPT.md").read_text(
        encoding="utf-8"
    )
    section7 = low_tier.split("## 7.", 1)[1]
    fence = section7.split("```json", 1)[1].split("```", 1)[0]
    payload = sp.normalize_script_payload(json.loads(fence))
    entries = sp.validate_director_script(payload["script"])
    assert len(entries) == len(payload["script"]) == 4
    assert payload["script"][0]["bgm"] == "assets/bgm/2_23_AM.mp3"
    assert all(
        e["bgm"] is None for e in payload["script"][1:]
    )
    assert len(payload["broll_manifest"]) == 1


def test_wp5_prompt_sources_agree_on_object_contract():
    templates = Path(sp.__file__).resolve().parent.parent / "templates"
    universal = (templates / "UNIVERSAL_AI_PROMPT.md").read_text(
        encoding="utf-8"
    )
    low_tier = (templates / "LOW_TIER_SYSTEM_PROMPT.md").read_text(
        encoding="utf-8"
    )
    built = sp.build_script_prompt("T", "D")
    for source in (universal, low_tier, built):
        assert '"broll_manifest"' in source
        assert "JSON array" not in source
    assert "single JSON object" in universal
    assert "single JSON object" in low_tier
    assert '"type": "broll_manifest"' not in low_tier
    assert "slide_type" not in low_tier
    assert "Return ONLY a JSON object" in built


def test_generate_script_file_writes_broll_and_thumbnail_config(tmp_path, monkeypatch):
    thumb_cfg = {
        "badge": "一次資料検証",
        "title_line1": "巨額投資の真実",
        "title_line2": "決算書が暴く現実",
        "sub_hook": "見落とされた数値",
    }
    full_reply = json.dumps(
        {
            "script": GOOD_ENTRIES,
            "broll_manifest": BROLL_CANONICAL,
            "thumbnail_config": thumb_cfg,
        },
        ensure_ascii=False,
    )
    monkeypatch.setattr(sp, "_read_paste_from_stdin", lambda: full_reply)
    script_out = tmp_path / "script.json"
    entries = sp.generate_script_file(
        "manual", "Test Topic", "Dossier", script_out, tmp_path / "script_prompt.md"
    )
    assert entries == sp.validate_pasted_script(GOOD_JSON)
    assert json.loads(script_out.read_text(encoding="utf-8")) == entries
    assert json.loads((tmp_path / "broll_manifest.json").read_text(encoding="utf-8")) == BROLL_CANONICAL
    assert json.loads((tmp_path / "thumbnail_config.json").read_text(encoding="utf-8")) == thumb_cfg


def test_manual_provider_extra_validator_reprompts():
    outputs: list = []
    calls = {"n": 0}

    def custom_gate(_payload):
        calls["n"] += 1
        return ["[PACING] Retention score too low"] if calls["n"] == 1 else []

    provider = sp.ManualHandoffProvider(
        paste_fn=_paste_queue(GOOD_JSON, GOOD_JSON),
        output_fn=outputs.append,
        extra_validator=custom_gate,
    )
    entries = provider.generate_script("T", "D")
    assert entries == sp.validate_pasted_script(GOOD_JSON)
    joined = "\n".join(outputs)
    assert "LLM RE-PROMPT BLOCK" in joined
    assert "[PACING] Retention score too low" in joined


def test_ingest_script_pure_notebooklm_table_with_provider(tmp_path, monkeypatch):
    md = tmp_path / "evidence.md"
    md.write_text(
        "| # | Claim | Verbatim Quote | Source & Page | Hard Metric |\n"
        "|---|---|---|---|---|\n"
        "| 1 | 認証不要のリモート実行欠陥 | 認証不要でサーバーを掌握可能 | CVE-2024-XXXX p.2 | CVSS 9.8 |\n",
        encoding="utf-8",
    )
    reply_obj = json.dumps(
        {"script": GOOD_ENTRIES, "broll_manifest": BROLL_CANONICAL},
        ensure_ascii=False,
    )
    monkeypatch.setattr(sp, "_read_paste_from_stdin", lambda: reply_obj)
    monkeypatch.setattr(sp, "build_project_gate_validator", lambda *_a, **_k: (lambda _p: []))
    _cmd_ingest_script([str(md), "--provider", "manual"])
    assert (tmp_path / "script.json").is_file()
    assert (tmp_path / "broll_manifest.json").is_file()
    claims = json.loads((tmp_path / "claims.json").read_text(encoding="utf-8"))
    assert isinstance(claims, list)


def test_handoff_validator_rejects_hallucinated_number_not_in_evidence(tmp_path):
    md = tmp_path / "evidence.md"
    md.write_text(
        "| # | Point of Contention / Claim | Canonical Period / Scope | "
        "Verbatim Quote Refuting or Explaining | Source Doc & Exact Section/Page | "
        "Root Cause / Hard Metric |\n"
        "|---|---|---|---|---|---|\n"
        "| 1 | 設備投資が850億ドルに達した | 2026-Q3 | "
        "Amazon capex reached $85 billion in FY2026. | primary_anchor_doc p.12 | "
        "$85B (850億ドル) |\n",
        encoding="utf-8",
    )
    validator = sp.build_project_gate_validator(tmp_path, audit_pacing=False, audit_facts=True)

    bad_script = [
        {"character": "ずんだもん", "text": "投資額は9999億ドルに達したのだ", "emotion": "surprised", "motion": "none", "image": None},
    ]
    bad_errors = validator({"script": bad_script, "broll_manifest": []})
    assert any(err.startswith("[FACTS]") for err in bad_errors)

    good_script = [
        {"character": "四国めたん", "text": "投資額は850億ドルに達したのですわ", "emotion": "normal", "motion": "none", "image": None},
    ]
    good_errors = validator({"script": good_script, "broll_manifest": []})
    assert good_errors == []


def test_e2e_notebooklm_webchat_to_fact_audit_and_broll(tmp_path, monkeypatch):
    from veraxi_ymmp.epistemic.fact_audit import audit_project_facts
    from veraxi_ymmp.graphics.broll import render_from_manifest

    proj = tmp_path / "capex_reality"
    cmd_ideate(["AI Capex Reality", "--archetype", "post_mortem", "--output", str(proj)])

    md = proj / "evidence.md"
    md.write_text(
        "| # | Point of Contention / Claim | Canonical Period / Scope | "
        "Verbatim Quote Refuting or Explaining | Source Doc & Exact Section/Page | "
        "Root Cause / Hard Metric |\n"
        "|---|---|---|---|---|---|\n"
        "| 1 | 設備投資が850億ドルに達した | 2026-Q3 | "
        "Amazon capex reached $85 billion in FY2026. | primary_anchor_doc p.12 | "
        "$85B (850億ドル) |\n"
        "| 2 | 深刻度は9.8の重大欠陥 | 2026 | "
        "Critical score 9.8 remote failure risk. | counter_analysis p.2 | "
        "Score 9.8 |\n",
        encoding="utf-8",
    )

    def _c(char, text, emo="normal", img=None):
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

    e2e_script = [
        _c("ずんだもん", "巨額投資があれば必ず儲かるのだ！", "excited", None),
        _c("四国めたん", "甘い幻想ですわ。設備投資は850億ドルですわ。", "smug", None),
        _c("ずんだもん", "えっ！？", "surprised", None),
        _c("四国めたん", "この巨額出費が利益を圧迫する現実ですわ。", "normal", "broll/slide_01.png"),
        _c("ずんだもん", "850億ドルって一体どれほどの負担なのだ？", "confused", "broll/slide_01.png"),
        _c("四国めたん", "償却費が雪だるま式に膨らみ続けますわ。", "normal", "broll/slide_01.png"),
        _c("春日部つむぎ", "現場のインフラでも危険度9.8の障害が出たっす！", "angry", None),
        _c("ずんだもん", "マジで！？", "surprised", None),
        _c("四国めたん", "しかも境界設計の欠陥まで放置されていましたわ。", "angry", "broll/slide_02.png"),
        _c("春日部つむぎ", "運用コストが現場を直撃してるっすよ。", "sad", "broll/slide_02.png"),
        _c("四国めたん", "投資を急ぐあまり検証が追いつきませんの。", "normal", "broll/slide_02.png"),
        _c("ずんだもん", "技術も予算も限界スレスレだったのだ…", "sad", None),
        _c("四国めたん", "一次資料を直視しない企業から脱落しますわ。", "smug", None),
        _c("春日部つむぎ", "現場の負荷を見落とすと取り返しがつかないっす。", "normal", None),
        _c("四国めたん", "結局は資金規律を保てるかどうかの勝負ですわ。", "normal", None),
        _c("ずんだもん", "財務の現実から目を背けちゃダメなのだ。", "normal", None),
    ]
    broll_specs = [
        {
            "type": "vs",
            "filename": "broll/slide_01.png",
            "title": "投資規模の比較",
            "hero_title": "楽観予測 vs 実測数値",
            "left_box": ["市場の期待", "コストは即回収可能", "amber"],
            "right_box": ["一次資料の現実", "年間投資850億ドル", "rose"],
            "bottom_text": "償却負担が利益を直撃",
            "theme_color": "blue",
        },
        {
            "type": "metric",
            "filename": "slide_02.png",
            "title": "公式評価指標",
            "hero_metric": "Score 9.8",
            "status_pill": "公式報告書",
            "impact_tag": "重大",
            "impact_text": "境界設計の欠陥が直撃する",
            "theme_color": "rose",
        },
    ]
    thumb_cfg = {
        "badge": "一次資料検証",
        "title_line1": "850億ドルの重圧",
        "title_line2": "決算書が暴く現実",
        "sub_hook": "投資回収の壁",
    }
    reply_obj = json.dumps(
        {"script": e2e_script, "broll_manifest": broll_specs, "thumbnail_config": thumb_cfg},
        ensure_ascii=False,
    )
    monkeypatch.setattr(sp, "_read_paste_from_stdin", lambda: reply_obj)

    _cmd_ingest_script([str(md), "--provider", "manual"])

    assert (proj / "script.json").is_file()
    assert (proj / "claims.json").is_file()
    assert (proj / "broll_manifest.json").is_file()
    assert (proj / "thumbnail_config.json").is_file()

    outcome = audit_project_facts(proj / "script.json")
    assert not outcome.blocked, f"Unexpected fact blockers: {outcome.blockers}"

    rendered = render_from_manifest(proj / "broll_manifest.json", proj / "broll")
    assert len(rendered) == 2
    assert (proj / "broll" / "slide_01.png").is_file()
    assert (proj / "broll" / "slide_02.png").is_file()
    assert not (proj / "broll" / "broll").exists()


def test_manual_provider_rollback_on_rejected_paste_and_eof(tmp_path: Path) -> None:
    """Rejected candidate pastes must not leave stale claims.json, sources/, or manifests behind on EOF."""
    (tmp_path / "evidence.md").write_text(
        "| # | Point of Contention / Claim | Canonical Period / Scope | "
        "Verbatim Quote Refuting or Explaining | Source Doc & Exact Section/Page | "
        "Root Cause / Hard Metric |\n"
        "|---|---|---|---|---|---|\n"
        "| 1 | 設備投資が850億ドルに達した | 2026-Q3 | "
        "Amazon capex reached $85 billion in FY2026. | primary_anchor_doc p.12 | "
        "$85B (850億ドル) |\n",
        encoding="utf-8",
    )
    bad_payload = json.dumps(
        {
            "script": [
                {
                    "character": "ずんだもん",
                    "character_position": "right",
                    "text": "投資額は9999億ドルに達したのだ",
                    "emotion": "surprised",
                    "motion": "none",
                    "bgm": None,
                    "sfx": None,
                    "image": None,
                },
                {
                    "character": "四国めたん",
                    "character_position": "left",
                    "text": "本当ですか？",
                    "emotion": "normal",
                    "motion": "none",
                    "bgm": None,
                    "sfx": None,
                    "image": None,
                },
            ],
            "broll_manifest": [
                {
                    "type": "metric",
                    "filename": "slide_01.png",
                    "title": "テスト",
                    "hero_metric": "9999億ドル",
                    "status_pill": "公式",
                    "impact_tag": "重大",
                    "impact_text": "確認が必要",
                    "theme_color": "rose",
                }
            ],
            "thumbnail_config": {
                "badge": "検証",
                "title_line1": "9999億ドル",
                "title_line2": "巨額投資",
                "sub_hook": "真実",
            },
        },
        ensure_ascii=False,
    )
    outputs: list = []
    validator = sp.build_project_gate_validator(tmp_path, audit_pacing=True, audit_facts=True)
    provider = sp.ManualHandoffProvider(
        paste_fn=_paste_queue(bad_payload, ""),
        output_fn=outputs.append,
        extra_validator=validator,
    )
    with pytest.raises(ValueError):
        provider.generate_script("Test Topic", "dossier")

    assert "[FACTS]" in "\n".join(outputs)
    assert not (tmp_path / "claims.json").exists()
    assert not (tmp_path / "broll_manifest.json").exists()
    assert not (tmp_path / "thumbnail_config.json").exists()
    assert not (tmp_path / "sources").exists()
    assert not (tmp_path / ".candidate_script.tmp.json").exists()


def test_handoff_validator_scale_and_cross_file_parity_without_strict_facts(tmp_path: Path) -> None:
    evidence_md = (
        "| # | Point of Contention / Claim | Canonical Period / Scope | "
        "Verbatim Quote Refuting or Explaining | Source Doc & Exact Section/Page | "
        "Root Cause / Hard Metric |\n"
        "|---|---|---|---|---|---|\n"
        "| 1 | 設備投資が850億ドルに達した | 2026-Q3 | "
        "Amazon capex reached $85 billion in FY2026. | "
        "https://www.sec.gov/Archives/edgar/data/0001018724/amzn-20260930.htm p.12 | "
        "$85B (850億ドル) |\n"
    )
    validator = sp.build_project_gate_validator(
        tmp_path, audit_pacing=False, audit_facts=False, evidence_markdown=evidence_md
    )

    # 1. Thumbnail & B-roll macro figure mismatch (950億ドル vs 850億ドル)
    mismatch_payload = {
        "script": [
            {"character": "四国めたん", "text": "設備投資は850億ドルに達したのですわ", "emotion": "normal", "motion": "none", "image": None},
        ],
        "broll_manifest": [
            {
                "type": "metric",
                "filename": "slide_01.png",
                "title": "設備投資規模",
                "hero_metric": "950億ドル",
                "status_pill": "決算報告",
                "impact_tag": "投資",
                "impact_text": "投資負担が拡大",
                "theme_color": "rose",
            }
        ],
        "thumbnail_config": {
            "badge": "決算検証",
            "title_line1": "950億ドルの衝撃",
            "title_line2": "投資の真実",
            "sub_hook": "注目",
        },
    }
    mismatch_errs = validator(mismatch_payload)
    assert any("[SCALE]" in e and "broll_manifest[0]" in e for e in mismatch_errs)
    assert any("[SCALE]" in e and "thumbnail_config" in e for e in mismatch_errs)

    # 2. 10x billion-to-億 conversion mistake ($85 billion -> 85億ドル)
    ten_x_payload = {
        "script": [
            {"character": "四国めたん", "text": "設備投資は85億ドルに達したのですわ", "emotion": "normal", "motion": "none", "image": None},
        ],
        "broll_manifest": [],
    }
    ten_x_errs = validator(ten_x_payload)
    assert any("[SCALE]" in e and "10x off" in e for e in ten_x_errs)

    # 3. Clean match passes without errors
    clean_payload = {
        "script": [
            {"character": "四国めたん", "text": "設備投資は850億ドルに達したのですわ", "emotion": "normal", "motion": "none", "image": None},
        ],
        "broll_manifest": [
            {
                "type": "metric",
                "filename": "slide_01.png",
                "title": "設備投資規模",
                "hero_metric": "850億ドル",
                "status_pill": "決算報告",
                "impact_tag": "投資",
                "impact_text": "投資負担が拡大",
                "theme_color": "rose",
            }
        ],
        "thumbnail_config": {
            "badge": "決算検証",
            "title_line1": "850億ドルの衝撃",
            "title_line2": "投資の真実",
            "sub_hook": "注目",
        },
    }
    assert validator(clean_payload) == []


def test_ingest_script_manual_defers_strict_facts_and_prints_next_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sec_url = "https://www.sec.gov/Archives/edgar/data/0001018724/amzn-20260930.htm"
    md = tmp_path / "evidence.md"
    md.write_text(
        "| # | Point of Contention / Claim | Canonical Period / Scope | "
        "Verbatim Quote Refuting or Explaining | Source Doc & Exact Section/Page | "
        "Root Cause / Hard Metric |\n"
        "|---|---|---|---|---|---|\n"
        "| 1 | 設備投資が850億ドルに達した | 2026-Q3 | "
        f"Amazon capex reached $85 billion in FY2026. | {sec_url} p.12 | "
        "$85B (850億ドル) |\n",
        encoding="utf-8",
    )

    def _c(char, text, emo="normal", img=None):
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

    script_with_secondary_pct = [
        _c("ずんだもん", "巨額投資があれば必ず儲かるのだ！", "excited", None),
        _c("四国めたん", "甘い幻想ですわ。設備投資は850億ドルですわ。", "smug", None),
        _c("ずんだもん", "えっ！？", "surprised", None),
        _c("四国めたん", "この巨額出費が利益を圧迫する現実ですわ。", "normal", "broll/slide_01.png"),
        _c("ずんだもん", "850億ドルって一体どれほどの負担なのだ？", "confused", "broll/slide_01.png"),
        _c("四国めたん", "償却費が雪だるま式に膨らみ続けますわ。", "normal", "broll/slide_01.png"),
        _c("春日部つむぎ", "現場のインフラでも負担が増えてるっす！", "angry", None),
        _c("ずんだもん", "マジで！？", "surprised", None),
        _c("四国めたん", "しかも境界設計の課題まで残っていましたわ。", "angry", "broll/slide_01.png"),
        _c("春日部つむぎ", "運用コストが現場を直撃してるっすよ。", "sad", "broll/slide_01.png"),
        _c("四国めたん", "投資を急ぐあまり検証が追いつきませんの。", "normal", "broll/slide_01.png"),
        _c("ずんだもん", "技術も予算も限界スレスレだったのだ…", "sad", None),
        _c("四国めたん", "一次資料を直視しない企業から脱落しますわ。", "smug", None),
        _c("春日部つむぎ", "現場の負荷を見落とすと取り返しがつかないっす。", "normal", None),
        _c("四国めたん", "ちなみに営業利益率は12%の推移ですわ。", "normal", None),
        _c("ずんだもん", "財務の現実から目を背けちゃダメなのだ。", "normal", None),
    ]
    broll_specs = [
        {
            "type": "metric",
            "filename": "slide_01.png",
            "title": "設備投資規模",
            "hero_metric": "850億ドル",
            "status_pill": "公式報告書",
            "impact_tag": "投資",
            "impact_text": "年間投資の現実",
            "theme_color": "rose",
        }
    ]
    reply_obj = json.dumps(
        {"script": script_with_secondary_pct, "broll_manifest": broll_specs},
        ensure_ascii=False,
    )

    monkeypatch.setattr(sp, "_read_paste_from_stdin", lambda: reply_obj)
    _cmd_ingest_script([str(md), "--provider", "manual"])
    out = capsys.readouterr().out
    assert "verify-notebooklm" in out
    assert (tmp_path / "script.json").is_file()
    assert (tmp_path / "claims.json").is_file()

    # With --strict-facts, the ungrounded secondary 12% figure triggers [FACTS] rejection
    strict_dir = tmp_path / "strict_case"
    strict_dir.mkdir()
    strict_md = strict_dir / "evidence.md"
    strict_md.write_text(md.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(sp, "_read_paste_from_stdin", _paste_queue(reply_obj, ""))
    with pytest.raises(ValueError):
        _cmd_ingest_script([str(strict_md), "--provider", "manual", "--strict-facts"])
    strict_out = capsys.readouterr().out
    assert "[FACTS]" in strict_out
