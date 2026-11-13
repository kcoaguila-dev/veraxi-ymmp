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
